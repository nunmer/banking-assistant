import io
import wave

import numpy as np
import pytest

from app.utils.audio import to_pcm_wav, wav_duration, ms_to_timestamp


def _make_wav(rate: int, channels: int, seconds: float = 1.0) -> bytes:
    n = int(rate * seconds)
    samples = (np.sin(np.linspace(0, 6.28, n)) * 32767).astype(np.int16)
    if channels == 2:
        samples = np.stack([samples, samples], axis=1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def test_pcm_wav_passthrough():
    wav = _make_wav(16000, 1)
    result = to_pcm_wav(wav)
    with wave.open(io.BytesIO(result)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getsampwidth() == 2


def test_pcm_wav_resample():
    wav = _make_wav(8000, 1)
    result = to_pcm_wav(wav)
    with wave.open(io.BytesIO(result)) as wf:
        assert wf.getframerate() == 16000


def test_pcm_wav_stereo_to_mono():
    wav = _make_wav(16000, 2)
    result = to_pcm_wav(wav)
    with wave.open(io.BytesIO(result)) as wf:
        assert wf.getnchannels() == 1


def test_wav_duration():
    wav = _make_wav(16000, 1, seconds=2.5)
    assert abs(wav_duration(wav) - 2.5) < 0.01


def test_ms_to_timestamp():
    assert ms_to_timestamp(0) == "00:00:00.000"
    assert ms_to_timestamp(61500) == "00:01:01.500"
    assert ms_to_timestamp(3661000) == "01:01:01.000"


def test_invalid_audio_raises():
    with pytest.raises(Exception):
        to_pcm_wav(b"not audio data")
