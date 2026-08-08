#!/usr/bin/env python3
"""Print settled-payment counters + GTM funnel metrics as JSON (read-only).
Used by the Hermes paid-call watchdog and the weekly GTM report."""
import asyncio
import json
import sys

sys.path.insert(0, "/opt/CortexCloudAPI")
from sqlalchemy import func, select  # noqa: E402

from app.database.session import AsyncSessionLocal  # noqa: E402
from app.models import Payment  # noqa: E402
from app.models.referral import Referral  # noqa: E402


async def main():
    async with AsyncSessionLocal() as db:
        paid = (
            await db.execute(select(func.count(Payment.id)).where(Payment.status == "settled"))
        ).scalar() or 0
        rev = (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount_usd), 0.0)).where(Payment.status == "settled")
            )
        ).scalar() or 0.0
        modes = (
            await db.execute(
                select(Payment.mode, func.count(), func.coalesce(func.sum(Payment.amount_usd), 0.0))
                .where(Payment.status == "settled")
                .group_by(Payment.mode)
            )
        ).all()
        # wallets with more than one settled payment
        repeat = (
            await db.execute(
                select(func.count())
                .select_from(
                    select(Payment.payer)
                    .where(Payment.status == "settled")
                    .group_by(Payment.payer)
                    .having(func.count(Payment.id) > 1)
                    .subquery()
                )
            )
        ).scalar() or 0
        wallets = (
            await db.execute(
                select(func.count(func.distinct(Payment.payer))).where(Payment.status == "settled")
            )
        ).scalar() or 0
        visitors = (
            await db.execute(select(func.count(Referral.id)))
        ).scalar() or 0
        print(json.dumps({
            "paid": int(paid),
            "revenue_usd": round(float(rev), 6),
            "by_mode": {m: {"count": int(n), "usd": round(float(v), 6)} for m, n, v in modes},
            "wallets": int(wallets),
            "repeat_customers": int(repeat),
            "visitors": int(visitors),
        }))


if __name__ == "__main__":
    asyncio.run(main())
