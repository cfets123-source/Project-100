from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Quote:
    provider: str
    symbol: str
    timestamp: float       # unix epoch seconds
    age_seconds: float
    bid: float
    ask: float
    last: float
    market_status: str     # open|closed|premarket|afterhours


@dataclass
class OrderRequest:
    symbol: str
    side: str               # buy|sell
    quantity: float
    order_type: str = "market"   # market|limit
    limit_price: Optional[float] = None
    time_in_force: str = "day"


@dataclass
class OrderResult:
    order_id: str
    status: str              # accepted|rejected|filled|partial|canceled
    filled_qty: float = 0.0
    fill_price: Optional[float] = None
    raw: Optional[dict] = None


class BrokerAdapter(ABC):
    """All broker integrations must implement this interface. The LLM never calls these
    methods directly; only the OrderValidator (post Risk Engine approval) may call placeOrder."""

    @abstractmethod
    def authenticate(self) -> bool: ...

    @abstractmethod
    def get_accounts(self) -> list[dict]: ...

    @abstractmethod
    def get_balances(self) -> dict: ...

    @abstractmethod
    def get_buying_power(self) -> float: ...

    @abstractmethod
    def get_positions(self) -> list[dict]: ...

    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> list[Quote]: ...

    @abstractmethod
    def get_orders(self) -> list[dict]: ...

    @abstractmethod
    def preview_order(self, order: OrderRequest) -> dict: ...

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict: ...
