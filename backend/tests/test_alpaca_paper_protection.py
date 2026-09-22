from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.base import OrderResult
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import TradeDecisionRecord
from app.services.alpaca_paper_protection import ensure_protective_stops, _sell_stop_price_for_broker


def _db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_places_alpaca_stop_for_unprotected_filled_position():
    db = _db()
    db.add(TradeDecisionRecord(symbol='AAPL', direction='long', strategy='test',
                               order_id='entry-1', stop_price=90.0, position_size=1.0))
    db.commit()
    adapter = MagicMock(paper=True)
    adapter.get_positions.return_value = [{'symbol': 'AAPL', 'qty': '1'}]
    adapter.get_orders.side_effect = [
        [{'id': 'entry-1', 'symbol': 'AAPL', 'side': 'buy', 'status': 'filled', 'filled_qty': '1'}],
        [{'id': 'entry-1', 'symbol': 'AAPL', 'side': 'buy', 'status': 'filled', 'filled_qty': '1'}],
        [{'id': 'entry-1', 'symbol': 'AAPL', 'side': 'buy', 'status': 'filled', 'filled_qty': '1'},
         {'symbol': 'AAPL', 'type': 'stop', 'status': 'accepted'}],
    ]
    # Alpaca commonly reports a newly accepted resting stop as ``new``.
    adapter.place_order.return_value = OrderResult(order_id='stop-1', status='new')

    result = ensure_protective_stops(db, adapter, SimpleNamespace())

    assert result['protected'] is True
    submitted = adapter.place_order.call_args.args[0]
    assert submitted.order_type == 'stop' and submitted.stop_price == 90.0
    assert submitted.time_in_force == 'day'


def test_missing_recorded_stop_halts_before_more_entries():
    db = _db()
    adapter = MagicMock(paper=True)
    adapter.get_positions.return_value = [{'symbol': 'AAPL', 'qty': '1'}]
    adapter.get_orders.return_value = []

    result = ensure_protective_stops(db, adapter, SimpleNamespace())

    assert result['protected'] is False and result['reason'] == 'missing_recorded_stop'
    assert result['emergency_exit']['submitted'] is True
    submitted = adapter.place_order.call_args.args[0]
    assert submitted.symbol == 'AAPL' and submitted.side == 'sell' and submitted.quantity == 1.0
    assert db.get(models.SystemStateRecord, 'current').state == 'halted'


def test_stop_submission_failure_submits_one_emergency_exit():
    db = _db()
    db.add(TradeDecisionRecord(symbol='AAPL', direction='long', strategy='test',
                               order_id='entry-1', stop_price=90.0, position_size=1.0))
    db.commit()
    adapter = MagicMock(paper=True)
    adapter.get_positions.return_value = [{'symbol': 'AAPL', 'qty': '1'}]
    adapter.get_orders.side_effect = [
        [{'id': 'entry-1', 'symbol': 'AAPL', 'side': 'buy', 'status': 'filled', 'filled_qty': '1'}],
        [{'id': 'entry-1', 'symbol': 'AAPL', 'side': 'buy', 'status': 'filled', 'filled_qty': '1'}],
    ]
    adapter.place_order.side_effect = [RuntimeError('broker declined stop'),
                                       OrderResult(order_id='exit-1', status='accepted')]

    result = ensure_protective_stops(db, adapter, SimpleNamespace())

    assert result['protected'] is False and result['reason'] == 'broker_error'
    assert result['emergency_exit']['submitted'] is True
    assert adapter.place_order.call_args_list[1].args[0].side == 'sell'


def test_sell_stop_price_uses_alpaca_tick_without_loosening_protection():
    assert _sell_stop_price_for_broker(145.8249) == 145.82
    assert _sell_stop_price_for_broker(0.98765) == 0.9876
