"""User account lookup against the MIB (mock today, real in prod).

Used to resolve spoken account kinds ("тенговый", "долларовый") to concrete
account IDs and human-readable names before an operation is confirmed.
"""
import logging

import httpx

from orchestrator.config import settings

logger = logging.getLogger("orchestrator.accounts")

DEFAULT_LANG = "ru-RU"


async def list_accounts(user_id: str) -> list[dict]:
    """Return the user's accounts, or [] when the lookup fails."""
    url = f"{settings.MIB_API_BASE}/accounts/{user_id}"
    headers = {"Authorization": f"Bearer {settings.MIB_API_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("accounts", [])
    except (httpx.HTTPError, ValueError) as e:
        logger.error("account lookup failed for %s: %s", user_id, e)
        return []


def find_by_kind(accounts: list[dict], kind: str) -> dict | None:
    """Match an account by its currency code (the LLM normalises kinds to codes)."""
    kind = (kind or "").upper()
    for account in accounts:
        if account.get("currency", "").upper() == kind:
            return account
    return None


def display_name(account: dict, lang: str) -> str:
    """Localised account name with a sensible fallback chain."""
    names = account.get("name") or {}
    return (
        names.get(lang)
        or names.get(DEFAULT_LANG)
        or next(iter(names.values()), account.get("account_id", ""))
    )
