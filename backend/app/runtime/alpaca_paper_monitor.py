"""Read-only external-paper cycle used before any paper execution is enabled."""
from __future__ import annotations

from app.audit.logger import log_and_commit
from app.market_data.alpaca import AlpacaMarketDataProvider
from app.market_data.base import validate_quote
from app.models.models import AccountSnapshot


def run_cycle(db, adapter, cfg, symbols: list[str]) -> dict:
    """Read broker state and validated quotes; never mutate Alpaca orders."""
    if not getattr(adapter, "paper", False):
        raise ValueError("external paper monitor refuses a live adapter")
    provider = AlpacaMarketDataProvider(adapter)
    snapshot = provider.refresh_account_snapshot()
    clock = adapter.get_market_clock()
    market_open = bool(clock.get("is_open"))
    failures, quotes = {}, {}
    for symbol in sorted({s.upper() for s in symbols if s.strip()}):
        try:
            if not market_open:
                continue
            quote = provider.get_quote(symbol)
            result = validate_quote(quote, cfg.MAX_QUOTE_AGE_SECONDS)
            if not result.valid:
                failures[symbol] = result.reason
            else:
                quotes[symbol] = {"bid": quote.bid, "ask": quote.ask, "last": quote.last,
                                  "source_timestamp": quote.source_timestamp}
        except Exception as exc:
            # Keep the error class in the durable audit data while retaining a
            # useful diagnosis for the operator dashboard.
            failures[symbol] = f"{type(exc).__name__}:{exc}"
    balances = snapshot["balances"]
    db.add(AccountSnapshot(equity=float(balances["equity"]), cash=float(balances["cash"]),
                           buying_power=float(balances["buying_power"])))
    result = {"paper_only": True, "market_open": market_open, "account_snapshot_fresh": provider.get_account_snapshot_age_seconds() <= cfg.MAX_QUOTE_AGE_SECONDS,
              "quotes": quotes, "failures": failures, "ready": not failures}
    log_and_commit(db, "alpaca_paper_monitor_cycle", {"symbols": sorted(quotes), "failures": failures})
    return result
