"""Controlled external-paper execution prerequisites.

No caller can obtain a submitting adapter unless the separate paper gate is on;
this module never enables that gate itself.
"""
from app.brokers.alpaca_connection import load_read_only_adapter
from app.market_data.alpaca import AlpacaMarketDataProvider
from app.market_data.base import validate_quote


def execution_prerequisites(db, cfg, symbol: str) -> dict:
    adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
    if not paper:
        return {"ready": False, "reason": "live_credential_refused"}
    if not cfg.ALPACA_PAPER_EXECUTION_ENABLED:
        return {"ready": False, "reason": "alpaca_paper_execution_gate_disabled"}
    provider = AlpacaMarketDataProvider(adapter)
    provider.refresh_account_snapshot()
    quote = provider.get_quote(symbol)
    freshness = validate_quote(quote, cfg.MAX_QUOTE_AGE_SECONDS)
    if not freshness.valid:
        return {"ready": False, "reason": f"quote_{freshness.reason}"}
    if provider.get_account_snapshot_age_seconds() > cfg.MAX_QUOTE_AGE_SECONDS:
        return {"ready": False, "reason": "stale_account_snapshot"}
    return {"ready": True, "reason": "", "quote": quote, "account": provider.account_snapshot}
