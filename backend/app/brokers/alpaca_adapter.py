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
        # Only idempotent GETs are retried, honoring broker reset guidance.
        for attempt in range(3):
            response = self.client.request(method, url, headers=self.headers, params=params, json=json)
            if method.upper() != "GET":
                break
            status = getattr(response, "status_code", None)
            headers = getattr(response, "headers", {}) or {}
            remaining = headers.get("X-RateLimit-Remaining")
            if status != 429 and remaining != "0":
                break
            if attempt == 2:
                break
            try:
                reset_delay = float(headers.get("X-RateLimit-Reset", "0")) - time.time()
            except (TypeError, ValueError):
                reset_delay = 0.0
            # Never busy-loop. The cap keeps a worker responsive; a remaining
            # 429 is recorded by its caller and retried on the next cycle.
            time.sleep(min(30.0, max(1.0 * (attempt + 1), reset_delay + 0.1)))
        try:
            response.raise_for_status()
            # Alpaca returns an empty successful response for DELETE /v2/orders.
            # Treat that as success rather than turning a completed cancellation
            # into an ambiguous broker outcome.
            if method.upper() == "DELETE":
                return {}
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Broker response details are essential for a safety halt.  Keep
            # them bounded and do not include request headers or credentials.
            status = getattr(response, "status_code", "unknown")
            detail = ""
            try:
                detail = str(response.text).strip().replace("\n", " ")[:500]
            except Exception:
                pass
            suffix = f": {detail}" if detail else ""
            raise AlpacaBrokerError(f"Alpaca {method} {path} failed ({status}){suffix}") from exc

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

    def get_account_capabilities(self) -> dict:
        """Read broker permission fields used by Veloikos capability gates."""
        account = self._request("GET", "/v2/account")
        return {
            "status": account.get("status"),
            "trading_blocked": bool(account.get("trading_blocked")),
            "trade_suspended_by_user": bool(account.get("trade_suspended_by_user")),
            "account_blocked": bool(account.get("account_blocked")),
            "crypto_status": account.get("crypto_status"),
            "options_approved_level": account.get("options_approved_level"),
            "options_trading_level": account.get("options_trading_level"),
        }

    def list_active_assets(self, *, asset_class: str = "us_equity") -> list[dict]:
        """Read Alpaca's instrument catalog; this endpoint cannot trade.

        Catalog availability is deliberately kept separate from the execution
        universe.  A symbol becoming discoverable must never make it eligible
        for an order without the strategy and paper-evidence gates.
        """
        raw = self._request("GET", "/v2/assets", params={
            "status": "active", "asset_class": asset_class,
        })
        return [{
            "id": item.get("id"), "symbol": item.get("symbol"),
            "name": item.get("name"), "asset_class": item.get("asset_class"),
            "exchange": item.get("exchange"), "tradable": bool(item.get("tradable")),
            "fractionable": bool(item.get("fractionable")),
            "shortable": bool(item.get("shortable")),
        } for item in raw if item.get("tradable") and item.get("symbol")]

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
        params = {
            "symbols": symbol, "timeframe": "1Day", "start": start, "end": end,
            "adjustment": "all", "feed": "iex", "limit": 10000,
        }
        bars = [item for page in self._stock_bar_pages("/v2/stocks/bars", params)
                for item in page.get("bars", {}).get(symbol, [])]
        return [{"timestamp": item["t"], "open": float(item["o"]), "high": float(item["h"]),
                "low": float(item["l"]), "close": float(item["c"]), "volume": float(item["v"])}
                for item in bars]

    def get_intraday_bars(self, symbol: str, start: str, end: str, *, timeframe: str = "5Min") -> list[dict]:
        """Read-only intraday research bars; never used to submit an order."""
        params = {
            "timeframe": timeframe, "start": start, "end": end, "adjustment": "all", "feed": "iex", "limit": 10000,
        }
        bars = [item for page in self._stock_bar_pages(f"/v2/stocks/{symbol.upper()}/bars", params)
                for item in page.get("bars", [])]
        return [{"timestamp": item["t"], "open": float(item["o"]), "high": float(item["h"]),
                 "low": float(item["l"]), "close": float(item["c"]), "volume": float(item["v"])}
                for item in bars]

    def _stock_bar_pages(self, path: str, params: dict):
        """Consume every page; Alpaca may return fewer rows than `limit`."""
        token = None
        seen = set()
        for _ in range(100):
            query = {**params, **({"page_token": token} if token else {})}
            raw = self._request("GET", path, data_api=True, params=query)
            yield raw
            token = raw.get("next_page_token")
            if not token:
                return
            if token in seen:
                raise AlpacaBrokerError("Alpaca returned a repeated stock-bars page token")
            seen.add(token)
        raise AlpacaBrokerError("Alpaca stock-bars pagination exceeded safety bound")

    def get_daily_bars_many(self, symbols: list[str], start: str, end: str,
                            *, adjustment: str = "all") -> dict[str, list[dict]]:
        """Fetch daily bars for a bounded research batch in one data request.

        This is intentionally research-only.  Batching avoids treating a broad
        universe scan as hundreds of individual API requests, which could starve
        order reconciliation or trigger avoidable broker throttling.
        """
        clean = list(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
        if not clean:
            return {}
        if adjustment not in {"all", "raw"}:
            raise ValueError("daily-bar adjustment must be 'all' or 'raw'")
        params = {
            "symbols": ",".join(clean), "timeframe": "1Day", "start": start, "end": end,
            "adjustment": adjustment, "feed": "iex", "limit": 10000,
        }
        bars = {symbol: [] for symbol in clean}
        for page in self._stock_bar_pages("/v2/stocks/bars", params):
            for symbol, rows in page.get("bars", {}).items():
                if symbol in bars:
                    bars[symbol].extend(rows)
        return {symbol: [{"timestamp": item["t"], "open": float(item["o"]),
                         "high": float(item["h"]), "low": float(item["l"]),
                         "close": float(item["c"]), "volume": float(item["v"])}
                         for item in bars[symbol]]
                for symbol in clean}

    def get_option_chain(self, underlying_symbol: str, *, limit: int = 100,
                         feed: str = "indicative") -> dict:
        """Read an option chain with an explicitly selected Alpaca data feed.

        This method never accesses the orders API.  ``indicative`` makes the
        data entitlement explicit; execution cannot treat this probe as an
        OPRA-grade live signal.
        """
        if not underlying_symbol.isalpha() or len(underlying_symbol) > 10:
            raise AlpacaBrokerError("invalid option-chain underlying")
        if feed not in {"indicative", "opra"}:
            raise AlpacaBrokerError("invalid option-chain feed")
        return self._request("GET", f"/v1beta1/options/snapshots/{underlying_symbol.upper()}",
                             data_api=True, params={"feed": feed, "limit": min(max(limit, 1), 1000)})

    def get_market_clock(self) -> dict:
        """Read Alpaca's market clock; this is a read-only endpoint."""
        return self._request("GET", "/v2/clock")

    def get_orders(self) -> list[dict]:
        # ``nested=true`` exposes bracket/OCO child legs.  Protection and
        # reconciliation must see those broker-managed stops rather than
        # mistaking a bracket position for an uncovered one.
        return self._request("GET", "/v2/orders", params={"status": "all", "limit": 500, "nested": "true"})

    def preview_order(self, order: OrderRequest) -> dict:
        # Alpaca has no separate preview endpoint. The risk engine is the preview.
        return {"previewed": True, "broker": "alpaca", "symbol": order.symbol,
                "side": order.side, "quantity": order.quantity, "order_type": order.order_type,
                "submission_enabled": self.allow_order_submission}

    def place_order(self, order: OrderRequest) -> OrderResult:
        if not self.allow_order_submission:
            raise AlpacaBrokerError("Alpaca order submission is disabled until final live activation")
        # Alpaca explicitly rejects fractional advanced orders (including
        # brackets): they must be simple DAY orders.  Fail locally before any
        # request so a strategy cannot spend broker rate budget on a known 422.
        if order.order_class is not None and not float(order.quantity).is_integer():
            raise AlpacaBrokerError("Alpaca fractional orders must be simple orders")
        payload = {"symbol": order.symbol, "side": order.side, "qty": str(order.quantity),
                   "type": order.order_type, "time_in_force": order.time_in_force}
        if order.limit_price is not None:
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price is not None:
            payload["stop_price"] = str(order.stop_price)
        if order.order_class is not None:
            payload["order_class"] = order.order_class
        if order.take_profit_price is not None:
            payload["take_profit"] = {"limit_price": str(order.take_profit_price)}
        if order.stop_loss_price is not None:
            payload["stop_loss"] = {"stop_price": str(order.stop_loss_price)}
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
