"""Regression checks reproduced against the original 2123a66 build."""
import time
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import OrderIntent, RiskReservation
from app.market_data.base import MarketQuote, validate_quote
from app.services.state_machine import StateManager, SHADOW, PAPER, HALTED
from app.services.protective_exit import place_protective_stop
from app.services.reconciliation import reconcile_all_pending
from app.core.config import Settings
from app.risk.engine import RiskEngine, TradeProposal
from app.brokers.base import Quote
from app.market_data.simulated import SimulatedMarketDataProvider
from tests.test_execution_gateway import make_gateway, good_signal, submit
from app.services.state_machine import OFF, RESEARCH, LIVE, SAFE
from app.brokers.paper_broker import PaperBrokerAdapter
from app.models.models import SystemStateRecord

@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session

def test_cached_quote_must_expire():
    q = MarketQuote('fixture', 'TST', 'equity', 'open', 1000, 1000.1, 10, 10.01, 10)
    assert not validate_quote(q, 5, now=1600).valid

def test_nan_quote_must_be_rejected():
    now = time.time()
    q = MarketQuote('fixture', 'TST', 'equity', 'open', now, now, float('nan'), 10, 10)
    assert not validate_quote(q, 5).valid

def test_halt_cannot_be_cleared_by_safe_transition(db):
    sm = StateManager(db)
    sm.activate_kill_switch('serious anomaly')
    sm.enter_safe_mode('later protective-order error')
    assert sm.get_state() == HALTED

def test_shadow_protective_path_must_not_call_broker(db):
    sm = StateManager(db)
    sm.transition(SHADOW, 'test')
    broker = MagicMock()
    broker.place_order.return_value = MagicMock(status='accepted', order_id='stop')
    place_protective_stop(db, broker, sm, 'TST', 1, 9)
    broker.place_order.assert_not_called()

def test_partial_orders_must_continue_reconciling(db):
    intent = OrderIntent(intent_key='x', account_id='paper', decision_id='d',
                         symbol='TST', side='buy', quantity=10, quantity_filled=3,
                         status='partial', broker_order_id='broker-x')
    db.add(intent)
    db.commit()
    broker = MagicMock()
    broker.get_order_status.return_value = dict(status='filled', filled_qty=10, fill_price=10)
    reconcile_all_pending(db, broker)
    assert intent.status == 'filled'

def test_short_direction_must_obey_short_prohibition():
    quote = Quote('fixture', 'TST', time.time(), 0, 9.99, 10.01, 10, 'open')
    p = TradeProposal('TST', 'short', 10, 10.5, 1000, 'fixture', quote, 5000000)
    assert not RiskEngine(Settings()).evaluate(p).approved

def test_long_stop_above_entry_must_be_rejected():
    quote = Quote('fixture', 'TST', time.time(), 0, 9.99, 10.01, 10, 'open')
    p = TradeProposal('TST', 'long', 10, 11, 1000, 'fixture', quote, 5000000)
    assert not RiskEngine(Settings()).evaluate(p).approved

def test_canceled_before_submission_releases_reservation(db):
    gw, broker, sm = make_gateway(db)
    md = SimulatedMarketDataProvider(prices={'TST': 10})
    md.inject_fault('stale')
    gw.market_data = md
    outcome = submit(gw, good_signal())
    assert outcome.reason == 'recheck_stale_quote'
    assert db.query(RiskReservation).filter_by(status='active').count() == 0

@pytest.mark.parametrize('state', [OFF, RESEARCH, SHADOW, LIVE, HALTED, 'corrupt'])
def test_defensive_mutation_denied_outside_supported_modes(db, state):
    sm = StateManager(db)
    rec = sm.get_record()
    rec.state = state
    db.commit()
    broker = MagicMock(spec=PaperBrokerAdapter)
    assert not place_protective_stop(db, broker, sm, 'TST', 1, 9)
    broker.place_order.assert_not_called()

@pytest.mark.parametrize('state', [PAPER, SAFE])
def test_nonpaper_adapter_cannot_use_defensive_paper_or_safe_path(db, state):
    sm = StateManager(db)
    sm.transition(PAPER, 'setup')
    if state == SAFE:
        sm.enter_safe_mode('recoverable interruption')
    broker = MagicMock()
    assert not place_protective_stop(db, broker, sm, 'TST', 1, 9)
    broker.place_order.assert_not_called()

def test_sticky_halt_survives_new_session_and_still_requires_reset(db):
    sm = StateManager(db)
    sm.activate_kill_switch('serious')
    sm.enter_safe_mode('late failure')
    with sessionmaker(bind=db.get_bind())() as restarted:
        resumed = StateManager(restarted)
        assert resumed.get_state() == HALTED
        with pytest.raises(Exception):
            resumed.transition(PAPER, 'attempted bypass')
        resumed.reset(actor='test-user', confirm=True)
        assert resumed.get_state() == OFF

def test_unknown_state_blocks_entries(db):
    sm = StateManager(db)
    rec = sm.get_record()
    rec.state = 'corrupt'
    db.commit()
    assert not sm.can_open_new_entries()[0]

@pytest.mark.parametrize('field', ['bid', 'ask', 'last', 'source_timestamp', 'receipt_timestamp'])
@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_quote_fields_fail_closed(field, value):
    now = time.time()
    q = MarketQuote('fixture', 'TST', 'equity', 'open', now, now, 10, 10.01, 10)
    setattr(q, field, value)
    assert not validate_quote(q, 5).valid

def test_quote_freshness_boundary_uses_injected_clock():
    q = MarketQuote('fixture', 'TST', 'equity', 'open', 1000, 1000.1, 10, 10.01, 10)
    assert validate_quote(q, 5, now=1005).valid
    assert not validate_quote(q, 5, now=1005.001).valid

def test_accepted_then_partial_then_filled_reconciles_every_tick(db):
    intent = OrderIntent(intent_key='accepted', account_id='paper', decision_id='a',
                         symbol='TST', side='buy', quantity=10, quantity_filled=0,
                         status='accepted', broker_order_id='broker-a')
    db.add(intent)
    db.commit()
    broker = MagicMock()
    broker.get_order_status.side_effect = [
        dict(status='partial', filled_qty=3, fill_price=10),
        dict(status='filled', filled_qty=10, fill_price=10),
    ]
    assert reconcile_all_pending(db, broker) == ['partial']
    assert reconcile_all_pending(db, broker) == ['filled']
    assert reconcile_all_pending(db, broker) == []
    assert intent.quantity_filled == 10
    broker.place_order.assert_not_called()

def test_shadow_decision_releases_real_budget(db):
    gw, broker, sm = make_gateway(db, state=SHADOW)
    assert submit(gw, good_signal()).reason == 'shadow_mode_no_broker_call'
    assert db.query(RiskReservation).filter_by(status='active').count() == 0

def test_provider_exception_releases_unsubmitted_budget(db):
    gw, broker, sm = make_gateway(db)
    md = MagicMock()
    md.get_quote.side_effect = ConnectionError('test feed unavailable')
    gw.market_data = md
    assert submit(gw, good_signal()).reason == 'market_data_unavailable'
    assert db.query(RiskReservation).filter_by(status='active').count() == 0
    assert broker.get_orders() == []

def test_kill_during_data_fetch_prevents_submission_and_releases_budget(db):
    gw, broker, sm = make_gateway(db)
    md = SimulatedMarketDataProvider(prices={'TST': 10})
    original = md.get_quote
    def delayed_fetch(symbol):
        sm.activate_kill_switch('halt during data fetch')
        return original(symbol)
    md.get_quote = delayed_fetch
    gw.market_data = md
    assert not submit(gw, good_signal()).submitted
    assert broker.get_orders() == []
    assert db.query(RiskReservation).filter_by(status='active').count() == 0

def test_uncertain_submission_keeps_budget(db):
    gw, broker, sm = make_gateway(db)
    broker.place_order = MagicMock(side_effect=TimeoutError('unknown outcome'))
    assert submit(gw, good_signal()).reason == 'uncertain_outcome_pending_reconciliation'
    assert db.query(RiskReservation).filter_by(status='active').count() == 1

@pytest.mark.parametrize('direction,stop', [('long', 9.5), ('short', 10.5)])
def test_valid_stop_sides_approve_only_with_corresponding_permission(direction, stop):
    quote = Quote('fixture', 'TST', time.time(), 0, 9.99, 10.01, 10, 'open')
    p = TradeProposal('TST', direction, 10, stop, 1000, 'fixture', quote, 5000000)
    assert RiskEngine(Settings(ALLOW_SHORTS=True)).evaluate(p).approved
