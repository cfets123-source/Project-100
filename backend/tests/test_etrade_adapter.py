from urllib.parse import unquote

import httpx

from app.brokers.etrade_adapter import ETradeError, ETradeReadOnlyAdapter, signed_header


def test_oauth_signature_matches_etrade_published_vector():
    header = signed_header("GET", "https://api.etrade.com/v1/accounts/list",
        "c5bb4dcb7bd6826c7c4340df3f791188", "7d30246211192cda43ede3abd9b393b9",
        token="VbiNYl63EejjlKdQM6FeENzcnrLACrZ2JYD6NQROfVI=",
        token_secret="XCF9RzyQr4UEPloA+WlC06BnTfYC1P0Fwr3GUw/B0Es=",
        timestamp=1344885636, nonce="0bba225a40d1bbac2430aa0c6163ce44")
    fields = dict(part.split("=", 1) for part in header.removeprefix("OAuth ").split(","))
    assert unquote(fields["oauth_signature"].strip('"')) == "UOnPVdzExTAgHkcGWLLfeTaaMSM="


def test_read_only_oauth_and_account_reads():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"].startswith("OAuth ")
        if request.url.path.endswith("request_token"):
            return httpx.Response(200, text="oauth_token=req&oauth_token_secret=reqsecret")
        if request.url.path.endswith("access_token"):
            return httpx.Response(200, text="oauth_token=access&oauth_token_secret=accesssecret")
        if request.url.path.endswith("accounts/list"):
            return httpx.Response(200, text="<AccountListResponse><Accounts><Account><accountId>12345678</accountId><accountIdKey>key1</accountIdKey><accountStatus>ACTIVE</accountStatus><institutionType>BROKERAGE</institutionType><accountType>INDIVIDUAL</accountType></Account></Accounts></AccountListResponse>")
        return httpx.Response(404)
    adapter = ETradeReadOnlyAdapter("key", "secret", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert adapter.request_token() == ("req", "reqsecret")
    assert "token=req" in adapter.authorization_url("req")
    token, secret = adapter.exchange_verifier("req", "reqsecret", "1234")
    reader = ETradeReadOnlyAdapter("key", "secret", access_token=token,
        access_secret=secret, client=adapter.client)
    assert reader.list_accounts() == [{"account_id_key": "key1", "account_last4": "5678",
        "status": "ACTIVE", "institution_type": "BROKERAGE", "account_type": "INDIVIDUAL"}]
    assert len(calls) == 3
    assert not hasattr(reader, "place_order")


def test_no_access_token_fails_before_network():
    adapter = ETradeReadOnlyAdapter("key", "secret")
    try:
        adapter.list_accounts()
    except ETradeError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("unauthorized E*TRADE read succeeded")
