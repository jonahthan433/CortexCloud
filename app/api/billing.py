"""Wallet-linked prepaid USDC subscriptions and weighted API credits.

Subscription renewal is manual: each month is paid by a new x402 USDC
settlement on Base. No automatic wallet withdrawals or recurring charges.
"""
from __future__ import annotations

import calendar
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.database.session import AsyncSessionLocal
from app.models import Payment
from app.models.subscription import WalletAPIKey, WalletCreditTransaction, WalletSubscription

router = APIRouter(prefix="/v1/billing", tags=["Billing"])

CREDIT_USD = 0.001
PLANS = {
    "starter": {"name": "Starter", "price_usd": 19.0, "credits": 19000},
    "trading-pro": {"name": "Trading Pro", "price_usd": 49.0, "credits": 49000},
    "agent-fleet": {"name": "Agent Fleet", "price_usd": 99.0, "credits": 99000},
}


def _add_month(value: datetime) -> datetime:
    month = value.month + 1
    year = value.year
    if month > 12:
        month, year = 1, year + 1
    return value.replace(year=year, month=month,
                         day=min(value.day, calendar.monthrange(year, month)[1]))


async def lookup_wallet_api_key(request: Request) -> WalletAPIKey | None:
    """Resolve a cx_live_ bearer key; only its SHA-256 hash is stored."""
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer cx_live_"):
        return None
    raw_key = authorization[7:].strip()
    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WalletAPIKey).where(
                WalletAPIKey.hashed_key == digest,
                WalletAPIKey.is_active.is_(True),
                WalletAPIKey.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


@router.get("/plans")
async def billing_plans():
    return {
        "currency": "USDC",
        "network": "eip155:8453",
        "billing": "manual prepaid monthly; no automatic wallet withdrawals",
        "credit_unit": "1 credit = $0.001 of advertised API price",
        "plans": [
            {"id": plan_id, **plan, "period": "1 calendar month"}
            for plan_id, plan in PLANS.items()
        ],
        "overage": "When credits are exhausted, requests fall back to the normal x402 per-call payment challenge.",
    }


@router.post("/subscribe/{plan_id}")
async def subscribe(plan_id: str, request: Request):
    plan = PLANS.get(plan_id)
    if not plan:
        return JSONResponse(status_code=404, content={"error": "unknown_plan"})
    wallet = (getattr(request.state, "x402_payer", None) or "").lower()
    nonce = getattr(request.state, "x402_nonce", None)
    if not wallet or not nonce:
        return JSONResponse(status_code=402, content={
            "error": "subscription_payment_required",
            "detail": "Pay the plan's x402 USDC challenge on Base; subscription renewal is manual.",
        })

    expected_atomic = int(round(plan["price_usd"] * 1_000_000))
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        payment_result = await db.execute(
            select(Payment).where(
                Payment.nonce == nonce,
                func.lower(Payment.payer) == wallet,
                Payment.endpoint == request.url.path,
                Payment.status == "settled",
            )
        )
        payment = payment_result.scalar_one_or_none()
        if payment is None or payment.amount_atomic != expected_atomic:
            return JSONResponse(status_code=409, content={"error": "settled_plan_payment_not_found"})

        duplicate = await db.execute(
            select(WalletCreditTransaction).where(WalletCreditTransaction.payment_nonce == nonce)
        )
        if duplicate.scalar_one_or_none():
            return JSONResponse(status_code=409, content={"error": "payment_already_credited"})

        result = await db.execute(
            select(WalletSubscription)
            .where(WalletSubscription.wallet_address == wallet)
            .with_for_update()
        )
        subscription = result.scalar_one_or_none()
        active = bool(subscription and subscription.status == "active" and subscription.period_end > now)
        period_start = subscription.period_end if active else now
        period_end = _add_month(period_start)
        remaining = (subscription.credits_remaining if active else 0) + plan["credits"]
        granted = (subscription.credits_granted if active else 0) + plan["credits"]

        if subscription is None:
            subscription = WalletSubscription(
                wallet_address=wallet,
                plan_id=plan_id,
                status="active",
                period_start=period_start,
                period_end=period_end,
                credits_granted=granted,
                credits_remaining=remaining,
            )
            db.add(subscription)
        else:
            subscription.plan_id = plan_id
            subscription.status = "active"
            subscription.period_start = period_start
            subscription.period_end = period_end
            subscription.credits_granted = granted
            subscription.credits_remaining = remaining

        db.add(WalletCreditTransaction(
            wallet_address=wallet,
            amount_credits=plan["credits"],
            type="subscription_grant",
            endpoint=request.url.path,
            payment_nonce=nonce,
        ))

        raw_key = "cx_live_" + secrets.token_urlsafe(32)
        prefix = raw_key[:16]
        db.add(WalletAPIKey(
            wallet_address=wallet,
            name=plan_id,
            prefix=prefix,
            hashed_key=hashlib.sha256(raw_key.encode()).hexdigest(),
            is_active=True,
        ))
        await db.commit()
        await db.refresh(subscription)

        return {
            "status": "active",
            "wallet": wallet,
            "plan": plan_id,
            "period_start": subscription.period_start.isoformat(),
            "period_end": subscription.period_end.isoformat(),
            "credits_granted": subscription.credits_granted,
            "credits_remaining": subscription.credits_remaining,
            "credit_unit_usd": CREDIT_USD,
            "api_key": raw_key,
            "api_key_notice": "Save this key now. It is shown only once; only its hash is stored.",
            "renewal": "manual; no automatic wallet withdrawals",
        }


@router.get("/account")
async def billing_account(request: Request):
    key = await lookup_wallet_api_key(request)
    if key is None:
        return JSONResponse(status_code=401, content={"error": "valid_subscription_api_key_required"})
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WalletSubscription).where(WalletSubscription.wallet_address == key.wallet_address)
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            return JSONResponse(status_code=404, content={"error": "subscription_not_found"})
        now = datetime.now(timezone.utc)
        status = "expired" if subscription.period_end <= now else subscription.status
        keys_result = await db.execute(
            select(WalletAPIKey).where(
                WalletAPIKey.wallet_address == key.wallet_address,
                WalletAPIKey.is_active.is_(True),
            ).order_by(WalletAPIKey.created_at.desc())
        )
        active_keys = keys_result.scalars().all()
        return {
            "wallet": key.wallet_address,
            "plan": subscription.plan_id,
            "status": status,
            "period_start": subscription.period_start.isoformat(),
            "period_end": subscription.period_end.isoformat(),
            "credits_granted": subscription.credits_granted,
            "credits_remaining": subscription.credits_remaining,
            "credit_unit_usd": CREDIT_USD,
            "api_keys": [
                {"id": str(item.id), "name": item.name, "prefix": item.prefix,
                 "created_at": item.created_at.isoformat()}
                for item in active_keys
            ],
        }


