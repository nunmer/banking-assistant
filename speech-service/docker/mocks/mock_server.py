"""Mock Yandex SpeechKit server for tests/local dev — no real API spend.

Point the service at it with:
    YANDEX_STT_URL=http://mock:8080/stt/v3/recognizeFileAsync
    YANDEX_TTS_URL=http://mock:8080/tts/v3/utteranceSynthesis

Run:
    uvicorn docker.mocks.mock_server:app --host 0.0.0.0 --port 8080
"""
import base64
import json

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI(title="Mock SpeechKit")


@app.post("/stt/v3/recognizeFileAsync")
async def recognize_async(request: Request):
    return {"id": "mock-operation-id"}


@app.get("/stt/v3/getRecognition")
def get_recognition(operationId: str = ""):
    body = json.dumps({
        "result": {
            "channelTag": "0",
            "final": {
                "alternatives": [
                    {"text": "mock transcript", "startTimeMs": 0, "endTimeMs": 1000}
                ]
            },
            "audioCursors": {"finalIndex": "0"},
        }
    })
    return PlainTextResponse(body)


@app.post("/tts/v3/utteranceSynthesis")
async def synthesize(request: Request):
    audio = base64.b64encode(b"RIFFmockwavdata").decode()
    body = json.dumps({"result": {"audioChunk": {"data": audio}}})
    return PlainTextResponse(body)
