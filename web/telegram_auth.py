"""Telegram Mini App initData verification.

When the site runs inside Telegram as a Mini App, the client receives an
`initData` query string signed by Telegram with the bot token. Verifying that
signature server-side gives the gateway an authenticated Telegram user id —
which we use as the session_id, so the Mini App shares one conversation
session with the Telegram chat bot.

Spec: data-check-string = all key=value pairs except `hash`, sorted by key,
joined with \n; secret = HMAC_SHA256(key="WebAppData", msg=bot_token);
valid iff HMAC_SHA256(secret, data-check-string) == hash.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

# Reject initData older than this — a replayed blob from a leaked URL should
# not grant a session forever. Telegram re-signs on every Mini App launch.
MAX_AGE_SECONDS = 24 * 3600


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Return the parsed initData fields if the signature is valid, else None."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    # Also rejects auth_date <= 0: the computed age is then always over the cap.
    if time.time() - auth_date > MAX_AGE_SECONDS:
        return None

    return pairs


def _user_dict(fields: dict) -> dict:
    try:
        user = json.loads(fields.get("user", ""))
    except (json.JSONDecodeError, TypeError):
        return {}
    return user if isinstance(user, dict) else {}


def user_id_from(fields: dict) -> str | None:
    """Extract the Telegram user id from verified initData fields."""
    uid = _user_dict(fields).get("id")
    return str(uid) if uid is not None else None


def user_name_from(fields: dict) -> str | None:
    """Extract the Telegram first name, for personalising a greeting reply."""
    name = _user_dict(fields).get("first_name")
    return str(name) if name else None


def username_from(fields: dict) -> str | None:
    """Extract the Telegram @handle ("tg nick"), for admin-panel session search."""
    handle = _user_dict(fields).get("username")
    return str(handle) if handle else None
