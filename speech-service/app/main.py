from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.ratelimit import rate_limit

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.routers import tts, stt, stt_stream, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level=settings.LOG_LEVEL, json_output=settings.LOG_JSON)
    yield


app = FastAPI(
    title="Speech Service",
    version="2.0.0",
    description="Multi-engine TTS/STT service",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

_protected = [Depends(rate_limit)]
app.include_router(tts.router, prefix="/tts", tags=["TTS"], dependencies=_protected)
app.include_router(stt.router, prefix="/stt", tags=["STT"], dependencies=_protected)
app.include_router(stt_stream.router, prefix="/stt", tags=["STT"], dependencies=_protected)
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"], dependencies=_protected)


@app.get("/health", tags=["Ops"])
def health():
    return {"status": "ok"}
