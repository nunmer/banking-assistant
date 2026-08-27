from app.services import dedup


def test_stt_hash_is_stable():
    a = dedup.stt_hash("recognize", "yandex", "ru-RU", b"audio-bytes")
    b = dedup.stt_hash("recognize", "yandex", "ru-RU", b"audio-bytes")
    assert a == b
    assert len(a) == 64


def test_stt_hash_varies_by_input():
    base = dedup.stt_hash("recognize", "yandex", "ru-RU", b"audio")
    assert base != dedup.stt_hash("transcribe", "yandex", "ru-RU", b"audio")
    assert base != dedup.stt_hash("recognize", "yandex", "kk-KZ", b"audio")
    assert base != dedup.stt_hash("recognize", "yandex", "ru-RU", b"other")


def test_tts_hash_varies_by_voice_and_format():
    base = dedup.tts_hash("hello", "jane", "ru-RU", "WAV", 1.15)
    assert base == dedup.tts_hash("hello", "jane", "ru-RU", "WAV", 1.15)
    assert base != dedup.tts_hash("hello", "madi", "ru-RU", "WAV", 1.15)
    assert base != dedup.tts_hash("hello", "jane", "ru-RU", "MP3", 1.15)


def test_tts_hash_varies_by_speed():
    # A speed change produces different audio — it must invalidate the cache,
    # not silently serve audio synthesized at the old rate.
    assert dedup.tts_hash("hello", "jane", "ru-RU", "WAV", 1.0) != \
        dedup.tts_hash("hello", "jane", "ru-RU", "WAV", 1.15)
