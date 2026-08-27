"""Qwen3-TTS engine (self-hosted, OpenAI-compatible speech API).

Its request shape only takes model/input/voice/language — no format or
speed parameter — so the backend always renders WAV (per the reference
curl's --output output.wav). Any other requested `fmt` is transcoded
locally via ffmpeg so callers (e.g. web/app.py, which always asks for MP3
for browser playback) get the container they actually asked for rather than
mislabeled WAV bytes.
"""
import subprocess

from app.engines.base import TTSEngine, TTSEngineType, EngineError
from app.engines.qwen.client import QwenAPIError, synthesize_speech

VOICES = ["vivian"]

LANG_NAME = {
    "ru": "Russian",
    "kk": "Kazakh",
    "en": "English",
}

# ffmpeg output args per TTSEngine `fmt` value.
_FFMPEG_ARGS = {
    "MP3": ["-f", "mp3", "-codec:a", "libmp3lame"],
    "OGG_OPUS": ["-f", "ogg", "-codec:a", "libopus"],
}


def _transcode(wav: bytes, fmt: str) -> bytes:
    args = _FFMPEG_ARGS.get(fmt.upper())
    if args is None:
        raise EngineError(f"Qwen TTS engine cannot produce fmt={fmt!r} (WAV in, MP3/OGG_OPUS out)")
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *args, "pipe:1"],
        input=wav, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise EngineError(f"ffmpeg transcode to {fmt} failed: {proc.stderr.decode(errors='replace')[:300]}")
    return proc.stdout


class QwenTTSEngine(TTSEngine):
    @property
    def engine_type(self) -> TTSEngineType:
        return TTSEngineType.QWEN

    def list_voices(self) -> list[str]:
        return VOICES

    def synthesize(self, text: str, voice: str = "vivian", lang: str = "ru-RU",
                   fmt: str = "WAV", speed: float = 1.15) -> bytes:
        language = LANG_NAME.get((lang or "")[:2].lower(), "English")
        try:
            wav = synthesize_speech(text, voice, language)
        except QwenAPIError as e:
            raise EngineError(str(e)) from e
        if fmt.upper() == "WAV":
            return wav
        return _transcode(wav, fmt)
