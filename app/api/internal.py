"""Internal-only metrics — revenue aggregates, never served publicly.

Gated by X-Internal-Token == INTERNAL_TOKEN (env). Endpoint is disabled
(503) when the token is unset so money figures can never leak by accident.
Plain /metrics (Prometheus, no revenue) stays public as before.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import func, select

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models import Benchmark, Execution, OptimizeJob, Payment

router = APIRouter()


@router.get("/internal/metrics", include_in_schema=False)
async def metrics_summary(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")):
    if not settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail="internal metrics disabled (INTERNAL_TOKEN unset)")
    if x_internal_token != settings.INTERNAL_TOKEN:
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
        }