"""Alpaca-backed market data with explicit freshness and account snapshots.

This provider only reads Alpaca data. It cannot submit, cancel, or preview orders.
It is usable for paper and live *readiness* checks; execution remains gated elsewhere.
"""
from __future__ import annotations

import time
from typing import Protocol

from app.market_data.base import MarketDataProvider, MarketQuote


class QuoteReader(Protocol):
    def get_quotes(self, symbols: list[str]): ...
    def get_balances(self) -> dict: ...
    def get_positions(self) -> list[dict]: ...


class AlpacaMarketDataProvider(MarketDataProvider):
    """Read market quotes and retain a verified account snapshot timestamp."""

    def __init__(self, adapter: QuoteReader, *, entitlement: str = "unknown"):
        self._adapter = adapter
        self._entitlement = entitlement
        self._account_snapshot_at: float | None = None
        self.account_snapshot: dict | None = None

    def refresh_account_snapshot(self) -> dict:
        """Fetch balances and positions together before a decision cycle."""
        receipt = time.time()
        balances = self._adapter.get_balances()
        positions = self._adapter.get_positions()
        if not isinstance(balances, dict) or not isinstance(positions, list):
            raise ValueError("Alpaca returned malformed account snapshot")
        self.account_snapshot = {"balances": balances, "positions": positions,
                                 "receipt_timestamp": receipt}
        self._account_snapshot_at = receipt
        return self.account_snapshot

    def get_quote(self, symbol: str) -> MarketQuote | None:
        receipt = time.time()
        rows = self._adapter.get_quotes([symbol])
        if not isinstance(rows, list):
            raise ValueError("Alpaca returned malformed quote collection")
        matches = [quote for quote in rows if quote.symbol.upper() == symbol.upper()]
        if len(matches) != 1:
            return None
        quote = matches[0]
        return MarketQuote(source="alpaca", symbol=quote.symbol, asset_class="equity",
                           market_session=quote.market_status, source_timestamp=quote.timestamp,
                           receipt_timestamp=receipt, bid=quote.bid, ask=quote.ask, last=quote.last,
                           entitlement=self._entitlement)

    def get_account_snapshot_age_seconds(self) -> float:
        if self._account_snapshot_at is None:
            return float("inf")
        return max(0.0, time.time() - self._account_snapshot_at)
