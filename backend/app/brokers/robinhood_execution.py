"""Account-bound Robinhood order transport, intentionally disconnected from workers.

The caller must persist a UUID ref_id before submission and reconcile an
uncertain response through the broker. No automatic retry is performed here.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.brokers.robinhood_adapter import RobinhoodMcpReadOnlyAdapter
from app.brokers.robinhood_mcp import RobinhoodMcpError


def _positive(value: object, name: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RobinhoodMcpError(f"Invalid {name}") from exc
    if not number.is_finite() or number <= 0:
        raise RobinhoodMcpError(f"Invalid {name}")
    return format(number, "f")


def _ref_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise RobinhoodMcpError("A durable UUID order reference is required") from exc


class RobinhoodOrderTransport:
    """Low-level broker mapping; no strategy or live authorization is implied."""

    def __init__(self, adapter: RobinhoodMcpReadOnlyAdapter, *, allow_equity: bool = False,
                 allow_crypto: bool = False):
        if not adapter.designated_account_id:
            raise RobinhoodMcpError("Agentic equity account is unavailable")
        self.adapter = adapter
        self.allow_equity = allow_equity
        self.allow_crypto = allow_crypto

    def equity_arguments(self, *, symbol: str, side: str, quantity: object,
                         order_type: str = "market", limit_price: object | None = None,
                         stop_price: object | None = None) -> dict:
        if not symbol or not symbol.isalnum() or len(symbol) > 8:
            raise RobinhoodMcpError("Invalid equity symbol")
        if side not in {"buy", "sell"} or order_type not in {"market", "limit", "stop_market", "stop_limit"}:
            raise RobinhoodMcpError("Unsupported equity order")
        args = {"account_number": self.adapter.designated_account_id,
                "symbol": symbol.upper(), "side": side, "type": order_type,
                "quantity": _positive(quantity, "quantity"),
                "time_in_force": "gtc" if order_type.startswith("stop_") else "gfd",
                "market_hours": "regular_hours"}
        if order_type in {"limit", "stop_limit"}:
            args["limit_price"] = _positive(limit_price, "limit price")
        elif limit_price is not None:
            raise RobinhoodMcpError("Market order cannot include a limit price")
        if order_type.startswith("stop_"):
            args["stop_price"] = _positive(stop_price, "stop price")
        elif stop_price is not None:
            raise RobinhoodMcpError("Non-stop order cannot include a stop price")
        if order_type != "market" and Decimal(args["quantity"]) % 1:
            raise RobinhoodMcpError("Fractional equity orders require market type")
        return args

    def crypto_arguments(self, *, symbol: str, side: str, quantity: object,
                         order_type: str = "market", limit_price: object | None = None,
                         stop_price: object | None = None) -> dict:
        rhs = self.adapter._crypto_account()
        if not symbol or not symbol.upper().endswith("USD") or not symbol.replace("-", "").isalnum():
            raise RobinhoodMcpError("Invalid crypto pair")
        if side not in {"buy", "sell"} or order_type not in {"market", "limit", "stop_loss", "stop_limit"}:
            raise RobinhoodMcpError("Unsupported crypto order")
        args = {"rhs_account_number": rhs, "symbol": symbol.upper().replace("-", ""),
                "side": side, "type": order_type, "quantity": _positive(quantity, "quantity"),
                "time_in_force": "gtc"}
        if order_type in {"limit", "stop_limit"}:
            args["limit_price"] = _positive(limit_price, "limit price")
        elif limit_price is not None:
            raise RobinhoodMcpError("Market order cannot include a limit price")
        if order_type in {"stop_loss", "stop_limit"}:
            args["stop_price"] = _positive(stop_price, "stop price")
        elif stop_price is not None:
            raise RobinhoodMcpError("Non-stop order cannot include a stop price")
        return args

    def preview_equity(self, **order) -> dict:
        return self.adapter._tool("review_equity_order", self.equity_arguments(**order))

    def preview_crypto(self, **order) -> dict:
        return self.adapter._tool("preview_crypto_order", self.crypto_arguments(**order))

    def submit_equity(self, *, ref_id: str, **order) -> dict:
        if not self.allow_equity:
            raise RobinhoodMcpError("Robinhood equity execution is disabled")
        args = self.equity_arguments(**order)
        args["ref_id"] = _ref_id(ref_id)
        return self.adapter._tool("place_equity_order", args)

    def submit_crypto(self, *, ref_id: str, **order) -> dict:
        if not self.allow_crypto:
            raise RobinhoodMcpError("Robinhood crypto execution is disabled")
        args = self.crypto_arguments(**order)
        args["ref_id"] = _ref_id(ref_id)
        return self.adapter._tool("place_crypto_order", args)

    def cancel_equity(self, order_id: str) -> dict:
        if not self.allow_equity:
            raise RobinhoodMcpError("Robinhood equity execution is disabled")
        self._owned_order("get_equity_orders", "orders", "account_number",
                          self.adapter.designated_account_id, order_id)
        return self.adapter._tool("cancel_equity_order", {
            "account_number": self.adapter.designated_account_id, "order_id": order_id})

    def cancel_crypto(self, order_id: str) -> dict:
        if not self.allow_crypto:
            raise RobinhoodMcpError("Robinhood crypto execution is disabled")
        rhs = self.adapter._crypto_account()
        self._owned_order("get_crypto_orders", "results", "rhs_account_number", rhs, order_id)
        return self.adapter._tool("cancel_crypto_order", {
            "rhs_account_number": rhs, "order_id": order_id})

    def get_equity_order(self, order_id: str) -> dict:
        return self._owned_order("get_equity_orders", "orders", "account_number",
                                 self.adapter.designated_account_id, order_id)

    def get_crypto_order(self, order_id: str) -> dict:
        return self._owned_order("get_crypto_orders", "results", "rhs_account_number",
                                 self.adapter._crypto_account(), order_id)

    def find_order_by_ref(self, asset_class: str, ref_id: str) -> dict | None:
        """Resolve an uncertain submission by the broker idempotency reference."""
        ref = _ref_id(ref_id)
        if asset_class == "equity":
            tool, key, args = "get_equity_orders", "orders", {
                "account_number": self.adapter.designated_account_id}
        elif asset_class == "crypto":
            tool, key, args = "get_crypto_orders", "results", {
                "rhs_account_number": self.adapter._crypto_account()}
        else:
            raise RobinhoodMcpError("Unsupported asset class")
        rows = self.adapter._tool(tool, args).get(key)
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Broker order history is unavailable")
        matches = [row for row in rows if isinstance(row, dict)
                   and str(row.get("ref_id") or row.get("client_order_id") or "") == ref]
        if len(matches) > 1:
            raise RobinhoodMcpError("Duplicate broker reference in order history")
        return matches[0] if matches else None

    def _owned_order(self, tool: str, rows_key: str, account_key: str,
                     account_id: str, order_id: str) -> dict:
        if not order_id:
            raise RobinhoodMcpError("Order identifier is required")
        data = self.adapter._tool(tool, {account_key: account_id, "order_id": order_id})
        rows = data.get(rows_key)
        if not isinstance(rows, list) or len(rows) != 1 or str(rows[0].get("id")) != order_id:
            raise RobinhoodMcpError("Order ownership could not be verified")
        actual = rows[0].get(account_key)
        if actual is not None and str(actual) != account_id:
            raise RobinhoodMcpError("Order belongs to a different account")
        return rows[0]


def load_agentic_order_transport(db, encryption_key: str, cfg) -> RobinhoodOrderTransport:
    """Use only the designated Agentic account and explicit broker-specific gates."""
    from app.brokers.robinhood_adapter import load_agentic_read_only_adapter
    from app.core.config import TradingMode

    adapter, _account = load_agentic_read_only_adapter(db, encryption_key)
    live = cfg.TRADING_MODE == TradingMode.LIVE and bool(cfg.LIVE_TRADING_ENABLED)
    return RobinhoodOrderTransport(
        adapter,
        allow_equity=live and bool(cfg.ROBINHOOD_EQUITY_EXECUTION_ENABLED),
        allow_crypto=live and bool(cfg.ROBINHOOD_CRYPTO_EXECUTION_ENABLED),
    )
