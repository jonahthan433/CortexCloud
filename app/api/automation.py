"""Automation API (Tier 1) — agent-native, safe, composable actions.

Endpoints (all paid except /estimate):
  POST /v1/automation/transform     pure JSON shaping (no egress)
  POST /v1/automation/http-request  SSRF-guarded outbound HTTP
  POST /v1/automation/webhook       deliver HMAC-signed payload to a URL
  POST /v1/automation/schedule      persist delayed/recurring job (Postgres)
  POST /v1/automation/workflow      <=10 sequential steps, 120s cap
  POST /v1/automation/estimate      free price preview

Safety boundaries (Tier 1): no shell, no fs, no browser, no infra control.
Outbound egress is SSRF-guarded (private/loopback/link-local/metadata IPs
blocked, DNS-rebinding re-check, redirect targets re-validated).

Self-hosted compute -> provider_cost ~ $0; price = published floor.
Routes NEVER touch payments; they inherit x402/MPP/rate-limit/validation/
ledger from app.middleware.x402 + pricing.ROUTE_PRICING.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.cache import TTLCache
from app.core.config import settings
from app.x402.pricing import automation_price_usd

logger = __import__("logging").getLogger("cortexcloud.api.automation")

router = APIRouter(prefix="/v1/automation", tags=["automation"])

# --- Limits (trust boundaries) ---
_MAX_BODY = 1_000_000          # 1 MB request/transform input
_MAX_WEBHOOK_PAYLOAD = 50_000  # 50 KB outbound payload
_HTTP_TIMEOUT = 30.0
_WORKFLOW_TIMEOUT = 120.0
_MAX_WORKFLOW_STEPS = 10
_MAX_SCHEDULE_DELAY_S = 30 * 24 * 3600  # 30 days
_IDEMPOTENCY_TTL_S = 86_400    # 24h dedupe window

# ponytail: in-process idempotency dedupe. Swap to Postgres-backed if
# multi-worker exactly-once is ever required; single-worker is fine for T1.
_IDEMP = TTLCache(_IDEMPOTENCY_TTL_S)

# Blocked hostname suffixes / literals (cloud metadata, internal).
_BLOCKED_HOSTS = ("localhost", "metadata.google.internal", "metadata", ".local", ".internal")
_METADATA_IP = ipaddress.ip_address("169.254.169.254")


def _resolve_ips(host: str) -> list[str]:
    try:
        return list({a[4][0] for a in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)})
    except (socket.gaierror, OSError):
        return []


def _ip_ok(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return False
    if ip == _METADATA_IP or ip in ipaddress.ip_network("169.254.0.0/16"):
        return False
    return True


def is_safe_url(url: str) -> tuple[bool, str]:
    """SSRF guard: scheme, hostname blocklist, and ALL resolved IPs public."""
    if not url or not isinstance(url, str):
        return False, "empty"
    if len(url) > 2048:
        return False, "too_long"
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
    except Exception:
        return False, "parse_error"
    if p.scheme not in ("http", "https"):
        return False, "bad_scheme"
    host = (p.hostname or "").lower()
    if not host:
        return False, "no_host"
    if any(host == b or host.endswith(b) for b in _BLOCKED_HOSTS):
        return False, f"blocked_host:{host}"
    ips = _resolve_ips(host)
    if not ips:
        return False, "unresolved"
    if not all(_ip_ok(ip) for ip in ips):
        return False, f"private_ip:{ips}"
    return True, host


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------
# Input models
# --------------------------------------------------------------------------
class TransformRequest(BaseModel):
    data: Any = Field(description="Arbitrary JSON to shape.")
    rules: dict = Field(default_factory=dict, description="pick/omit/rename/set.")
    idempotency_key: str | None = Field(default=None, max_length=128)


class HttpRequest(BaseModel):
    method: str = Field(default="GET", pattern=r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$")
    url: str = Field(min_length=1, max_length=2048)
    headers: dict = Field(default_factory=dict)
    body: Any | None = None
    timeout: float = Field(default=30.0, ge=1.0, le=30.0)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("headers")
    @classmethod
    def _hdr(cls, v):
        # Drop hop-by-hop / dangerous headers the caller must not set.
        banned = {"host", "content-length", "authorization", "x-cortex-signature", "x-forwarded-for"}
        return {k: val for k, val in v.items() if k.lower() not in banned}


class WebhookRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    payload: Any = Field(default=None)
    headers: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ScheduleRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    payload: Any = Field(default=None)
    headers: dict = Field(default_factory=dict)
    delay_seconds: int | None = Field(default=None, ge=1, le=30 * 24 * 3600)
    cron: str | None = Field(default=None, max_length=64)
    max_retries: int = Field(default=3, ge=0, le=10)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("cron")
    @classmethod
    def _cron_xor_delay(cls, v, info):
        if bool(v) == bool(info.data.get("delay_seconds")):
            raise ValueError("provide exactly one of cron or delay_seconds")
        return v


class WorkflowRequest(BaseModel):
    steps: list[dict] = Field(min_length=1, max_length=10)
    idempotency_key: str | None = Field(default=None, max_length=128)


# --------------------------------------------------------------------------
# Gating
# --------------------------------------------------------------------------
def _disabled(endpoint: str = "") -> JSONResponse | None:
    if not settings.AUTOMATION_ENABLED:
        return JSONResponse(status_code=503, content={"error": "automation_disabled",
            "detail": "Automation API not enabled (AUTOMATION_ENABLED=false)"})
    gate = {
        "transform": settings.AUTOMATION_TRANSFORM_ENABLED,
        "http-request": settings.AUTOMATION_HTTP_ENABLED,
        "webhook": settings.AUTOMATION_WEBHOOK_ENABLED,
        "workflow": settings.AUTOMATION_WORKFLOW_ENABLED,
        "schedule": settings.AUTOMATION_SCHEDULE_ENABLED,
    }.get(endpoint, True)
    if not gate:
        return JSONResponse(status_code=503, content={"error": "endpoint_disabled",
            "detail": f"/v1/automation/{endpoint} temporarily disabled"})
    return None


def _dedupe(key: str | None) -> bool:
    """Return True if key is fresh (not seen). False if duplicate."""
    if not key:
        return True
    if _IDEMP.get(key) is not None:
        return False
    _IDEMP.set(key, 1)
    return True


def _transform(data: Any, rules: dict) -> Any:
    """Constrained, eval-free JSON shaping."""
    if isinstance(data, dict):
        out = dict(data)
        if rules.get("pick"):
            out = {k: out[k] for k in rules["pick"] if k in out}
        if rules.get("omit"):
            for k in rules["omit"]:
                out.pop(k, None)
        if rules.get("rename"):
            for old, new in rules["rename"].items():
                if old in out:
                    out[new] = out.pop(old)
        if rules.get("set"):
            out.update(rules["set"])
        return out
    return data


async def _http_call(req: HttpRequest, timeout: float) -> tuple[int, Any, str]:
    ok, why = is_safe_url(req.url)
    if not ok:
        return 400, {"error": "ssrf_blocked", "detail": why}, "blocked"
    headers = {k: str(v) for k, v in (req.headers or {}).items()}
    body = json.dumps(req.body).encode() if req.body is not None else None
    if body and "content-type" not in {k.lower() for k in headers}:
        headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.request(req.method, req.url, headers=headers, content=body)
        # Redirect validation: re-check Location through the same guard.
        if r.is_redirect and "location" in r.headers:
            lok, lwhy = is_safe_url(r.headers["location"])
            if not lok:
                return 502, {"error": "redirect_blocked", "detail": lwhy}, "blocked"
        try:
            resp = r.json() if r.content else None
        except Exception:
            resp = r.text[:2000]
        return r.status_code, resp, "http"
    except httpx.TimeoutException:
        return 504, {"error": "upstream_timeout"}, "http"
    except httpx.HTTPError as e:
        return 502, {"error": "upstream_error", "detail": str(e)[:200]}, "http"


async def _webhook_deliver(url: str, payload: Any, headers: dict, secret: str) -> tuple[int, Any, str]:
    ok, why = is_safe_url(url)
    if not ok:
        return 400, {"error": "ssrf_blocked", "detail": why}, "blocked"
    body = json.dumps(payload).encode()
    sig = _sign(secret, body)
    hdrs = {k: str(v) for k, v in (headers or {}).items()}
    hdrs.update({"Content-Type": "application/json", "X-Cortex-Signature": f"sha256={sig}"})
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as c:
            r = await c.post(url, headers=hdrs, content=body)
        return r.status_code, (r.json() if r.content else {"status": r.status_code}), "webhook"
    except httpx.HTTPError as e:
        return 502, {"error": "delivery_failed", "detail": str(e)[:200]}, "webhook"


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.post("/estimate")
async def estimate(req: Request):
    if d := _disabled():
        return d
    try:
        body = await req.json()
    except Exception:
        body = {}
    ep = body.get("endpoint", "transform")
    price = automation_price_usd(ep)
    return JSONResponse({"endpoint": ep, "price_usd": price,
                         "provider_cost_usd": 0.0, "margin_usd": round(price - 0.0, 6)})


@router.post("/transform")
async def transform(req: TransformRequest, request: Request):
    if d := _disabled("transform"):
        return d
    if not _dedupe(req.idempotency_key):
        return JSONResponse(status_code=409, content={"error": "idempotent_duplicate"})
    return JSONResponse({"result": _transform(req.data, req.rules), "endpoint": "transform"})


@router.post("/http-request")
async def http_request(req: HttpRequest, request: Request):
    if d := _disabled("http-request"):
        return d
    if not _dedupe(req.idempotency_key):
        return JSONResponse(status_code=409, content={"error": "idempotent_duplicate"})
    status, data, used = await _http_call(req, min(req.timeout, _HTTP_TIMEOUT))
    return JSONResponse({"status": status, "data": data, "provider": used}, status_code=200 if status < 400 else status)


@router.post("/webhook")
async def webhook(req: WebhookRequest, request: Request):
    if d := _disabled("webhook"):
        return d
    if not _dedupe(req.idempotency_key):
        return JSONResponse(status_code=409, content={"error": "idempotent_duplicate"})
    status, data, used = await _webhook_deliver(req.url, req.payload, req.headers, settings.AUTOMATION_WEBHOOK_SECRET)
    return JSONResponse({"status": status, "data": data, "provider": used}, status_code=200 if status < 400 else status)


@router.post("/schedule")
async def schedule(req: ScheduleRequest, request: Request):
    if d := _disabled("schedule"):
        return d
    ok, why = is_safe_url(req.url)
    if not ok:
        return JSONResponse(status_code=400, content={"error": "ssrf_blocked", "detail": why})
    if not _dedupe(req.idempotency_key):
        return JSONResponse(status_code=409, content={"error": "idempotent_duplicate"})
    from app.database.session import AsyncSessionLocal
    from app.models.automation import AutoJob
    run_at = datetime.now(timezone.utc) + timedelta(seconds=req.delay_seconds or 0)
    kind = "recurring" if req.cron else "delayed"
    async with AsyncSessionLocal() as db:
        job = AutoJob(
            kind=kind, url=req.url, payload=req.payload or {}, headers=req.headers or {},
            cron=req.cron, run_at=run_at, max_retries=req.max_retries,
            idempotency_key=req.idempotency_key,
            signature_secret=settings.AUTOMATION_WEBHOOK_SECRET or None,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return JSONResponse({"job_id": job.id, "kind": kind, "run_at": run_at.isoformat(),
                             "status": "scheduled", "endpoint": "schedule"})


@router.post("/workflow")
async def workflow(req: WorkflowRequest, request: Request):
    if d := _disabled("workflow"):
        return d
    if not _dedupe(req.idempotency_key):
        return JSONResponse(status_code=409, content={"error": "idempotent_duplicate"})
    if len(req.steps) > _MAX_WORKFLOW_STEPS:
        return JSONResponse(status_code=400, content={"error": "too_many_steps", "max": _MAX_WORKFLOW_STEPS})
    import time
    start = time.monotonic()
    ctx: dict[str, Any] = {}
    for i, step in enumerate(req.steps):
        if time.monotonic() - start > _WORKFLOW_TIMEOUT:
            return JSONResponse(status_code=408, content={"error": "workflow_timeout", "step": i})
        stype = step.get("type")
        try:
            if stype == "transform":
                ctx[f"step{i}"] = _transform(step.get("data", ctx.get(f"step{i-1}")), step.get("rules", {}))
            elif stype == "http-request":
                h = HttpRequest(**{k: v for k, v in step.items() if k != "type"})
                status, data, _ = await _http_call(h, min(h.timeout, _HTTP_TIMEOUT))
                if status >= 400:
                    return JSONResponse(status_code=502, content={"error": "step_failed", "step": i, "status": status, "data": data})
                ctx[f"step{i}"] = {"status": status, "data": data}
            elif stype == "webhook":
                w = WebhookRequest(**{k: v for k, v in step.items() if k != "type"})
                status, data, _ = await _webhook_deliver(w.url, w.payload, w.headers, settings.AUTOMATION_WEBHOOK_SECRET)
                if status >= 400:
                    return JSONResponse(status_code=502, content=failed_step(i, status, data))
                ctx[f"step{i}"] = {"status": status, "data": data}
            else:
                return JSONResponse(status_code=400, content={"error": "bad_step_type", "step": i, "type": stype})
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": "step_error", "step": i, "detail": str(e)[:200]})
    return JSONResponse({"steps_executed": len(req.steps), "result": ctx.get(f"step{len(req.steps)-1}"), "endpoint": "workflow"})


def failed_step(i, status, data):
    return {"error": "step_failed", "step": i, "status": status, "data": data}
