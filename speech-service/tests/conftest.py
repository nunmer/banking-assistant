import io
import os
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

# app.core.config.Settings requires DATABASE_URL at import time (no
# production fallback — see its own comment). setdefault() so a real value
# from the environment is never clobbered; this is a fixture placeholder,
# never a real credential.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_wav() -> bytes:
    """1-second 16kHz mono sine-wave WAV."""
    rate = 16000
    t = np.linspace(0, 1.0, rate, dtype=np.float32)
    samples = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()
