"""Autonomous Alpaca paper worker. Requires the separate paper execution gate."""
import time
from app.brokers.alpaca_connection import load_read_only_adapter
from app.runtime.alpaca_paper_controller import evaluate_candidate
from app.runtime.alpaca_paper_reconciler import run_reconciliation_cycle
from app.strategies.test_dip_buy import TestDipBuyStrategy


def run_cycle(db, cfg, account_id: str, symbols: list[str], references: dict[str, float]):
    """Run one guarded paper cycle; caller owns scheduling and persistence."""
    reconciliation = run_reconciliation_cycle(db, cfg, symbols)
    if not reconciliation['market_open'] or not cfg.ALPACA_PAPER_EXECUTION_ENABLED:
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
    return {**reconciliation, 'entries': entries, 'references': references, 'processed_at': time.time()}
