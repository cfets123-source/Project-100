"""E*TRADE OAuth 1.0a transport and read-only brokerage adapter.

The broker's sandbox returns canned responses, so a successful sandbox call is
connection evidence only. This module has no order submission methods.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx


API_BASE = "https://api.etrade.com"
SANDBOX_BASE = "https://apisb.etrade.com"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"


class ETradeError(RuntimeError):
    """Safe-to-display broker connection error; excludes response body and keys."""


def _escape(value: object) -> str:
    return quote(str(value), safe="~-._")


def signed_header(method: str, url: str, consumer_key: str, consumer_secret: str,
                  *, token: str = "", token_secret: str = "", extra: dict | None = None,
                  timestamp: int | None = None, nonce: str | None = None) -> str:
    """Build an RFC 5849 HMAC-SHA1 Authorization header, including query params."""
    if not consumer_key or not consumer_secret:
        raise ETradeError("E*TRADE consumer credentials are not configured")
    parts = urlsplit(url)
    base_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    oauth = {"oauth_consumer_key": consumer_key, "oauth_nonce": nonce or secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(timestamp or int(time.time()))}
    if token:
        oauth["oauth_token"] = token
    oauth.update(extra or {})
    params = parse_qsl(parts.query, keep_blank_values=True) + list(oauth.items())
    normalized = "&".join(f"{_escape(k)}={_escape(v)}" for k, v in sorted(
        params, key=lambda pair: (_escape(pair[0]), _escape(pair[1]))))
    signature_base = "&".join((_escape(method.upper()), _escape(base_url), _escape(normalized)))
    signing_key = f"{_escape(consumer_secret)}&{_escape(token_secret)}".encode()
    oauth["oauth_signature"] = base64.b64encode(hmac.new(
        signing_key, signature_base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ",".join(f'{_escape(k)}="{_escape(v)}"' for k, v in sorted(oauth.items()))


def _xml(response: httpx.Response) -> ElementTree.Element:
    try:
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise ETradeError("E*TRADE response is too large")
        return ElementTree.fromstring(response.content)
    except (httpx.HTTPError, ElementTree.ParseError) as exc:
        raise ETradeError(f"E*TRADE read failed ({response.status_code})") from exc


class ETradeReadOnlyAdapter:
    def __init__(self, consumer_key: str, consumer_secret: str, *, access_token: str = "",
                 access_secret: str = "", sandbox: bool = False, client: httpx.Client | None = None):
        if not consumer_key or not consumer_secret:
            raise ETradeError("E*TRADE consumer credentials are not configured")
        self.consumer_key, self.consumer_secret = consumer_key, consumer_secret
        self.access_token, self.access_secret = access_token, access_secret
        self.base_url = SANDBOX_BASE if sandbox else API_BASE
        self.client = client or httpx.Client(timeout=15)

    def _get(self, url: str, *, token: str = "", token_secret: str = "",
             extra: dict | None = None) -> httpx.Response:
        headers = {"Authorization": signed_header("GET", url, self.consumer_key,
            self.consumer_secret, token=token, token_secret=token_secret, extra=extra)}
        try:
            response = self.client.get(url, headers=headers)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise ETradeError("E*TRADE request failed; check API key, session, and agreement") from exc

    def request_token(self) -> tuple[str, str]:
        response = self._get(API_BASE + "/oauth/request_token", extra={"oauth_callback": "oob"})
        payload = dict(parse_qsl(response.text, keep_blank_values=True))
        if not payload.get("oauth_token") or not payload.get("oauth_token_secret"):
            raise ETradeError("E*TRADE did not return a request token")
        return payload["oauth_token"], payload["oauth_token_secret"]

    def authorization_url(self, request_token: str) -> str:
        return AUTHORIZE_URL + "?key=" + _escape(self.consumer_key) + "&token=" + _escape(request_token)

    def exchange_verifier(self, request_token: str, request_secret: str,
                          verifier: str) -> tuple[str, str]:
        if not verifier or len(verifier) > 128:
            raise ETradeError("E*TRADE verification code is missing or invalid")
        response = self._get(API_BASE + "/oauth/access_token", token=request_token,
                             token_secret=request_secret, extra={"oauth_verifier": verifier})
        payload = dict(parse_qsl(response.text, keep_blank_values=True))
        if not payload.get("oauth_token") or not payload.get("oauth_token_secret"):
            raise ETradeError("E*TRADE did not return an access token")
        return payload["oauth_token"], payload["oauth_token_secret"]

    def _api(self, path: str) -> ElementTree.Element:
        if not self.access_token or not self.access_secret:
            raise ETradeError("E*TRADE authorization is incomplete")
        return _xml(self._get(self.base_url + path, token=self.access_token,
                              token_secret=self.access_secret))

    def list_accounts(self) -> list[dict]:
        root = self._api("/v1/accounts/list")
        return [{"account_id_key": item.findtext("accountIdKey"),
                 "account_last4": (item.findtext("accountId") or "")[-4:],
                 "status": item.findtext("accountStatus"),
                 "institution_type": item.findtext("institutionType"),
                 "account_type": item.findtext("accountType")}
                for item in root.findall(".//Account") if item.findtext("accountIdKey")]

    def account_balance(self, account_id_key: str) -> dict:
        if not account_id_key or "/" in account_id_key:
            raise ETradeError("E*TRADE account key is invalid")
        root = self._api("/v1/accounts/" + _escape(account_id_key)
                         + "/balance?instType=BROKERAGE&realTimeNAV=true")
        return {"account_last4": (root.findtext("accountId") or "")[-4:],
                "account_type": root.findtext("accountType"),
                "option_level": root.findtext("optionLevel"),
                "cash_buying_power": root.findtext(".//cashBuyingPower"),
                "margin_buying_power": root.findtext(".//marginBuyingPower"),
                "account_balance": root.findtext(".//accountBalance")}

    def quote(self, symbol: str) -> dict:
        if not symbol or len(symbol) > 20 or not symbol.replace(".", "").isalnum():
            raise ETradeError("E*TRADE quote symbol is invalid")
        root = self._api("/v1/market/quote/" + _escape(symbol.upper()))
        item = root.find(".//QuoteData")
        if item is None:
            raise ETradeError("E*TRADE returned no quote")
        return {"symbol": item.findtext(".//Product/symbol") or symbol.upper(),
                "status": item.findtext("quoteStatus"),
                "timestamp": item.findtext("dateTimeUTC"),
                "bid": item.findtext(".//All/bid"), "ask": item.findtext(".//All/ask"),
                "last": item.findtext(".//All/lastTrade")}
