"""Unit tests for the live-streaming voice route (/ws/converse).

Uses the sync TestClient (Starlette's supported way to test WebSocket routes)
rather than the async httpx client the rest of the gateway tests use — the
two styles coexist fine in separate files.
"""
import asyncio
import json
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

import web.app as gateway
from tests.test_web_gateway import _StubClient, _StubResponse


class _FakeUpstreamConnection:
    """Stands in for the websockets connection to speechkit's /stt/stream."""

    def __init__(self, events: list[dict]):
        self.sent: list = []
        self._events = events

    async def send(self, data) -> None:
        self.sent.append(data)

    def __aiter__(self):
        return self._iter_events()

    async def _iter_events(self):
        for event in self._events:
            # Yields control back to the event loop between events so a
            # concurrently-sent browser control message (e.g. "bot_speaking")
            # is guaranteed to be processed before the next upstream event —
            # otherwise this is a race in real asyncio scheduling, not just
            # in the test.
            await asyncio.sleep(0.02)
            yield json.dumps(event)


class _FakeConnect:
    """Stands in for websockets.connect(uri, **kwargs) — an async context
    manager factory, called once per /ws/converse turn."""

    def __init__(self, upstream: _FakeUpstreamConnection):
        self.upstream = upstream
        self.calls: list = []

    def __call__(self, uri, **kwargs):
        self.calls.append({"uri": uri, **kwargs})
        return self

    async def __aenter__(self):
        return self.upstream

    async def __aexit__(self, *args):
        return False


def test_ws_converse_relays_partials_then_sends_final_reply():
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [
            {"type": "partial", "text": "перевед"},
            {"type": "final", "text": "переведи 5000 на счёт"},
            {"type": "done"},
        ]
    )
    fake_connect = _FakeConnect(upstream)
    operation = {"summary": "Перевод 5000", "status": "success",
                 "tx_id": "MOCK-1", "channel": "web"}
    _StubClient.responses = [
        _StubResponse(json_data={"action": "reply", "message": "Готово!",
                                  "speech": None, "lang": "ru-RU",
                                  "operation": operation}),  # chat
        _StubResponse(content=b"mp3bytes"),                 # tts
    ]

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-1", "lang": "ru-RU"})
            ws.send_bytes(b"\x00" * 640)
            ws.send_json({"action": "end"})

            partial = ws.receive_json()
            reply = ws.receive_json()

    assert partial == {"type": "partial", "text": "перевед"}
    assert reply["type"] == "reply"
    assert reply["message"] == "Готово!"
    assert reply["operation"] == operation
    assert reply["audio"] is not None

    # The chat call used the FINAL transcript, not the partial fragment.
    chat_call = _StubClient.calls[0]
    assert chat_call["json"]["text"] == "переведи 5000 на счёт"
    assert chat_call["json"]["session_id"] == "u-stream-1"

    # session opened with the requested language, audio + end control relayed upstream.
    assert fake_connect.calls[0]["uri"] == gateway.SPEECH_STREAM_URL
    assert json.loads(upstream.sent[0]) == {"lang": "ru-RU"}
    assert b"\x00" * 640 in upstream.sent
    assert json.loads(upstream.sent[-1]) == {"action": "end"}


def test_ws_converse_forwards_user_name_from_first_message():
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [{"type": "final", "text": "привет"}, {"type": "done"}]
    )
    fake_connect = _FakeConnect(upstream)
    _StubClient.responses = [
        _StubResponse(json_data={"action": "reply", "message": "Привет, Санжар!",
                                  "speech": None, "lang": "ru-RU"}),
        _StubResponse(content=b"mp3bytes"),
    ]

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-3", "user_name": "Санжар"})
            ws.send_json({"action": "end"})
            ws.receive_json()

    chat_call = _StubClient.calls[0]
    assert chat_call["json"]["user_name"] == "Санжар"


def test_ws_converse_no_utterance_sends_no_reply():
    """If the session ends before any final arrives, there's nothing to
    reply to — no chat call, no empty placeholder reply either."""
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection([{"type": "done"}])
    fake_connect = _FakeConnect(upstream)

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-2", "lang": "ru-RU"})
            ws.send_json({"action": "end"})

    assert _StubClient.calls == []


