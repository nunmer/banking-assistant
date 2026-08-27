import io
from unittest.mock import patch


def test_recognize_no_file(client):
    r = client.post("/stt/recognize")
    assert r.status_code == 422


def test_recognize_bad_audio(client):
    r = client.post(
        "/stt/recognize",
        data={"lang": "ru-RU"},
        files={"file": ("test.wav", b"not audio", "audio/wav")},
    )
    assert r.status_code == 400


def test_recognize_returns_text(client, sample_wav):
    with patch("app.engines.yandex.stt.YandexSTTEngine.recognize", return_value="hello world"):
        r = client.post(
            "/stt/recognize",
            data={"lang": "ru-RU"},
            files={"file": ("test.wav", sample_wav, "audio/wav")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "hello world"
    assert data["lang"] == "ru-RU"
    assert "engine" in data
    assert "duration_seconds" in data


def test_transcribe_returns_speakers(client, sample_wav):
    mock_channels = [
        {"speaker": "0", "text": "hello", "utterances": [
            {"text": "hello", "start_ms": 0, "end_ms": 1000}
        ]}
    ]
    with patch("app.engines.yandex.stt.YandexSTTEngine.transcribe", return_value=mock_channels):
        r = client.post(
            "/stt/transcribe",
            data={"lang": "ru-RU"},
            files={"file": ("test.wav", sample_wav, "audio/wav")},
        )
    assert r.status_code == 200
    data = r.json()
    assert "speakers" in data
    assert data["speakers"][0]["speaker"] == "0"
    assert "start" in data["speakers"][0]["utterances"][0]
    assert "end" in data["speakers"][0]["utterances"][0]


def test_transcribe_no_file(client):
    r = client.post("/stt/transcribe")
    assert r.status_code == 422
