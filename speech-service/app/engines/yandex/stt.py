"""Yandex SpeechKit STT engine.

IMPORTANT (Kazakh recognition): the language list must be sent inside
``recognitionModel.languageRestriction`` with ``restrictionType=WHITELIST``.
Without WHITELIST the restriction type defaults to UNSPECIFIED, the language
codes are ignored, and Kazakh audio is silently mis-recognized as Russian.
"""
import base64
import io
import wave
from typing import Any

from app.engines.base import STTEngine, STTEngineType, EngineError
from app.engines.yandex.client import YandexAPIError, post, poll_result, iter_json_objects
from app.core.config import settings


class YandexSTTEngine(STTEngine):
    @property
    def engine_type(self) -> STTEngineType:
        return STTEngineType.YANDEX

    def recognize(self, audio: bytes, lang: str = "ru-RU") -> str:
        try:
            raw = self._poll(self._submit(audio, lang, speaker_labeling=False))
        except YandexAPIError as e:
            raise EngineError(str(e)) from e

        normalized: dict[tuple, str] = {}
        fallback: dict[tuple, str] = {}
        order: list[tuple] = []

        for obj in iter_json_objects(raw):
            result = obj.get("result", {})
            channel = str(result.get("channelTag", "0"))
            if "finalRefinement" in result:
                ref = result["finalRefinement"]
                alts = ref.get("normalizedText", {}).get("alternatives", [])
                if alts and alts[0].get("text"):
                    key = (channel, ref.get("finalIndex", self._segment_index(result)))
                    normalized[key] = alts[0]["text"]
                    if key not in order:
                        order.append(key)
            elif "final" in result:
                alts = result["final"].get("alternatives", [])
                if alts and alts[0].get("text"):
                    key = (channel, self._segment_index(result))
                    fallback[key] = alts[0]["text"]
                    if key not in order:
                        order.append(key)

        return " ".join(normalized.get(k) or fallback.get(k, "") for k in order).strip()

    def transcribe(self, audio: bytes, lang: str = "ru-RU") -> list[dict[str, Any]]:
        mono = self._wav_channels(audio) == 1
        try:
            raw = self._poll(self._submit(audio, lang, speaker_labeling=mono))
        except YandexAPIError as e:
            raise EngineError(str(e)) from e

        segments: dict[tuple, dict] = {}
        normalized: dict[tuple, str] = {}
        order: list[tuple] = []

        for obj in iter_json_objects(raw):
            result = obj.get("result", {})
            channel = str(result.get("channelTag", "0"))
            if "final" in result:
                alts = result["final"].get("alternatives", [])
                if not alts:
                    continue
                alt = alts[0]
                key = (channel, self._segment_index(result))
                segments[key] = {
                    "channel": channel,
                    "text": alt.get("text", ""),
                    "start_ms": int(alt.get("startTimeMs", 0)),
                    "end_ms": int(alt.get("endTimeMs", 0)),
                }
                if key not in order:
                    order.append(key)
            elif "finalRefinement" in result:
                ref = result["finalRefinement"]
                alts = ref.get("normalizedText", {}).get("alternatives", [])
                if alts:
                    normalized[(channel, ref.get("finalIndex", "0"))] = alts[0].get("text", "")

        channels: dict[str, dict] = {}
        for key in order:
            seg = segments[key]
            channel = channels.setdefault(
                seg["channel"], {"speaker": seg["channel"], "text": "", "utterances": []}
            )
            channel["utterances"].append({
                "text": normalized.get(key, seg["text"]),
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
            })

        for channel in channels.values():
            channel["text"] = " ".join(u["text"] for u in channel["utterances"]).strip()
        return list(channels.values())

    # -- private helpers --

    def _submit(self, audio: bytes, lang: str, speaker_labeling: bool) -> str:
        # `lang` may be a single tag ("kk-KZ") or a comma-separated set
        # ("ru-RU,kk-KZ"). A multi-language WHITELIST lets SpeechKit auto-detect
        # which language was spoken — so a user can switch mid-conversation.
        languages = [c.strip() for c in lang.split(",") if c.strip()] or [lang]
        model = {
            "audioFormat": {"containerAudio": {"containerAudioType": "WAV"}},
            "textNormalization": {"textNormalization": "TEXT_NORMALIZATION_ENABLED"},
            "languageRestriction": {
                "restrictionType": "WHITELIST",
                "languageCode": languages,
            },
        }
        body: dict[str, Any] = {
            "content": base64.b64encode(audio).decode(),
            "recognitionModel": model,
        }
        if speaker_labeling:
            body["speakerLabeling"] = {"speakerLabeling": "SPEAKER_LABELING_ENABLED"}

        resp = post(settings.YANDEX_STT_URL, body)
        op_id = resp.json().get("id")
        if not op_id:
            raise YandexAPIError(f"No operation id in STT response: {resp.text}")
        return op_id

    def _poll(self, operation_id: str) -> str:
        return poll_result(operation_id)

    @staticmethod
    def _segment_index(result: dict) -> str:
        return result.get("audioCursors", {}).get("finalIndex", "0")

    @staticmethod
    def _wav_channels(audio: bytes) -> int:
        try:
            with wave.open(io.BytesIO(audio), "rb") as w:
                return w.getnchannels()
        except (wave.Error, EOFError):
            return 1
