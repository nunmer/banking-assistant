"""Audio file storage on a shared volume (mounted into API + worker)."""
import os
import uuid

from app.core.config import settings


def save_audio(data: bytes) -> str:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4().hex}.wav")
    with open(path, "wb") as f:
        f.write(data)
    return path


def load_audio(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def delete_audio(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass
