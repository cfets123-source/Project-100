from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.base import OrderResult, Quote
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import ExternalLiveProtection, TradeDecisionRecord, OrderIntent, RiskReservation
from app.runtime.alpaca_live_position_manager import (
    manage_live_positions, manage_paper_positions, release_flat_account_reservations,
)


def test_flat_broker_account_releases_only_non_pending_reservations():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        RiskReservation(id='release-me', account_id='acct', decision_id='closed', risk_dollars=1,
                        notional=50, status='active'),
        RiskReservation(id='keep-me', account_id='acct', decision_id='pending', risk_dollars=1,
                        notional=50, status='active'),
        OrderIntent(intent_key='closed', account_id='acct', decision_id='closed', symbol='SPY',
                    side='buy', quantity=.5, status='filled', broker_order_id='closed-order'),
        OrderIntent(intent_key='pending', account_id='acct', decision_id='pending', symbol='QQQ',
                    side='buy', quantity=.5, status='pending', broker_order_id='pending-order'),
    ])
    db.commit()
    adapter = MagicMock(paper=False)
    adapter.get_positions.return_value = []
    adapter.get_orders.return_value = [{'id': 'pending-order', 'status': 'accepted'}]

    released = release_flat_account_reservations(db, adapter, 'acct')

    assert released == ['release-me']
    assert db.get(RiskReservation, 'release-me').status == 'released'
    assert db.get(RiskReservation, 'keep-me').status == 'active'


def test_target_exit_is_submitted_once_and_keeps_stop_while_position_open():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(TradeDecisionRecord(symbol='SPY', strategy='daily-trend-pullback-portfolio-v1',
                               direction='long', order_id='entry-1', fill_price=100,
                               target_price=106, position_size=0.5, status='open'))
    db.add(ExternalLiveProtection(entry_order_id='entry-1', symbol='SPY', quantity=.5,
                                  stop_price=94, protective_order_id='stop-1'))
    db.commit()
    adapter = MagicMock(paper=False)
    adapter.get_positions.return_value = [{'symbol': 'SPY', 'qty': '.5'}]
    adapter.get_orders.return_value = [{'id': 'stop-1', 'symbol': 'SPY', 'status': 'accepted', 'type': 'stop'}]
    adapter.get_quotes.return_value = [Quote('alpaca', 'SPY', 1, 0, 106, 106.1, 106.05, 'open')]
    adapter.place_order.return_value = OrderResult(order_id='exit-1', status='accepted')

    result = manage_live_positions(db, adapter, allow_legacy_target_exit=True)

    assert result['target_exits_submitted'][0]['exit_order_id'] == 'exit-1'
    assert adapter.cancel_order.call_count == 0
    manage_live_positions(db, adapter, allow_legacy_target_exit=True)
    assert adapter.place_order.call_count == 1


def test_paper_target_exit_uses_the_paper_ledger_only():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(TradeDecisionRecord(symbol='QQQ', strategy='daily-trend-pullback-portfolio-v1',
                               direction='long', order_id='paper-entry', fill_price=100,
                               target_price=106, position_size=.5, status='open'))
    db.add(models.ExternalPaperProtection(entry_order_id='paper-entry', symbol='QQQ', quantity=.5,
                                          stop_price=94, protective_order_id='paper-stop'))
    db.add(TradeDecisionRecord(symbol='QQQ', strategy='old', direction='long', order_id='old-entry',
                               fill_price=90, target_price=91, position_size=.5, status='closed'))
    db.add(models.ExternalPaperProtection(entry_order_id='old-entry', symbol='QQQ', quantity=.5,
                                          stop_price=85, protective_order_id='old-stop'))
    db.commit()
    adapter = MagicMock(paper=True)
    adapter.get_positions.return_value = [{'symbol': 'QQQ', 'qty': '.5'}]
    adapter.get_orders.return_value = [{'id': 'paper-stop', 'symbol': 'QQQ', 'status': 'accepted', 'type': 'stop'}]
    adapter.get_quotes.return_value = [Quote('alpaca', 'QQQ', 1, 0, 106, 106.1, 106.05, 'open')]
    adapter.place_order.return_value = OrderResult(order_id='paper-exit', status='accepted')

    result = manage_paper_positions(db, adapter, allow_legacy_target_exit=True)

    assert result['target_exits_submitted'][0]['exit_order_id'] == 'paper-exit'
    assert db.get(models.ExternalPaperExit, 'paper-entry').exit_order_id == 'paper-exit'


