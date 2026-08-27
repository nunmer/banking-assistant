import io
import wave
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from app.main import app


def _wav() -> bytes:
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


def test_async_recognize_lifecycle():
    client = TestClient(app)
    audio = _wav()

    with patch(
        "app.engines.yandex.stt.YandexSTTEngine.recognize",
        return_value="integration text",
    ):
        submit = client.post(
            "/stt/recognize/async",
            data={"lang": "ru-RU"},
            files={"file": ("a.wav", audio, "audio/wav")},
        )
        assert submit.status_code == 202
        job_id = submit.json()["job_id"]
        assert submit.json()["cached"] is False

        poll = client.get(f"/jobs/{job_id}")
        assert poll.status_code == 200
        body = poll.json()
        assert body["status"] == "completed"
        assert body["result"]["text"] == "integration text"

        # Same audio again → served from the deduplicated completed job.
        again = client.post(
            "/stt/recognize/async",
            data={"lang": "ru-RU"},
            files={"file": ("a.wav", audio, "audio/wav")},
        )
        assert again.json()["cached"] is True
        assert again.json()["job_id"] == job_id


def test_job_not_found():
    client = TestClient(app)
    assert client.get("/jobs/does-not-exist").status_code == 404
