"""Alpaca Trading API adapter.

This adapter is deliberately inert by default: it can verify an account and
read broker state, but will not submit an order until the caller explicitly
constructs it with ``allow_order_submission=True``.  That flag is separate from
Project 100's system-wide LIVE_TRADING_ENABLED gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import time

import httpx

from app.brokers.base import BrokerAdapter, OrderRequest, OrderResult, Quote


class AlpacaBrokerError(RuntimeError):
    pass


class AlpacaBrokerAdapter(BrokerAdapter):
    """Small, auditable REST adapter for Alpaca paper or live Trading API."""

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    LIVE_BASE_URL = "https://api.alpaca.markets"
    DATA_BASE_URL = "https://data.alpaca.markets"

    def __init__(self, api_key: str, api_secret: str, *, paper: bool = True,
                 allow_order_submission: bool = False, client: httpx.Client | None = None):
        if not api_key or not api_secret:
            raise AlpacaBrokerError("Alpaca API key and secret are required")
        self.paper = paper
        self.allow_order_submission = allow_order_submission
        self.base_url = self.PAPER_BASE_URL if paper else self.LIVE_BASE_URL
        self.client = client or httpx.Client(timeout=15)
        self.headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}

    def _request(self, method: str, path: str, *, data_api: bool = False,
                 params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> Any:
        url = (self.DATA_BASE_URL if data_api else self.base_url) + path
        response = None
        # A transient read throttling response must not turn into an order retry.
        # Only idempotent GETs are retried, with a bounded delay.
        for attempt in range(3):
            response = self.client.request(method, url, headers=self.headers, params=params, json=json)
            if method.upper() != "GET" or getattr(response, "status_code", None) != 429:
                break
            time.sleep(1.0 * (attempt + 1))
        try:
            response.raise_for_status()
            # Alpaca returns an empty successful response for DELETE /v2/orders.
            # Treat that as success rather than turning a completed cancellation
            # into an ambiguous broker outcome.
            if method.upper() == "DELETE":
                return {}
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AlpacaBrokerError(f"Alpaca {method} {path} failed") from exc

    def authenticate(self) -> bool:
        account = self._request("GET", "/v2/account")
        return account.get("status") == "ACTIVE"

    def get_accounts(self) -> list[dict]:
        account = self._request("GET", "/v2/account")
        return [{"account_id": account.get("id"), "status": account.get("status"),
                 "currency": account.get("currency"), "paper": self.paper}]

    def get_balances(self) -> dict:
        account = self._request("GET", "/v2/account")
        return {"equity": float(account.get("equity", 0)), "cash": float(account.get("cash", 0)),
                "buying_power": float(account.get("buying_power", 0))}

    def get_buying_power(self) -> float:
        return self.get_balances()["buying_power"]

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/v2/positions")

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        if not symbols:
            return []
        raw = self._request("GET", "/v2/stocks/quotes/latest", data_api=True,
                            params={"symbols": ",".join(symbols)})
        result = []
        for symbol, item in raw.get("quotes", {}).items():
            try:
                timestamp = datetime.fromisoformat(item["t"].replace("Z", "+00:00")).timestamp()
                bid, ask = float(item["bp"]), float(item["ap"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AlpacaBrokerError("Alpaca returned an invalid quote") from exc
            result.append(Quote(provider="alpaca", symbol=symbol, timestamp=timestamp,
                                age_seconds=max(0, datetime.now(timezone.utc).timestamp() - timestamp),
                                bid=bid, ask=ask, last=(bid + ask) / 2, market_status="unknown"))
        return result

    def get_daily_bars(self, symbol: str, start: str, end: str) -> list[dict]:
        """Read adjusted daily bars for research. This endpoint cannot trade."""
        raw = self._request("GET", "/v2/stocks/bars", data_api=True, params={
            "symbols": symbol, "timeframe": "1Day", "start": start, "end": end,
            "adjustment": "all", "feed": "iex", "limit": 10000,
        })
        bars = raw.get("bars", {}).get(symbol, [])
        return [{"timestamp": item["t"], "open": float(item["o"]), "high": float(item["h"]),
                 "low": float(item["l"]), "close": float(item["c"]), "volume": float(item["v"])}
                for item in bars]

    def get_market_clock(self) -> dict:
        """Read Alpaca's market clock; this is a read-only endpoint."""
        return self._request("GET", "/v2/clock")

    def get_orders(self) -> list[dict]:
        return self._request("GET", "/v2/orders", params={"status": "all", "limit": 500})

    def preview_order(self, order: OrderRequest) -> dict:
        # Alpaca has no separate preview endpoint. The risk engine is the preview.
        return {"previewed": True, "broker": "alpaca", "symbol": order.symbol,
                "side": order.side, "quantity": order.quantity, "order_type": order.order_type,
                "submission_enabled": self.allow_order_submission}

    def place_order(self, order: OrderRequest) -> OrderResult:
        if not self.allow_order_submission:
            raise AlpacaBrokerError("Alpaca order submission is disabled until final live activation")
        payload = {"symbol": order.symbol, "side": order.side, "qty": str(order.quantity),
                   "type": order.order_type, "time_in_force": order.time_in_force}
        if order.limit_price is not None:
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price is not None:
            payload["stop_price"] = str(order.stop_price)
        raw = self._request("POST", "/v2/orders", json=payload)
        return OrderResult(order_id=str(raw["id"]), status=str(raw.get("status", "accepted")),
                           filled_qty=float(raw.get("filled_qty") or 0),
                           fill_price=float(raw["filled_avg_price"]) if raw.get("filled_avg_price") else None,
                           raw=raw)

    def cancel_order(self, order_id: str) -> bool:
        if not self.allow_order_submission:
            raise AlpacaBrokerError("Alpaca cancellation is disabled until final live activation")
        self._request("DELETE", f"/v2/orders/{order_id}")
        return True

    def get_order_status(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/orders/{order_id}")
