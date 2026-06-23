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


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
async def catch_all(path: str, request: Request) -> MIBResponse:
    tx_id = f"MOCK-{uuid4().hex[:8].upper()}"
    return MIBResponse(
        status="success",
        tx_id=tx_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=f"Operation /{path} completed. Ref: {tx_id}",
    )
