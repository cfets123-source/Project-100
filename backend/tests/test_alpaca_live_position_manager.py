from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.base import OrderResult, Quote
from app.db.session import Base
from app.models import models  # noqa: F401
from app.models.models import ExternalLiveProtection, TradeDecisionRecord
from app.runtime.alpaca_live_position_manager import manage_live_positions


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
    adapter = MagicMock()
    adapter.get_positions.return_value = [{'symbol': 'SPY', 'qty': '.5'}]
    adapter.get_orders.return_value = [{'id': 'stop-1', 'symbol': 'SPY', 'status': 'accepted', 'type': 'stop'}]
    adapter.get_quotes.return_value = [Quote('alpaca', 'SPY', 1, 0, 106, 106.1, 106.05, 'open')]
    adapter.place_order.return_value = OrderResult(order_id='exit-1', status='accepted')

    result = manage_live_positions(db, adapter)

    assert result['target_exits_submitted'][0]['exit_order_id'] == 'exit-1'
    assert adapter.cancel_order.call_count == 0
    manage_live_positions(db, adapter)
    assert adapter.place_order.call_count == 1
