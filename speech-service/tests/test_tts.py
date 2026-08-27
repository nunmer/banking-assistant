from unittest.mock import MagicMock, patch

import pytest

from app.core.auth import require_api_key
from app.main import app


@pytest.fixture(autouse=True)
def _no_api_key_required():
    # These tests exercise synthesis/speed logic, not auth — bypass it
    # regardless of the environment's API_KEY_ENABLED setting.
    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)


def test_list_voices(client):
    r = client.get("/tts/voices")
    assert r.status_code == 200
    data = r.json()
    assert "voices" in data
    assert "engine" in data
    assert len(data["voices"]) > 0


def test_synthesize_empty_text(client):
    r = client.post("/tts/synthesize", json={"text": "   "})
    assert r.status_code == 400


def test_synthesize_invalid_engine(client):
    r = client.get("/tts/voices?engine=nonexistent")
    assert r.status_code == 400
    assert "Unknown" in r.json()["detail"]


def test_synthesize_returns_audio(client, sample_wav):
    fake_audio = b"RIFF" + b"\x00" * 36  # minimal fake WAV
    with patch("app.engines.yandex.tts.YandexTTSEngine.synthesize", return_value=fake_audio):
        r = client.post("/tts/synthesize", json={"text": "hello", "voice": "jane", "format": "WAV"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == fake_audio


def test_synthesize_defaults_to_faster_than_neutral_speed(client):
    # A request that omits "speed" must still ask for a livelier-than-1.0
    # pace — that's the whole point of the default living server-side.
    fake_audio = b"RIFF" + b"\x00" * 36
    with patch(
        "app.engines.yandex.tts.YandexTTSEngine.synthesize", return_value=fake_audio
    ) as synth:
        r = client.post("/tts/synthesize", json={"text": "hello"})
    assert r.status_code == 200
    assert synth.call_args.kwargs["speed"] == 1.15


def test_synthesize_speed_is_overridable(client):
    fake_audio = b"RIFF" + b"\x00" * 36
    with patch(
        "app.engines.yandex.tts.YandexTTSEngine.synthesize", return_value=fake_audio
    ) as synth:
        r = client.post("/tts/synthesize", json={"text": "hello", "speed": 1.0})
    assert r.status_code == 200
    assert synth.call_args.kwargs["speed"] == 1.0


def test_yandex_synthesize_sends_speed_hint():
    """The Yandex request body must carry a distinct {"speed": ...} hint —
    it's a separate Hints oneof entry from {"voice": ...}, not a merged dict."""
    from app.engines.yandex import tts as tts_module

    fake_resp = MagicMock()
    fake_resp.text = (
        '{"result": {"audioChunk": {"data": "' + __import__("base64").b64encode(b"x").decode() + '"}}}'
    )
    with patch.object(tts_module, "post", return_value=fake_resp) as post:
        tts_module.YandexTTSEngine().synthesize("hello", voice="marina", lang="ru-RU", speed=1.15)

    body = post.call_args[0][1]
    assert {"voice": "marina"} in body["hints"]
    assert {"speed": 1.15} in body["hints"]


def test_resolve_voice_corrects_russian_voice_on_kazakh():
    """kk-KZ must never be spoken by a Russian voice — fall back to madi."""
    from app.engines.yandex.tts import YandexTTSEngine

    resolve = YandexTTSEngine._resolve_voice
    assert resolve("jane", "kk-KZ") == "amira"   # russian voice → kazakh default
    assert resolve("madi", "kk-KZ") == "madi"    # kazakh voice kept as-is
    assert resolve("amira", "ru-RU") == "marina"  # kazakh voice → russian default
    assert resolve("marina", "ru-RU") == "marina"  # russian voice kept for russian
    assert resolve("john", "en-US") == "john"    # no dedicated en voice → passthrough
