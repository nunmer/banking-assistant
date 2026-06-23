"""LLM intent classification via an OpenAI-compatible endpoint."""
import json
import logging
import re

from openai import AsyncOpenAI

from orchestrator.config import settings
from orchestrator.models import IntentResult

logger = logging.getLogger("orchestrator.llm")

SYSTEM_PROMPT = """
You are a banking assistant. Extract the user's intent and parameters from their message.

Respond ONLY with valid JSON. No explanation. No markdown.

Schema:
{
  "intent": "<intent_name>",
  "params": {
    "<param_name>": "<value>"
  },
  "confidence": 0.0-1.0
}

Available intents: transfer, balance, payment, statement, unknown

Examples:
User: "Transfer 500 dollars to account KZ123"
Response: {"intent": "transfer", "params": {"amount": "500", "currency": "USD", "to_account": "KZ123"}, "confidence": 0.97}

User: "What is my balance"
Response: {"intent": "balance", "params": {}, "confidence": 0.99}

User: "Pay utility bill 8842 for 12000"
Response: {"intent": "payment", "params": {"bill_id": "8842", "amount": "12000"}, "confidence": 0.95}

User: "Show my last 5 transactions"
Response: {"intent": "statement", "params": {"limit": "5"}, "confidence": 0.96}

User: "Play music"
Response: {"intent": "unknown", "params": {}, "confidence": 0.95}
""".strip()

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

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
