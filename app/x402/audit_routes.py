"""S3 + S6: public audit endpoints — /pubkey, /usage, /receipts.

Backed by the PostgreSQL x402_payments ledger (written by the x402
middleware after every settled call). Usage aggregates per wallet;
receipts paginate raw entries. Fail-open: no records -> zeros.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select

from app.database.session import AsyncSessionLocal
from app.models import Payment
from app.x402.trust import get_pubkey_pem

router = APIRouter(prefix="/x402/v1", tags=["x402"])


@router.get("/pubkey")
async def get_pubkey():
    try:
        return {"public_key_pem": get_pubkey_pem()}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "pubkey_unavailable", "detail": str(exc)})


@router.get("/usage")
async def usage(address: str = Query(...)):
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(Payment.endpoint, func.count(Payment.id), func.sum(Payment.amount_usd))
                    .where(Payment.payer == address.lower())
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
    address: str = Query(...),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(Payment)
                    .where(Payment.payer == address.lower())
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