"""Forte Assistant orchestrator — FastAPI application."""
import logging

from fastapi import FastAPI

from orchestrator.routers import chat, confirm

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Forte Assistant Orchestrator")

app.include_router(chat.router)
app.include_router(confirm.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
