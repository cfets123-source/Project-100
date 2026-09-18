"""Final live adapter boundary.  No service imports this module by default."""
from app.brokers.alpaca_connection import load_live_execution_adapter
from app.services.state_machine import StateManager


def load_finally_authorized_adapter(db, cfg):
    """Require both config and persisted state before any live mutation exists."""
    state = StateManager(db, cfg)
    allowed, reason = state.live_broker_mutation_allowed()
    if not allowed:
        raise RuntimeError(reason)
    return load_live_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY,
                                       enabled=bool(cfg.LIVE_TRADING_ENABLED))
