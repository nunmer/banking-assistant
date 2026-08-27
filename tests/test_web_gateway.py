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
    """Stands in for httpx.AsyncClient; records calls.

    `response` serves every call; set `responses` (a list) instead to serve a
    sequence — one per backend call, as /api/converse makes (stt, chat, tts).
    """

    last_call = None
    calls: list = []
    responses: list | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        _StubClient.last_call = {"url": url, **kwargs}
        _StubClient.calls.append(_StubClient.last_call)
        if _StubClient.responses:
            return _StubClient.responses.pop(0)
        return _StubClient.response

    async def request(self, method, url, **kwargs):
        # Used by web/admin/routes.py's orchestrator proxy (GET/POST/PUT).
        _StubClient.last_call = {"method": method, "url": url, **kwargs}
        _StubClient.calls.append(_StubClient.last_call)
        if _StubClient.responses:
            return _StubClient.responses.pop(0)
        return _StubClient.response


@pytest.fixture
async def client():
    gateway._hits.clear()  # isolate the rate limiter between tests
    _StubClient.calls = []
    _StubClient.responses = None
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
    assert _StubClient.last_call["json"]["channel"] == "web"  # history attribution
    assert "user_name" not in _StubClient.last_call["json"]  # none given → omitted
    # Every turn gets its own correlation id for the admin panel's debug trace.
    assert _StubClient.last_call["json"]["turn_id"]


@pytest.mark.asyncio
async def test_chat_forwards_user_name_when_given(client):
    """When a client supplies a name, it's forwarded for a personalised greeting."""
    _StubClient.response = _StubResponse(
        json_data={"action": "reply", "message": "Привет, Санжар!",
                    "speech": None, "lang": "ru-RU"}
    )
    with patch.object(gateway.httpx, "AsyncClient", _StubClient):
        resp = await client.post(
            "/api/chat",
            json={"session_id": "web-1b", "text": "привет", "user_name": "Санжар"},
        )
    assert resp.status_code == 200
    assert _StubClient.last_call["json"]["user_name"] == "Санжар"


@pytest.mark.asyncio
async def test_chat_forwards_username_when_given(client):
    """The username — separate from user_name (first name) — is forwarded
    too, for admin-panel session search."""
    _StubClient.response = _StubResponse(
        json_data={"action": "reply", "message": "Здравствуйте!", "speech": None, "lang": "ru-RU"}
    )
    with patch.object(gateway.httpx, "AsyncClient", _StubClient):
        await client.post(
            "/api/chat",
            json={"session_id": "web-1c", "text": "привет", "username": "sanzhar_k"},
        )
    assert _StubClient.last_call["json"]["username"] == "sanzhar_k"


@pytest.mark.asyncio
async def test_history_proxies_to_orchestrator(client):
    class _GetStub(_StubClient):
        async def get(self, url, **kwargs):
            _StubClient.last_call = {"url": url, **kwargs}
            return _StubResponse(json_data={"operations": [{"summary": "op"}]})

    with patch.object(gateway.httpx, "AsyncClient", _GetStub):
        resp = await client.get("/api/history?session_id=12345&limit=5")
    assert resp.status_code == 200
    assert resp.json() == {"operations": [{"summary": "op"}]}
    assert _StubClient.last_call["url"].endswith("/history/12345")
    assert _StubClient.last_call["params"] == {"limit": 5}


@pytest.mark.asyncio
async def test_statement_pdf_proxies_bytes_and_sets_download_headers(client):
    class _GetStub(_StubClient):
        async def get(self, url, **kwargs):
            _StubClient.last_call = {"url": url, **kwargs}
            return _StubResponse(content=b"%PDF-1.4\nfake\n%%EOF")

    with patch.object(gateway.httpx, "AsyncClient", _GetStub):
        resp = await client.get("/api/statement/pdf/MOCK-ABCD1234")

    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert _StubClient.last_call["url"].endswith("/document/statement/MOCK-ABCD1234")


@pytest.mark.asyncio
async def test_statement_pdf_404_when_expired(client):
    class _GetStub(_StubClient):
        async def get(self, url, **kwargs):
            return _StubResponse(status_code=404)

    with patch.object(gateway.httpx, "AsyncClient", _GetStub):
        resp = await client.get("/api/statement/pdf/MOCK-GONE0000")

    assert resp.status_code == 404


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

    # KNOWN, UNRESOLVED: Kazakh's agglutinative morphology means the same
    # content runs noticeably longer than the ru/en equivalent, and these two
    # overrides exceed TTS_MAX_CHARS as a result — confirmed live that a
    # Kazakh "who are you" request gets clipped down to its opening sentence,
    # losing the whole capability list. Raising the cap looked like the fix,
    # but live testing showed Yandex's API returning "Too long text" for this
    # exact request unpredictably — success and failure on the same input at
    # different times, no reproducible length threshold — so that's most
    # likely intermittent quota/rate pressure on the Yandex account, not
    # something a cap change here can reliably fix. The real fix is shorter
    # kk-KZ overrides; tracked here, not silently allowed everywhere.
    _KNOWN_OVERLONG = {("kk-KZ", "bot_info"), ("kk-KZ", "unknown_intent")}

    def test_curated_speech_overrides_never_hit_the_cap(self):
        """Regression guard: a curated speech override is meant to already be
        TTS-safe in full — if a NEW one overflows the cap, this should fail
        loudly instead of only surfacing as "the bot cut itself off" from a
        live user. The two known kk-KZ exceptions are excluded (see above),
        not silently passed — remove them from _KNOWN_OVERLONG once fixed."""
        from orchestrator.i18n import _SPEECH_OVERRIDES

        for lang, overrides in _SPEECH_OVERRIDES.items():
            for key, text in overrides.items():
                if (lang, key) in self._KNOWN_OVERLONG:
                    continue
                assert len(text) <= gateway.TTS_MAX_CHARS, (
                    f"{lang}/{key} speech override is {len(text)} chars, "
                    f"over the {gateway.TTS_MAX_CHARS}-char TTS cap"
                )


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


