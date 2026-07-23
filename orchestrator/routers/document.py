"""GET /document/statement/{tx_id} — fetch a previously generated statement PDF.

Internal-only: reached by the web gateway (web/app.py proxies its public
/api/statement/pdf/{tx_id} here), never directly by a browser — see
docker-compose.yml, where only `web` is published.
"""
from fastapi import APIRouter, HTTPException, Response

from orchestrator.services import statement_pdf

router = APIRouter()


@router.get("/document/statement/{tx_id}")
async def get_statement_pdf(tx_id: str) -> Response:
    pdf_bytes = await statement_pdf.fetch(tx_id)
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="Statement not found or expired")
    return Response(content=pdf_bytes, media_type="application/pdf")
