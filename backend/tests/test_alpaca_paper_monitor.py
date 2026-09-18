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
    def get_quotes(self, symbols): return [Quote("alpaca", symbols[0], datetime.now(timezone.utc).timestamp(), 0, 10, 10.1, 10.05, "open")]

def test_monitor_records_fresh_broker_snapshot_without_order_methods():
    engine=create_engine("sqlite:///:memory:"); Base.metadata.create_all(engine); db=sessionmaker(bind=engine)()
    report=run_cycle(db, Adapter(), Settings(), ["AAPL"])
    assert report["ready"] and report["paper_only"]
    assert db.query(models.AccountSnapshot).count() == 1
