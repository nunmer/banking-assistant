"""Content hashing for deduplication."""
import hashlib


def stt_hash(kind: str, engine: str, lang: str, audio: bytes) -> str:
    """Stable hash of an STT request: kind + engine + lang + audio bytes."""
    h = hashlib.sha256()
    h.update(f"{kind}|{engine}|{lang}|".encode())
    h.update(audio)
    return h.hexdigest()


def tts_hash(text: str, voice: str, lang: str, fmt: str, speed: float) -> str:
    """Stable hash of a TTS request."""
    payload = f"{text}|{voice}|{lang}|{fmt}|{speed}".encode()
    return hashlib.sha256(payload).hexdigest()
