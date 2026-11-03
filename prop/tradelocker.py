"""TradeLocker client (Eightcap Challenges and other TradeLocker prop firms) with the order/position interface the bot
uses for TopstepX. Standard library only (macOS system Python 3.9+).

Signals still come from the TopstepX MNQ feed (same Nasdaq-100 index); this module only places and reads orders on the
TradeLocker account and supplies its own CFD price for P&L, take-profit and sizing.
Endpoints: https://public-api.tradelocker.com (JWT from email/password/server; accNum header on /trade calls).
The password is read from the macOS Keychain by the caller and is never written to files.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from topstepx import BUY, LIMIT, LONG, SELL, SHORT, TopstepXError

BASES = {"live": "https://live.tradelocker.com/backend-api", "demo": "https://demo.tradelocker.com/backend-api"}
NASDAQ_NAMES = ("US100", "NAS100", "USTEC", "NDX100", "US100.i", "NAS100.i", "USTECH", "NQ100")


class TradeLocker:
    def __init__(self, email, password, server, env="live", opener=None, clock=time.time):
        self.email, self._pw, self.server, self.base = email, password, server, BASES[env]
        self._open, self._clock = opener or urllib.request.urlopen, clock
        self.token, self.refresh, self.token_at = None, None, 0.0
        self.acc_num, self.account_id = None, None
        self._cfg, self._instr = None, None

    # --- transport -------------------------------------------------------------------------------------------
    def _raw(self, method, path, params=None, body=None, auth=True, acc=True):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method=method.upper(),
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "accept": "application/json"})
        if auth:
            req.add_header("Authorization", "Bearer " + self._ensure_token())
        if acc and self.acc_num is not None:
            req.add_header("accNum", str(self.acc_num))
        with self._open(req, timeout=20) as r:
            text = r.read().decode()
        return json.loads(text) if text else {}

    def _req(self, method, path, params=None, body=None, auth=True, acc=True, retries=1):
        for attempt in range(retries + 1):
            try:
                out = self._raw(method, path, params, body, auth, acc)
            except urllib.error.HTTPError as e:
                if e.code == 401 and auth and attempt < retries:
                    self.token = None
                    continue
                if e.code >= 500 and attempt < retries and method.lower() == "get":
                    time.sleep(1)
                    continue
                raise TopstepXError("tradelocker %s HTTP %s" % (path, e.code))
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < retries and method.lower() == "get":
                    time.sleep(1)
                    continue
                raise TopstepXError("tradelocker %s network: %s" % (path, type(e).__name__))
            if isinstance(out, dict) and out.get("s") not in (None, "ok"):
                raise TopstepXError("tradelocker %s failed: %s" % (path, out.get("errmsg") or out.get("s")))
            return out
        raise TopstepXError("tradelocker %s retries exhausted" % path)

    def _ensure_token(self):
        if self.token and self._clock() - self.token_at < 45 * 60:
            return self.token
        out = self._req("post", "/auth/jwt/token", body={"email": self.email, "password": self._pw,
                                                          "server": self.server}, auth=False, acc=False)
        self.token, self.refresh, self.token_at = out["accessToken"], out.get("refreshToken"), self._clock()
        return self.token

    # --- account selection -----------------------------------------------------------------------------------
    def all_accounts(self):
        return self._req("get", "/auth/jwt/all-accounts", acc=False).get("accounts") or []

    def select(self, acc_num=None, account_id=None):
        accts = self.all_accounts()
        pick = [a for a in accts if (acc_num is not None and str(a.get("accNum")) == str(acc_num))
                or (account_id is not None and str(a.get("id")) == str(account_id))] if (acc_num or account_id) else accts[:1]
        if len(pick) != 1:
            raise TopstepXError("tradelocker account not found (accNum=%s id=%s): %s" % (
                acc_num, account_id, [(a.get("id"), a.get("accNum"), a.get("name")) for a in accts]))
        self.acc_num, self.account_id = pick[0]["accNum"], pick[0]["id"]
        return pick[0]

    def config(self):
        if self._cfg is None:
            self._cfg = self._req("get", "/trade/config")["d"]
        return self._cfg

    def _cols(self, key):
        return [c["id"] for c in self.config()[key]["columns"]]

    def instruments(self):
        if self._instr is None:
            self._instr = self._req("get", "/trade/accounts/%s/instruments" % self.account_id)["d"]["instruments"]
        return self._instr

    def instrument(self, names=NASDAQ_NAMES):
        by = {str(i.get("name")).upper(): i for i in self.instruments()}
        for n in names:
            if n.upper() in by:
                return by[n.upper()]
        raise TopstepXError("no Nasdaq-100 instrument found; names include %s" % sorted(by)[:40])

    def route(self, instr, kind):
        ids = [r["id"] for r in instr.get("routes") or [] if r.get("type") == kind]
        if not ids:
            raise TopstepXError("no %s route for %s" % (kind, instr.get("name")))
        return ids[0]

    def details(self, instr):
        return self._req("get", "/trade/instruments/%s" % instr["tradableInstrumentId"],
                         params={"routeId": self.route(instr, "INFO"), "locale": "en"})["d"]

    # --- reads -----------------------------------------------------------------------------------------------
    def state(self):
        vals = self._req("get", "/trade/accounts/%s/state" % self.account_id)["d"]["accountDetailsData"]
        return dict(zip(self._cols("accountDetailsConfig"), vals))

    def positions(self):
        rows = self._req("get", "/trade/accounts/%s/positions" % self.account_id)["d"]["positions"]
        cols = self._cols("positionsConfig")
        return [dict(zip(cols, r)) for r in rows]

    def orders(self):
        rows = self._req("get", "/trade/accounts/%s/orders" % self.account_id)["d"]["orders"]
        cols = self._cols("ordersConfig")
        return [dict(zip(cols, r)) for r in rows]

    def quote(self, instr):
        d = self._req("get", "/trade/quotes", params={"tradableInstrumentId": instr["tradableInstrumentId"],
                                                      "routeId": self.route(instr, "INFO")})["d"]
        return float(d["ap"]), float(d["bp"])

    # --- writes ----------------------------------------------------------------------------------------------
    def place(self, instr, side, qty, type_="market", price=None, strategy_id=None):
        body = {"price": price, "qty": str(qty), "routeId": self.route(instr, "TRADE"), "side": side,
                "validity": "IOC" if type_ == "market" else "GTC", "tradableInstrumentId": str(instr["tradableInstrumentId"]),
                "type": type_, "strategyId": strategy_id}
        out = self._req("post", "/trade/accounts/%s/orders" % self.account_id, body=body, retries=0)
        return int(out["d"]["orderId"])

    def delete_order(self, order_id):
        self._req("delete", "/trade/orders/%s" % order_id, retries=0)

    def close_all(self, instr):
        self._req("delete", "/trade/accounts/%s/positions" % self.account_id,
                  params={"tradableInstrumentId": instr["tradableInstrumentId"]}, retries=0)


class TradeLockerAccount:
    """The bot's account interface (account/positions/market/close/limit/open_orders/cancel) over one TradeLocker
    account and its Nasdaq-100 CFD. Sizes are lots (fractional)."""

    def __init__(self, tl, cfg, instr):
        self.tl, self.cfg, self.instr = tl, cfg, instr
        self.iid = int(instr["tradableInstrumentId"])
        self.aid = "tl-%s" % cfg["name"]
        self.cid = None   # set by the fleet to the signal contract id (MNQ); orders always go to self.instr
        self.lot_step = float(cfg.get("lot_step") or 0.01)

    def account(self):
        st = self.tl.state()
        bal = float(st.get("balance") or st.get("cashBalance") or 0)
        return {"id": self.aid, "name": self.cfg["name"], "balance": bal, "canTrade": True, "simulated": True,
                "firm": self.cfg.get("firm", "Eightcap"), "estimated": False}

    def accounts(self):
        return [self.account()]

    def price(self):
        ask, bid = self.tl.quote(self.instr)
        return (ask + bid) / 2

    def positions(self, account_id=None):
        net, cost = 0.0, 0.0
        for p in self.tl.positions():
            if int(p.get("tradableInstrumentId") or 0) != self.iid:
                continue
            q = float(p.get("qty") or 0) * (1 if str(p.get("side")).lower() == "buy" else -1)
            net += q
            cost += q * float(p.get("avgPrice") or 0)
        net = round(net, 8)
        if abs(net) < 1e-9:
            return []
        return [{"contractId": self.cid, "type": LONG if net > 0 else SHORT, "size": abs(net),
                 "averagePrice": cost / net}]

    def market(self, account_id, contract_id, side, size, tag=None):
        return self.tl.place(self.instr, "buy" if side == BUY else "sell", round(float(size), 2),
                             strategy_id=(tag or "")[:30] or None)

    def close(self, account_id, contract_id):
        self.tl.close_all(self.instr)

    def limit(self, account_id, contract_id, side, size, price, tag=None):
        return self.tl.place(self.instr, "buy" if side == BUY else "sell", round(float(size), 2), "limit", float(price))

    def open_orders(self, account_id=None):
        out = []
        for o in self.tl.orders():
            if int(o.get("tradableInstrumentId") or 0) != self.iid or str(o.get("type")).lower() != "limit":
                continue
            out.append({"id": o["id"], "contractId": self.cid, "type": LIMIT,
                        "side": BUY if str(o.get("side")).lower() == "buy" else SELL,
                        "size": float(o.get("qty") or 0), "limitPrice": float(o.get("price") or 0)})
        return out

    def cancel(self, account_id, order_id):
        self.tl.delete_order(order_id)


def load_config(path):
    import os
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [c for c in json.load(f) if c.get("name") and c.get("server") and c.get("email")]
