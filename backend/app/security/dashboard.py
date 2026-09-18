"""HTTP Basic protection for the operator dashboard and its data endpoints."""
import base64
import secrets

from fastapi import HTTPException, Request, status

from app.core.config import settings


def require_dashboard_access(request: Request) -> None:
    """Require a deployment-managed password outside local development."""
    if not settings.DASHBOARD_PASSWORD:
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
