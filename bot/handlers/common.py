"""Shared helpers for talking to the orchestrator."""
import httpx

from bot.config import settings


async def send_to_orchestrator(session_id: str, text: str) -> dict:
    """POST a user utterance to the orchestrator /chat endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ORCHESTRATOR_URL}/chat",
            json={"session_id": session_id, "text": text},
        )
        resp.raise_for_status()
        return resp.json()
