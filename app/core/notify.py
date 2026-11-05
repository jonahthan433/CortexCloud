"""Telegram outbound alerting.

Single destination for operational alerts (payment settlement failures,
proof rejections, rate-limit breaches). No-op unless both TELEGRAM_BOT_TOKEN
and TELEGRAM_ALERT_CHAT_ID are configured, so a missing destination never
breaks the request path and never looks like a delivered alert.

The bot token is read from the service environment only — never logged,
never returned by any endpoint, never committed.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("cortexcloud.notify")

API = "https://api.telegram.org/bot{token}/sendMessage"


async def notify(text: str) -> bool:
    """Send one alert. Returns True only on a Telegram HTTP 200."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat = settings.TELEGRAM_ALERT_CHAT_ID
    if not token or not chat:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                API.format(token=token),
                json={
                    "chat_id": chat,
                    "text": text[:4000],
                    "disable_web_page_preview": True,
                },
            )
        if r.status_code != 200:
            logger.warning(f"telegram alert not delivered: HTTP {r.status_code}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"telegram alert error: {type(e).__name__}")
        return False


def format_alert(event: str, count: int, fields: dict) -> str:
    """Compact, secret-free alert body."""
    detail = " ".join(f"{k}={v}" for k, v in fields.items()
                      if k in ("payer", "reason", "ip", "bucket"))
    return f"CortexCloud alert: {event} (count={count}) {detail}".strip()
