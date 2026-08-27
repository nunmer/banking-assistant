"""API-key authentication.

Keys are presented via the configured header and matched against the SHA256 of
their stored hash. Disabled by default (API_KEY_ENABLED=false) for local dev.
"""
import hashlib

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import ApiKey


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ApiKey | None:
    if not settings.API_KEY_ENABLED:
        return None
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    stmt = select(ApiKey).where(
        ApiKey.key_hash == hash_key(x_api_key), ApiKey.is_active.is_(True)
    )
    key = db.execute(stmt).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key
