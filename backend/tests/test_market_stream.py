"""Real-time relay: trade normalization, viewer fan-out, symbol cap, connection reuse."""
import asyncio
import json

from app.services.market_stream import MAX_SYMBOLS, MarketStream


class FakeWS:
    def __init__(self, inbound):
        self.sent, self.inbound = [], list(inbound)

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        if self.inbound:
            return json.dumps(self.inbound.pop(0))
        await asyncio.sleep(3600)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def test_trade_fans_out_and_keeps_last_price():
    async def go():
        s = MarketStream(lambda: ("k", "s"))
        s.ensure_running = lambda: None
        q = s.listen()
        s.handle({"T": "t", "S": "EWT", "p": 116.4, "s": 10, "t": "2026-10-07T15:00:00Z"})
        s.handle({"T": "success", "msg": "connected"})
        assert (await q.get())["price"] == 116.4 and q.empty()
        assert s.last["EWT"]["type"] == "trade"
    asyncio.run(go())


def test_symbol_cap_drops_oldest_and_rejects_bad_symbols():
    s = MarketStream(lambda: ("k", "s"))
    s.ensure_running = lambda: None
    s.want(["bad sym!", "x1"])
    for i in range(MAX_SYMBOLS + 5):
        s.want(["S" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i % 26] * (1 + i // 26)])
    assert len(s.symbols) == MAX_SYMBOLS and "BAD SYM!" not in s.symbols


def test_upstream_auth_then_subscribe_and_relay():
    ws = FakeWS([[{"T": "success", "msg": "connected"}], [{"T": "success", "msg": "authenticated"}],
                 [{"T": "subscription", "trades": ["EWT"]}], [{"T": "t", "S": "EWT", "p": 117.0, "s": 5, "t": "x"}]])

    async def go():
        s = MarketStream(lambda: ("key", "secret"), connect=lambda *a, **k: ws)
        q = s.listen()
        s.want(["EWT"])
        ev = await asyncio.wait_for(q.get(), timeout=2)
        s._task.cancel()
        return s, ev
    s, ev = asyncio.run(go())
    assert ws.sent[0] == {"action": "auth", "key": "key", "secret": "secret"}
    assert ws.sent[1]["action"] == "subscribe" and ws.sent[1]["trades"] == ["EWT"]
    assert ev["symbol"] == "EWT" and ev["price"] == 117.0 and s.status == "live"
