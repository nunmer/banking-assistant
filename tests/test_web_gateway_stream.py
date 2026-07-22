"""Unit tests for the live-streaming voice route (/ws/converse).

Uses the sync TestClient (Starlette's supported way to test WebSocket routes)
rather than the async httpx client the rest of the gateway tests use — the
two styles coexist fine in separate files.
"""
import json
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


def test_ws_converse_empty_transcript_short_circuits():
    upstream = _FakeUpstreamConnection([{"type": "done"}])
    fake_connect = _FakeConnect(upstream)

    with patch.object(gateway.websockets, "connect", fake_connect):
        with TestClient(gateway.app) as client, client.websocket_connect("/ws/converse") as ws:
            ws.send_json({"session_id": "u-stream-2", "lang": "ru-RU"})
            ws.send_json({"action": "end"})

            reply = ws.receive_json()

    assert reply == {"type": "reply", "message": None, "audio": None,
                      "action": None, "operation": None}
