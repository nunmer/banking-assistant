"""Unit tests for the real-time STT WebSocket route — the gRPC session is
mocked entirely; these only verify the WS protocol/relay logic."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_api_key
from app.main import app


@pytest.fixture(autouse=True)
def _no_api_key_required():
    # This route is behind the same require_api_key dependency as the REST
    # endpoints; these tests exercise the WS relay logic, not auth, so bypass
    # it regardless of the environment's API_KEY_ENABLED setting.
    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)


class _FakeSession:
    """Stands in for StreamingSession: records chunks, yields canned events."""

    def __init__(self, lang):
        self.lang = lang
        self.chunks: list[bytes] = []
        self.ended = False
        self.closed = False
        self._events = [
            {"type": "partial", "text": "перевед"},
            {"type": "final", "text": "переведи 5000"},
        ]

    async def send_chunk(self, pcm: bytes) -> None:
        self.chunks.append(pcm)

    async def end(self) -> None:
        self.ended = True

    async def responses(self):
        for event in self._events:
            yield event

    async def close(self) -> None:
        self.closed = True


def test_stream_relays_partial_and_final_events():
    fake = _FakeSession("ru-RU")
    with patch("app.routers.stt_stream.StreamingSession", return_value=fake):
        with TestClient(app) as client, client.websocket_connect("/stt/stream") as ws:
            ws.send_json({"lang": "ru-RU"})
            ws.send_bytes(b"\x00" * 640)
            ws.send_json({"action": "end"})

            messages = [ws.receive_json() for _ in range(3)]

    assert messages == [
        {"type": "partial", "text": "перевед"},
        {"type": "final", "text": "переведи 5000"},
        {"type": "done"},
    ]
    assert fake.chunks == [b"\x00" * 640]
    assert fake.ended is True
    assert fake.closed is True


def test_stream_passes_lang_from_first_message():
    captured = {}

    def _make(lang):
        captured["lang"] = lang
        return _FakeSession(lang)

    with patch("app.routers.stt_stream.StreamingSession", side_effect=_make):
        with TestClient(app) as client, client.websocket_connect("/stt/stream") as ws:
            ws.send_json({"lang": "kk-KZ,ru-RU"})
            ws.send_json({"action": "end"})
            for _ in range(3):
                ws.receive_json()

    assert captured["lang"] == "kk-KZ,ru-RU"


def test_stream_closes_session_on_client_disconnect():
    fake = MagicMock()
    fake.send_chunk = AsyncMock()
    fake.end = AsyncMock()
    fake.close = AsyncMock()

    async def _no_responses():
        return
        yield  # pragma: no cover - makes this an async generator

    fake.responses = _no_responses

    with patch("app.routers.stt_stream.StreamingSession", return_value=fake):
        with TestClient(app) as client, client.websocket_connect("/stt/stream") as ws:
            ws.send_json({"lang": "ru-RU"})
            # Exiting the `with` block disconnects without an explicit "end".

    fake.close.assert_awaited_once()
