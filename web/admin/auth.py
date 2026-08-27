"""Basic Auth gate for the admin panel.

Independent of orchestrator's own admin auth (routers/admin.py there) —
each service checks its own credentials; the gateway doesn't forward the
browser's Authorization header when it proxies to orchestrator, it builds a
fresh one from its own env vars (see routes.py).
"""
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# No default: a guessable fallback credential must never ship in source.
# Fails at import time (process won't start) if either is unset.
ADMIN_USER = os.environ["ADMIN_USER"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

_security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> None:
    user_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    pass_ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
