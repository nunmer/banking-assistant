"""Configuration for the speech-api proxy service."""
import os

# URL of the ForteBank speech-service (hosted on port 8000).
# Inside Docker: use host.docker.internal to reach the host.
# In production: point to the real service URL.
SPEECH_SERVICE_URL = os.getenv("SPEECH_SERVICE_URL", "http://host.docker.internal:8000")

# Engine passed to the speech-service (yandex | whisper | …).
SPEECH_ENGINE = os.getenv("SPEECH_ENGINE", "yandex")

# Default language when none is provided by the caller.
DEFAULT_LANG = os.getenv("SPEECH_DEFAULT_LANG", "ru-RU")

# Per-language TTS voice names.  The speech-service picks the voice
# from the "voice" field in the TTS request body.
TTS_VOICE_DEFAULT = os.getenv("TTS_VOICE_DEFAULT", "jane")
TTS_VOICE: dict[str, str] = {
    "ru-RU": os.getenv("TTS_VOICE_RU", "jane"),
    "kk-KZ": os.getenv("TTS_VOICE_KK", "amira"),  # Yandex SpeechKit Kazakh voice
    "en-US": os.getenv("TTS_VOICE_EN", "john"),
}
