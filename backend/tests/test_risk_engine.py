import time
import pytest
from app.risk.engine import RiskEngine, TradeProposal
from app.brokers.base import Quote
from app.core.config import Settings


def make_quote(bid=9.98, ask=10.02, last=10.0, age=1.0):
    return Quote(provider="test", symbol="TST", timestamp=time.time(), age_seconds=age,
                 bid=bid, ask=ask, last=last, market_status="open")


def make_proposal(**overrides):
    base = dict(
        symbol="TST", direction="long", entry_price=10.0, stop_price=9.5,
        account_equity=1000.0, strategy="momentum", quote=make_quote(),
        avg_dollar_volume=5_000_000.0, sector="tech", sector_exposure_pct=0.0,
        open_position_count=0, daily_pnl_pct=0.0, weekly_drawdown_pct=0.0,
        total_drawdown_pct=0.0, strategy_enabled=True,
    )
    base.update(overrides)
    return TradeProposal(**base)


@pytest.fixture
def engine():
    return RiskEngine(cfg=Settings())


def test_approves_valid_trade(engine):
    d = engine.evaluate(make_proposal())
    assert d.approved
    assert d.position_size > 0
    assert d.risk_dollars == pytest.approx(1000.0 * 0.01)


def test_rejects_missing_stop(engine):
    d = engine.evaluate(make_proposal(stop_price=10.0))
    assert not d.approved
    assert "missing_or_invalid_stop" in d.reasons


def test_rejects_stale_market_data(engine):
    d = engine.evaluate(make_proposal(quote=make_quote(age=999)))
    assert not d.approved
    assert "stale_market_data" in d.reasons


def test_rejects_excessive_spread(engine):
    d = engine.evaluate(make_proposal(quote=make_quote(bid=8.0, ask=12.0)))
    assert not d.approved
    assert "excessive_spread" in d.reasons


def test_rejects_insufficient_liquidity(engine):
    d = engine.evaluate(make_proposal(avg_dollar_volume=100.0))
    assert not d.approved
    assert "insufficient_liquidity" in d.reasons


def test_rejects_after_daily_loss_limit(engine):
    d = engine.evaluate(make_proposal(daily_pnl_pct=-0.05))
    assert not d.approved
    assert "daily_loss_limit_reached" in d.reasons


def test_rejects_weekly_drawdown_breach(engine):
    d = engine.evaluate(make_proposal(weekly_drawdown_pct=0.07))
    assert not d.approved
    assert "weekly_drawdown_limit_reached" in d.reasons


def test_rejects_total_drawdown_breach(engine):
    d = engine.evaluate(make_proposal(total_drawdown_pct=0.15))
    assert not d.approved
    assert "total_drawdown_limit_reached" in d.reasons


def test_rejects_max_positions(engine):
    d = engine.evaluate(make_proposal(open_position_count=5))
    assert not d.approved
    assert "max_positions_reached" in d.reasons


def test_rejects_disabled_strategy(engine):
    d = engine.evaluate(make_proposal(strategy_enabled=False))
    assert not d.approved
    assert "strategy_disabled" in d.reasons


def test_rejects_margin_when_disabled(engine):
    d = engine.evaluate(make_proposal(uses_margin=True))
    assert not d.approved
    assert "margin_disabled" in d.reasons


def test_rejects_shorts_when_disabled(engine):
    d = engine.evaluate(make_proposal(is_short=True))
    assert not d.approved
    assert "shorts_disabled" in d.reasons


def test_rejects_options_when_disabled(engine):
    d = engine.evaluate(make_proposal(is_option=True))
    assert not d.approved
    assert "options_disabled" in d.reasons


def test_rejects_martingale(engine):
    d = engine.evaluate(make_proposal(is_martingale_after_loss=True))
    assert not d.approved
    assert "martingale_forbidden" in d.reasons


def test_position_size_capped_by_max_position_pct(engine):
    # very tight stop -> raw risk-based size would be huge notional; must be capped
    d = engine.evaluate(make_proposal(entry_price=10.0, stop_price=9.99, account_equity=1000.0))
    assert d.approved
    notional = d.position_size * 10.0
    assert notional <= 1000.0 * Settings().MAX_POSITION_PCT + 1e-6
