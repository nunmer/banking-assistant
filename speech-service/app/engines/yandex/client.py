"""Low-level HTTP transport for Yandex SpeechKit REST API v3.

Pure HTTPS/REST — no gRPC — so it works through corporate HTTP proxies and
firewalls that block HTTP/2.
"""
import json
import time
from typing import Iterator

import requests

from app.core.config import settings


POLL_ATTEMPTS = 30
POLL_DELAY = 2.0


class YandexAPIError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
        "x-folder-id": settings.YANDEX_FOLDER_ID,
        "Content-Type": "application/json",
    }


def _proxies() -> dict | None:
    proxy = (settings.YANDEX_HTTPS_PROXY or settings.YANDEX_HTTP_PROXY).strip()
    if proxy and "://" in proxy:
        return {"https": proxy, "http": proxy}
    return None


def _verify() -> bool:
    if not settings.YANDEX_SSL_VERIFY:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return settings.YANDEX_SSL_VERIFY


def post(url: str, body: dict) -> requests.Response:
    try:
        resp = requests.post(
            url, headers=_headers(), data=json.dumps(body),
            timeout=settings.YANDEX_TIMEOUT, verify=_verify(), proxies=_proxies(),
        )
    except requests.RequestException as e:
        raise YandexAPIError(f"Request to {url} failed: {e}") from e
    if not resp.ok:
        raise YandexAPIError(f"API error {resp.status_code}: {resp.text}")
    return resp


def get(url: str, params: dict | None = None) -> requests.Response:
    try:
        resp = requests.get(
            url, headers=_headers(), params=params,
            timeout=settings.YANDEX_TIMEOUT, verify=_verify(), proxies=_proxies(),
        )
    except requests.RequestException as e:
        raise YandexAPIError(f"Request to {url} failed: {e}") from e
    return resp


def poll_result(operation_id: str) -> str:
    stt_get_url = settings.YANDEX_STT_URL.replace("recognizeFileAsync", "getRecognition")
    params = {"operationId": operation_id}
    for _ in range(POLL_ATTEMPTS):
        r = get(stt_get_url, params=params)
        if r.status_code == 404:
            time.sleep(POLL_DELAY)
            continue
        if not r.ok:
            raise YandexAPIError(f"getRecognition error {r.status_code}: {r.text}")
        return r.text
    raise YandexAPIError(
        f"STT result not ready after {POLL_ATTEMPTS} polls for {operation_id}"
    )


def iter_json_objects(text: str) -> Iterator[dict]:
    """Yield each JSON object from a streamed response body."""
    decoder = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        obj, i = decoder.raw_decode(text, i)
        yield obj
