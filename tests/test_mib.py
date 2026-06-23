"""Unit tests for orchestrator/services/mib.py — HTTP error mapping."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from orchestrator.services.mib import execute


def _mock_client(status_code=200, json_data=None, raise_exc=None):
    """Return a mock AsyncClient context manager."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or {
        "status": "success",
        "tx_id": "MOCK-OK",
        "message": "Done",
    }
    if raise_exc:
        mock_resp.raise_for_status.side_effect = raise_exc
    else:
        mock_resp.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = AsyncMock(return_value=mock_resp)
    return mock_client


@pytest.mark.asyncio
async def test_execute_success():
    with patch("orchestrator.services.mib.httpx.AsyncClient", return_value=_mock_client()):
        result = await execute("/transfer", {"amount": "500"})
    assert result.status == "success"
    assert result.tx_id == "MOCK-OK"


@pytest.mark.asyncio
async def test_execute_http_status_error_returns_friendly():
    exc = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500)
    )
    client = _mock_client(status_code=500, raise_exc=exc)
    with patch("orchestrator.services.mib.httpx.AsyncClient", return_value=client):
        result = await execute("/transfer", {})
    assert result.status == "error"
    assert result.tx_id == ""
    assert "try again" in result.message.lower()


@pytest.mark.asyncio
async def test_execute_network_error_returns_friendly():
    client = _mock_client()
    client.request = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    with patch("orchestrator.services.mib.httpx.AsyncClient", return_value=client):
        result = await execute("/balance", {})
    assert result.status == "error"
    assert "unavailable" in result.message.lower()
