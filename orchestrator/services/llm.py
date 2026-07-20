"""LLM intent classification via an OpenAI-compatible endpoint.

OPENAI_API_BASE defaults to the OpenAI endpoint but can be pointed at any
OpenAI-compatible server, including a local LiteLLM proxy.  Change only
OPENAI_API_BASE (and optionally OPENAI_MODEL) in .env — this module does not
need to change.
"""
import json
import logging
import re

from openai import AsyncOpenAI

from orchestrator.config import settings
from orchestrator.models import IntentResult

logger = logging.getLogger("orchestrator.llm")

SUPPORTED_LANGS = frozenset({"kk-KZ", "ru-RU", "en-US"})

# Works for Kazakh (kk), Russian (ru), and English (en) input.
SYSTEM_PROMPT = """
You are a multilingual banking assistant for ForteBank Kazakhstan.
Extract the user's intent and parameters from their message.

The user may write in Kazakh (kk), Russian (ru), or English (en), and may mix
Kazakh and Russian in one message.
Always respond ONLY with valid JSON regardless of the input language.
No explanation. No markdown.

Also detect the language the user is writing in and return it as "lang"
(one of kk-KZ, ru-RU, en-US) — this is the language the assistant should reply
in. For a Kazakh-Russian mix, choose the dominant language (the one the main
request is in); if truly balanced, use kk-KZ.

Schema:
{
  "intent": "<intent_name>",
  "params": {
    "<param_name>": "<value>"
  },
  "confidence": 0.0-1.0,
  "lang": "kk-KZ" | "ru-RU" | "en-US"
}

Available intents: transfer, transfer_own, transfer_phone, balance, payment,
statement, statement_pdf, deposit_open, card_block, card_unblock, card_limit,
certificate, navigation, manager, unknown

Choosing between similar intents:
- transfer        — to an external account/IBAN the user names ("на счёт KZ123").
- transfer_own    — between the user's OWN accounts named by kind
                    ("с тенгового на долларовый").
- transfer_phone  — to a phone number ("на номер +7 701 …").
- statement       — a list of recent transactions ("последние 5 транзакций").
- statement_pdf   — a statement document for a period ("выписку за месяц").
- navigation      — how-to / where-is questions (ATM, branch, app steps).
- manager         — the user asks to talk to a human/manager.

Important: if the user clearly names an operation but leaves out details
(amount, account, card, phone, term, …), STILL return that intent with high
confidence and whatever parameters are present (possibly none) — the missing
details are collected in a follow-up question. A bare "I want to transfer money"
or "хочу открыть депозит" is a confident intent, not "unknown". Use "unknown"
only when the message is not a banking request at all.

Parameter rules:
- amount: numeric string (digits only, no currency symbols)
- currency: ISO 4217 code (USD, KZT, EUR, RUB, …).  Infer from text:
    "тенге/теңге" → KZT, "доллар/dollar" → USD, "евро/euro" → EUR.
    If unknown, omit.
- to_account: account number or IBAN as provided by the user.
- bill_id: identifier of the bill/utility.
- limit: number of transactions as a string.
- from_account_kind / to_account_kind: the user's own account by kind, as a
    currency code — "тенговый/tenge"→KZT, "долларовый/dollar"→USD, "евровый/euro"→EUR.
- phone: recipient phone number, digits with country code if given (e.g. +77012345678).
- term: deposit term in months (digits only).
- card_last4: the last 4 digits of a card.
- card_kind: card type/name if named (gold, platinum, salary, …); optional.
- limit_kind: "daily" or "monthly".
- limit_amount: the new limit (digits only).
- period: statement period — one of week, month, quarter, year (or a date range as given).
- cert_kind: certificate type — "account", "no_debt", or "balance".

Examples:
User: "Transfer 500 dollars to account KZ123"
Response: {"intent": "transfer", "params": {"amount": "500", "currency": "USD", "to_account": "KZ123"}, "confidence": 0.97, "lang": "en-US"}

User: "KZ456 шотына 12000 теңге аудар"
Response: {"intent": "transfer", "params": {"amount": "12000", "currency": "KZT", "to_account": "KZ456"}, "confidence": 0.96, "lang": "kk-KZ"}

User: "Переведи 300 евро на KZ789"
Response: {"intent": "transfer", "params": {"amount": "300", "currency": "EUR", "to_account": "KZ789"}, "confidence": 0.97, "lang": "ru-RU"}

User: "What is my balance"
Response: {"intent": "balance", "params": {}, "confidence": 0.99, "lang": "en-US"}

User: "Менің балансым қанша?"
Response: {"intent": "balance", "params": {}, "confidence": 0.99, "lang": "kk-KZ"}

User: "Какой мой баланс?"
Response: {"intent": "balance", "params": {}, "confidence": 0.99, "lang": "ru-RU"}

User: "Балансымды покажи, пожалуйста"
Response: {"intent": "balance", "params": {}, "confidence": 0.95, "lang": "ru-RU"}

User: "Pay utility bill 8842 for 12000"
Response: {"intent": "payment", "params": {"bill_id": "8842", "amount": "12000"}, "confidence": 0.95}

User: "8842 шотты 5000 теңгеге төле"
Response: {"intent": "payment", "params": {"bill_id": "8842", "amount": "5000"}, "confidence": 0.95}

User: "Show my last 5 transactions"
Response: {"intent": "statement", "params": {"limit": "5"}, "confidence": 0.96}

User: "Соңғы 10 транзакцияны көрсет"
Response: {"intent": "statement", "params": {"limit": "10"}, "confidence": 0.96}

User: "Переведи 50000 с тенгового на долларовый счёт"
Response: {"intent": "transfer_own", "params": {"from_account_kind": "KZT", "to_account_kind": "USD", "amount": "50000"}, "confidence": 0.95}

User: "Теңгелік шоттан долларлық шотқа 10000 аудар"
Response: {"intent": "transfer_own", "params": {"from_account_kind": "KZT", "to_account_kind": "USD", "amount": "10000"}, "confidence": 0.95}

User: "Переведи 5000 на номер +7 701 234 5678"
Response: {"intent": "transfer_phone", "params": {"phone": "+77012345678", "amount": "5000"}, "confidence": 0.96}

User: "Открой депозит на 12 месяцев на сумму 100000"
Response: {"intent": "deposit_open", "params": {"term": "12", "amount": "100000"}, "confidence": 0.95}

User: "12 айға 500000 теңгеге депозит аш"
Response: {"intent": "deposit_open", "params": {"term": "12", "amount": "500000"}, "confidence": 0.95}

User: "Заблокируй карту 4321"
Response: {"intent": "card_block", "params": {"card_last4": "4321"}, "confidence": 0.96}

User: "4321 картасын бұғаттан шығар"
Response: {"intent": "card_unblock", "params": {"card_last4": "4321"}, "confidence": 0.95}

User: "Установи суточный лимит 500000 на карту 4321"
Response: {"intent": "card_limit", "params": {"card_last4": "4321", "limit_kind": "daily", "limit_amount": "500000"}, "confidence": 0.95}

User: "Set the monthly limit to 1000000 on card 8899"
Response: {"intent": "card_limit", "params": {"card_last4": "8899", "limit_kind": "monthly", "limit_amount": "1000000"}, "confidence": 0.95}

User: "Пришли выписку за месяц"
Response: {"intent": "statement_pdf", "params": {"period": "month"}, "confidence": 0.95}

User: "Нужна справка об отсутствии задолженности"
Response: {"intent": "certificate", "params": {"cert_kind": "no_debt"}, "confidence": 0.95}

User: "Где ближайший банкомат?"
Response: {"intent": "navigation", "params": {}, "confidence": 0.94}

User: "Соедините меня с менеджером"
Response: {"intent": "manager", "params": {}, "confidence": 0.96}

User: "Play music"
Response: {"intent": "unknown", "params": {}, "confidence": 0.95}
""".strip()

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# OpenAI-compatible client.  Point OPENAI_API_BASE at a LiteLLM proxy to
# switch models without touching this file.
client = AsyncOpenAI(
    base_url=settings.OPENAI_API_BASE,
    api_key=settings.OPENAI_API_KEY or "sk-noop",
)


