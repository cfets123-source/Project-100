"""
MarketDataProvider abstraction. Every quote used for a trading decision carries
explicit provenance and freshness fields so staleness/malformation can be
rejected BEFORE it reaches the Risk Engine, not inferred after the fact.
"""
import time
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MarketQuote:
    source: str
    symbol: str
    asset_class: str
    market_session: str          # open|closed|premarket|afterhours
    source_timestamp: float      # when the source says the data was generated
    receipt_timestamp: float     # when WE received it (time.time() at fetch)
    bid: float | None
    ask: float | None
    last: float | None
    entitlement: str = "unknown"  # e.g. real_time|delayed_15m|unknown
    delay_seconds: float = 0.0

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.source_timestamp)


@dataclass
class QuoteValidation:
    valid: bool
    reason: str = ""


def validate_quote(q: MarketQuote, max_age_seconds: float, now: float | None = None) -> QuoteValidation:
    now = now if now is not None else time.time()

    if q is None:
        return QuoteValidation(False, "missing_quote")
    if q.bid is None or q.ask is None or q.last is None:
        return QuoteValidation(False, "malformed_missing_fields")
    values = (q.bid, q.ask, q.last, q.source_timestamp, q.receipt_timestamp,
              q.delay_seconds, now, max_age_seconds)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return QuoteValidation(False, "malformed_nonfinite_value")
    if max_age_seconds < 0 or q.delay_seconds < 0:
        return QuoteValidation(False, "invalid_freshness_parameters")
    if q.bid <= 0 or q.ask <= 0 or q.last <= 0:
        return QuoteValidation(False, "malformed_nonpositive_price")
    if q.bid > q.ask:
        return QuoteValidation(False, "malformed_inverted_bid_ask")
    if q.source_timestamp > now + 1.0 or q.receipt_timestamp > now + 1.0:
        return QuoteValidation(False, "future_dated_quote")
    if q.receipt_timestamp < q.source_timestamp:
        return QuoteValidation(False, "out_of_order_timestamps")
    if now - q.source_timestamp > max_age_seconds or now - q.receipt_timestamp > max_age_seconds:
        return QuoteValidation(False, "stale_quote")
    return QuoteValidation(True)


class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, symbol: str) -> MarketQuote: ...

    @abstractmethod
    def get_account_snapshot_age_seconds(self) -> float:
        """Age of the last known account balance/positions snapshot — stale
        ACCOUNT state must block entries just as stale PRICE data does."""
