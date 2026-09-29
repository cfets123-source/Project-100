"""Read-only broker observation, isolated from every order-execution permission."""
import argparse
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import Settings, TradingMode, AutonomyLevel
from app.db.session import initialize_schema
from app.audit.logger import log_and_commit
from app.runtime.alpaca_position_supervisor import supervise_positions


def observe_once(db, cfg):
    observer_cfg = cfg.model_copy(update={
        'TRADING_MODE': TradingMode.PAPER,
        'AUTONOMY_LEVEL': AutonomyLevel.LEVEL_0_RESEARCH_ONLY,
        'AUTO_EXECUTION': False, 'LIVE_TRADING_ENABLED': False,
        'LIVE_POSITION_MANAGEMENT_ENABLED': False, 'ALPACA_PAPER_EXECUTION_ENABLED': False,
        'ROBINHOOD_EQUITY_EXECUTION_ENABLED': False,
        'ROBINHOOD_CRYPTO_EXECUTION_ENABLED': False,
        'ROBINHOOD_OPTIONS_EXECUTION_ENABLED': False})
    try:
        result=supervise_positions(db,observer_cfg)
        status={'read_only':True,'order_execution_enabled':False,
                'risk_ready':bool(result.get('risk_ready')),
                'position_count':result.get('positions'),
                'milestone_phase':result.get('milestone',{}).get('phase'),
                'next_target':result.get('milestone',{}).get('next_target'),
                'reason':result.get('risk_error')}
    except Exception as exc:
        db.rollback()
        status={'read_only':True,'order_execution_enabled':False,
                'risk_ready':False,'reason':type(exc).__name__}
    log_and_commit(db,'live_account_observed',status)
    return status


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--interval',type=float,default=60)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    cfg=Settings();engine=create_engine(cfg.DATABASE_URL)
    initialize_schema(engine)
    while True:
        with Session(engine) as db:
            print(observe_once(db,cfg),flush=True)
        if args.once: break
        time.sleep(max(60,args.interval))


if __name__=='__main__': main()
