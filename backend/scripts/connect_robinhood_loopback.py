"""One-time Robinhood MCP OAuth bridge for a rejected hosted redirect.

Runs only on the operator's desktop. The authorization code stays on localhost;
the refresh token is sent over the existing SSH connection directly to the
deployed app, encrypted there, and never printed or written to disk.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import secrets
import shlex
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

MCP_URL = "https://agent.robinhood.com/mcp/trading"
REGISTRATION_URL = "https://agent.robinhood.com/oauth/trading/register"
AUTHORIZATION_URL = "https://robinhood.com/oauth"
TOKEN_URL = "https://api.robinhood.com/oauth2/token/"


def post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def register_client(redirect_uri: str) -> str:
    body = json.dumps({
        "client_name": "Veloikos Trading",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "internal",
    }).encode()
    req = urllib.request.Request(REGISTRATION_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if redirect_uri not in payload.get("redirect_uris", []):
        raise RuntimeError("Robinhood did not register the local callback")
    client_id = payload.get("client_id")
    if not isinstance(client_id, str) or not client_id:
        raise RuntimeError("Robinhood did not return a client ID")
    return client_id


def authorization_url(client_id: str, redirect_uri: str, state: str, verifier: str) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "response_type": "code", "client_id": client_id,
        "redirect_uri": redirect_uri, "scope": "internal", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "resource": MCP_URL,
    }
    return AUTHORIZATION_URL + "?" + urllib.parse.urlencode(params)


def import_on_host(host: str, key_path: str, client_id: str, refresh_token: str) -> None:
    # Secrets enter the remote container over SSH stdin. They are never shell
    # arguments, environment variables, local files, or command output.
    remote_code = (
        "import json,sys,datetime as dt; "
        "from sqlalchemy.orm import Session; "
        "from app.db.session import engine; "
        "from app.core.config import settings; "
        "from app.models.models import BrokerConnection; "
        "from app.brokers.robinhood_oauth import BROKER,_fernet; "
        "p=json.load(sys.stdin); "
        "assert isinstance(p.get('client_id'),str) and isinstance(p.get('refresh_token'),str); "
        "assert p['client_id'] and p['refresh_token']; "
        "blob=_fernet(settings.BROKER_TOKEN_ENCRYPTION_KEY).encrypt(p['refresh_token'].encode()).decode(); "
        "db=Session(engine); "
        "row=db.get(BrokerConnection,BROKER); "
        "row=row or BrokerConnection(broker=BROKER,client_id=p['client_id'],encrypted_refresh_token=blob,status='authorized'); "
        "row.client_id=p['client_id']; row.encrypted_refresh_token=blob; "
        "row.connected_at=dt.datetime.utcnow(); row.status='authorized'; "
        "db.add(row); db.commit(); db.close(); print('stored_encrypted')"
    )
    result = subprocess.run(
        ["ssh", "-i", key_path, "-o", "BatchMode=yes", host,
         "docker exec -i project-100-api-1 python -c " + shlex.quote(remote_code)],
        input=json.dumps({"client_id": client_id, "refresh_token": refresh_token}),
        text=True, capture_output=True, timeout=30,
    )
    if result.returncode != 0 or "stored_encrypted" not in result.stdout:
        raise RuntimeError("Secure import to Veloikos failed; no credential was printed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect Veloikos to Robinhood Agentic Trading")
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    result: dict[str, str] = {}
    completed = threading.Event()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != "/callback" or query.get("state", [None])[0] != state:
                self.send_error(400, "Invalid callback")
                return
            result["code"] = query.get("code", [""])[0]
            result["error"] = query.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"<h1>Robinhood returned to Veloikos</h1><p>You may return to Codex.</p>")
            completed.set()

        def log_message(self, *_args):
            pass  # Callback query contains an authorization code; never log it.

    with http.server.HTTPServer(("127.0.0.1", 0), Callback) as server:
        server.timeout = 1
        redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
        client_id = register_client(redirect_uri)
        url = authorization_url(client_id, redirect_uri, state, verifier)
        if not webbrowser.open(url):
            raise RuntimeError("Could not open desktop browser")
        print("Robinhood sign-in opened in your desktop browser. Complete the authorization there.", flush=True)
        for _ in range(args.timeout):
            server.handle_request()
            if completed.is_set():
                break
        if not completed.is_set():
            raise RuntimeError("Robinhood did not return to the local callback before timeout")
    if result.get("error"):
        raise RuntimeError("Robinhood declined authorization: " + result["error"][:80])
    if not result.get("code"):
        raise RuntimeError("Robinhood returned without an authorization code")
    tokens = post_form(TOKEN_URL, {
        "grant_type": "authorization_code", "client_id": client_id,
        "code": result["code"], "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    })
    refresh = tokens.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise RuntimeError("Robinhood did not issue a refresh token")
    import_on_host(args.ssh_host, args.ssh_key, client_id, refresh)
    print("Credential stored encrypted in Veloikos. Read-only account verification is next.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Robinhood connection was not completed: {exc}", file=sys.stderr)
        sys.exit(1)
