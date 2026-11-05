"""S3 + S6: audit endpoints — /pubkey, /usage, /receipts.

Backed by the PostgreSQL x402_payments ledger (written by the x402
middleware after every settled call). Usage aggregates per wallet;
receipts paginate raw entries. Fail-open: no records -> zeros.

Privacy: /usage and /receipts expose customer payment history, so they
require proof of ownership of the queried address — either the operator's
X-Internal-Token or a wallet-linked subscription API key (Bearer cx_live_...)
whose wallet matches. Payer matching is case-insensitive because the ledger
stores EIP-55 checksummed addresses.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models import Payment
from app.x402.trust import get_pubkey_pem

router = APIRouter(prefix="/x402/v1", tags=["x402"])


def _internal_ok(x_internal_token: str | None) -> bool:
    return bool(settings.INTERNAL_TOKEN) and hmac.compare_digest(
        x_internal_token or "", settings.INTERNAL_TOKEN
    )


async def _authorize_address(address: str, request: Request) -> JSONResponse | None:
    """Return a 401 unless the caller is the operator or controls the wallet."""
    if _internal_ok(request.headers.get("x-internal-token")):
        return None
    try:
        from app.api.billing import lookup_wallet_api_key
        key = await lookup_wallet_api_key(request)
    except Exception:  # noqa: BLE001
        key = None
    if key and str(key.wallet_address).lower() == address.lower():
        return None
    return JSONResponse(
        status_code=401,
        content={
            "error": "payment_privacy",
            "detail": "Provide X-Internal-Token, or a Bearer cx_live_ key for the same wallet.",
        },
    )


@router.get("/pubkey")
async def get_pubkey():
    try:
        return {"public_key_pem": get_pubkey_pem()}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "pubkey_unavailable", "detail": str(exc)})


@router.get("/usage")
async def usage(request: Request, address: str = Query(...)):
    err = await _authorize_address(address, request)
    if err is not None:
        return err
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(Payment.endpoint, func.count(Payment.id), func.sum(Payment.amount_usd))
                    .where(func.lower(Payment.payer) == address.lower())
                    .group_by(Payment.endpoint)
                )
            ).all()
        return {
            "address": address,
            "usage": [
                {"endpoint": ep, "calls": int(cnt), "total_usd": float(total or 0.0)}
                for ep, cnt, total in rows
            ],
        }
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "usage_store_unavailable", "detail": str(exc)})


@router.get("/receipts")
async def receipts(
    request: Request,
    address: str = Query(...),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    err = await _authorize_address(address, request)
    if err is not None:
        return err
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(Payment)
                    .where(func.lower(Payment.payer) == address.lower())
                    .order_by(desc(Payment.occurred_at))
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars().all()
        receipts_out = [
            {
                "ts": r.occurred_at.isoformat() if r.occurred_at else None,
                "endpoint": r.endpoint,
                "amount_usd": float(r.amount_usd),
                "amount_atomic_usdc": r.amount_atomic,
                "mode": r.mode,
                "n_vars": r.n_vars,
                "nonce": r.nonce,
            }
            for r in rows
        ]
        return {"receipts": receipts_out, "count": len(receipts_out), "limit": limit, "offset": offset}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "receipts_store_unavailable", "detail": str(exc)})