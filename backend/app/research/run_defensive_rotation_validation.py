import argparse,datetime as dt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.db.session import Base
from app.research.defensive_rotation import STRATEGY_VERSION,RISK_ON,DEFENSIVE,monthly_returns
from app.research.portfolio_risk import volatility_targeted_returns
from app.research.strategy_validation import ValidationResult,assess_out_of_sample,record_validation

EXECUTION_MISMATCH = "monthly_holding_period_not_supported_by_fractional_day_stop_worker"

def promotion_result(research_result: ValidationResult) -> ValidationResult:
 """Retain measured returns but fail promotion until the same execution exists."""
 return ValidationResult(trades=research_result.trades,
                         win_rate=research_result.win_rate,
                         total_return=research_result.total_return,
                         max_drawdown=research_result.max_drawdown,
                         passed=False,
                         reasons=[*research_result.reasons, EXECUTION_MISMATCH])
def main():
 p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--start',default='2016-01-01T00:00:00Z');p.add_argument('--split',default='2023-01-01T00:00:00Z');p.add_argument('--end',default=dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT00:00:00Z'));a=p.parse_args();cfg=Settings(DATABASE_URL=a.database);e=create_engine(a.database);Base.metadata.create_all(e);db=sessionmaker(bind=e)()
 try:
  ad,_=load_read_only_adapter(db,cfg.BROKER_TOKEN_ENCRYPTION_KEY,paper=True);raw=monthly_returns({s:ad.get_daily_bars(s,a.start,a.end) for s in RISK_ON+DEFENSIVE},a.split);r=promotion_result(assess_out_of_sample(volatility_targeted_returns(raw)));record_validation(db,strategy=STRATEGY_VERSION+'-vol-targeted',result=r);print({'strategy':STRATEGY_VERSION+'-vol-targeted',**r.__dict__});return 0 if r.passed else 2
 finally: db.close()
if __name__=='__main__':raise SystemExit(main())
