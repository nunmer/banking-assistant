import base64

from app.engines.base import TTSEngine, TTSEngineType, EngineError
from app.engines.yandex.client import YandexAPIError, post, iter_json_objects
from app.core.config import settings


VOICES = ["marina", "jane", "madi", "amira", "saule", "zhanar"]

# SpeechKit v3 derives the spoken language from the voice — there is no separate
# language field. Classify each voice so a mismatched request (e.g. a Russian
# voice on Kazakh text) can be corrected rather than read with the wrong phonetics.
VOICE_LANG = {
    "marina": "ru", "jane": "ru",
    "amira": "kk", "madi": "kk", "saule": "kk", "zhanar": "kk",
}
# Default voice per language, used when the requested voice doesn't match `lang`.
# marina/amira are the pilot's primary voices — chosen for a warmer, more natural
# read than the earlier jane/madi defaults.
LANG_DEFAULT_VOICE = {"ru": "marina", "kk": "amira"}


class YandexTTSEngine(TTSEngine):
    @property
    def engine_type(self) -> TTSEngineType:
        return TTSEngineType.YANDEX

    def list_voices(self) -> list[str]:
        return VOICES

    @staticmethod
    def _resolve_voice(voice: str, lang: str) -> str:
        """Ensure the voice matches the requested language.

        Because the voice — not a separate flag — selects the spoken language,
        a Russian voice on Kazakh text would mispronounce it. When the requested
        voice doesn't belong to `lang`, fall back to that language's default
        voice (kk → amira, ru → marina). Languages without a dedicated voice
        (e.g. en-US) keep the requested voice.
        """
        lang_code = (lang or "")[:2].lower()
        default = LANG_DEFAULT_VOICE.get(lang_code)
        if default and VOICE_LANG.get(voice) != lang_code:
            return default
        return voice

    def synthesize(self, text: str, voice: str = "marina", lang: str = "ru-RU",
                   fmt: str = "WAV", speed: float = 1.15) -> bytes:
        voice = self._resolve_voice(voice, lang)
        body = {
            "text": text,
            "outputAudioSpec": {"containerAudio": {"containerAudioType": fmt}},
            "hints": [{"voice": voice}, {"speed": speed}],
        }
        try:
            resp = post(settings.YANDEX_TTS_URL, body)
        except YandexAPIError as e:
            raise EngineError(str(e)) from e

        audio = bytearray()
        for obj in iter_json_objects(resp.text):
            chunk = (obj.get("result") or obj).get("audioChunk", {})
            data = chunk.get("data", "")
            if data:
                audio.extend(base64.b64decode(data))
        if not audio:
            raise EngineError(f"TTS returned no audio: {resp.text[:300]}")
        return bytes(audio)