@router.get("/usage")
async def billing_usage(request: Request):
    key = await lookup_wallet_api_key(request)
    if key is None:
        return JSONResponse(status_code=401, content={"error": "valid_subscription_api_key_required"})
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WalletCreditTransaction)
            .where(WalletCreditTransaction.wallet_address == key.wallet_address)
            .order_by(WalletCreditTransaction.created_at.desc())
            .limit(100)
        )
        rows = result.scalars().all()
        return {
            "wallet": key.wallet_address,
            "transactions": [
                {"amount_credits": row.amount_credits, "type": row.type,
                 "endpoint": row.endpoint, "created_at": row.created_at.isoformat()}
                for row in rows
            ],
        }


class RevokeKeyRequest(BaseModel):
    key_id: uuid.UUID


@router.post("/keys/revoke")
async def revoke_api_key(req: RevokeKeyRequest, request: Request):
    key = await lookup_wallet_api_key(request)
    if key is None:
        return JSONResponse(status_code=401, content={"error": "valid_subscription_api_key_required"})
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WalletAPIKey).where(
                WalletAPIKey.id == req.key_id,
                WalletAPIKey.wallet_address == key.wallet_address,
                WalletAPIKey.is_active.is_(True),
            )
        )
        target = result.scalar_one_or_none()
        if target is None:
            return JSONResponse(status_code=404, content={"error": "api_key_not_found"})
        target.is_active = False
        target.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return {"revoked": True, "key_id": str(req.key_id)}
