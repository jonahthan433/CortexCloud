"""Internal-only metrics — revenue aggregates, never served publicly.

Gated by X-Internal-Token == INTERNAL_TOKEN (env). Endpoint is disabled
(503) when the token is unset so money figures can never leak by accident.
Plain /metrics (Prometheus, no revenue) stays public as before.

/internal/revenue adds endpoint-level business analytics: organic (external
paying wallets) vs internal test traffic, repeat payers (7d/30d),
first-to-second purchase conversion, provider cost + gross margin, and
acquisition source. Internal test wallets are excluded from organic metrics.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models import Benchmark, Execution, OptimizeJob, Payment

router = APIRouter()


@router.get("/internal/metrics", include_in_schema=False)
async def metrics_summary(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")):
    if not settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail="internal metrics disabled (INTERNAL_TOKEN unset)")
    if not hmac.compare_digest(x_internal_token or "", settings.INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="invalid internal token")

    async with AsyncSessionLocal() as db:
        jobs = (await db.execute(select(func.count(OptimizeJob.id)))).scalar() or 0
        paid = (await db.execute(select(func.count(Payment.id)))).scalar() or 0
        settled = (
            await db.execute(select(func.count(Payment.id)).where(Payment.status == "settled"))
        ).scalar() or 0
        failed_pay = (
            await db.execute(select(func.count(Payment.id)).where(Payment.status != "settled"))
        ).scalar() or 0
        revenue = (await db.execute(select(func.coalesce(func.sum(Payment.amount_usd), 0.0)))).scalar() or 0.0
        avg_ms = (
            await db.execute(select(func.coalesce(func.avg(Execution.runtime_ms), 0)))
        ).scalar() or 0.0

        solver_rows = (await db.execute(
            select(Execution.solver_id, func.count(), func.avg(Execution.runtime_ms)).group_by(Execution.solver_id)
        )).all()
        provider_rows = (await db.execute(
            select(Execution.mode, func.count()).group_by(Execution.mode)
        )).all()
        cost_rows = (await db.execute(
            select(
                func.coalesce(func.sum(Benchmark.provider_cost_usd), 0.0),
                func.coalesce(func.sum(Benchmark.price_usd), 0.0),
                func.coalesce(func.sum(Benchmark.margin_usd), 0.0),
            ).where(Benchmark.provider_cost_usd.is_not(None))
        )).one()
        mode_rev = (await db.execute(
            select(Payment.mode, func.count(), func.coalesce(func.sum(Payment.amount_usd), 0.0))
            .where(Payment.status == "settled")
            .group_by(Payment.mode)
        )).all()
        rev_24h = (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount_usd), 0.0)).where(
                    Payment.status == "settled",
                    Payment.occurred_at >= func.now() - text("interval '24 hours'"),
                )
            )
        ).scalar() or 0.0

        return {
            "optimization_requests": int(jobs),
            "paid_requests": int(paid),
            "successful_payments": int(settled),
            "failed_payments": int(failed_pay),
            "solvers_selected": {sid: {"runs": int(n), "avg_runtime_ms": round(float(avg or 0), 1)} for sid, n, avg in solver_rows},
            "providers_selected": {m: int(n) for m, n in provider_rows},
            "average_execution_time_ms": round(float(avg_ms), 1),
            "provider_compute_cost_usd": round(float(cost_rows[0]), 6),
            "cortexcloud_revenue_usd": round(float(revenue), 6),
            "cortexcloud_margin_usd": round(float(cost_rows[2]), 6),
            "from_benchmarks": round(float(cost_rows[1]), 6),
            "revenue_by_mode": {m: {"count": int(n), "usd": round(float(v), 6)} for m, n, v in mode_rev},
            "revenue_last_24h_usd": round(float(rev_24h), 6),
        }

# ---------------------------------------------------------------------------
# Revenue analytics — organic (external) demand vs internal test traffic.
#
# All SQL is parameterized (text() with :name params), wallet filtering runs
# on lower(payer) so checksummed rows group correctly, and the fixed
# infra+payment overhead per settled call is deducted from gross margin so
# the margin line matches the pricing model (INFRA_COST_USD 0.001 +
# PAYMENT_COST_USD 0.0005 in app/x402/pricing.py).
# ---------------------------------------------------------------------------

from app.x402.pricing import INFRA_COST_USD, PAYMENT_COST_USD  # noqa: E402

# Internal / subsidized payers — excluded from organic-demand metrics.
# Our own test buyer plus any free-tier demo wallet. Revenue still shows in
# the "all" totals, never in organic.
TEST_PAYERS = ["0xced8a9ff"]

_ORG_PREFIX = "status='settled' AND lower(payer) NOT LIKE ALL(ARRAY[" + ",".join(
    f"'{p}%'" for p in TEST_PAYERS
) + "])"


@router.get("/internal/revenue", include_in_schema=False)
async def revenue_analytics(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    """Endpoint-level revenue analytics (organic vs internal test).

    Returns: settled USDC revenue (all + organic), independent paying
    wallets, repeat payers 7d/30d, first-to-second purchase conversion,
    provider cost, gross margin (after fixed infra+payment overhead),
    per-endpoint and per-payer breakdowns, acquisition source
    (referer/user-agent), and daily organic revenue for 30d.
    """
    if not settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail="internal metrics disabled (INTERNAL_TOKEN unset)")
    if not hmac.compare_digest(x_internal_token or "", settings.INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="invalid internal token")

    org = _ORG_PREFIX
    async with AsyncSessionLocal() as db:
        async def rows(sql: str):
            return (await db.execute(text(sql))).all()

        async def scalar(sql: str) -> float:
            return float((await db.execute(text(sql))).scalar() or 0.0)

        all_settled, all_rev = (await rows(
            "SELECT count(*), coalesce(sum(amount_usd),0) FROM x402_payments WHERE status='settled'"
        ))[0]
        org_settled, org_rev = (await rows(
            f"SELECT count(*), coalesce(sum(amount_usd),0) FROM x402_payments WHERE {org}"
        ))[0]
        org_cost, org_margin_gross = (await rows(
            f"SELECT coalesce(sum(coalesce(provider_cost_usd,0)),0), "
            f"coalesce(sum(amount_usd - coalesce(provider_cost_usd,0)),0) "
            f"FROM x402_payments WHERE {org}"
        ))[0]
        fixed = int(org_settled) * (INFRA_COST_USD + PAYMENT_COST_USD)
        margin = float(org_margin_gross) - fixed

        org_wallets = int(await scalar(
            f"SELECT count(DISTINCT lower(payer)) FROM x402_payments WHERE {org}"
        ))
        rep7 = int(await scalar(
            f"SELECT count(*) FROM (SELECT lower(payer) FROM x402_payments WHERE {org} "
            f"AND occurred_at >= now() - interval '7 days' GROUP BY lower(payer) "
            f"HAVING count(*)>1) t"
        ))
        rep30 = int(await scalar(
            f"SELECT count(*) FROM (SELECT lower(payer) FROM x402_payments WHERE {org} "
            f"AND occurred_at >= now() - interval '30 days' GROUP BY lower(payer) "
            f"HAVING count(*)>1) t"
        ))
        conv_n = int(await scalar(
            f"""SELECT count(*) FROM (
                  SELECT lower(payer), count(*) c FROM x402_payments
                  WHERE {org} GROUP BY lower(payer)) t WHERE c > 1"""
        ))
        conv_rate = round(conv_n / org_wallets, 4) if org_wallets else 0.0
        rev7 = await scalar(
            f"SELECT coalesce(sum(amount_usd),0) FROM x402_payments WHERE {org} "
            f"AND occurred_at >= now() - interval '7 days'"
        )
        rev30 = await scalar(
            f"SELECT coalesce(sum(amount_usd),0) FROM x402_payments WHERE {org} "
            f"AND occurred_at >= now() - interval '30 days'"
        )
        rep30_rev = await scalar(
            f"""SELECT coalesce(sum(amount_usd),0) FROM x402_payments p
                WHERE {org} AND occurred_at >= now() - interval '30 days'
                AND lower(payer) IN (SELECT lower(payer) FROM x402_payments
                    WHERE {org} AND occurred_at >= now() - interval '30 days'
                    GROUP BY lower(payer) HAVING count(*) > 1)"""
        )

        ep_rows = await rows(
            f"""SELECT endpoint, category, count(*),
                       round(sum(amount_usd)::numeric, 6),
                       round(sum(coalesce(provider_cost_usd, 0))::numeric, 6),
                       count(DISTINCT lower(payer))
                FROM x402_payments WHERE {org}
                GROUP BY endpoint, category ORDER BY 4 DESC"""
        )
        payer_rows = await rows(
            f"""SELECT lower(payer), count(*), round(sum(amount_usd)::numeric, 6),
                       min(occurred_at)::date, max(occurred_at)::date
                FROM x402_payments WHERE {org}
                GROUP BY lower(payer) ORDER BY 3 DESC"""
        )
        attr_rows = await rows(
            f"""SELECT coalesce(nullif(referer,''), '(direct)') AS src,
                       coalesce(user_agent, '-'), count(*),
                       round(sum(amount_usd)::numeric, 6)
                FROM x402_payments WHERE {org}
                GROUP BY 1, 2 ORDER BY 4 DESC"""
        )
        daily_rows = await rows(
            f"""SELECT occurred_at::date, count(*), round(sum(amount_usd)::numeric, 6)
                FROM x402_payments WHERE {org}
                  AND occurred_at >= now() - interval '30 days'
                GROUP BY 1 ORDER BY 1"""
        )

    return {
        "totals": {
            "all_settled_payments": int(all_settled),
            "all_revenue_usd": round(float(all_rev), 6),
            "organic_settled_payments": int(org_settled),
            "organic_revenue_usd": round(float(org_rev), 6),
            "organic_provider_cost_usd": round(float(org_cost), 6),
            "organic_gross_margin_usd": round(margin, 6),
            "organic_gross_margin_pct": round(margin / float(org_rev) * 100, 1) if float(org_rev) else 0.0,
            "internal_test_revenue_usd": round(float(all_rev) - float(org_rev), 6),
        },
        "buyers": {
            "independent_paying_wallets": org_wallets,
            "repeat_payers_7d": rep7,
            "repeat_payers_30d": rep30,
            "first_to_second_purchase_conversion": conv_rate,
            "repeat_revenue_share_30d_pct": round(rep30_rev / rev30 * 100, 1) if rev30 else 0.0,
        },
        "revenue_windows": {"last_7d_usd": round(rev7, 6), "last_30d_usd": round(rev30, 6)},
        "by_endpoint": [
            {"endpoint": e, "category": c or "uncategorized", "calls": int(n),
             "revenue_usd": float(r), "provider_cost_usd": float(pc), "wallets": int(w)}
            for e, c, n, r, pc, w in ep_rows
        ],
        "by_payer": [
            {"wallet": p, "calls": int(n), "revenue_usd": float(r), "first": str(f), "last": str(l)}
            for p, n, r, f, l in payer_rows
        ],
        "acquisition_source": [
            {"referer": s, "user_agent": ua, "calls": int(n), "revenue_usd": float(r)}
            for s, ua, n, r in attr_rows
        ],
        "daily_organic_30d": [
            {"date": str(d), "calls": int(n), "revenue_usd": float(r)} for d, n, r in daily_rows
        ],
    }