def test_ws_converse_handles_multiple_turns_in_one_session():
    """The core hands-free capability: several utterances, detected by
    Yandex's own end-of-utterance classifier, each get their own reply
    without the browser reconnecting or re-sending "end" in between."""
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [
            {"type": "final", "text": "какой у меня баланс"},
            {"type": "partial", "text": "переве"},
            {"type": "final", "text": "переведи 1000 тенге на счёт KZ1"},
            {"type": "done"},
        ]
    )
    fake_connect = _FakeConnect(upstream)
    _StubClient.responses = [
        _StubResponse(json_data={"action": "reply", "message": "Баланс: 10000 тенге",
                                  "speech": None, "lang": "ru-RU"}),   # chat turn 1
        _StubResponse(content=b"mp3-1"),                              # tts turn 1
        _StubResponse(json_data={"action": "confirm", "message": "Перевести 1000?",
                                  "speech": None, "lang": "ru-RU"}),   # chat turn 2
        _StubResponse(content=b"mp3-2"),                              # tts turn 2
    ]

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-multi"})

            reply1 = ws.receive_json()
            partial = ws.receive_json()
            reply2 = ws.receive_json()

    assert reply1["message"] == "Баланс: 10000 тенге"
    assert partial == {"type": "partial", "text": "переве"}
    assert reply2["message"] == "Перевести 1000?"
    assert reply2["action"] == "confirm"

    # Two separate chat calls, one per detected utterance, same session.
    chat_calls = [c for c in _StubClient.calls if c["url"].endswith("/chat")]
    assert len(chat_calls) == 2
    assert chat_calls[0]["json"]["text"] == "какой у меня баланс"
    assert chat_calls[1]["json"]["text"] == "переведи 1000 тенге на счёт KZ1"
    assert all(c["json"]["session_id"] == "u-stream-multi" for c in chat_calls)


def test_ws_converse_interrupt_word_stops_bot_without_a_chat_call():
    """Saying "stop" while the bot is mid-reply cuts it off — and must never
    itself be sent to chat as if it were a real banking request."""
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [{"type": "final", "text": "так, стоп"}, {"type": "done"}]
    )
    fake_connect = _FakeConnect(upstream)

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-interrupt"})
            ws.send_json({"action": "bot_speaking", "value": True})

            reply = ws.receive_json()
            ws.send_json({"action": "end"})

    assert reply == {"type": "interrupt"}
    assert _StubClient.calls == []


def test_ws_converse_kazakh_interrupt_word_stops_bot():
    """The interrupt list isn't Russian/English-only — a Kazakh "тоқта"
    (stop) must cut the bot off just like the Russian/English words do."""
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [{"type": "final", "text": "жарайды, тоқта"}, {"type": "done"}]
    )
    fake_connect = _FakeConnect(upstream)

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-interrupt-kk"})
            ws.send_json({"action": "bot_speaking", "value": True})

            reply = ws.receive_json()
            ws.send_json({"action": "end"})

    assert reply == {"type": "interrupt"}
    assert _StubClient.calls == []


def test_ws_converse_ignores_non_interrupt_speech_while_bot_speaking():
    """No echo cancellation — anything heard mid-reply that ISN'T an
    interrupt word is presumed to be the bot hearing itself and dropped."""
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [{"type": "final", "text": "какая-то случайная фраза"}, {"type": "done"}]
    )
    fake_connect = _FakeConnect(upstream)

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-echo"})
            ws.send_json({"action": "bot_speaking", "value": True})
            ws.send_json({"action": "end"})

    assert _StubClient.calls == []


def test_ws_converse_suppresses_reply_when_not_understood():
    """Ambient chatter that the classifier can't tie to a real request stays
    silent instead of interrupting with "I didn't understand"."""
    _StubClient.calls = []
    upstream = _FakeUpstreamConnection(
        [{"type": "final", "text": "и потом мы пошли в кино"}, {"type": "done"}]
    )
    fake_connect = _FakeConnect(upstream)
    _StubClient.responses = [
        _StubResponse(json_data={"action": "reply", "message": "Не совсем понял...",
                                  "speech": None, "lang": "ru-RU", "understood": False}),
        _StubResponse(content=b"mp3bytes"),
    ]

    with (
        patch.object(gateway.websockets, "connect", fake_connect),
        patch.object(gateway.httpx, "AsyncClient", _StubClient),
    ):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-ambient"})
            ws.send_json({"action": "end"})
            # No "reply" (or anything else) should ever arrive. There's
            # nothing to synchronize on (the suppressed path sends nothing),
            # so give the server task a moment to actually finish the turn
            # before checking what it did.
            time.sleep(0.15)

    # Classification (and, today, a wasted TTS call) still ran server-side,
    # but nothing was ever sent back to the client to interrupt with.
    chat_calls = [c for c in _StubClient.calls if c["url"].endswith("/chat")]
    assert len(chat_calls) == 1
