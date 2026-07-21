"""Unit tests for the web voice-bot gateway — proxies mocked, no network."""
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import web.app as gateway


class _StubResponse:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = str(json_data)

    def json(self):
        return self._json


class _StubClient:
    """Stands in for httpx.AsyncClient; records the last call."""

    last_call = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        _StubClient.last_call = {"url": url, **kwargs}
        return _StubClient.response


@pytest.fixture
async def client():
    gateway._hits.clear()  # isolate the rate limiter between tests
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_chat_proxies_to_orchestrator(client):
    _StubClient.response = _StubResponse(
        json_data={"action": "confirm", "message": "ok?", "speech": None, "lang": "ru-RU"}
    )
    with patch.object(gateway.httpx, "AsyncClient", _StubClient):
        resp = await client.post(
            "/api/chat", json={"session_id": "web-1", "text": "баланс"}
        )
    assert resp.status_code == 200
    assert resp.json()["action"] == "confirm"
    assert _StubClient.last_call["url"].endswith("/chat")
    assert _StubClient.last_call["json"]["session_id"] == "web-1"


@pytest.mark.asyncio
async def test_chat_rejects_empty_text(client):
    resp = await client.post("/api/chat", json={"session_id": "web-2", "text": "  "})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stt_rejects_empty_audio(client):
    resp = await client.post("/api/stt", files={"file": ("a.webm", b"", "audio/webm")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stt_transcodes_browser_audio_to_wav(client):
    """Browser WebM/MP4 recordings are ffmpeg-transcoded to WAV before STT —
    the speech service's decoder does not read browser container formats."""
    _StubClient.response = _StubResponse(json_data={"text": "баланс"})
    with (
        patch.object(gateway, "_to_wav", new=AsyncMock(return_value=b"RIFFwav")) as to_wav,
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        resp = await client.post(
            "/api/stt", files={"file": ("voice.webm", b"webm-bytes", "audio/webm")}
        )
    assert resp.status_code == 200
    assert resp.json() == {"text": "баланс"}
    to_wav.assert_awaited_once_with(b"webm-bytes")
    sent_name, sent_bytes, sent_mime = _StubClient.last_call["files"]["file"]
    assert sent_name == "audio.wav" and sent_bytes == b"RIFFwav" and sent_mime == "audio/wav"


class TestTTSTruncation:
    def test_short_text_untouched(self):
        assert gateway._tts_text("Готово!") == "Готово!"

    def test_long_text_cut_at_sentence_boundary(self):
        text = "Первое предложение. " + "х" * 400
        out = gateway._tts_text(text)
        assert out == "Первое предложение."

    def test_no_boundary_hard_cut(self):
        out = gateway._tts_text("б" * 400)
        assert len(out) == gateway.TTS_MAX_CHARS


@pytest.mark.asyncio
async def test_tts_uses_kazakh_voice_for_kk(client):
    _StubClient.response = _StubResponse(content=b"mp3bytes")
    with patch.object(gateway.httpx, "AsyncClient", _StubClient):
        resp = await client.post("/api/tts", json={"text": "Сәлем", "lang": "kk-KZ"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/mpeg")
    assert _StubClient.last_call["json"]["voice"] == gateway.TTS_VOICE_KK
    assert _StubClient.last_call["json"]["format"] == "MP3"


@pytest.mark.asyncio
async def test_rate_limit_trips(client):
    # Pre-fill the caller's window to the limit; the next request must 429.
    now = time.monotonic()
    ip = "127.0.0.1"  # ASGITransport default client host
    gateway._hits[ip].extend([now] * gateway.RATE_LIMIT_PER_MIN)
    resp = await client.post("/api/chat", json={"session_id": "web-3", "text": "hi"})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_index_serves_ui(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "sphere" in resp.text  # the digital sphere canvas is present
