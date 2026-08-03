"""
the402.ai provider webhook relay.

Receives signed job_dispatch webhooks from the402 marketplace, executes the
brief against the CortexCloud gateway (same ModelRouter the paid x402 routes
use), and delivers the result to the402's callback URL.

Security (trust boundary — fail closed):
  - No THE402_WEBHOOK_SECRET configured -> endpoint refuses (503).
  - Signature: X-Webhook-Signature "sha256=<hex>" = HMAC-SHA256(secret,
    f"{timestamp}.{raw_body}"), verified with hmac.compare_digest.
  - X-Webhook-Timestamp older than 5 minutes -> rejected (replay guard).
"""

import hashlib
import hmac
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.routing.router import ModelRouter
from app.schemas.openai import ChatCompletionRequest

logger = logging.getLogger("cortexcloud.x402.webhook")

router = APIRouter()

MAX_AGE_SECONDS = 300  # reject timestamps older than 5 min


def _verify_signature(secret: str, timestamp: str, signature: str, raw_body: bytes) -> bool:
    """Constant-time check of sha256=<hex> HMAC over `${timestamp}.${raw_body}`."""
    if not signature.startswith("sha256="):
        return False
    provided = signature[len("sha256="):]
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


@router.post("/webhook")
async def the402_webhook(req: Request, db: AsyncSession = Depends(get_db)):
    secret = settings.THE402_WEBHOOK_SECRET
    if not secret:
        return JSONResponse(status_code=503, content={"status": "unconfigured", "detail": "THE402_WEBHOOK_SECRET not set"})

    raw = await req.body()

    # Replay guard + signature verification
    try:
        ts = int(req.headers.get("X-Webhook-Timestamp", ""))
    except ValueError:
        return JSONResponse(status_code=401, content={"status": "invalid", "detail": "bad timestamp"})
    if abs(time.time() - ts) > MAX_AGE_SECONDS:
        return JSONResponse(status_code=401, content={"status": "invalid", "detail": "stale timestamp"})
    sig = req.headers.get("X-Webhook-Signature", "")
    if not _verify_signature(secret, str(ts), sig, raw):
        return JSONResponse(status_code=401, content={"status": "invalid", "detail": "bad signature"})

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"status": "invalid", "detail": "bad json"})

    if payload.get("type") != "job_dispatch":
        # Ignore non-dispatch events (request.created etc.) — idempotent
        return {"status": "ignored", "type": payload.get("type")}

    brief = payload.get("brief") or {}
    job_id = payload.get("job_id", "unknown")
    callback_url = payload.get("callback_url")
    correlation_id = f"the402-{job_id}-{uuid.uuid4().hex[:8]}"

    # Execute the brief through the same router the paid /x402/v1 routes use
    try:
        chat_request = ChatCompletionRequest.model_validate(brief)
        response, routed_model, latency_ms = await ModelRouter(db).route_chat_completion(
            chat_request, correlation_id
        )
        result = response.model_dump()
        logger.info(f"the402 job {job_id}: model={routed_model.name} latency_ms={int(latency_ms)}")
    except Exception as exc:  # noqa: BLE001 — deliver failure to marketplace
        logger.warning(f"the402 job {job_id} failed: {exc}")
        await _callback(callback_url, {"status": "failed", "message": str(exc)})
        return JSONResponse(status_code=502, content={"status": "failed", "detail": str(exc)})

    # Deliver via callback if configured; else return result inline
    if callback_url and settings.THE402_API_KEY:
        ok = await _callback(callback_url, {"status": "completed", "result": result, "message": "Completed"})
        if not ok:
            logger.warning(f"the402 job {job_id}: callback to {callback_url} failed")
        return {"status": "completed", "job_id": job_id, "callback_delivered": ok}
    return {"status": "completed", "job_id": job_id, "result": result}


async def _callback(callback_url: str | None, body: dict) -> bool:
    if not callback_url or not settings.THE402_API_KEY:
        return False
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(callback_url, json=body, headers={"X-API-Key": settings.THE402_API_KEY})
        return r.status_code < 300
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"the402 callback failed: {exc}")
        return False
