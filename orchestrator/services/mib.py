"""MIB API client. Talks to mib-service (Go, still mocked) today, a real
endpoint in prod.

Swapping in the real MIB is a config change (MIB_API_BASE); this module does
not change. Domain errors are mapped to user-friendly messages.
"""
import logging

import httpx

from orchestrator.config import settings
from orchestrator.models import MIBResult

logger = logging.getLogger("orchestrator.mib")


async def execute(endpoint: str, params: dict, method: str = "POST") -> MIBResult:
    url = f"{settings.MIB_API_BASE}{endpoint}"
    headers = {"Authorization": f"Bearer {settings.MIB_API_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(method, url, json=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("MIB returned %s for %s", e.response.status_code, endpoint)
        return MIBResult(
            status="error",
            tx_id="",
            message="The bank could not process this operation. Please try again later.",
        )
    except httpx.HTTPError as e:
        logger.error("MIB request failed for %s: %s", endpoint, e)
        return MIBResult(
            status="error",
            tx_id="",
            message="The banking service is unavailable right now. Please try again later.",
        )

    return MIBResult(
        status=data.get("status", "success"),
        tx_id=data.get("tx_id", ""),
        message=data.get("message", "Operation completed."),
    )
