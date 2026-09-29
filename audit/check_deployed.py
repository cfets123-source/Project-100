"""Read-only deployment/account snapshot. Never prints credentials or submits orders."""
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.models.models import SystemStateRecord
from app.brokers.alpaca_connection import load_read_only_adapter
cfg=Settings()
with Session(create_engine(cfg.DATABASE_URL)) as db:
    reader,paper=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=False)
    if paper or reader.allow_order_submission: raise RuntimeError('expected read-only live adapter')
    balances=reader.get_balances()
    positions=reader.get_positions()
    orders=reader.get_orders()
    terminal={'filled','canceled','expired','rejected','replaced'}
    states=[{'scope':r.id,'state':r.state,'reason':r.reason} for r in db.query(SystemStateRecord).all()]
    print(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'read_only':True,
                      'balances':balances,'position_count':len(positions),
                      'active_order_count':sum(o.get('status') not in terminal for o in orders),
                      'states':states,'api_live_flag':cfg.LIVE_TRADING_ENABLED}))
