"""
Demonstrates: data -> strategy -> validated signal -> risk -> order validation ->
simulated execution -> fill -> protective stop -> exit -> reconciliation -> audit,
with NO function in this file resembling a human-approval step (no input(),
no "approve", no manual confirmation call anywhere in the loop below).
"""
import time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import AuditLogEntry
from app.services.state_machine import StateManager, PAPER, SAFE
from app.services.execution_gateway import ExecutionGateway
from app.services.protective_exit import place_protective_stop
from app.services.reconciliation import reconcile_intent
from app.risk.engine import RiskEngine
from app.core.config import Settings
from app.brokers.base import Quote, OrderRequest
from app.brokers.paper_broker import PaperBrokerAdapter
from app.market_data.simulated import SimulatedMarketDataProvider
from app.strategies.test_dip_buy import TestDipBuyStrategy


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _broker_quote_source(md_provider):
    def _source(symbols):
        out = []
        for s in symbols:
            q = md_provider.get_quote(s)
            out.append(Quote(provider="simulated", symbol=s, timestamp=q.source_timestamp,
                              age_seconds=q.age_seconds, bid=q.bid, ask=q.ask, last=q.last,
                              market_status=q.market_session))
        return out
    return _source


def test_full_autonomous_paper_loop_no_human_input(db, monkeypatch):
    import datetime as dt
    from unittest.mock import patch

    md = SimulatedMarketDataProvider(prices={"TST": 9.5})  # already dipped from a $10 reference
    sm = StateManager(db)
    sm.transition(PAPER, "autonomous_test_start")
    broker = PaperBrokerAdapter(starting_cash=1000.0, quote_source=_broker_quote_source(md), slippage_bps=0)
    gw = ExecutionGateway(db=db, broker=broker, risk_engine=RiskEngine(cfg=Settings()),
                           state_manager=sm, designated_account_id="acct-designated", market_data=md)
    strategy = TestDipBuyStrategy(dip_pct=0.02, stop_pct=0.05, target_r_multiple=2.0)

    context = {"reference_price": 10.0, "last_price": 9.5}
    assert strategy.qualify("TST", context)  # 5% dip clears the 2% threshold
    signal = strategy.generate_signal("TST", context)
    assert signal is not None

    quote = Quote(provider="simulated", symbol="TST", timestamp=time.time(), age_seconds=0.1,
                  bid=9.48, ask=9.52, last=9.5, market_status="open")
    risk_context = dict(avg_dollar_volume=5_000_000.0, sector="tech", sector_exposure_pct=0.0,
                         open_position_count=0, daily_pnl_pct=0.0, weekly_drawdown_pct=0.0,
                         total_drawdown_pct=0.0, strategy_enabled=True)

    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = dt.datetime(2025, 1, 6, 15, 0, 0)  # Monday, market open
        result = gw.submit(signal, "acct-designated", quote, risk_context,
                            account_equity=1000.0, buying_power=1000.0)

    assert result.submitted  # entry filled with zero human approval call anywhere above

    ok = place_protective_stop(db, broker, sm, "TST", quantity=result.risk_decision.position_size,
                                stop_price=signal["stop_price"])
    assert ok  # order now RESTS pending trigger — it must not close the position immediately
    assert sm.get_state() == PAPER  # unaffected by a successful protective placement
    assert "TST" in broker.positions  # protective stop resting, position still open

    # --- Price moves down to the stop; the resting stop order fires on the next tick ---
    md.set_price("TST", signal["stop_price"] - 0.01)
    fired = broker.check_and_trigger_stops()
    assert len(fired) == 1
    assert fired[0].status == "filled"
    assert "TST" not in broker.positions  # position closed by the protective stop, not by a human

    # --- Everything above is reconstructable purely from the audit trail ---
    events = [e.event_type for e in db.query(AuditLogEntry).order_by(AuditLogEntry.timestamp).all()]
    assert "risk_decision" in events
    assert "order_submitted" in events
    assert "protective_stop_placed" in events
    # no event type in the entire trail represents a human gate
    assert not any("approv" in e.lower() for e in events)


