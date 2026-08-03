"""S3 + S6: public audit endpoints — /pubkey, /usage, /receipts.

Receipts are stored as an append-only Redis LIST per payer (hash of address),
RPUSHed by the x402 middleware on every settled payment. /usage aggregates and
/receipts paginates that list. Fail-open: no records -> zeros, Redis down -> 503.
"""
import json
import hashlib
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.cache import get_redis
from app.x402.trust import get_pubkey_pem

logger = None
router = APIRouter()


def _key(address: str) -> str:
    return f"x402:rx:{hashlib.sha256(address.encode()).hexdigest()}"


async def _records(address: str):
    r = get_redis()
    raw = await r.lrange(_key(address), 0, -1)
    out = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except Exception:
            continue
    return out


@router.get("/pubkey")
async def get_pubkey():
    """S6: public ECDSA P-256 key used to verify X-Cortex-Signature header."""
    return JSONResponse({
        "algorithm": "ECDSA_P-256_SHA256",
        "public_key_pem": get_pubkey_pem(),
    })


@router.get("/usage")
async def usage(address: str = Query(...)):
    """S3: per-wallet call count + total spend + per-endpoint breakdown (30d)."""
    try:
        recs = await _records(address)
        total = sum(int(r.get("payment_amount_atomic", 0)) for r in recs)
        breakdown = {}
        for r in recs:
            ep = r.get("endpoint", "?")
            breakdown[ep] = breakdown.get(ep, 0) + int(r.get("payment_amount_atomic", 0))
        return JSONResponse({
            "address": address,
            "call_count": len(recs),
            "total_spend_atomic": str(total),
            "total_spend_usdc": f"{total / 1_000_000:.6f}",
            "breakdown": {k: str(v) for k, v in breakdown.items()},
        })
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "usage_store_unavailable", "detail": str(exc)})


@router.get("/receipts")
async def receipts(
    address: str = Query(...),
    cursor: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """S6: paginated append-only receipt history for a wallet address."""
    try:
        recs = await _records(address)
        page = recs[cursor:cursor + limit]
        return JSONResponse({
            "address": address,
            "count": len(page),
            "next_cursor": cursor + len(page) if cursor + len(page) < len(recs) else None,
            "receipts": page,
        })
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "receipts_store_unavailable", "detail": str(exc)})