from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from scripts.connect_robinhood_loopback import authorization_url, import_on_host


def test_loopback_oauth_uses_pkce_and_exact_redirect():
    url = authorization_url("client-1", "http://127.0.0.1:8765/callback", "state-1", "verifier-1")
    query = parse_qs(urlsplit(url).query)
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state-1"]
    assert "verifier-1" not in url


@patch("scripts.connect_robinhood_loopback.subprocess.run")
def test_import_sends_secret_only_over_ssh_stdin(run):
    run.return_value = Mock(returncode=0, stdout="stored_encrypted\n")
    import_on_host("root@example.test", "/tmp/key", "client-1", "refresh-secret")
    args, kwargs = run.call_args
    assert "refresh-secret" not in " ".join(args[0])
    assert '"refresh_token": "refresh-secret"' in kwargs["input"]
    assert kwargs["capture_output"] is True
