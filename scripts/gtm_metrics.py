"""GTM metrics — external paid calls only.

Filters out the known internal test-buyer wallet so the numbers reflect
real external agents/customers. Read-only; safe to run on prod.

Usage: PYTHONPATH=. ENV=production python scripts/gtm_metrics.py
"""
import asyncio
import os
import sys

from sqlalchemy import text

# Internal wallets to exclude (test-buyer + any known internal payer).
INTERNAL_PAYERS = {
    "0xCed8a9ff73427302cD0F0F95892EbfC2Ac83374A".lower(),
}

async def main():
    # late import so the script runs from repo root with PYTHONPATH set
    from app.database.session import AsyncSessionLocal
    # stored payer addresses are mixed-case; compare case-insensitively
    internal = ",".join(f"'{p}'" for p in INTERNAL_PAYERS)  # INTERNAL_PAYERS already lowercased
    async with AsyncSessionLocal() as db:
        q = f"""
            SELECT
                count(*)                                                          AS paid_calls,
                count(DISTINCT payer)                                             AS unique_payers,
                coalesce(sum(amount_usd), 0)                                      AS revenue,
                coalesce(sum(margin_usd), 0)                                      AS margin,
                count(*) FILTER (WHERE lower(payer) IN ({internal}))             AS internal_calls,
                count(*) FILTER (WHERE lower(payer) NOT IN ({internal}) OR payer IS NULL) AS external_calls
            FROM x402_payments
            WHERE status = 'settled'
        """
        row = (await db.execute(text(q))).fetchone()
        print("=== CortexCloud GTM metrics (settled payments) ===")
        print(f"  total paid calls : {row[0]}")
        print(f"  internal (excluded): {row[4]}")
        print(f"  EXTERNAL paid calls: {row[5]}")
        print(f"  external unique payers: {row[1] - (1 if row[4] else 0)}")
        print(f"  external revenue : ${float(row[2]):.4f}")
        print(f"  external margin  : ${float(row[3]):.4f}")

        print("\n=== external calls by category ===")
        rows = (await db.execute(text(
            f"SELECT category, count(*) FROM x402_payments "
            f"WHERE status='settled' AND lower(payer) NOT IN ({internal}) GROUP BY category ORDER BY count(*) DESC"
        ))).fetchall()
        for r in rows:
            print(f"  {r[0] or 'unknown':10} {r[1]}")

        print("\n=== external repeat payers (>=2 calls) ===")
        reps = (await db.execute(text(
            f"SELECT payer, count(*) c FROM x402_payments "
            f"WHERE status='settled' AND lower(payer) NOT IN ({internal}) "
            f"GROUP BY payer HAVING count(*) > 1"
        ))).fetchall()
        print(f"  repeat payers: {len(reps)}")
        for r in reps:
            print(f"  {r[0]} -> {r[1]} calls")

        print(f"\nMILESTONE: {row[5]}/100 external paid calls")

asyncio.run(main())