def _parse(raw: str) -> dict:
    """Parse model output as JSON, with a regex fallback for chatty models."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_RE.search(raw or "")
        if not match:
            raise
        return json.loads(match.group(0))


# Focused single-slot extraction, used during multi-turn parameter collection.
# The user was asked for one specific parameter; pull just that value out of
# their reply. Giving the model the parameter name as context lets it handle
# bare answers ("12 months", "100000", "тенге") that a full classify would miss.
_EXTRACT_PROMPT = """
You are helping a ForteBank assistant collect one missing parameter.
The user is performing intent "{intent}" and was just asked to provide "{param}".
Extract ONLY the value of "{param}" from their reply.

Rules for the value:
- amount / limit: digits only, no currency symbols or words.
- currency: ISO 4217 code (KZT, USD, EUR, RUB). "тенге/теңге"→KZT, "доллар"→USD, "евро"→EUR.
- to_account / bill_id: the identifier exactly as given.
- Any other parameter: the literal value the user provided.

Respond ONLY with JSON: {{"value": "<value>"}} — or {{"value": null}} if the
reply does not contain the requested parameter.
No explanation. No markdown.
""".strip()


async def extract_param(text: str, intent: str, param: str, lang: str) -> str | None:
    """Extract a single named parameter from a follow-up reply, or None.

    `lang` is accepted for symmetry/logging; the extraction is language-agnostic
    because the prompt lists the multilingual cues explicitly.
    """
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _EXTRACT_PROMPT.format(intent=intent, param=param)},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    try:
        data = _parse(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("extract_param unparseable output: %r", raw)
        return None

    value = data.get("value")
    if value is None:
        return None
    value = str(value).strip()
    return value or None


async def classify(text: str, session_id: str) -> IntentResult:
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    try:
        data = _parse(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("LLM returned unparseable output: %r", raw)
        return IntentResult(intent="unknown", params={}, confidence=0.0)

    # Coerce param values to strings — the schema promises dict[str, str].
    params = {str(k): str(v) for k, v in (data.get("params") or {}).items()}

    # Only accept a supported language tag; otherwise leave it unset and the
    # caller falls back to the session language.
    lang = data.get("lang")
    lang = lang if lang in SUPPORTED_LANGS else None

    return IntentResult(
        intent=str(data.get("intent", "unknown")),
        params=params,
        confidence=float(data.get("confidence", 1.0)),
        lang=lang,
    )
