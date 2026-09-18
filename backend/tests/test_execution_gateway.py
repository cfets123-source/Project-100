import time
from dataclasses import replace
import uuid
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import models  # noqa: F401 register tables
from app.services.execution_gateway import ExecutionGateway, WrongAccountError
from app.services.state_machine import StateManager, OFF, PAPER, SHADOW, LIVE, HALTED, SAFE
from app.risk.engine import RiskEngine
from app.core.config import Settings
from app.brokers.base import Quote
from app.brokers.paper_broker import PaperBrokerAdapter


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def good_quote():
    return Quote(provider="t", symbol="TST", timestamp=time.time(), age_seconds=0.5,
                 bid=9.98, ask=10.02, last=10.0, market_status="open")


def good_signal(decision_id=None, symbol="TST"):
    return {"symbol": symbol, "direction": "long", "strategy": "momentum",
            "decision_id": decision_id or str(uuid.uuid4()),
            "entry_price": 10.0, "stop_price": 9.5, "target_price": 11.0,
            "thesis": "test", "ai_confidence": 0.7}


def base_risk_context(**overrides):
    ctx = dict(avg_dollar_volume=5_000_000.0, sector="tech", sector_exposure_pct=0.0,
               open_position_count=0, daily_pnl_pct=0.0, weekly_drawdown_pct=0.0,
               total_drawdown_pct=0.0, strategy_enabled=True)
    ctx.update(overrides)
    return ctx


def make_gateway(db, broker=None, state=PAPER):
    sm = StateManager(db)
    sm.transition(state, "test_setup") if state != OFF else None
    broker = broker or PaperBrokerAdapter(starting_cash=1000.0, quote_source=lambda syms: [good_quote() for _ in syms])
    if isinstance(broker, PaperBrokerAdapter):
        # Gateway tests exercise authorization/exposure, not the wall clock.
        # Market-hours behavior is covered separately in test_paper_broker.py.
        broker._is_market_open = lambda: True
    gw = ExecutionGateway(db=db, broker=broker, risk_engine=RiskEngine(cfg=Settings()),
                           state_manager=sm, designated_account_id="acct-designated")
    return gw, broker, sm


def submit(gw, sig, account_equity=1000.0, buying_power=1000.0, account="acct-designated"):
    return gw.submit(sig, account, replace(good_quote(), symbol=sig["symbol"]), base_risk_context(), account_equity, buying_power)


# --- 1. Durable decision-id idempotency ---

