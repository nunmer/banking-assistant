"""Low-level HTTP transport for the self-hosted GigaAM STT server.

OpenAI-compatible /v1/audio/transcriptions (multipart), same shape as
Whisper-style servers — plain REST, no gRPC.
"""
import subprocess

import requests

from app.core.config import settings


class GigaamAPIError(Exception):
    pass


def _to_mulaw(wav: bytes) -> bytes:
    """Re-encode PCM16 WAV as mu-law before sending to GigaAM.

    Confirmed by direct testing: this server transcribes mu-law-encoded WAV
    correctly (mono or stereo, 8kHz or 16kHz alike) but silently returns an
    empty transcript for standard PCM16 WAV — the exact format
    app.utils.audio.to_pcm_wav produces for every other engine/caller. This
    is a workaround for that server-side quirk, not a GigaAM requirement
    documented anywhere; revisit if a future GigaAM version fixes PCM input.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-acodec", "pcm_mulaw", "-f", "wav", "pipe:1"],
        input=wav, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise GigaamAPIError(
            f"ffmpeg mu-law transcode failed: {proc.stderr.decode(errors='replace')[:300]}"
        )
    return proc.stdout


def transcribe_file(
    audio: bytes, model: str, temperature: float = 0.0,
    response_format: str | None = None,
) -> dict:
    data = {"model": model, "temperature": str(temperature)}
    if response_format:
        data["response_format"] = response_format
    audio = _to_mulaw(audio)
    try:
        resp = requests.post(
            settings.GIGAAM_STT_URL,
            files={"file": ("audio.wav", audio, "audio/wav")},
            data=data,
            timeout=settings.GIGAAM_TIMEOUT,
            # requests honors HTTP_PROXY/HTTPS_PROXY env vars by default, which
            # corrupts requests to this internal-LAN host through a corporate
            # proxy that can't reach it properly — explicitly disable, same
            # reasoning as yandex/client.py's opt-in-only proxy handling.
            proxies={"http": None, "https": None},
        )
    except requests.RequestException as e:
        raise GigaamAPIError(f"Request to {settings.GIGAAM_STT_URL} failed: {e}") from e
    if not resp.ok:
        raise GigaamAPIError(f"API error {resp.status_code}: {resp.text}")
    return resp.json()
