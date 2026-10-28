"""Accounts at firms without a usable API (Lucid, MyFundedFutures, FTMO Futures ...), traded through a webhook relay
such as TradersPost, which places the orders in the firm's Tradovate/Rithmic account.

The relay does not report fills or balances back, so this module keeps its own book per account: position, average
price and realized P&L (from the market price when each order is sent, minus commission). The app shows these numbers
as estimates. Market data comes from the shared TopstepX feed (same MNQ contract).

Accounts are listed in ~/.p100-prop/relay.json, e.g.
  [{"firm": "Lucid", "name": "LUCID-50K-FLEX-1", "size_k": 50, "kind": "combine", "start_balance": 50000,
    "ticker": "MNQZ2026", "secret": "p100-relay-lucid-1"}]
"secret" names the macOS Keychain item holding the relay's webhook URL (it contains the relay password, so it is
never written to files). Without a webhook URL the account runs in dry run.
"""
import json
import os
import urllib.request

from topstepx import BUY, LONG, SHORT, TopstepXError

COMMISSION_PER_SIDE = 0.37   # $ per MNQ contract per side (typical prop-firm micro commission)
RELAY_CONFIG = os.path.expanduser("~/.p100-prop/relay.json")


def load_config(path=RELAY_CONFIG):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        cfg = json.load(f)
    return [c for c in cfg if c.get("name") and c.get("firm")]


class RelayAPI:
    """Order side of one relay account plus its local book. Implements the calls the bot makes on an account."""

    def __init__(self, cfg, price_fn, home, webhook_url=None, opener=None, point_value=2.0):
        self.cfg, self.price_fn, self.point_value = cfg, price_fn, point_value
        self.aid = "relay-%s" % cfg["name"]
        self.cid = None  # set by the fleet to the traded contract id
        self.url = webhook_url
        self.open = opener or urllib.request.urlopen
        self.path = os.path.join(home, "book-%s.json" % cfg["name"])
        self.book = {"pos": 0, "avg": None, "realized": 0.0, "tags": []}
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.book.update(json.load(f))

    # ---- what the bot reads ---------------------------------------------------------------------------------
    def account(self):
        return {"id": self.aid, "name": self.cfg["name"], "balance": self.balance(), "canTrade": True,
                "simulated": True, "firm": self.cfg["firm"], "estimated": True}

    def balance(self):
        return float(self.cfg.get("start_balance", self.cfg.get("size_k", 50) * 1000)) + self.book["realized"]

    def positions(self, account_id):
        b = self.book
        if not b["pos"]:
            return []
        return [{"contractId": self.cid, "type": LONG if b["pos"] > 0 else SHORT, "size": abs(b["pos"]),
                 "averagePrice": b["avg"]}]

    # ---- orders ---------------------------------------------------------------------------------------------
    def _send(self, payload):
        if not self.url:
            return "dry"
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with self.open(req, timeout=10) as r:
                r.read()
        except Exception as exc:  # noqa: BLE001
            raise TopstepXError("relay %s: %s" % (self.cfg["firm"], type(exc).__name__))
        return "sent"

    def _fill(self, delta, price):
        b = self.book
        pos, avg = b["pos"], b["avg"]
        new = pos + delta
        b["realized"] -= COMMISSION_PER_SIDE * abs(delta)
        if pos == 0:
            avg = price
        elif (pos > 0) == (delta > 0):                       # adding to the position
            avg = (avg * abs(pos) + price * abs(delta)) / abs(new)
        else:                                                # reducing, closing or reversing
            closing = min(abs(delta), abs(pos)) * (1 if pos > 0 else -1)
            b["realized"] += (price - avg) * closing * self.point_value
            if new == 0:
                avg = None
            elif (new > 0) != (pos > 0):
                avg = price
        b["pos"], b["avg"] = new, avg
        self._save()

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.book, f)

    def market(self, account_id, contract_id, side, size, tag=None):
        if tag and tag in self.book["tags"]:
            raise TopstepXError("duplicate customTag")
        price = self.price_fn()
        action = "buy" if side == BUY else "sell"
        self._send({"ticker": self.cfg.get("ticker", "MNQ1!"), "action": action, "orderType": "market",
                    "quantity": int(size), "extras": {"tag": tag, "ref_price": price}})
        self.book["tags"] = (self.book["tags"] + [tag])[-200:] if tag else self.book["tags"]
        self._fill(size if side == BUY else -size, price)
        return tag or "relay"

    def close(self, account_id, contract_id):
        if not self.book["pos"]:
            return
        price = self.price_fn()
        self._send({"ticker": self.cfg.get("ticker", "MNQ1!"), "action": "exit", "orderType": "market",
                    "extras": {"ref_price": price}})
        self._fill(-self.book["pos"], price)


class RelayMarket:
    """Market wrapper for a relay account: shared bars, but the account list comes from the local book."""

    def __init__(self, market, relay):
        self.market, self.relay = market, relay

    def history_bars(self, start, end):
        return self.market.history_bars(start, end)

    def today_bars(self, start, now):
        return self.market.today_bars(start, now)

    def accounts(self):
        return [self.relay.account()]
