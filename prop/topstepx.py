"""Minimal TopstepX (ProjectX Gateway) client. Standard library only (runs on macOS system Python 3.9+).

Endpoints and fields follow https://api.topstepx.com/swagger/v1/swagger.json (checked 2026-10-21).
Credentials are never stored by this module; the caller passes them in (install.sh keeps them in the macOS Keychain).
"""
import json
import time
import urllib.error
import urllib.request

BASE = "https://api.topstepx.com"
MARKET, LIMIT, STOP = 2, 1, 4
BUY, SELL = 0, 1
LONG, SHORT = 1, 2


class TopstepXError(Exception):
    pass


class TopstepX:
    def __init__(self, username, api_key, base=BASE, opener=None):
        self._user, self._key, self.base = username, api_key, base
        self._open = opener or urllib.request.urlopen
        self.token, self.token_at = None, 0.0

    # --- transport -------------------------------------------------------------------------------------------
    def _post(self, path, body, auth=True, retries=2):
        data = json.dumps(body).encode()
        for attempt in range(retries + 1):
            req = urllib.request.Request(self.base + path, data=data, method="POST",
                                         headers={"Content-Type": "application/json", "accept": "text/plain"})
            if auth:
                req.add_header("Authorization", "Bearer " + self._ensure_token())
            try:
                with self._open(req, timeout=20) as r:
                    out = json.loads(r.read().decode() or "{}")
            except urllib.error.HTTPError as e:
                if e.code == 401 and auth and attempt < retries:
                    self.token = None
                    continue
                if e.code >= 500 and attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise TopstepXError("%s HTTP %s" % (path, e.code))
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < retries:
                    time.sleep(1 + attempt)
                    continue
                raise TopstepXError("%s network: %s" % (path, type(e).__name__))
            if out.get("success") is False:
                raise TopstepXError("%s failed: code %s %s" % (path, out.get("errorCode"), out.get("errorMessage")))
            return out
        raise TopstepXError(path + " retries exhausted")

    def _ensure_token(self):
        now = time.time()
        if self.token and now - self.token_at < 20 * 3600:
            return self.token
        out = self._post("/api/Auth/loginKey", {"userName": self._user, "apiKey": self._key}, auth=False)
        self.token, self.token_at = out["token"], now
        return self.token

    # --- reads -----------------------------------------------------------------------------------------------
    def accounts(self):
        return self._post("/api/Account/search", {"onlyActiveAccounts": True}).get("accounts") or []

    def contract(self, symbol="MNQ", live=False):
        cs = self._post("/api/Contract/search", {"searchText": symbol, "live": live}).get("contracts") or []
        act = [c for c in cs if c.get("activeContract") and (c.get("name") or "").upper().startswith(symbol)]
        if not act:
            raise TopstepXError("no active contract for " + symbol)
        return act[0]

    def bars(self, contract_id, start_iso, end_iso, minutes=5, limit=20000, live=False):
        body = {"contractId": contract_id, "live": live, "startTime": start_iso, "endTime": end_iso,
                "unit": 2, "unitNumber": minutes, "limit": limit, "includePartialBar": False}
        return self._post("/api/History/retrieveBars", body).get("bars") or []

    def positions(self, account_id):
        return self._post("/api/Position/searchOpen", {"accountId": account_id}).get("positions") or []

    def open_orders(self, account_id):
        return self._post("/api/Order/searchOpen", {"accountId": account_id}).get("orders") or []

    def trades(self, account_id, start_iso, end_iso=None):
        body = {"accountId": account_id, "startTimestamp": start_iso}
        if end_iso:
            body["endTimestamp"] = end_iso
        return self._post("/api/Trade/search", body).get("trades") or []

    # --- writes ----------------------------------------------------------------------------------------------
    def market(self, account_id, contract_id, side, size, tag=None):
        body = {"accountId": account_id, "contractId": contract_id, "type": MARKET, "side": side, "size": int(size)}
        if tag:
            body["customTag"] = tag
        return self._post("/api/Order/place", body, retries=0)["orderId"]

    def cancel(self, account_id, order_id):
        return self._post("/api/Order/cancel", {"accountId": account_id, "orderId": order_id})

    def close(self, account_id, contract_id):
        return self._post("/api/Position/closeContract", {"accountId": account_id, "contractId": contract_id},
                          retries=0)
