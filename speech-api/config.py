"""Environment-driven configuration for the speech-api wrapper."""
import os

PROVIDER = os.getenv("SPEECH_PROVIDER", "whisper")  # speechkit | whisper
DEFAULT_LANG = os.getenv("SPEECH_DEFAULT_LANG", "ru-RU")

# speechkit provider — proxies to the existing speech-service
# (https://github.com/nunmer/speechkit).
SPEECHKIT_URL = os.getenv("SPEECHKIT_URL", "http://host.docker.internal:8000")
SPEECHKIT_ENGINE = os.getenv("SPEECHKIT_ENGINE", "yandex")
SPEECHKIT_TTS_VOICE = os.getenv("SPEECHKIT_TTS_VOICE", "jane")

# whisper provider — local faster-whisper.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
