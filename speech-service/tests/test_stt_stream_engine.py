"""Unit tests for the streaming STT session-options builder — pure protobuf
construction, no network calls (connectivity is verified separately, live)."""
from app.engines.yandex.stt_stream import EOU_PAUSE_MS, SAMPLE_RATE_HERTZ, _session_options
from yandex.cloud.ai.stt.v3 import stt_pb2


def test_session_options_use_pcm_at_expected_rate():
    opts = _session_options("ru-RU")
    raw = opts.recognition_model.audio_format.raw_audio
    assert raw.audio_encoding == stt_pb2.RawAudio.LINEAR16_PCM
    assert raw.sample_rate_hertz == SAMPLE_RATE_HERTZ
    assert raw.audio_channel_count == 1


def test_session_options_whitelist_multiple_languages():
    opts = _session_options("ru-RU,kk-KZ")
    restriction = opts.recognition_model.language_restriction
    assert restriction.restriction_type == stt_pb2.LanguageRestrictionOptions.WHITELIST
    assert list(restriction.language_code) == ["ru-RU", "kk-KZ"]


def test_session_options_single_language():
    opts = _session_options("kk-KZ")
    assert list(opts.recognition_model.language_restriction.language_code) == ["kk-KZ"]


def test_session_options_real_time_processing():
    opts = _session_options("ru-RU")
    assert (
        opts.recognition_model.audio_processing_type
        == stt_pb2.RecognitionModelOptions.REAL_TIME
    )


def test_session_options_enables_end_of_utterance_detection():
    # This is the "algorithm that finds when the user gave enough context" —
    # Yandex's own pause-based EOU classifier, so a hands-free conversation
    # doesn't need a manual stop-tap after every turn.
    opts = _session_options("ru-RU")
    classifier = opts.eou_classifier.default_classifier
    assert classifier.type == stt_pb2.DefaultEouClassifier.DEFAULT
    assert classifier.max_pause_between_words_hint_ms == EOU_PAUSE_MS