def test_continuous_worker_does_not_retry_legacy_target_exit_requests():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(TradeDecisionRecord(symbol='LCID', strategy='legacy', direction='long',
                               order_id='entry-legacy', fill_price=4.2,
                               target_price=4.3, position_size=1, status='open'))
    db.add(models.ExternalPaperProtection(entry_order_id='entry-legacy', symbol='LCID', quantity=1,
                                          stop_price=4.1, protective_order_id='stop-legacy'))
    db.commit()
    adapter = MagicMock(paper=True)
    adapter.get_positions.return_value = [{'symbol': 'LCID', 'qty': '1'}]
    adapter.get_orders.return_value = [{'id': 'stop-legacy', 'symbol': 'LCID',
                                        'status': 'accepted', 'type': 'stop'}]

    result = manage_paper_positions(db, adapter)

    assert result['legacy_target_management_disabled'] == [
        {'symbol': 'LCID', 'entry_order_id': 'entry-legacy'}]
    adapter.get_quotes.assert_not_called()
    adapter.place_order.assert_not_called()


def test_target_exit_broker_failure_keeps_stop_and_returns_safe_result():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(TradeDecisionRecord(symbol='QQQ', strategy='daily-trend-pullback-portfolio-v1',
                               direction='long', order_id='paper-entry', fill_price=100,
                               target_price=106, position_size=.5, status='open'))
    db.add(models.ExternalPaperProtection(entry_order_id='paper-entry', symbol='QQQ', quantity=.5,
                                          stop_price=94, protective_order_id='paper-stop'))
    db.commit()
    adapter = MagicMock(paper=True)
    adapter.get_positions.return_value = [{'symbol': 'QQQ', 'qty': '.5'}]
    adapter.get_orders.return_value = [{'id': 'paper-stop', 'symbol': 'QQQ', 'status': 'accepted', 'type': 'stop'}]
    adapter.get_quotes.return_value = [Quote('alpaca', 'QQQ', 1, 0, 106, 106.1, 106.05, 'open')]
    adapter.place_order.side_effect = RuntimeError('rate limited')

    result = manage_paper_positions(db, adapter, allow_legacy_target_exit=True)

    assert result['target_exit_failures'][0]['error'] == 'RuntimeError'
    adapter.cancel_order.assert_not_called()
    retry = db.get(models.ExternalTargetExitRetry, 'paper-entry')
    assert retry is not None and retry.failures == -1
    result = manage_paper_positions(db, adapter, allow_legacy_target_exit=True)
    assert result['legacy_target_management_disabled'][0]['entry_order_id'] == 'paper-entry'
    assert adapter.place_order.call_count == 1


def test_reconciles_filled_broker_bracket_target_into_closed_trade():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    trade = TradeDecisionRecord(symbol='LCID', strategy='daily-trend-pullback-portfolio-v1',
                                direction='long', order_id='entry-bracket', fill_price=4.2,
                                target_price=4.3, position_size=1, risk_dollars=.1, status='open')
    db.add(trade); db.commit()
    adapter = MagicMock(paper=True)
    adapter.get_orders.return_value = [{
        'id': 'entry-bracket', 'legs': [
            {'id': 'target-leg', 'type': 'limit', 'status': 'filled',
             'filled_qty': '1', 'filled_avg_price': '4.3'},
            {'id': 'stop-leg', 'type': 'stop', 'status': 'canceled'},
        ],
    }]
    from app.runtime.alpaca_live_position_manager import reconcile_broker_bracket_exits
    result = reconcile_broker_bracket_exits(db, adapter, mode='paper')

    assert result['bracket_trades_closed'][0]['reason'] == 'target_hit'
    assert trade.status == 'closed' and trade.exit_price == 4.3
