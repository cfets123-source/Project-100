"""Stage Runner v1: signal rule, whole-share sizing, GTC brackets, owner-experiment gate."""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.session import Base
from app.models import models  # noqa: F401 register tables
from app.risk.engine import RiskEngine, TradeProposal
from app.runtime import stage_runner_worker as worker
from app.runtime.alpaca_live_execution import require_execution_validation
from app.services import owner_experiment as oe
from app.strategies.stage_runner import STAGE_RUNNER_VERSION, StageRunner, trend_is_up


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _adapter(closes, *, equity=100.0, bid=77.40, ask=77.45, age=1.0):
    a = MagicMock()
    a.get_balances.return_value = {"equity": equity}
    a.get_daily_bars.return_value = [{"close": c} for c in closes]
    a.get_quotes.return_value = [SimpleNamespace(symbol="TQQQ", bid=bid, ask=ask, last=ask,
                                                 age_seconds=age, timestamp=time.time() - age)]
    return a


RISING = [100 + i * 0.1 for i in range(260)]
FALLING = [200 - i * 0.1 for i in range(260)]


def test_trend_filter():
    assert trend_is_up(RISING)[0] is True
    assert trend_is_up(FALLING)[0] is False
    assert trend_is_up(RISING[:150]) == (False, None)


def test_signal_brackets_plus50_minus25_in_uptrend():
    s = StageRunner(max_equity=250, floor_equity=50).portfolio_signal(_adapter(RISING))
    assert s["symbol"] == "TQQQ" and s["strategy"] == STAGE_RUNNER_VERSION
    assert s["stop_price"] == round(77.45 * 0.75, 2) and s["target_price"] == round(77.45 * 1.5, 2)


@pytest.mark.parametrize("kwargs,reason", [
    ({"closes": FALLING}, "trend_filter_off"),
    ({"closes": RISING, "equity": 40}, "below_floor_equity"),
    ({"closes": RISING, "equity": 300}, "above_experiment_cap"),
    ({"closes": RISING, "age": 60}, "quote_stale"),
    ({"closes": RISING, "bid": 76.0}, "spread_too_wide"),
    ({"closes": RISING, "equity": 60, "bid": 79.9, "ask": 80.0}, "one_share_exceeds_equity"),
])
def test_no_signal_cases(kwargs, reason):
    closes = kwargs.pop("closes")
    runner = StageRunner(max_equity=250, floor_equity=50)
    assert runner.portfolio_signal(_adapter(closes, **kwargs)) is None
    assert runner.last_skip["reason"] == reason


def test_paper_override_ignores_broker_paper_equity():
    runner = StageRunner(max_equity=250, floor_equity=50, equity_override=100)
    assert runner.portfolio_signal(_adapter(RISING, equity=100_000)) is not None


def _proposal(equity, entry=77.45):
    from app.brokers.base import Quote
    q = Quote(provider="t", symbol="TQQQ", timestamp=time.time(), age_seconds=0.5,
              bid=entry - 0.02, ask=entry, last=entry, market_status="open")
    return TradeProposal(symbol="TQQQ", direction="long", entry_price=entry,
                         stop_price=round(entry * 0.75, 2), account_equity=equity,
                         strategy=STAGE_RUNNER_VERSION, quote=q, avg_dollar_volume=5e9)


STAGE_CFG = dict(MAX_RISK_PER_TRADE=0.25, MAX_POSITION_PCT=0.95, MAX_DAILY_LOSS=0.25,
                 MAX_WEEKLY_DRAWDOWN=0.5, MAX_TOTAL_DRAWDOWN=0.5, MAX_SECTOR_CONCENTRATION=0.95)


def test_whole_share_sizing_under_stage_settings():
    whole = RiskEngine(Settings(**STAGE_CFG, WHOLE_SHARES_ONLY=True))
    d = whole.evaluate(_proposal(100.0))
    assert d.approved and d.position_size == 1.0
    assert whole.evaluate(_proposal(180.0)).position_size == 2.0
    # $60 cannot fund one whole share: rejected rather than sized fractionally.
    assert not whole.evaluate(_proposal(60.0)).approved
    frac = RiskEngine(Settings(**STAGE_CFG)).evaluate(_proposal(100.0))
    assert not float(frac.position_size).is_integer()


