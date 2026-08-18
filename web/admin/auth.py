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

# Intentionally weak default (admin/admin) — explicit pilot-stage choice, not
# an oversight. Publicly reachable with no IP restriction, by instruction.
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

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
