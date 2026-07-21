"""Compact one-line operation summaries for the history view.

The full confirmation text ("Перевожу 10000 со счёта … . Подтверждаете?") is a
question, not a record. History wants the essentials only: what, how much,
where — "Перевод 5000 тенге → 8 (775) 815 55 76". Built deterministically
from the params, localised through the same speechtext rendering the confirm
uses (currency words, grouped phones, enum words).
"""
from orchestrator.services import speechtext

_LABELS = {
    "ru-RU": {
        "transfer": "Перевод",
        "transfer_own": "Перевод",
        "transfer_phone": "Перевод",
        "payment": "Оплата счёта",
        "deposit_open": "Депозит",
        "card_block": "Блокировка карты",
        "card_unblock": "Разблокировка карты",
        "card_limit": "Лимит карты",
        "balance": "Баланс",
        "statement": "Выписка",
        "statement_pdf": "Выписка",
        "certificate": "Справка",
    },
    "kk-KZ": {
        "transfer": "Аударым",
        "transfer_own": "Аударым",
        "transfer_phone": "Аударым",
        "payment": "Шот төлеу",
        "deposit_open": "Депозит",
        "card_block": "Картаны бұғаттау",
        "card_unblock": "Картаны бұғаттан шығару",
        "card_limit": "Карта лимиті",
        "balance": "Баланс",
        "statement": "Үзінді",
        "statement_pdf": "Үзінді",
        "certificate": "Анықтама",
    },
    "en-US": {
        "transfer": "Transfer",
        "transfer_own": "Transfer",
        "transfer_phone": "Transfer",
        "payment": "Bill payment",
        "deposit_open": "Deposit",
        "card_block": "Card block",
        "card_unblock": "Card unblock",
        "card_limit": "Card limit",
        "balance": "Balance",
        "statement": "Statement",
        "statement_pdf": "Statement",
        "certificate": "Certificate",
    },
}

_MONTHS = {"ru-RU": "мес.", "kk-KZ": "ай", "en-US": "mo"}


def short(intent: str, params: dict, lang: str) -> str:
    """One line: operation, amount, destination. Falls back to the bare label."""
    p = speechtext.for_display(dict(params), lang)
    labels = _LABELS.get(lang) or _LABELS["ru-RU"]
    label = labels.get(intent, intent)

    amount = p.get("amount", "")
    if amount and p.get("currency"):
        amount = f"{amount} {p['currency']}"

    if intent == "transfer":
        return f"{label} {amount} → {p.get('to_account', '')}".strip(" →")
    if intent == "transfer_own":
        route = f"{p.get('from_account_name', '')} → {p.get('to_account_name', '')}".strip(" →")
        return f"{label} {amount}: {route}".strip(": ")
    if intent == "transfer_phone":
        return f"{label} {amount} → {p.get('phone', '')}".strip(" →")
    if intent == "payment":
        return f"{label} {p.get('bill_id', '')} — {amount}".strip(" —")
    if intent == "deposit_open":
        months = _MONTHS.get(lang, _MONTHS["ru-RU"])
        term = p.get("term", "")
        return f"{label} {amount}, {term} {months}".strip(", ") if term else f"{label} {amount}".strip()
    if intent in ("card_block", "card_unblock"):
        last4 = p.get("card_last4", "")
        return f"{label} •• {last4}".strip(" •")
    if intent == "card_limit":
        return f"{label} •• {p.get('card_last4', '')} → {p.get('limit_amount', '')}".strip(" •→")
    if intent == "statement_pdf":
        return f"{label}: {p.get('period', '')}".strip(": ")
    if intent == "certificate":
        return f"{label}: {p.get('cert_kind', '')}".strip(": ")

    return label
