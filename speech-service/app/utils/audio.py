import io
import wave

import numpy as np
import soundfile as sf

TARGET_RATE = 16000

# Browser tap-to-start/tap-to-stop recordings carry dead air at both ends
# (the gap between tapping and actually speaking). Confirmed by direct
# testing: GigaAM returns an empty transcript whenever that silence is a
# large fraction of the clip, even though the speech itself is perfectly
# audible — trimming it to just the speech (plus a small margin) fixes
# transcription reliably. Kept here (not engine-specific) since no engine
# benefits from silence padding.
_WINDOW_MS = 20
_PADDING_MS = 150
_MIN_THRESHOLD = 200.0
_THRESHOLD_FACTOR = 3.0


def _trim_silence(samples: np.ndarray, rate: int) -> np.ndarray:
    win = max(1, int(rate * _WINDOW_MS / 1000))
    n_windows = len(samples) // win
    if n_windows < 2:
        return samples

    trimmed_len = n_windows * win
    windows = samples[:trimmed_len].astype(np.float64).reshape(n_windows, win)
    rms = np.sqrt(np.mean(windows**2, axis=1))

    # Noise floor from the *quiet* end of the distribution, not the median —
    # a long, mostly-loud recording's median RMS is itself speech-level, which
    # would push the threshold high enough to clip real (if softer) words at
    # the edges. The 10th percentile reliably lands on true silence/room noise
    # even in continuous speech, since brief pauses between words/sentences
    # are common.
    noise_floor = np.percentile(rms, 10)
    threshold = max(_MIN_THRESHOLD, _THRESHOLD_FACTOR * noise_floor)
    voiced = np.where(rms >= threshold)[0]
    if len(voiced) == 0:
        return samples  # looks like silence throughout — let it fail naturally downstream

    pad = int(rate * _PADDING_MS / 1000)
    start = max(0, voiced[0] * win - pad)
    end = min(len(samples), (voiced[-1] + 1) * win + pad)
    return samples[start:end]


def to_pcm_wav(data: bytes) -> bytes:
    """Normalize any audio soundfile can read to mono 16-bit 16kHz PCM WAV."""
    samples, rate = sf.read(io.BytesIO(data), dtype="int16", always_2d=True)

    if samples.shape[1] > 1:
        samples = samples.mean(axis=1).astype(np.int16)
    else:
        samples = samples[:, 0]

    if rate != TARGET_RATE:
        ratio = TARGET_RATE / rate
        new_len = int(len(samples) * ratio)
        indices = (np.arange(new_len) / ratio).astype(np.float64)
        idx0 = indices.astype(int)
        idx1 = np.clip(idx0 + 1, 0, len(samples) - 1)
        frac = indices - idx0
        samples = (samples[idx0] * (1 - frac) + samples[idx1] * frac).astype(np.int16)

    samples = _trim_silence(samples, TARGET_RATE)

    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(samples.tobytes())
    return out.getvalue()


def wav_duration(wav_bytes: bytes) -> float:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def ms_to_timestamp(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