def test_owner_experiment_gate(db):
    with pytest.raises(RuntimeError, match="owner_experiment_not_accepted"):
        require_execution_validation(db, STAGE_RUNNER_VERSION)
    with pytest.raises(ValueError):
        oe.accept(db, STAGE_RUNNER_VERSION, accepted_by="me", max_equity=250, floor_equity=50,
                  acknowledgement="ok")
    oe.accept(db, STAGE_RUNNER_VERSION, accepted_by="me", max_equity=250, floor_equity=50,
              acknowledgement=oe.ACKNOWLEDGEMENT)
    assert require_execution_validation(db, STAGE_RUNNER_VERSION).max_equity == 250
    # Acceptance never creates or satisfies a research validation record.
    assert db.get(models.StrategyValidationRecord, STAGE_RUNNER_VERSION) is None
    oe.revoke(db, STAGE_RUNNER_VERSION)
    with pytest.raises(RuntimeError):
        require_execution_validation(db, STAGE_RUNNER_VERSION)


def test_owner_experiment_rejects_other_strategies(db):
    with pytest.raises(ValueError):
        oe.accept(db, "daily-trend-pullback-v1", accepted_by="me", max_equity=250,
                  floor_equity=50, acknowledgement=oe.ACKNOWLEDGEMENT)


def test_worker_refuses_day_brackets_or_fractional(db):
    assert worker.run_once(db, Settings(), mode="live")["reason"] == "stage_runner_requires_gtc_brackets"
    cfg = Settings(ALPACA_BRACKET_TIME_IN_FORCE="gtc")
    assert worker.run_once(db, cfg, mode="live")["reason"] == "stage_runner_requires_whole_shares"
    cfg = Settings(ALPACA_BRACKET_TIME_IN_FORCE="gtc", WHOLE_SHARES_ONLY=True)
    assert worker.run_once(db, cfg, mode="live")["reason"].startswith("owner_experiment_not_accepted")


@pytest.mark.parametrize("tif", ["gtc", "day"])
def test_gateway_bracket_uses_configured_time_in_force(db, tif):
    from dataclasses import replace as dc_replace
    from app.brokers.alpaca_adapter import AlpacaBrokerAdapter
    from app.brokers.base import OrderResult, Quote
    from app.services.execution_gateway import ExecutionGateway
    from app.services.state_machine import PAPER, StateManager

    sent = []

    class FakeAlpaca(AlpacaBrokerAdapter):
        def place_order(self, order):
            sent.append(order)
            return OrderResult(order_id="o1", status="accepted", filled_qty=0.0)

        def __getattr__(self, name):  # any read the gateway performs
            return MagicMock(return_value=[])

    cfg = Settings(**STAGE_CFG, WHOLE_SHARES_ONLY=True, ALPACA_PAPER_EXECUTION_ENABLED=True,
                   ALPACA_BRACKET_TIME_IN_FORCE=tif)
    sm = StateManager(db, cfg)
    sm.transition(PAPER, "test")
    broker = FakeAlpaca("k", "s", paper=True, allow_order_submission=True)
    signal = StageRunner(max_equity=250, floor_equity=50).portfolio_signal(_adapter(RISING))
    quote = Quote(provider="t", symbol="TQQQ", timestamp=time.time(), age_seconds=0.5,
                  bid=77.43, ask=77.45, last=77.45, market_status="open")
    ctx = dict(avg_dollar_volume=5e9, sector="etf", sector_exposure_pct=0.0, open_position_count=0,
               daily_pnl_pct=0.0, weekly_drawdown_pct=0.0, total_drawdown_pct=0.0, strategy_enabled=True)
    result = ExecutionGateway(db, broker, RiskEngine(cfg), sm, "acct").submit(
        signal, "acct", quote, ctx, 100.0, 95.0)
    assert result.submitted, result.reason
    assert sent[0].order_class == "bracket" and sent[0].quantity == 1.0
    assert sent[0].time_in_force == tif
