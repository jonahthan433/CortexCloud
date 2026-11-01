"""Whale-alert webhooks — registration (x402-paid), listing/unregistering, and
HMAC-signed delivery.

Surface:
  POST   /v1/webhooks/whale-alerts        register   $0.10 (x402, USDC on Base)
  GET    /v1/webhooks/whale-alerts        list       free (requires owner=)
  DELETE /v1/webhooks/whale-alerts/{id}   unregister free (requires token)

Delivery is metered, not paywalled: an outbound webhook cannot answer an x402
challenge, so each successfully delivered alert accrues $0.02 on the
registration (`deliveries`, `amount_due_usd` in the list response). Nothing is
silently charged — the ledger of what is owed is always readable.

Security:
  - HTTPS only, no credentials in the URL, public host only (literal private /
    loopback / link-local IPs are rejected; the host is re-resolved before each
    delivery and skipped if it resolves private).
  - The caller-supplied `secret` is used for HMAC-SHA256 over the exact request
    body and echoed as `X-CortexCloud-Signature: sha256=<hex>`. No secret => no
    signature header and `signed: false` in the payload.
  - The management token is returned exactly once (at registration); only its
    SHA-256 hash is stored.
  - The HMAC secret is stored as supplied (it is required to sign) in a 0600
    JSON store. It is never returned by any endpoint.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import socket
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.x402.pricing import DATA_CHAINS, DEFAULT_CHAIN, is_solana

logger = logging.getLogger("cortexcloud.api.webhooks")

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])

REGISTER_PRICE_USD = 0.10
DELIVERY_PRICE_USD = 0.02
_MAX_SEEN = 500
_MAX_DELIVERIES_PER_CYCLE = 10

_store_lock = asyncio.Lock()
_worker: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class WhaleAlertWebhookRequest(BaseModel):
    url: str = Field(description="HTTPS endpoint that receives alert deliveries.")
    secret: str | None = Field(
        default=None, min_length=8, max_length=256,
        description="Optional caller-supplied secret; enables HMAC-SHA256 signing.",
    )
    address: str = Field(description="EVM wallet to watch (from or to).")
    chain: str = Field(default=DEFAULT_CHAIN, description="EVM chain of the watched wallet.")
    min_usd: float = Field(default=100000.0, ge=0, description="USD floor for 'large' transfers.")
    limit: int = Field(default=50, ge=1, le=100, description="Transfers to scan per direction.")

    @field_validator("address")
    @classmethod
    def _addr(cls, v: str) -> str:
        import re
        if not isinstance(v, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", v):
            raise ValueError("address must be a 0x-prefixed 40-hex EVM address")
        return v.lower()

    @model_validator(mode="after")
    def _evm_only(self):
        if is_solana(self.chain):
            raise ValueError("Solana is not implemented for whale-alert webhooks")
        if str(self.chain).lower() not in DATA_CHAINS:
            raise ValueError(f"unsupported chain: {self.chain}")
        return self


# ---------------------------------------------------------------------------
# Store (JSON on disk, 0600). Small N by design (WEBHOOK_MAX_SUBSCRIPTIONS).
# ---------------------------------------------------------------------------
def _store_path() -> str:
    return os.path.abspath(settings.WEBHOOK_STORE_PATH)


def _empty_store() -> dict:
    return {"version": 1, "subscriptions": []}


async def _load() -> dict:
    path = _store_path()

    def _read() -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("subscriptions"), list):
                return data
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError) as e:  # noqa: BLE001
            logger.warning(f"webhook store unreadable ({e}); starting empty")
        return _empty_store()

    async with _store_lock:
        return await asyncio.to_thread(_read)


async def _save(store: dict) -> None:
    path = _store_path()

    def _write() -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    async with _store_lock:
        await asyncio.to_thread(_write)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public_sub(sub: dict) -> dict:
    """List/registration view: never leak secrets or the token hash."""
    return {
        "id": sub.get("id"),
        "url": sub.get("url"),
        "chain": sub.get("chain"),
        "address": sub.get("address"),
        "min_usd": sub.get("min_usd"),
        "limit": sub.get("limit"),
        "active": bool(sub.get("active")),
        "owner": sub.get("owner"),
        "created_at": sub.get("created_at"),
        "last_delivery_at": sub.get("last_delivery_at"),
        "deliveries": int(sub.get("deliveries") or 0),
        "delivery_price_usd": DELIVERY_PRICE_USD,
        "amount_due_usd": round(float(sub.get("amount_due_usd") or 0.0), 6),
        "signed": bool(sub.get("secret")),
        "last_error": sub.get("last_error"),
    }


# ---------------------------------------------------------------------------
# URL safety (HTTPS only + public host)
# ---------------------------------------------------------------------------
def _literal_ip(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _ip_is_public(ip) -> bool:
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


def validate_webhook_url(url: str) -> str | None:
    """Return an error string, or None when the URL is an acceptable target."""
    try:
        p = urlparse(url)
    except ValueError:
        return "url is not parseable"
    if p.scheme != "https":
        return "url must use https:// (plain http is rejected)"
    if not p.hostname:
        return "url must include a host"
    if p.username or p.password:
        return "url must not embed credentials"
    host = p.hostname.lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal")):
        return "url host is not publicly routable"
    ip = _literal_ip(host)
    if ip is not None and not _ip_is_public(ip):
        return "url host must be a public address"
    return None


async def _host_resolves_public(host: str) -> bool:
    """Re-resolve before delivery so a DNS rebind cannot reach private space."""
    ip = _literal_ip(host)
    if ip is not None:
        return _ip_is_public(ip)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return False
    for info in infos:
        addr = info[4][0]
        try:
            if not _ip_is_public(ipaddress.ip_address(addr)):
                return False
        except ValueError:
            return False
    return bool(infos)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/whale-alerts")
async def register_webhook(req: WhaleAlertWebhookRequest, request: Request):
    if not settings.DATA_ENABLED:
        return JSONResponse(status_code=503, content={
            "error": "data_disabled",
            "detail": "Data API not enabled on this instance (DATA_ENABLED=false)",
        })
    why = validate_webhook_url(req.url)
    if why:
        return JSONResponse(status_code=400, content={"error": "invalid_webhook_url", "detail": why})
    host = urlparse(req.url).hostname or ""
    if not await _host_resolves_public(host):
        return JSONResponse(status_code=400, content={
            "error": "invalid_webhook_url",
            "detail": "url host does not resolve to a public address",
        })

    store = await _load()
    if len(store["subscriptions"]) >= settings.WEBHOOK_MAX_SUBSCRIPTIONS:
        return JSONResponse(status_code=429, content={
            "error": "webhook_limit_reached",
            "detail": f"max {settings.WEBHOOK_MAX_SUBSCRIPTIONS} registrations on this instance",
        })

    token = secrets.token_urlsafe(32)
    sub = {
        "id": str(uuid.uuid4()),
        "url": req.url,
        "secret": req.secret,
        "address": req.address,
        "chain": req.chain.lower(),
        "min_usd": req.min_usd,
        "limit": req.limit,
        "active": True,
        "owner": (getattr(request.state, "x402_payer", None) or None),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "token_hash": _hash_token(token),
        "primed": False,
        "seen": [],
        "deliveries": 0,
        "amount_due_usd": 0.0,
        "last_delivery_at": None,
        "last_error": None,
    }
    store["subscriptions"].append(sub)
    await _save(store)

    body = _public_sub(sub)
    body.update({
        "management_token": token,
        "management_token_note": "store this now; only its SHA-256 is kept. DELETE with ?token=...",
        "price_usd": REGISTER_PRICE_USD,
        "hmac": ("sha256 over the exact request body in X-CortexCloud-Signature"
                 if req.secret else "unsigned (no secret supplied)"),
    })
    return body


@router.get("/whale-alerts")
async def list_webhooks(request: Request, owner: str | None = None):
    """Free list, scoped to an owner (the x402 payer of the registration).

    Without `owner=` the caller's settled payer is used; with neither, the
    request is refused rather than exposing every registration.
    """
    who = (owner or getattr(request.state, "x402_payer", None) or "").strip().lower()
    if not who:
        return JSONResponse(status_code=400, content={
            "error": "owner_required",
            "detail": "pass ?owner=0x... (the wallet that paid for the registration)",
        })
    store = await _load()
    subs = [_public_sub(s) for s in store["subscriptions"]
            if str(s.get("owner") or "").lower() == who]
    return {
        "owner": who,
        "count": len(subs),
        "delivery_price_usd": DELIVERY_PRICE_USD,
        "registrations": subs,
    }


@router.delete("/whale-alerts/{sub_id}")
async def unregister_webhook(sub_id: str, request: Request, token: str | None = None):
    supplied = token or request.headers.get("x-webhook-token") or ""
    if not supplied:
        return JSONResponse(status_code=401, content={
            "error": "management_token_required",
            "detail": "pass ?token=... or the X-Webhook-Token header",
        })
    store = await _load()
    for i, sub in enumerate(store["subscriptions"]):
        if sub.get("id") != sub_id:
            continue
        if not hmac.compare_digest(_hash_token(supplied), str(sub.get("token_hash") or "")):
            return JSONResponse(status_code=403, content={"error": "invalid_management_token"})
        removed = store["subscriptions"].pop(i)
        await _save(store)
        return {"deleted": True, "id": removed.get("id"),
                "deliveries": int(removed.get("deliveries") or 0),
                "amount_due_usd": round(float(removed.get("amount_due_usd") or 0.0), 6)}
    return JSONResponse(status_code=404, content={"error": "not_found"})


# ---------------------------------------------------------------------------
# Delivery worker — polls whale-alerts and POSTs new alerts.
# ---------------------------------------------------------------------------
def _alert_key(alert: dict) -> str:
    raw = "|".join(str(alert.get(k)) for k in
                   ("hash", "block_num", "direction", "asset", "value", "from", "to"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _deliver(sub: dict, alert: dict) -> bool:
    payload = {
        "type": "whale_alert",
        "subscription_id": sub["id"],
        "chain": sub["chain"],
        "watched_address": sub["address"],
        "delivered_at": datetime.now(timezone.utc).isoformat(),
        "delivery_price_usd": DELIVERY_PRICE_USD,
        "alert": alert,
        "signed": bool(sub.get("secret")),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CortexCloud-Webhook/1.0",
        "X-CortexCloud-Event": "whale_alert",
        "X-CortexCloud-Delivery": str(uuid.uuid4()),
        "X-CortexCloud-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
    }
    if sub.get("secret"):
        headers["X-CortexCloud-Signature"] = _sign(sub["secret"], body)

    host = urlparse(sub["url"]).hostname or ""
    if not await _host_resolves_public(host):
        sub["last_error"] = "target host no longer resolves public"
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as c:
            r = await c.post(sub["url"], content=body, headers=headers)
        ok = 200 <= r.status_code < 300
        sub["last_error"] = None if ok else f"http_{r.status_code}"
        return ok
    except Exception as e:  # noqa: BLE001
        sub["last_error"] = f"delivery_failed:{type(e).__name__}"
        logger.warning(f"webhook delivery {sub.get('id')} failed: {type(e).__name__}")
        return False


async def deliver_once() -> dict:
    """One polling pass. Priming pass records current alerts without sending,
    so a new registration only receives alerts that happen after it exists."""
    from app.api.data import WhaleAlertRequest, whale_alert_payload
    from app.api.data import _network

    store = await _load()
    stats = {"subscriptions": 0, "delivered": 0, "failed": 0, "primed": 0}
    changed = False
    for sub in store["subscriptions"]:
        if not sub.get("active"):
            continue
        try:
            network = _network(sub["chain"])
        except ValueError:
            sub["last_error"] = "unsupported_chain"
            changed = True
            continue
        stats["subscriptions"] += 1
        try:
            payload = await whale_alert_payload(
                WhaleAlertRequest(address=sub["address"], chain=sub["chain"],
                                  min_usd=sub["min_usd"], limit=sub["limit"]),
                network,
            )
        except Exception as e:  # noqa: BLE001
            sub["last_error"] = f"scan_failed:{type(e).__name__}"
            changed = True
            continue

        seen = list(sub.get("seen") or [])
        seen_set = set(seen)
        fresh = [al for al in payload.get("alerts", []) if _alert_key(al) not in seen_set]
        if not sub.get("primed"):
            sub["seen"] = (seen + [_alert_key(al) for al in fresh])[-_MAX_SEEN:]
            sub["primed"] = True
            stats["primed"] += 1
            changed = True
            continue

        for alert in fresh[:_MAX_DELIVERIES_PER_CYCLE]:
            if await _deliver(sub, alert):
                stats["delivered"] += 1
                sub["deliveries"] = int(sub.get("deliveries") or 0) + 1
                sub["amount_due_usd"] = round(
                    float(sub.get("amount_due_usd") or 0.0) + DELIVERY_PRICE_USD, 6)
                sub["last_delivery_at"] = datetime.now(timezone.utc).isoformat()
                seen.append(_alert_key(alert))
            else:
                stats["failed"] += 1
            changed = True
        sub["seen"] = seen[-_MAX_SEEN:]
    if changed:
        await _save(store)
    return stats


async def _delivery_loop() -> None:
    await asyncio.sleep(10)
    while True:
        try:
            stats = await deliver_once()
            if stats["delivered"] or stats["failed"]:
                logger.info(f"webhook delivery pass: {stats}")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"webhook delivery pass failed: {type(e).__name__}: {e}")
        await asyncio.sleep(settings.WEBHOOK_DELIVERY_INTERVAL_S)


def start_delivery_worker() -> None:
    global _worker
    if not (settings.WEBHOOKS_ENABLED and settings.DATA_ENABLED):
        return
    if _worker and not _worker.done():
        return
    try:
        _worker = asyncio.create_task(_delivery_loop())
        logger.info("whale-alert webhook delivery worker started")
    except RuntimeError:  # no running loop (tests/import)
        _worker = None


async def stop_delivery_worker() -> None:
    global _worker
    if _worker and not _worker.done():
        _worker.cancel()
        try:
            await _worker
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _worker = None
