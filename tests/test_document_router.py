"""Unit tests for GET /document/statement/{tx_id}."""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_returns_pdf_bytes_when_found(client):
    with patch(
        "orchestrator.services.statement_pdf.fetch",
        new=AsyncMock(return_value=b"%PDF-1.4\nfake\n%%EOF"),
    ):
        resp = await client.get("/document/statement/MOCK-ABCD1234")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_returns_404_when_missing_or_expired(client):
    with patch(
        "orchestrator.services.statement_pdf.fetch", new=AsyncMock(return_value=None)
    ):
        resp = await client.get("/document/statement/MOCK-GONE0000")

    assert resp.status_code == 404
