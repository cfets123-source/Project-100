"""Autonomous Alpaca paper worker. Requires the separate paper execution gate."""
import time
from app.brokers.alpaca_connection import load_read_only_adapter
from app.runtime.alpaca_paper_controller import evaluate_candidate
from app.runtime.alpaca_paper_reconciler import run_reconciliation_cycle
from app.strategies.test_dip_buy import TestDipBuyStrategy
from app.audit.logger import log_and_commit
from app.models.models import ExternalPaperRuntimeState
from app.services.protective_order_verification import verify_protective_orders


def run_cycle(db, cfg, account_id: str, symbols: list[str], references: dict[str, float] | None = None):
    """Run one guarded paper cycle with durable reference-price state."""
    state = db.get(ExternalPaperRuntimeState, "alpaca-paper-1")
    if state is None:
        state = ExternalPaperRuntimeState(id="alpaca-paper-1", payload={"references": {}}, heartbeat=time.time(), status="waiting")
        db.add(state); db.commit()
    references = references if references is not None else dict(state.payload.get("references", {}))
    state.heartbeat = time.time(); state.status = "running"; db.commit()
    log_and_commit(db, 'alpaca_paper_worker_cycle_started', {'symbols': symbols})
    reconciliation = run_reconciliation_cycle(db, cfg, symbols)
    read_adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
    protection = verify_protective_orders(read_adapter)
    if not protection['protected']:
        state.status = 'halted_unprotected_position'; db.commit()
        log_and_commit(db, 'alpaca_paper_worker_unprotected_position', protection)
        return {**reconciliation, **protection, 'entries': []}
    if not reconciliation['market_open'] or not cfg.ALPACA_PAPER_EXECUTION_ENABLED:
        log_and_commit(db, 'alpaca_paper_worker_entries_blocked', {'market_open': reconciliation['market_open'], 'paper_gate': cfg.ALPACA_PAPER_EXECUTION_ENABLED})
        state.payload={**state.payload, 'references': references}; state.status='blocked'; db.commit()
        return {**reconciliation, 'entries': []}
    adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper: raise RuntimeError('paper worker refuses live credential')
    strategy, entries = TestDipBuyStrategy(), []
    for quote in adapter.get_quotes(symbols):
        reference = references.setdefault(quote.symbol, quote.last)
        signal = strategy.generate_signal(quote.symbol, {'last_price': quote.last, 'reference_price': reference})
        if not signal: continue
        context={'avg_dollar_volume':5_000_000, 'sector':'unclassified', 'open_position_count':0,
                 'daily_pnl_pct':0.0, 'weekly_drawdown_pct':0.0, 'total_drawdown_pct':0.0}
        entries.append(evaluate_candidate(db, cfg, account_id, signal, context))
    log_and_commit(db, 'alpaca_paper_worker_cycle_completed', {'entry_count': len(entries)})
    state.payload={**state.payload, 'references': references}; state.status='healthy'; db.commit()
    return {**reconciliation, 'entries': entries, 'references': references, 'processed_at': time.time()}

if __name__ == '__main__':
    # Service wiring is intentionally not self-activating; compose passes the
    # default-off paper gate through the environment.
    import argparse
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import Settings
    parser=argparse.ArgumentParser(); parser.add_argument('--database', required=True); parser.add_argument('--account-id', required=True); parser.add_argument('--symbols', required=True); parser.add_argument('--once', action='store_true')
    args=parser.parse_args(); cfg=Settings(); engine=create_engine(args.database)
    with Session(engine) as db:
        print(run_cycle(db, cfg, args.account_id, args.symbols.split(',')))
