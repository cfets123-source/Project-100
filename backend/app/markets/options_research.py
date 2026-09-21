"""Read-only option-chain availability and quote-quality assessment."""
from __future__ import annotations


def assess_option_chain(payload: dict, *, underlying: str) -> dict:
    """Summarize chain availability without choosing or authorizing a contract."""
    snapshots = payload.get("snapshots") or {}
    quoted = 0
    tight = 0
    for snapshot in snapshots.values():
        quote = snapshot.get("latestQuote") or {}
        bid = float(quote.get("bp") or 0)
        ask = float(quote.get("ap") or 0)
        if bid <= 0 or ask <= bid:
            continue
        quoted += 1
        midpoint = (bid + ask) / 2
        if midpoint > 0 and (ask - bid) / midpoint <= 0.10:
            tight += 1
    return {
        "underlying": underlying,
        "feed": "indicative",
        "contracts_returned": len(snapshots),
        "quoted_contracts": quoted,
        "tight_quote_contracts": tight,
        "market_data_ready": quoted > 0,
        "status": "research_only",
        "execution_note": "No contract selection, order, or execution authority is created by this probe.",
    }