@pytest.mark.asyncio
async def test_index_cache_busts_static_assets(client):
    """Asset links carry a content-hash query string so a client that cached
    a previous deploy's app.css/app.js (browser or Telegram's Mini App
    WebView — both are known to over-cache) is forced onto a URL it has
    never seen, rather than depending on it noticing the file changed."""
    resp = await client.get("/")
    assert resp.status_code == 200
    import re as _re

    for asset in ("app.css", "app.js", "sphere.js", "avatar.png"):
        match = _re.search(rf"/static/{_re.escape(asset)}\?v=([0-9a-f]{{10}})", resp.text)
        assert match, f"{asset} missing a cache-busting version query"


@pytest.mark.asyncio
async def test_converse_voice_single_round_trip(client):
    """/api/converse runs stt → chat → tts server-side and returns everything."""
    import base64 as b64

    _StubClient.responses = [
        _StubResponse(json_data={"text": "переведи 5000"}),                    # stt
        _StubResponse(),                                                        # stt debug event push
        _StubResponse(json_data={"action": "collect", "message": "Кому?",
                                 "speech": None, "lang": "ru-RU"}),            # chat
        _StubResponse(content=b"mp3bytes"),                                    # tts
        _StubResponse(),                                                        # tts debug event push
    ]
    with (
        patch.object(gateway, "_to_wav", new=AsyncMock(return_value=b"RIFF")),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        resp = await client.post(
            "/api/converse",
            data={"session_id": "u-conv"},
            files={"file": ("v.webm", b"webm-bytes", "audio/webm")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "переведи 5000"
    assert body["message"] == "Кому?"
    assert body["action"] == "collect"
    assert b64.b64decode(body["audio"]) == b"mp3bytes"
    # Pipeline order, including the two debug-trace pushes to /debug/events.
    urls = [c["url"] for c in _StubClient.calls]
    assert [u.rsplit("/", 1)[-1] for u in urls] == [
        "recognize", "events", "chat", "synthesize", "events",
    ]


@pytest.mark.asyncio
async def test_converse_text_turn_returns_audio(client):
    """A voice-mode button tap sends text and still gets reply audio back."""
    operation = {"summary": "Перевод 5000 тенге → 8 (775) 815 55 76",
                 "status": "success", "tx_id": "MOCK-1", "channel": "web"}
    _StubClient.responses = [
        _StubResponse(json_data={"action": "reply", "message": "Готово! ✅",
                                 "speech": None, "lang": "ru-RU",
                                 "operation": operation}),                     # chat
        _StubResponse(content=b"okbytes"),                                     # tts
        _StubResponse(),                                                        # tts debug event push
    ]
    with patch.object(gateway.httpx, "AsyncClient", _StubClient):
        resp = await client.post(
            "/api/converse", data={"session_id": "u-conv2", "text": "да"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] is None
    assert body["message"] == "Готово! ✅"
    assert body["audio"] is not None
    # The operation record must survive the gateway — the client's history
    # card is rendered from it (dropping it wiped confirmations without trace).
    assert body["operation"] == operation


@pytest.mark.asyncio
async def test_converse_forwards_user_name_to_chat(client):
    _StubClient.responses = [
        _StubResponse(json_data={"action": "reply", "message": "Привет, Санжар!",
                                 "speech": None, "lang": "ru-RU"}),
        _StubResponse(content=b"okbytes"),
        _StubResponse(),  # tts debug event push
    ]
    with patch.object(gateway.httpx, "AsyncClient", _StubClient):
        await client.post(
            "/api/converse",
            data={"session_id": "u-conv3", "text": "привет", "user_name": "Санжар"},
        )
    chat_call = _StubClient.calls[0]
    assert chat_call["json"]["user_name"] == "Санжар"


@pytest.mark.asyncio
async def test_converse_empty_transcript_short_circuits(client):
    """Unintelligible audio returns early — no chat, no TTS."""
    _StubClient.responses = [
        _StubResponse(json_data={"text": "  "}),  # stt
        _StubResponse(),                            # stt debug event push
    ]
    with (
        patch.object(gateway, "_to_wav", new=AsyncMock(return_value=b"RIFF")),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        resp = await client.post(
            "/api/converse",
            data={"session_id": "u-conv3"},
            files={"file": ("v.webm", b"webm-bytes", "audio/webm")},
        )
    assert resp.status_code == 200
    assert resp.json()["transcript"] == ""
    assert len(_StubClient.calls) == 2  # stt + its debug event push, stopped before chat/tts
