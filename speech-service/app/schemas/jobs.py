from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    kind: str
    engine: str
    lang: str
    cached: bool = False


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    kind: str
    engine: str
    lang: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