def test_same_decision_id_retried_is_suppressed_regardless_of_time():
    """Distinct from the old time-bucket approach: dedupe key is the decision_id,
    so even a retry issued much later than any wall-clock window still collides."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    gw, broker, sm = make_gateway(db)
    sig = good_signal(decision_id="fixed-decision-1")
    r1 = submit(gw, sig)
    assert r1.submitted
    # simulate a client retry arriving much later (no time-bucket dependency anymore)
    r2 = submit(gw, sig)
    assert not r2.submitted
    assert r2.reason == "duplicate_intent_suppressed"


def test_distinct_decisions_for_same_symbol_are_not_suppressed(db):
    gw, broker, sm = make_gateway(db)
    r1 = submit(gw, good_signal(decision_id="decision-A"))
    r2 = submit(gw, good_signal(decision_id="decision-B"))
    assert r1.submitted
    assert r2.submitted  # a genuinely new decision must never be treated as a duplicate


def test_sequential_duplicate_submission_only_one_wins(db):
    """Sequential duplicate delivery; does not prove concurrent worker safety."""
    gw, broker, sm = make_gateway(db)
    sig = good_signal(decision_id="race-decision")
    r1 = submit(gw, sig)
    r2 = submit(gw, sig)  # second "worker" hits the same key
    outcomes = sorted([r1.submitted, r2.submitted])
    assert outcomes == [False, True]


def test_restart_with_uncertain_outcome_is_reconciled_not_resubmitted(db):
    """Broker call raises (simulated timeout) -> intent recorded 'unknown'. A new
    session against the same engine (simulating process restart) must resolve it
    via reconciliation, never by calling place_order again.
    NOTE: exercised under LIVE with LIVE_TRADING_ENABLED explicitly overridden to
    True for THIS TEST ONLY, purely to route through a non-PaperBroker adapter
    stand-in (a MagicMock playing the role of a real broker). This override is
    test-only and is never how the shipped default config behaves (default is
    False and validated as such in test_config_consistency.py)."""
    from app.services.state_machine import StateManager, SHADOW, LIVE
    test_cfg = Settings(LIVE_TRADING_ENABLED=True)
    sm = StateManager(db, cfg=test_cfg)
    sm.transition(SHADOW, "setup")
    sm.transition(LIVE, "setup_promote_for_test")
    flaky_broker = MagicMock()
    flaky_broker.place_order.side_effect = TimeoutError("no response from broker")
    gw = ExecutionGateway(db=db, broker=flaky_broker, risk_engine=RiskEngine(cfg=Settings(LIVE_TRADING_ENABLED=True)),
                           state_manager=sm, designated_account_id="acct-designated")
    sig = good_signal(decision_id="uncertain-decision")
    result = submit(gw, sig)
    assert not result.submitted
    assert result.reason == "uncertain_outcome_pending_reconciliation"

    from app.models.models import OrderIntent
    from app.services.execution_gateway import _intent_key
    intent = db.get(OrderIntent, _intent_key("acct-designated", "uncertain-decision"))
    assert intent.status == "unknown"

    resolved_broker = MagicMock()
    resolved_broker.get_order_status.return_value = {"status": "filled", "filled_qty": intent.quantity,
                                                       "fill_price": 10.02}
    intent.broker_order_id = "recovered-order-id"
    db.commit()
    from app.services.reconciliation import reconcile_intent
    status = reconcile_intent(db, resolved_broker, intent)
    assert status == "filled"
    flaky_broker.place_order.assert_called_once()  # never retried


# --- 2. State machine gating ---

def test_off_and_research_block_new_entries(db):
    gw, broker, sm = make_gateway(db, state=OFF)
    result = submit(gw, good_signal())
    assert not result.submitted
    assert "off" in result.reason


def test_safe_blocks_new_entries(db):
    gw, broker, sm = make_gateway(db, state=PAPER)
    sm.enter_safe_mode("test")
    result = submit(gw, good_signal())
    assert not result.submitted
    assert "safe" in result.reason


def test_halted_blocks_new_entries_and_survives_restart(db):
    gw, broker, sm = make_gateway(db, state=PAPER)
    sm.activate_kill_switch("test_halt")
    result = submit(gw, good_signal())
    assert not result.submitted
    assert "halted" in result.reason
    # "restart": fresh StateManager against the same session/engine still sees HALTED
    sm2 = StateManager(db)
    assert sm2.get_state() == HALTED


def test_halted_cannot_be_exited_without_explicit_confirm(db):
    gw, broker, sm = make_gateway(db, state=PAPER)
    sm.activate_kill_switch("test_halt")
    with pytest.raises(Exception):
        sm.reset(actor="system", confirm=True)  # actor must be human, not 'system'
    with pytest.raises(Exception):
        sm.reset(actor="eduardo", confirm=False)  # confirm must be explicit True
    sm.reset(actor="eduardo", confirm=True)  # only this succeeds
    assert sm.get_state() == OFF


def test_shadow_mode_never_calls_broker(db):
    broker = MagicMock()
    gw, _, sm = make_gateway(db, broker=broker, state=SHADOW)
    result = submit(gw, good_signal())
    assert not result.submitted
    assert result.reason == "shadow_mode_no_broker_call"
    broker.place_order.assert_not_called()
    broker.preview_order.assert_not_called()


def test_paper_state_refuses_a_real_broker_instance(db):
    """Defense in depth: if PAPER state is ever wired to something other than
    PaperBrokerAdapter, refuse rather than silently mutate a real account."""
    fake_real_broker = MagicMock()
    gw, _, sm = make_gateway(db, broker=fake_real_broker, state=PAPER)
    with pytest.raises(RuntimeError):
        submit(gw, good_signal())


def test_live_is_hard_blocked_even_in_live_state(db):
    """LIVE_TRADING_ENABLED defaults False and must stay False for this task
    regardless of state or autonomy level."""
    broker = MagicMock()
    gw, _, sm = make_gateway(db, broker=broker, state=SHADOW)
    sm.transition(LIVE, "promote_for_test")
    result = submit(gw, good_signal())
    assert not result.submitted
    assert result.reason == "live_trading_hard_disabled_in_config"
    broker.place_order.assert_not_called()


def test_kill_switch_race_blocks_at_recheck_before_broker_call(db):
    """Simulates the kill switch activating in the gap between the initial state
    check and the broker call, via a StateManager subclass that activates on the
    exact recheck call. NOTE: uses LIVE_TRADING_ENABLED=True test-only override
    (see note in test_restart_with_uncertain_outcome...) purely to exercise a
    non-PaperBroker adapter stand-in without the PAPER-type guard short-circuiting
    the test before the race window is reached."""
    class RacingStateManager(StateManager):
        def __init__(self, db, cfg=None):
            super().__init__(db, cfg=cfg or Settings())
            self._calls = 0

        def can_open_new_entries(self):
            self._calls += 1
            if self._calls == 1:
                return True, ""  # initial check: still LIVE, no kill switch yet
            self.activate_kill_switch("raced_kill_switch")
            return False, "new_entries_blocked_state_halted"  # recheck: now HALTED

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db2 = sessionmaker(bind=engine)()
    test_cfg = Settings(LIVE_TRADING_ENABLED=True)
    sm = RacingStateManager(db2, cfg=test_cfg)
    sm.transition(SHADOW, "setup")
    sm.transition(LIVE, "setup_promote_for_test")
    broker = MagicMock()
    gw = ExecutionGateway(db=db2, broker=broker, risk_engine=RiskEngine(cfg=Settings(LIVE_TRADING_ENABLED=True)),
                           state_manager=sm, designated_account_id="acct-designated")
    result = submit(gw, good_signal())
    assert not result.submitted
    assert result.reason == "new_entries_blocked_state_halted"
    broker.place_order.assert_not_called()
    assert sm.get_state() == HALTED


# --- 3. Aggregate risk / buying power reservation ---

def test_two_individually_valid_proposals_jointly_exceed_buying_power(db):
    """Each proposal alone fits (risk-based sizing keeps notional at $200 here);
    together they need $400 which exceeds a deliberately tight $300 buying-power
    ceiling. RiskEngine (per-trade) approves both; the aggregate reservation must
    reject the second on buying power, not risk."""
    gw, broker, sm = make_gateway(db, state=PAPER)
    equity = 1000.0
    buying_power = 300.0
    sig_a = good_signal(decision_id="agg-a", symbol="AAA")
    sig_b = good_signal(decision_id="agg-b", symbol="BBB")
    r1 = submit(gw, sig_a, account_equity=equity, buying_power=buying_power)
    r2 = submit(gw, sig_b, account_equity=equity, buying_power=buying_power)
    assert r1.submitted
    assert not r2.submitted
    assert r2.reason == "insufficient_buying_power_aggregate"


def test_two_proposals_jointly_exceed_aggregate_risk_cap(db):
    gw, broker, sm = make_gateway(db, state=PAPER)
    equity = 1000.0
    # aggregate_risk_cap = min(MAX_POSITIONS * MAX_RISK_PER_TRADE, MAX_DAILY_LOSS) * equity
    #                     = min(2*0.01, 0.03) * 1000 = 0.02 * 1000 = $20
    # each single trade risk = equity * MAX_RISK_PER_TRADE = $10 -> two fit exactly at $20,
    # so force a third to prove the cap is enforced.
    sigs = [good_signal(decision_id=f"risk-cap-{i}", symbol=f"SYM{i}") for i in range(3)]
    results = [submit(gw, s, account_equity=equity, buying_power=100_000.0) for s in sigs]
    approved = [r.submitted for r in results]
    assert approved.count(True) == 2
    assert approved.count(False) == 1
    assert results[2].reason == "aggregate_risk_limit_exceeded"
