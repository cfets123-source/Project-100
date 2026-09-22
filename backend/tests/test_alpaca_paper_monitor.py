from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.brokers.base import Quote
from app.core.config import Settings
from app.db.session import Base
from app.models import models  # noqa
from app.runtime.alpaca_paper_monitor import run_cycle

class Adapter:
    paper = True
    def get_balances(self): return {"cash": 100, "equity": 100, "buying_power": 100}
    def get_positions(self): return []
    def get_market_clock(self): return {"is_open": True}
    def get_quotes(self, symbols): return [Quote("alpaca", symbols[0], datetime.now(timezone.utc).timestamp(), 0, 10, 10.1, 10.05, "open")]

def test_monitor_records_fresh_broker_snapshot_without_order_methods():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=sessionmaker(bind=engine)()
    report=run_cycle(db, Adapter(), Settings(), ["AAPL"])
    assert report["ready"] and report["paper_only"]
    assert db.query(models.AccountSnapshot).count() == 1

    
def test_monitor_marks_closed_market_without_stale_quote_failure():
    class ClosedAdapter(Adapter):
        def get_market_clock(self): return {"is_open": False}
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=sessionmaker(bind=engine)()
    report=run_cycle(db, ClosedAdapter(), Settings(), ["AAPL"])
    assert report["ready"] and report["market_open"] is False and report["quotes"] == {}


def test_monitor_uses_one_batched_quote_request_for_multiple_symbols():
    class BatchAdapter(Adapter):
        def __init__(self): self.requests = []
        def get_quotes(self, symbols):
            self.requests.append(symbols)
            now = datetime.now(timezone.utc).timestamp()
            return [Quote("alpaca", symbol, now, 0, 10, 10.1, 10.05, "open") for symbol in symbols]
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=sessionmaker(bind=engine)()
    adapter = BatchAdapter()
    report = run_cycle(db, adapter, Settings(), ["AAPL", "MSFT", "AAPL"])
    assert report["ready"]
    assert adapter.requests == [["AAPL", "MSFT"]]
