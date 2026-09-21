"""Autonomous Alpaca paper worker. Requires the separate paper execution gate."""
import time
from app.brokers.alpaca_connection import load_read_only_adapter, load_paper_execution_adapter
from app.runtime.alpaca_paper_controller import evaluate_candidate
from app.runtime.alpaca_paper_reconciler import run_reconciliation_cycle
from app.strategies.daily_trend_pullback import DailyTrendPullback
from app.audit.logger import log_and_commit
from app.models.models import ExternalPaperRuntimeState
from app.services.alpaca_paper_protection import ensure_protective_stops
from app.research.strategy_validation import require_passing_validation
from app.brokers.alpaca_adapter import AlpacaBrokerError
from app.runtime.alpaca_live_position_manager import manage_paper_positions, reconcile_broker_bracket_exits


def run_cycle(db, cfg, account_id: str, symbols: list[str], references: dict[str, float] | None = None,
              strategy: DailyTrendPullback | None = None, state_id: str = "alpaca-paper-1"):
    """Run one guarded paper cycle with durable reference-price state."""
    state = db.get(ExternalPaperRuntimeState, state_id)
    if state is None:
        state = ExternalPaperRuntimeState(id=state_id, payload={"references": {}}, heartbeat=time.time(), status="waiting")
        db.add(state); db.commit()
    references = references if references is not None else dict(state.payload.get("references", {}))
    state.heartbeat = time.time(); state.status = "running"; db.commit()
    log_and_commit(db, 'alpaca_paper_worker_cycle_started', {'symbols': symbols})
    try:
        reconciliation = run_reconciliation_cycle(db, cfg, symbols)
    except AlpacaBrokerError as exc:
        # A broker throttle is external and temporary.  Do not restart-loop or
        # create an entry while account/position state is unavailable.
        state.status = 'broker_rate_limited'
        state.payload = {**state.payload, 'references': references,
                         'last_broker_error': type(exc).__name__}
        db.commit()
        log_and_commit(db, 'alpaca_paper_worker_rate_limited', {'error': type(exc).__name__})
        return {'entries': [], 'reason': 'broker_rate_limited', 'processed_at': time.time()}
    if not reconciliation['market_open'] or not cfg.ALPACA_PAPER_EXECUTION_ENABLED:
        log_and_commit(db, 'alpaca_paper_worker_entries_blocked', {'market_open': reconciliation['market_open'], 'paper_gate': cfg.ALPACA_PAPER_EXECUTION_ENABLED})
        state.payload={**state.payload, 'references': references}; state.status='blocked'; db.commit()
        return {**reconciliation, 'entries': []}
    # Reconciliation may have discovered a fill since the last cycle.  Create
    # its broker-side stop before evaluating any new entry.
    execution_adapter = load_paper_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY,
                                                     enabled=cfg.ALPACA_PAPER_EXECUTION_ENABLED)
    protection = ensure_protective_stops(db, execution_adapter, cfg)
    if not protection['protected']:
        state.status = 'halted_unprotected_position'; db.commit()
        log_and_commit(db, 'alpaca_paper_worker_unprotected_position', protection)
        return {**reconciliation, **protection, 'entries': []}
    lifecycle = manage_paper_positions(db, execution_adapter, allow_legacy_target_exit=True)
    bracket_reconciliation = reconcile_broker_bracket_exits(db, execution_adapter, mode="paper")
    adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper: raise RuntimeError('paper worker refuses live credential')
    strategy, entries = strategy or DailyTrendPullback(), []
    require_passing_validation(db, strategy.name)
    scan_day=time.strftime('%Y-%m-%d', time.gmtime())
    if state.payload.get('last_strategy_scan_day') == scan_day:
        state.status='daily_scan_already_recorded'; db.commit()
        return {**reconciliation, 'entries': [], 'reason': 'daily_scan_already_recorded', 'lifecycle': lifecycle,
                'bracket_reconciliation': bracket_reconciliation}
    # Never create a second entry while the broker reports any open position.
    positions = execution_adapter.get_positions()
    if positions:
        state.payload={**state.payload, 'references': references, 'last_strategy_scan_day': scan_day}
        state.status='position_already_open'; db.commit()
        return {**reconciliation, 'entries': [], 'reason': 'position_already_open', 'lifecycle': lifecycle,
                'bracket_reconciliation': bracket_reconciliation}
    signal = strategy.portfolio_signal(adapter, symbols)
    if signal:
        context={'avg_dollar_volume':5_000_000, 'sector':'unclassified', 'open_position_count':len(positions),
                 'daily_pnl_pct':0.0, 'weekly_drawdown_pct':0.0, 'total_drawdown_pct':0.0}
        entries.append(evaluate_candidate(db, cfg, account_id, signal, context))
    else:
        log_and_commit(db, 'alpaca_paper_worker_no_qualifying_signal', {
            'strategy': strategy.name, 'symbols': list(symbols), 'scan_day': scan_day,
        })
    state.payload={**state.payload, 'references': references, 'last_strategy_scan_day': scan_day}
    log_and_commit(db, 'alpaca_paper_worker_cycle_completed', {'entry_count': len(entries)})
    state.status='healthy'; db.commit()
    return {**reconciliation, 'paper_execution_gate': cfg.ALPACA_PAPER_EXECUTION_ENABLED,
            'strategy': strategy.name, 'signal_found': bool(signal), 'entries': entries,
            'references': references, 'processed_at': time.time(), 'lifecycle': lifecycle,
            'bracket_reconciliation': bracket_reconciliation}

if __name__ == '__main__':
    # Service wiring is intentionally not self-activating; compose passes the
    # default-off paper gate through the environment.
    import argparse
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import Settings
    parser=argparse.ArgumentParser(); parser.add_argument('--database', required=True); parser.add_argument('--account-id', required=True); parser.add_argument('--symbols', required=True); parser.add_argument('--once', action='store_true'); parser.add_argument('--interval', type=float, default=15.0)
    args=parser.parse_args(); cfg=Settings(); engine=create_engine(args.database)
    while True:
        with Session(engine) as db:
            print(run_cycle(db, cfg, args.account_id, args.symbols.split(',')), flush=True)
        if args.once:
            break
        time.sleep(max(1.0, args.interval))
