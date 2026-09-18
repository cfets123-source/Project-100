"""HTTP Basic protection for the operator dashboard and its data endpoints."""
import base64
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

_COOKIE_NAME = "project100_dashboard"


def _session_token() -> str:
    """A short-lived browser convenience token; the password never reaches JS."""
    message = settings.DASHBOARD_USERNAME.encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()
    return f"{settings.DASHBOARD_USERNAME}.{signature}"


def _has_valid_session(request: Request) -> bool:
    supplied = request.cookies.get(_COOKIE_NAME, "")
    return bool(supplied) and secrets.compare_digest(supplied, _session_token())


def require_dashboard_access(request: Request, response: Response) -> None:
    """Require a deployment-managed password outside local development."""
    if not settings.DASHBOARD_PASSWORD:
        return
    if _has_valid_session(request):
        return
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Dashboard authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="Project 100"'})
    try:
        username, password = base64.b64decode(auth[6:]).decode().split(":", 1)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Dashboard authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="Project 100"'}) from exc
    if not (secrets.compare_digest(username, settings.DASHBOARD_USERNAME) and
            secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Dashboard authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="Project 100"'})
    response.set_cookie(
        _COOKIE_NAME,
        _session_token(),
        max_age=8 * 60 * 60,
        httponly=True,
        samesite="strict",
        secure=settings.DASHBOARD_COOKIE_SECURE,
    )
