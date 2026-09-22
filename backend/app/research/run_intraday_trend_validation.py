"""Run bounded, read-only validation for the intraday research hypothesis."""
from __future__ import annotations
import argparse
import datetime as dt
from dataclasses import replace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.db.session import Base
from app.research.intraday_trend_pullback import STRATEGY_VERSION, UNIVERSE, evaluate
from app.research.strategy_validation import assess_out_of_sample, record_validation

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--database',required=True); p.add_argument('--days',type=int,default=60); a=p.parse_args()
    cfg=Settings(DATABASE_URL=a.database); db=sessionmaker(bind=create_engine(a.database))(); Base.metadata.create_all(bind=db.get_bind())
    try:
        adapter,paper=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=True)
        if not paper: raise RuntimeError('intraday research requires paper credential')
        end=dt.datetime.now(dt.UTC); start=end-dt.timedelta(days=a.days)
        data={s:adapter.get_intraday_bars(s,start.isoformat(),end.isoformat()) for s in UNIVERSE}
        trades=evaluate(data)
        # This same recent window informed the candidate. Its apparent return is
        # exploratory, not untouched out-of-sample evidence. Persist an explicit
        # failed promotion record so it cannot satisfy the live strategy gate.
        result=assess_out_of_sample([t.applied_return for t in trades],minimum_trades=30)
        promotion=replace(result,passed=False,reasons=[*result.reasons,
            'exploratory reused sample; independent holdout and paper lifecycle required'])
        record_validation(db,strategy=STRATEGY_VERSION,result=promotion,sample_start=start,sample_end=end)
        print({'strategy':STRATEGY_VERSION,'universe_size':len(UNIVERSE),'days':a.days,
               'trades':result.trades,'modeled_account_return':result.total_return,
               'max_drawdown':result.max_drawdown,'live_eligible':False,
               'reasons':promotion.reasons})
        return 0
    finally: db.close()
if __name__=='__main__': raise SystemExit(main())
