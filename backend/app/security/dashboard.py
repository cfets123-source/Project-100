"""HTTP Basic protection for the operator dashboard and its data endpoints."""
import base64
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request, status

from app.core.config import settings


def _session_token() -> str:
    """Deterministic, HTTP-only browser session token; never expose the password."""
    material = f"{settings.DASHBOARD_USERNAME}:{settings.DASHBOARD_PASSWORD}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), material, hashlib.sha256).hexdigest()


def dashboard_access_granted(request: Request) -> bool:
    if not settings.DASHBOARD_PASSWORD:
        return True
    if secrets.compare_digest(request.cookies.get("project100_dashboard", ""), _session_token()):
        return True
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        username, password = base64.b64decode(auth[6:]).decode().split(":", 1)
    except Exception:
        return False
    return (secrets.compare_digest(username, settings.DASHBOARD_USERNAME) and
            secrets.compare_digest(password, settings.DASHBOARD_PASSWORD))


def issue_dashboard_session(username: str, password: str) -> str | None:
    if (secrets.compare_digest(username, settings.DASHBOARD_USERNAME) and
            secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)):
        return _session_token()
    return None


def require_dashboard_access(request: Request) -> None:
    """Require a deployment-managed password outside local development."""
    if not dashboard_access_granted(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Dashboard authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="Project 100"'})
