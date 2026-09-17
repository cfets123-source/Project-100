"""
Deterministic, fault-injectable market data source for PAPER/SHADOW and tests.
NOT a real market data vendor integration — clearly labeled as simulated.
"""
import time
from app.market_data.base import MarketDataProvider, MarketQuote


class SimulatedMarketDataProvider(MarketDataProvider):
    def __init__(self, prices: dict[str, float], account_snapshot_age: float = 0.5):
        self.prices = dict(prices)
        self._account_snapshot_age = account_snapshot_age
        self._fault: str | None = None  # 'stale' | 'future' | 'missing' | 'malformed' | None

    def set_price(self, symbol: str, price: float):
        self.prices[symbol] = price

    def inject_fault(self, fault: str | None):
        self._fault = fault

    def get_quote(self, symbol: str) -> MarketQuote:
        now = time.time()
        if self._fault == "missing" or symbol not in self.prices:
            return None
        px = self.prices[symbol]

        source_ts = now
        bid, ask, last = px - 0.02, px + 0.02, px

        if self._fault == "stale":
            source_ts = now - 3600
        elif self._fault == "future":
            source_ts = now + 3600
        elif self._fault == "malformed":
            bid, ask = ask, bid  # inverted

        return MarketQuote(source="simulated", symbol=symbol, asset_class="equity",
                            market_session="open", source_timestamp=source_ts, receipt_timestamp=now,
                            bid=bid, ask=ask, last=last, entitlement="simulated")

    def get_account_snapshot_age_seconds(self) -> float:
        return self._account_snapshot_age
