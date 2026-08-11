"""
Benchmark & evidence endpoint — real data from the production DB.
GET /benchmarks — solver performance, execution stats, revenue summary.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.database.session import AsyncSessionLocal

router = APIRouter(tags=["benchmarks"])


@router.get("/benchmarks", summary="Real solver benchmarks from production executions")
async def benchmarks() -> dict:
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT solver_id, mode, COUNT(*), "
            "AVG(runtime_ms)::int, MIN(runtime_ms)::int, MAX(runtime_ms)::int "
            "FROM opt_executions "
            "GROUP BY solver_id, mode ORDER BY COUNT(*) DESC"
        ))
        solver_stats = [
            {
                "solver_id": row[0],
                "mode": row[1],
                "runs": row[2],
                "avg_runtime_ms": row[3],
                "min_runtime_ms": row[4],
                "max_runtime_ms": row[5],
            }
            for row in r
        ]

        r = await db.execute(text(
            "SELECT status, COUNT(*) FROM opt_jobs GROUP BY status"
        ))
        job_stats = {row[0]: row[1] for row in r}

        r = await db.execute(text("SELECT COUNT(*) FROM benchmarks"))
        evidence_rows = r.scalar()

    return {
        "solver_performance": solver_stats,
        "job_stats": job_stats,
        "benchmark_evidence_rows": evidence_rows,
        "note": "All data from production executions. No synthetic benchmarks.",
    }
