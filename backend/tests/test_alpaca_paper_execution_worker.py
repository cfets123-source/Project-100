from unittest.mock import MagicMock
from app.runtime.alpaca_paper_execution_worker import run_cycle

def test_worker_never_loads_broker_when_paper_gate_is_off(monkeypatch):
    monkeypatch.setattr('app.runtime.alpaca_paper_execution_worker.run_reconciliation_cycle', lambda *_, **__: {'market_open':True})
    loader=MagicMock(); monkeypatch.setattr('app.runtime.alpaca_paper_execution_worker.load_read_only_adapter', loader)
    cfg=MagicMock(ALPACA_PAPER_EXECUTION_ENABLED=False)
    result=run_cycle(MagicMock(), cfg, 'acct', ['AAPL'], {})
    assert result['entries']==[]
    loader.assert_not_called()

def test_worker_persists_references_when_entries_are_blocked(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base
    from app.models import models  # noqa
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine); db=sessionmaker(bind=engine)()
    monkeypatch.setattr('app.runtime.alpaca_paper_execution_worker.run_reconciliation_cycle', lambda *_, **__: {'market_open':False})
    cfg=MagicMock(ALPACA_PAPER_EXECUTION_ENABLED=False)
    run_cycle(db, cfg, 'acct', ['AAPL'], {'AAPL': 100.0})
    assert db.get(models.ExternalPaperRuntimeState, 'alpaca-paper-1').payload['references']['AAPL'] == 100.0
