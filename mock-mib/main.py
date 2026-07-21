"""Mock MIB API — returns HTTP 200 with a fake transaction ID for any request.

Swap for the real MIB by pointing MIB_API_BASE at the real endpoint; the
orchestrator's mib.py client does not change.
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(title="Mock MIB API")


class MIBResponse(BaseModel):
    status: str
    tx_id: str
    timestamp: str
    message: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Every pilot user gets the same plausible account set. Names are per-language
# base forms the orchestrator drops into confirm templates.
_ACCOUNTS = [
    {
        "account_id": "ACC-KZT-001",
        "currency": "KZT",
        "balance": 245000,
        "name": {"ru-RU": "Тенговый", "kk-KZ": "Теңгелік", "en-US": "Tenge"},
    },
    {
        "account_id": "ACC-USD-001",
        "currency": "USD",
        "balance": 1200,
        "name": {"ru-RU": "Долларовый", "kk-KZ": "Долларлық", "en-US": "Dollar"},
    },
    {
        "account_id": "ACC-EUR-001",
        "currency": "EUR",
        "balance": 640,
        "name": {"ru-RU": "Евро", "kk-KZ": "Еуро", "en-US": "Euro"},
    },
]


@app.get("/accounts/{user_id}")
async def accounts(user_id: str) -> dict:
    """The user's accounts — used to resolve 'тенговый/долларовый' to real IDs."""
    return {"user_id": user_id, "accounts": _ACCOUNTS}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
async def catch_all(path: str, request: Request) -> MIBResponse:
    tx_id = f"MOCK-{uuid4().hex[:8].upper()}"
    return MIBResponse(
        status="success",
        tx_id=tx_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=f"Operation /{path} completed. Ref: {tx_id}",
    )
