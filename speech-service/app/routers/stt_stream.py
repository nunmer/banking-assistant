"""Real-time STT over WebSocket — bridges a caller's audio-chunk stream to a
Yandex gRPC RecognizeStreaming session and relays partial/final text back.

Protocol (caller = the banking-assistant `web` gateway, not the browser
directly — same trust boundary as the existing REST endpoints):
  1. Caller connects, then sends one JSON text message: {"lang": "ru-RU,kk-KZ"}.
  2. Caller sends binary frames: raw PCM16LE mono @ 16kHz chunks.
  3. Caller may send {"action": "end"} to signal no more audio.
  4. Server sends JSON text messages: {"type": "partial"|"final", "text": ...},
     and finally {"type": "done"} once the stream closes, or
     {"type": "error", "detail": ...} on failure.
"""
import asyncio
import json
import logging

import grpc
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.engines.yandex.stt_stream import StreamingSession

logger = logging.getLogger("speech_service.stt_stream")

router = APIRouter()


async def _pump_client_to_session(ws: WebSocket, session: StreamingSession) -> None:
    """Relay caller frames into the gRPC session until disconnect or "end"."""
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            break
        data = message.get("bytes")
        if data is not None:
            await session.send_chunk(data)
            continue
        text = message.get("text")
        if text is not None:
            try:
                control = json.loads(text)
            except json.JSONDecodeError:
                continue
            if control.get("action") == "end":
                break
    await session.end()


async def _pump_session_to_client(ws: WebSocket, session: StreamingSession) -> None:
    """Relay partial/final transcript events back to the caller as JSON."""
    async for event in session.responses():
        try:
            await ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            # Caller went away mid-stream — nothing left to relay to.
            return


@router.websocket("/stream")
async def stt_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        first = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    lang = first.get("lang") or "ru-RU"

    session = StreamingSession(lang)
    try:
        # Both directions run concurrently: audio keeps flowing in while
        # transcripts flow out — a streaming session is bidirectional, not
        # request-then-response.
        to_session = asyncio.create_task(_pump_client_to_session(websocket, session))
        to_client = asyncio.create_task(_pump_session_to_client(websocket, session))
        await asyncio.gather(to_session, to_client)
        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
    except grpc.RpcError as e:
        logger.error("streaming STT gRPC error: %s", e)
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        await session.close()