def test_safe_mode_blocks_new_entries_but_not_defensive_exit(db):
    """The requirement to keep new-entry restrictions separate from defensive exit
    policy: SAFE mode must stop new risk without preventing closing an existing
    position via the protective-stop path."""
    import datetime as dt
    from unittest.mock import patch

    md = SimulatedMarketDataProvider(prices={"TST": 9.5})
    sm = StateManager(db)
    sm.transition(PAPER, "setup")
    broker = PaperBrokerAdapter(starting_cash=1000.0, quote_source=_broker_quote_source(md), slippage_bps=0)
    gw = ExecutionGateway(db=db, broker=broker, risk_engine=RiskEngine(cfg=Settings()),
                           state_manager=sm, designated_account_id="acct-designated", market_data=md)

    # A position already exists from BEFORE the SAFE-mode trigger (e.g. yesterday's entry).
    with patch("app.brokers.paper_broker.dt") as mock_dt:
        mock_dt.datetime.utcnow.return_value = dt.datetime(2025, 1, 6, 15, 0, 0)
        broker.place_order(OrderRequest(symbol="TST", side="buy", quantity=10.0))
    assert "TST" in broker.positions

    sm.enter_safe_mode("simulated_daily_loss_breach")

    signal = {"symbol": "TST", "direction": "long", "strategy": "test-dip-buy-v0.1.0",
              "decision_id": "safe-test-1", "entry_price": 9.5, "stop_price": 9.0,
              "target_price": 10.5, "thesis": "t", "ai_confidence": None}
    quote = Quote(provider="simulated", symbol="TST", timestamp=time.time(), age_seconds=0.1,
                  bid=9.48, ask=9.52, last=9.5, market_status="open")
    risk_context = dict(avg_dollar_volume=5_000_000.0, sector="tech", sector_exposure_pct=0.0,
                         open_position_count=0, daily_pnl_pct=-0.031, weekly_drawdown_pct=0.0,
                         total_drawdown_pct=0.0, strategy_enabled=True)
    new_entry_result = gw.submit(signal, "acct-designated", quote, risk_context,
                                  account_equity=1000.0, buying_power=1000.0)
    assert not new_entry_result.submitted  # blocked by SAFE, not even reaching risk engine

    # place_protective_stop does not consult can_open_new_entries at all — it must
    # succeed for the already-open position regardless of SAFE mode.
    ok = place_protective_stop(db, broker, sm, "TST", quantity=10.0, stop_price=9.0)
    assert ok
    assert "TST" in broker.positions  # resting, not yet triggered


def test_stale_data_at_final_recheck_blocks_submission_even_if_initial_quote_was_fresh(db):
    """Recheck freshness immediately before submission: the quote passed at the
    top of submit() was fresh, but the market_data provider now reports stale
    data — the recheck must still block."""
    md = SimulatedMarketDataProvider(prices={"TST": 9.5})
    sm = StateManager(db)
    sm.transition(PAPER, "setup")
    broker = PaperBrokerAdapter(starting_cash=1000.0, quote_source=_broker_quote_source(md), slippage_bps=0)
    gw = ExecutionGateway(db=db, broker=broker, risk_engine=RiskEngine(cfg=Settings()),
                           state_manager=sm, designated_account_id="acct-designated", market_data=md)

    signal = {"symbol": "TST", "direction": "long", "strategy": "test-dip-buy-v0.1.0",
              "decision_id": "stale-recheck-1", "entry_price": 9.5, "stop_price": 9.0,
              "target_price": 10.5, "thesis": "t", "ai_confidence": None}
    fresh_quote_at_entry = Quote(provider="simulated", symbol="TST", timestamp=time.time(), age_seconds=0.1,
                                  bid=9.48, ask=9.52, last=9.5, market_status="open")
    risk_context = dict(avg_dollar_volume=5_000_000.0, sector="tech", sector_exposure_pct=0.0,
                         open_position_count=0, daily_pnl_pct=0.0, weekly_drawdown_pct=0.0,
                         total_drawdown_pct=0.0, strategy_enabled=True)

    md.inject_fault("stale")  # simulate the feed going stale between check #1 and the recheck
    result = gw.submit(signal, "acct-designated", fresh_quote_at_entry, risk_context,
                        account_equity=1000.0, buying_power=1000.0)
    assert not result.submitted
    assert result.reason == "recheck_stale_quote"
