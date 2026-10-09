"""Read-only real-time trade relay: one upstream Alpaca IEX websocket, many dashboard viewers.

Alpaca's free market-data plan allows one stream connection per account and a
limited number of symbols, so the API process holds a single shared upstream
connection and fans trades out to browser Server-Sent-Event listeners. Keys stay
on the server; browsers only ever receive public trade prints.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

STREAM_URL = "wss://stream.data.alpaca.markets/v2/iex"
MAX_SYMBOLS = 30          # free-plan websocket symbol limit
IDLE_CLOSE_SECONDS = 120  # drop the upstream connection when no viewer remains


class MarketStream:
    def __init__(self, credentials: Callable[[], tuple[str, str]], connect=None):
        self._credentials = credentials
        self._connect = connect
        self.symbols: dict[str, float] = {}   # symbol -> last requested (monotonic)
        self.listeners: set[asyncio.Queue] = set()
        self.last: dict[str, dict] = {}
        self.status = "idle"
        self.error: str | None = None
        self._task: asyncio.Task | None = None
        self._ws = None
        self._subscribed: set[str] = set()

    # ---------- viewer side ----------
    def want(self, symbols) -> list[str]:
        now = time.monotonic()
        for s in symbols:
            s = str(s).upper()
            if s and s.replace(".", "").isalpha() and s not in ("BTCUSD", "ETHUSD", "SOLUSD"):
                self.symbols[s] = now
        if len(self.symbols) > MAX_SYMBOLS:
            for s, _ in sorted(self.symbols.items(), key=lambda kv: kv[1])[:len(self.symbols) - MAX_SYMBOLS]:
                del self.symbols[s]
        self.ensure_running()
        return sorted(self.symbols)

    def listen(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.listeners.add(q)
        return q

    def unlisten(self, q: asyncio.Queue) -> None:
        self.listeners.discard(q)

    def ensure_running(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self._run())
        elif self._ws is not None:
            asyncio.get_event_loop().create_task(self._sync_subscriptions())

    # ---------- upstream side ----------
    def handle(self, message: dict) -> dict | None:
        """Normalize one upstream message; returns the event broadcast to viewers."""
        kind = message.get("T")
        if kind == "t":
            event = {"type": "trade", "symbol": message.get("S"), "price": float(message["p"]),
                     "size": float(message.get("s") or 0), "time": message.get("t")}
        elif kind in ("b", "u"):
            event = {"type": "bar", "symbol": message.get("S"), "open": float(message["o"]),
                     "high": float(message["h"]), "low": float(message["l"]),
                     "close": float(message["c"]), "volume": float(message.get("v") or 0),
                     "time": message.get("t")}
        elif kind == "error":
            self.error = f"{message.get('code')}: {message.get('msg')}"
            return None
        else:
            return None
        if event["symbol"]:
            self.last[event["symbol"]] = event
        for q in list(self.listeners):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    async def _sync_subscriptions(self) -> None:
        ws, wanted = self._ws, set(self.symbols)
        if ws is None:
            return
        add, drop = sorted(wanted - self._subscribed), sorted(self._subscribed - wanted)
        try:
            if drop:
                await ws.send(json.dumps({"action": "unsubscribe", "trades": drop, "updatedBars": drop}))
            if add:
                await ws.send(json.dumps({"action": "subscribe", "trades": add, "updatedBars": add}))
            self._subscribed = wanted
        except Exception:
            pass

    async def _run(self) -> None:
        import websockets
        connect = self._connect or websockets.connect
        backoff = 2.0
        idle_since = None
        while True:
            if not self.listeners:
                idle_since = idle_since or time.monotonic()
                if time.monotonic() - idle_since > IDLE_CLOSE_SECONDS:
                    self.status = "idle"
                    return
            else:
                idle_since = None
            try:
                key, secret = self._credentials()
                self.status = "connecting"
                async with connect(STREAM_URL, open_timeout=15, close_timeout=5) as ws:
                    await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                    authed = False
                    for _ in range(4):
                        for message in json.loads(await asyncio.wait_for(ws.recv(), timeout=15)):
                            if message.get("T") == "error":
                                self.handle(message)
                                raise ConnectionError(self.error)
                            if message.get("msg") == "authenticated":
                                authed = True
                        if authed:
                            break
                    if not authed:
                        raise ConnectionError("stream_auth_timeout")
                    self._ws, self._subscribed = ws, set()
                    await self._sync_subscriptions()
                    self.status, self.error, backoff = "live", None, 2.0
                    while True:
                        if not self.listeners:
                            idle_since = idle_since or time.monotonic()
                            if time.monotonic() - idle_since > IDLE_CLOSE_SECONDS:
                                self.status = "idle"
                                return
                        else:
                            idle_since = None
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            continue
                        for message in json.loads(raw):
                            if message.get("T") == "error" and message.get("code") in (402, 406, 409):
                                self.handle(message)
                                raise ConnectionError(self.error)
                            self.handle(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = "reconnecting"
                self.error = self.error or f"{type(exc).__name__}"
                # 406 = another connection already open for this account; wait longer.
                backoff = 60.0 if "406" in str(self.error) else min(backoff * 2, 60.0)
            finally:
                self._ws, self._subscribed = None, set()
            await asyncio.sleep(backoff)
