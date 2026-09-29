from __future__ import annotations
import argparse, datetime as dt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.db.session import Base
from app.research.monthly_etf_rotation import STRATEGY_VERSION, UNIVERSE, monthly_returns
from app.research.strategy_validation import assess_out_of_sample, record_validation

def main():
    p=argparse.ArgumentParser(); p.add_argument('--database', required=True); p.add_argument('--start',default='2016-01-01T00:00:00Z'); p.add_argument('--split',default='2023-01-01T00:00:00Z'); p.add_argument('--end',default=dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT00:00:00Z')); a=p.parse_args()
    cfg=Settings(DATABASE_URL=a.database); engine=create_engine(a.database); Base.metadata.create_all(engine); db=sessionmaker(bind=engine)()
    try:
        adapter,paper=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=True)
        if not paper: raise RuntimeError('paper credential required')
        result=assess_out_of_sample(monthly_returns({s:adapter.get_daily_bars(s,a.start,a.end) for s in UNIVERSE},a.split))
        record_validation(db,strategy=STRATEGY_VERSION,result=result,sample_start=dt.datetime.fromisoformat(a.split.replace('Z','+00:00')),sample_end=dt.datetime.fromisoformat(a.end.replace('Z','+00:00')))
        print({'strategy':STRATEGY_VERSION,**result.__dict__}); return 0 if result.passed else 2
    finally: db.close()
if __name__=='__main__': raise SystemExit(main())
