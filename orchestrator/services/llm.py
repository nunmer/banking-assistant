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

# Works for Kazakh (kk), Russian (ru), and English (en) input.
SYSTEM_PROMPT = """
You are a multilingual banking assistant for ForteBank Kazakhstan.
Extract the user's intent and parameters from their message.

The user may write in Kazakh (kk), Russian (ru), or English (en).
Always respond ONLY with valid JSON regardless of the input language.
No explanation. No markdown.

Schema:
{
  "intent": "<intent_name>",
  "params": {
    "<param_name>": "<value>"
  },
  "confidence": 0.0-1.0
}

Available intents: transfer, balance, payment, statement, unknown

Parameter rules:
- amount: numeric string (digits only, no currency symbols)
- currency: ISO 4217 code (USD, KZT, EUR, RUB, …).  Infer from text:
    "тенге/теңге" → KZT, "доллар/dollar" → USD, "евро/euro" → EUR.
    If unknown, omit.
- to_account: account number or IBAN as provided by the user.
- bill_id: identifier of the bill/utility.
- limit: number of transactions as a string.

Examples:
User: "Transfer 500 dollars to account KZ123"
Response: {"intent": "transfer", "params": {"amount": "500", "currency": "USD", "to_account": "KZ123"}, "confidence": 0.97}

User: "KZ456 шотына 12000 теңге аудар"
Response: {"intent": "transfer", "params": {"amount": "12000", "currency": "KZT", "to_account": "KZ456"}, "confidence": 0.96}

User: "Переведи 300 евро на KZ789"
Response: {"intent": "transfer", "params": {"amount": "300", "currency": "EUR", "to_account": "KZ789"}, "confidence": 0.97}

User: "What is my balance"
Response: {"intent": "balance", "params": {}, "confidence": 0.99}

User: "Менің балансым қанша?"
Response: {"intent": "balance", "params": {}, "confidence": 0.99}

User: "Какой мой баланс?"
Response: {"intent": "balance", "params": {}, "confidence": 0.99}

User: "Pay utility bill 8842 for 12000"
Response: {"intent": "payment", "params": {"bill_id": "8842", "amount": "12000"}, "confidence": 0.95}

User: "8842 шотты 5000 теңгеге төле"
Response: {"intent": "payment", "params": {"bill_id": "8842", "amount": "5000"}, "confidence": 0.95}

User: "Show my last 5 transactions"
Response: {"intent": "statement", "params": {"limit": "5"}, "confidence": 0.96}

User: "Соңғы 10 транзакцияны көрсет"
Response: {"intent": "statement", "params": {"limit": "10"}, "confidence": 0.96}

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

    return IntentResult(
        intent=str(data.get("intent", "unknown")),
        params=params,
        confidence=float(data.get("confidence", 1.0)),
    )
