#!/usr/bin/env python3
"""Print settled-payment counters as JSON (read-only). Used by the Hermes
paid-call watchdog. Mirrors /internal/metrics fields without needing the
INTERNAL_TOKEN endpoint enabled."""
import asyncio
import json
import sys

sys.path.insert(0, "/opt/CortexCloudAPI")

from sqlalchemy import func, select  # noqa: E402

from app.database.session import AsyncSessionLocal  # noqa: E402
from app.models import Payment  # noqa: E402


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
        print(json.dumps({
            "paid": int(paid),
            "revenue_usd": round(float(rev), 6),
            "by_mode": {m: {"count": int(n), "usd": round(float(v), 6)} for m, n, v in modes},
        }))


if __name__ == "__main__":
    asyncio.run(main())
