"""Run in a candidate container with production data mounted read-only.

Broker adapter is read-only. All derived risk records are temporary/in memory.
Does not import app.main, initialize production schema, or change broker state.
"""
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.session import Base
from app.brokers.alpaca_connection import load_read_only_adapter
from app.services.alpaca_risk_reconciliation import collect_risk_observation
cfg=Settings()
source=create_engine('sqlite:///file:/data/paper.db?mode=ro&uri=true')
temporary=create_engine('sqlite:///:memory:')
Base.metadata.create_all(temporary)
with Session(source) as production, Session(temporary) as scratch:
    reader,paper=load_read_only_adapter(production,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=False)
    if paper or reader.allow_order_submission: raise RuntimeError('reader must be live and non-submitting')
    evidence=collect_risk_observation(scratch,reader,'candidate-read-only-check')
    evidence.pop('account_id',None)
    print(json.dumps({'read_only_broker':True,'production_database_read_only':True,
                      'candidate_risk_evidence':evidence}))
