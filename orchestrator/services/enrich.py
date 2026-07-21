"""Per-intent parameter enrichment, run after validation and before confirm.

Some scenarios need bank data to finish shaping the confirmation: resolving
account kinds to real accounts, picking a deposit product for a term, reading a
card's current limit. Each such intent registers an enricher here; `apply` is
the single hook `_advance` calls. An enricher returns either updated params or
a localised error message that ends the turn (e.g. "no such account").
"""
import logging
from typing import Awaitable, Callable

from orchestrator.i18n import t
from orchestrator.services import accounts

logger = logging.getLogger("orchestrator.enrich")

# An enricher: (session_id, params, lang) -> (params, error_message | None)
Enricher = Callable[[str, dict, str], Awaitable[tuple[dict, str | None]]]


async def _transfer_own(session_id: str, params: dict, lang: str) -> tuple[dict, str | None]:
    """Resolve from/to account kinds to account IDs and display names."""
    user_accounts = await accounts.list_accounts(session_id)
    if not user_accounts:
        return params, t(lang, "accounts_unavailable")

    available = ", ".join(accounts.display_name(a, lang) for a in user_accounts)

    resolved = {}
    for side in ("from", "to"):
        kind = params.get(f"{side}_account_kind", "")
        account = accounts.find_by_kind(user_accounts, kind)
        if account is None:
            return params, t(lang, "no_account_kind", kind=kind, available=available)
        resolved[side] = account

    if resolved["from"]["account_id"] == resolved["to"]["account_id"]:
        return params, t(lang, "same_account")

    return {
        **params,
        "from_account_id": resolved["from"]["account_id"],
        "to_account_id": resolved["to"]["account_id"],
        "from_account_name": accounts.display_name(resolved["from"], lang),
        "to_account_name": accounts.display_name(resolved["to"], lang),
    }, None


_ENRICHERS: dict[str, Enricher] = {
    "transfer_own": _transfer_own,
}


async def apply(intent: str, session_id: str, params: dict, lang: str) -> tuple[dict, str | None]:
    """Run the intent's enricher, if any. No enricher → params pass through."""
    enricher = _ENRICHERS.get(intent)
    if enricher is None:
        return params, None
    return await enricher(session_id, params, lang)
