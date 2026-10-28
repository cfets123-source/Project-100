"""Binance.US spot execution for the crypto worker (market orders only, no withdrawals).

Separate from the read-only BinanceUSReader so the dashboard's connection checks can
never place an order. Every signed request carries a server timestamp; nothing here
logs or returns the key, secret, signature or raw query string.
"""
from __future__ import annotations

import hashlib
import hmac
from decimal import ROUND_DOWN, Decimal
from urllib.parse import urlencode

import httpx

from app.brokers.binance_us import BASE_URL, BinanceError, BinanceUSReader, _decode, amount
from app.models.models import BrokerConnection

BROKER = "binance_us_spot"
PAIRS = {"BTC/USD": "BTCUSD", "ETH/USD": "ETHUSD", "SOL/USD": "SOLUSD"}


def floor_step(qty: float, step: str) -> Decimal:
    s = Decimal(step)
    return (Decimal(str(qty)) / s).to_integral_value(rounding=ROUND_DOWN) * s if s > 0 else Decimal(str(qty))


class BinanceUSTrader:
    """Market buys by USD amount, market sells by quantity, order/balance reads."""

    def __init__(self, api_key: str = "", api_secret: str = "", *, enabled: bool = False, client=None):
        self._key, self._secret, self.enabled = api_key, api_secret, enabled
        self._http = client or httpx.Client(timeout=12, follow_redirects=False)
        self._filters: dict = {}

    # ---------- public market data ----------
    def _public(self, path, params):
        try:
            r = self._http.get(BASE_URL + path, params=params)
            if r.status_code != 200:
                raise BinanceError(f"Binance.US public request failed ({r.status_code})")
            return r.json()
        except (httpx.HTTPError, ValueError):
            raise BinanceError("Binance.US could not be reached") from None

    def book(self, pair: str) -> dict:
        b = self._public("/api/v3/ticker/bookTicker", {"symbol": PAIRS[pair]})
        bid, ask = float(amount(b["bidPrice"])), float(amount(b["askPrice"]))
        if bid <= 0 or ask < bid:
            raise BinanceError("Binance.US returned an invalid book")
        return {"bid": bid, "ask": ask, "last": (bid + ask) / 2}

    def daily_bars(self, pair: str, limit: int = 420) -> list[dict]:
        import datetime as dt
        raw = self._public("/api/v3/klines", {"symbol": PAIRS[pair], "interval": "1d", "limit": limit})
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        rows = [{"timestamp": dt.datetime.fromtimestamp(r[0] / 1000, dt.timezone.utc).date().isoformat(),
                 "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]),
                 "volume": float(r[5])} for r in raw]
        return [r for r in rows if r["timestamp"] < today]  # completed UTC days only

    def filters(self, pair: str) -> dict:
        if pair not in self._filters:
            info = self._public("/api/v3/exchangeInfo", {"symbol": PAIRS[pair]})["symbols"][0]
            f = {x["filterType"]: x for x in info["filters"]}
            minimum = f.get("NOTIONAL", f.get("MIN_NOTIONAL", {})).get("minNotional", "1")
            self._filters[pair] = {"step": f["LOT_SIZE"]["stepSize"], "min_notional": float(minimum),
                                   "base": info["baseAsset"], "trading": info["status"] == "TRADING"}
        return self._filters[pair]

    # ---------- signed account / order calls ----------
    def _signed(self, method: str, path: str, params: dict):
        if path not in {"/api/v3/order", "/api/v3/account"}:
            raise BinanceError("Unsupported Binance.US signed endpoint")
        if method != "GET" and not self.enabled:
            raise BinanceError("Binance.US order submission is disabled")
        if not self._key or not self._secret:
            raise BinanceError("Binance.US credentials are required")
        server = self._public("/api/v3/time", {})
        params = {**params, "timestamp": int(server["serverTime"]), "recvWindow": 5000}
        query = urlencode(params)
        params["signature"] = hmac.new(self._secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        try:
            r = self._http.request(method, BASE_URL + path, params=params, headers={"X-MBX-APIKEY": self._key})
        except httpx.HTTPError:
            raise BinanceError("Binance.US request outcome unknown (network)") from None
        if r.status_code != 200:
            try:
                msg = str(r.json().get("msg", ""))[:160]
            except ValueError:
                msg = ""
            raise BinanceError(f"Binance.US rejected the request ({r.status_code}) {msg}")
        return r.json()

    def balances(self) -> dict:
        data = self._signed("GET", "/api/v3/account", {})
        return {row["asset"]: float(amount(row["free"])) + float(amount(row["locked"]))
                for row in data.get("balances", [])}

    def buy_usd(self, pair: str, usd: float, client_id: str) -> dict:
        return self._signed("POST", "/api/v3/order", {"symbol": PAIRS[pair], "side": "BUY", "type": "MARKET",
                                                      "quoteOrderQty": f"{usd:.2f}", "newClientOrderId": client_id})

    def sell_qty(self, pair: str, qty: float, client_id: str) -> dict:
        q = floor_step(qty, self.filters(pair)["step"])
        if q <= 0:
            raise BinanceError("Quantity below the Binance.US lot size")
        return self._signed("POST", "/api/v3/order", {"symbol": PAIRS[pair], "side": "SELL", "type": "MARKET",
                                                      "quantity": format(q.normalize(), "f"),
                                                      "newClientOrderId": client_id})

    def order(self, pair: str, client_id: str) -> dict:
        return self._signed("GET", "/api/v3/order", {"symbol": PAIRS[pair], "origClientOrderId": client_id})


def load_trader(db, encryption_key: str, *, enabled: bool) -> BinanceUSTrader:
    row = db.get(BrokerConnection, BROKER)
    if not row or row.status != "authorized":
        raise BinanceError("Connect your Binance.US API key first")
    stored = _decode(row, encryption_key)
    if BinanceUSReader(stored["api_key"], stored["api_secret"]).account()["uid"] != stored["uid"]:
        raise BinanceError("Binance.US account identity changed")
    return BinanceUSTrader(stored["api_key"], stored["api_secret"], enabled=enabled)
