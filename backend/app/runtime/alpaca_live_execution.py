"""Final live adapter boundary.  No service imports this module by default."""
from app.brokers.alpaca_connection import load_live_execution_adapter, verify_read_only
from app.services.state_machine import StateManager
from app.research.strategy_validation import require_passing_validation


def load_finally_authorized_adapter(db, cfg, strategy: str):
    """Require final controls and a passing record for the exact strategy.

    ``strategy`` is mandatory so an approved record can never be reused by an
    unrelated strategy implementation.
    """
    state = StateManager(db, cfg)
    allowed, reason = state.live_broker_mutation_allowed()
    if not allowed:
        raise RuntimeError(reason)
    require_passing_validation(db, strategy)
    # A final flag alone is insufficient. Each live worker must prove the
    # distinct live account is readable before it can construct a mutating
    # adapter. This never submits or previews an order.
    readiness = verify_read_only(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    if not readiness.get("read_only_ready") or readiness.get("paper"):
        raise RuntimeError("live broker read-only verification incomplete")
    return load_live_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY,
                                       enabled=bool(cfg.LIVE_TRADING_ENABLED))
