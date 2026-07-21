"""Best-effort Telegram notifications for operations executed elsewhere.

When a Telegram-authenticated user completes an operation in the Mini App /
web client, their Telegram chat gets a short message about it — so both
surfaces show the same history as it happens. Telegram sessions use the
numeric Telegram user id as session_id, which doubles as the chat id.
"""
import logging
import os

import httpx

logger = logging.getLogger("orchestrator.notify")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")


def is_telegram_session(session_id: str) -> bool:
    """Telegram sessions are the numeric user id; browser sessions are UUIDs."""
    return session_id.isdigit()


async def telegram_operation(session_id: str, summary: str, result_message: str) -> None:
    """Send an operation record to the user's Telegram chat; never raises."""
    if not TELEGRAM_TOKEN or not is_telegram_session(session_id):
        return
    text = f"🌐 {summary}\n{result_message}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": int(session_id), "text": text},
            )
            if resp.status_code != 200:
                logger.warning("telegram notify failed %s: %s", resp.status_code, resp.text[:200])
    except httpx.HTTPError as e:
        logger.warning("telegram notify error for %s: %s", session_id, e)
