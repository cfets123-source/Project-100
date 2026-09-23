"""External Alpaca paper reconciliation cycle. Never submits orders."""
from app.brokers.alpaca_connection import load_read_only_adapter
from app.runtime.alpaca_paper_monitor import run_cycle
from app.services.reconciliation import reconcile_all_pending


def run_reconciliation_cycle(db, cfg, symbols, *, account_id: str):
    adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper:
        raise RuntimeError("reconciliation cycle refuses live credential")
    monitor = run_cycle(db, adapter, cfg, symbols)
    resolved = reconcile_all_pending(db, adapter, account_id=account_id)
    return {**monitor, "reconciled_intents": len(resolved), "order_submission": False}
