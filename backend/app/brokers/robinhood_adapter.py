"""Robinhood Trading MCP broker adapter.

Read-only by design.  It is used to prove account identity, balances, open
positions, orders, and quote freshness before any future execution adapter can
be considered.  Order mutation methods deliberately fail closed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.brokers.base import BrokerAdapter, OrderRequest, OrderResult, Quote
from app.brokers.robinhood_mcp import RobinhoodMcpDiscoveryClient, RobinhoodMcpError


class RobinhoodMcpReadOnlyAdapter(BrokerAdapter):
    """Maps only documented read tools from the authenticated Trading MCP."""

    def __init__(self, access_token: str, designated_account_id: str):
        self._client = RobinhoodMcpDiscoveryClient(access_token)
        self.designated_account_id = designated_account_id
        self._authenticated = False

    def _tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self._client._initialize()
        payload = self._client._request("tools/call", {"name": name, "arguments": arguments or {}})
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("isError"):
            raise RobinhoodMcpError("Robinhood rejected the read-only broker request")
        content = result.get("content")
        if not isinstance(content, list):
            raise RobinhoodMcpError("Robinhood returned malformed broker data")
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                import json
                try:
                    decoded = json.loads(item["text"])
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    return decoded.get("data", decoded)
        raise RobinhoodMcpError("Robinhood returned unreadable broker data")

    def authenticate(self) -> bool:
        accounts = self._tool("get_accounts")
        rows = accounts.get("accounts")
        self._authenticated = isinstance(rows, list)
        return self._authenticated

    def get_accounts(self) -> list[dict]:
        rows = self._tool("get_accounts").get("accounts")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed accounts")
        return [{**row, "account_id": str(row.get("account_number", ""))} for row in rows if isinstance(row, dict)]

    def _portfolio(self) -> dict:
        result = self._tool("get_portfolio", {"account_number": self.designated_account_id})
        if not isinstance(result, dict):
            raise RobinhoodMcpError("Robinhood returned malformed portfolio")
        return result

    def get_balances(self) -> dict:
        p = self._portfolio()
        try:
            return {"cash": float(p["cash"]), "equity": float(p["total_value"])}
        except (KeyError, TypeError, ValueError) as exc:
            raise RobinhoodMcpError("Robinhood returned invalid balances") from exc

    def get_buying_power(self) -> float:
        try:
            return float(self._portfolio()["buying_power"]["buying_power"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RobinhoodMcpError("Robinhood returned invalid buying power") from exc

    def get_positions(self) -> list[dict]:
        rows = self._tool("get_equity_positions", {"account_number": self.designated_account_id}).get("positions")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed positions")
        return [row for row in rows if isinstance(row, dict)]

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        rows = self._tool("get_equity_quotes", {"symbols": symbols}).get("results")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed quotes")
        quotes: list[Quote] = []
        for row in rows:
            raw = row.get("quote") if isinstance(row, dict) else None
            if not isinstance(raw, dict):
                continue
            try:
                ts = datetime.fromisoformat(raw["venue_last_trade_time"].replace("Z", "+00:00")).timestamp()
                bid, ask, last = float(raw["bid_price"]), float(raw["ask_price"]), float(raw["last_trade_price"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RobinhoodMcpError("Robinhood returned invalid quote data") from exc
            if bid <= 0 or ask <= 0:
                raise RobinhoodMcpError("Robinhood quote has no active bid or ask")
            quotes.append(Quote(provider="robinhood_mcp", symbol=str(raw.get("symbol", "")), timestamp=ts,
                                age_seconds=max(0, datetime.now(timezone.utc).timestamp() - ts), bid=bid, ask=ask,
                                last=last, market_status="open"))
        return quotes

    def get_orders(self) -> list[dict]:
        rows = self._tool("get_equity_orders", {"account_number": self.designated_account_id}).get("orders")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed orders")
        return [row for row in rows if isinstance(row, dict)]

    def get_equity_tradability(self, symbols: list[str]) -> list[dict]:
        if not symbols or len(symbols) > 10:
            raise RobinhoodMcpError("Tradability check requires 1 to 10 symbols")
        rows = self._tool("get_equity_tradability", {
            "account_number": self.designated_account_id, "symbols": symbols,
        }).get("results")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed equity tradability")
        return [row for row in rows if isinstance(row, dict)]

    def get_crypto_positions(self) -> list[dict]:
        rows = self._tool("get_crypto_positions", {
            "rhs_account_number": self.designated_account_id,
        }).get("results")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed crypto positions")
        return [row for row in rows if isinstance(row, dict)]

    def get_crypto_orders(self) -> list[dict]:
        rows = self._tool("get_crypto_orders", {
            "rhs_account_number": self.designated_account_id, "state_group": "open",
        }).get("results")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed crypto orders")
        return [row for row in rows if isinstance(row, dict)]

    def get_crypto_quotes(self, symbols: list[str], *, max_age_seconds: float = 5) -> list[dict]:
        """Return broker-routed crypto quotes with an explicit execution-quality flag."""
        if not symbols:
            raise RobinhoodMcpError("Crypto quote symbols are required")
        rows = self._tool("get_crypto_quotes", {
            "rhs_account_number": self.designated_account_id,
            "symbols": symbols, "timezone": "America/New_York",
        }).get("results")
        if not isinstance(rows, list):
            raise RobinhoodMcpError("Robinhood returned malformed crypto quotes")
        requested = {symbol.upper().replace("-", "") for symbol in symbols}
        quotes = []
        for row in rows:
            if not isinstance(row, dict) or str(row.get("symbol", "")).upper() not in requested:
                raise RobinhoodMcpError("Robinhood returned an unexpected crypto symbol")
            try:
                bid, ask, mark = (float(row[key]) for key in ("bid_price", "ask_price", "mark_price"))
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))).total_seconds()
            except (KeyError, TypeError, ValueError) as exc:
                raise RobinhoodMcpError("Robinhood returned invalid crypto quote data") from exc
            spread = (ask - bid) / ((ask + bid) / 2) if bid > 0 and ask > 0 else None
            if bid <= 0 or ask <= 0 or mark <= 0:
                quality_reason = "missing_price"
            elif ask < bid:
                quality_reason = "crossed_market"
            elif age < 0 or age > max_age_seconds:
                quality_reason = "stale_quote"
            elif spread is None or spread > 0.01:
                quality_reason = "wide_spread"
            else:
                quality_reason = "current"
            quotes.append({"symbol": row["symbol"], "bid": bid, "ask": ask, "mark": mark,
                           "age_seconds": max(0, age), "spread_pct": spread,
                           "routing": row.get("routing"), "as_of": row["updated_at"],
                           "valid_for_execution": quality_reason == "current",
                           "quality_reason": quality_reason})
        if len(quotes) != len(symbols):
            raise RobinhoodMcpError("Robinhood omitted a requested crypto quote")
        return quotes

    def preview_order(self, order: OrderRequest) -> dict:
        raise RobinhoodMcpError("Order preview is disabled until live readiness is verified")

    def place_order(self, order: OrderRequest) -> OrderResult:
        raise RobinhoodMcpError("Live order submission is disabled until explicit final activation")

    def cancel_order(self, order_id: str) -> bool:
        raise RobinhoodMcpError("Order cancellation is disabled in the read-only adapter")

    def get_order_status(self, order_id: str) -> dict:
        matches = [o for o in self.get_orders() if str(o.get("id")) == order_id]
        if len(matches) != 1:
            raise RobinhoodMcpError("Robinhood order was not found exactly once")
        return matches[0]


def load_agentic_read_only_adapter(db, encryption_key: str) -> tuple[RobinhoodMcpReadOnlyAdapter, dict]:
    """Bind to exactly one active Agentic account; never fall back to a personal account."""
    from app.brokers.robinhood_mcp import _access_token

    adapter = RobinhoodMcpReadOnlyAdapter(_access_token(db, encryption_key), designated_account_id="")
    accounts = adapter.get_accounts()
    matches = [a for a in accounts if a.get("agentic_allowed") is True and a.get("state") == "active"
               and not a.get("deactivated") and not a.get("permanently_deactivated")]
    if len(matches) != 1:
        raise RobinhoodMcpError("Expected exactly one active Agentic account")
    adapter.designated_account_id = str(matches[0]["account_id"])
    return adapter, matches[0]


def verify_agentic_readiness(db, encryption_key: str) -> dict:
    """Run the complete read-only broker gate for the one Agentic account.

    No account identifier is accepted from a caller: the adapter selects exactly
    one active account explicitly marked as usable by the authenticated agent.
    """
    from app.services.broker_readiness import verify_read_only_connection

    try:
        adapter, account = load_agentic_read_only_adapter(db, encryption_key)
    except RobinhoodMcpError:
        return {"connected": False, "read_only_ready": False, "execution_enabled": False,
                "reasons": ["expected exactly one active Agentic account"]}
    return verify_read_only_connection(adapter, str(account["account_id"]))
