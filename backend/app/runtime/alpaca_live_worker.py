"""Isolated live worker. The compose profile remains default-off."""
import time
from app.runtime.alpaca_live_execution import load_finally_authorized_adapter
from app.strategies.daily_trend_pullback import DailyTrendPullback
from app.services.execution_gateway import ExecutionGateway
from app.services.state_machine import StateManager
from app.risk.engine import RiskEngine
from app.services.alpaca_paper_protection import ensure_protective_stops
from app.audit.logger import log_and_commit
from app.runtime.alpaca_live_position_manager import manage_live_positions, reconcile_broker_bracket_exits
from app.brokers.alpaca_adapter import AlpacaBrokerError

LIVE_SYMBOLS=("SPY","QQQ","IWM","GLD","TLT")

def start_live_worker(db, cfg):
    strategy=DailyTrendPullback()
    # This constructs the broker mutation adapter only after state, final flag,
    # and this exact strategy's passing validation record have all been checked.
    return load_finally_authorized_adapter(db, cfg, strategy.name)

def run_cycle(db, cfg):
    """One guarded live cycle; disabled gates fail before any broker mutation."""
    adapter=start_live_worker(db,cfg)
    protection=ensure_protective_stops(db, adapter, cfg, mode="live")
    if not protection.get('protected'):
        StateManager(db,cfg).activate_kill_switch('live position lacks verified protective stop')
        return {"started": True, "entries": [], "protection": protection}
    lifecycle = manage_live_positions(db, adapter, allow_legacy_target_exit=True)
    bracket_reconciliation = reconcile_broker_bracket_exits(db, adapter, mode="live")
    positions = adapter.get_positions()
    if positions:
        return {"started": True, "entries": [], "reason": "position_already_open",
                "protection": protection, "lifecycle": lifecycle,
                "bracket_reconciliation": bracket_reconciliation}
    strategy=DailyTrendPullback()
    signal=strategy.portfolio_signal(adapter, LIVE_SYMBOLS)
    if not signal:
        log_and_commit(db, "alpaca_live_worker_no_qualifying_signal", {"strategy": strategy.name})
        return {"started": True, "entries": [], "reason": "no_qualifying_signal",
                "protection": protection, "lifecycle": lifecycle,
                "bracket_reconciliation": bracket_reconciliation}
    quote=adapter.get_quotes([signal['symbol']])[0]
    balances=adapter.get_balances(); equity=min(float(balances['equity']), float(cfg.STARTING_CAPITAL))
    account_id=str(adapter.get_accounts()[0]['account_id'])
    result=ExecutionGateway(db,adapter,RiskEngine(cfg),StateManager(db,cfg),account_id).submit(
        signal, account_id, quote,
        {'avg_dollar_volume':5_000_000,'sector':'unclassified','open_position_count':0,
         'daily_pnl_pct':0,'weekly_drawdown_pct':0,'total_drawdown_pct':0},
        equity, min(float(balances['buying_power']), equity*cfg.MAX_POSITION_PCT))
    log_and_commit(db, "alpaca_live_worker_cycle_completed", {"strategy": strategy.name,
                   "submitted": result.submitted, "reason": result.reason, "trade_id": result.trade_id})
    return {"started": True, **result.__dict__, "protection": protection, "lifecycle": lifecycle,
            "bracket_reconciliation": bracket_reconciliation}


if __name__ == '__main__':
    import argparse
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import Settings
    parser=argparse.ArgumentParser(); parser.add_argument('--database', required=True); parser.add_argument('--once', action='store_true'); parser.add_argument('--interval', type=float, default=60.0)
    args=parser.parse_args(); cfg=Settings(); engine=create_engine(args.database)
    while True:
        with Session(engine) as db:
            # Read throttling is an external, temporary condition.  Never let
            # it terminate the supervised live worker or turn into an order
            # retry; record it and wait for the next normal cycle instead.
            try:
                result = run_cycle(db, cfg)
            except AlpacaBrokerError as exc:
                log_and_commit(db, "alpaca_live_worker_rate_limited", {
                    "error": type(exc).__name__,
                })
                result = {"started": True, "entries": [], "reason": "broker_rate_limited"}
            print(result, flush=True)
        if args.once: break
        time.sleep(max(5.0, args.interval))
