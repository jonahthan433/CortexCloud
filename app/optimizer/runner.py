"""Async optimization job lifecycle (PostgreSQL-backed).

Submit -> queued -> running -> succeeded|failed. Runs in a background
asyncio task; stale jobs (crashed worker) are requeued at boot.

Benchmark evidence is recorded from every real run so /v1/estimate can
learn; never from synthetic data.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models import Benchmark, Execution, OptimizeJob
from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers import registry

logger = logging.getLogger("cortexcloud.optimizer.runner")

_TASKS: set[asyncio.Task] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_mode(mode: str) -> str:
    return mode if mode in ("classical", "hybrid", "quantum") else "auto"


def pick_solver(mode: str, n: int):
    """auto: cheapest available per problem size (same rule as estimator)."""
    if mode == "quantum":
        return registry.for_mode("quantum")[0] if registry.for_mode("quantum") else None
    if mode == "hybrid":
        ordered = registry.for_mode("hybrid")
        return ordered[0] if ordered else None
    if mode == "classical":
        cls = registry.for_mode("classical")
        # exact when cheap, else annealing
        for s in cls:
            if s.spec.id == "brute-force" and n <= s.spec.max_variables:
                return s
        for s in cls:
            if s.spec.id != "brute-force":
                return s
        return cls[0] if cls else None
    # auto: exact when it fits, else annealing
    for s in registry.solvers():
        if s.spec.id == "brute-force" and n <= min(s.spec.max_variables, 18):
            return s
    for s in registry.solvers():
        if s.spec.id == "simulated-annealing":
            return s
    return None


async def create_job(problem: ProblemInput, mode: str, price_usd: float | None) -> str:
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        db.add(
            OptimizeJob(
                id=job_id,
                problem_type=problem.problem_type,
                n=problem.n,
                mode=_clean_mode(mode),
                request={"problem": problem.model_dump(), "mode": mode},
                price_usd=price_usd,
            )
        )
        await db.commit()
    return job_id


def schedule(job_id: str) -> None:
    task = asyncio.create_task(run_job(job_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def run_job(job_id: str) -> None:
    t0 = time.time()
    async with AsyncSessionLocal() as db:
        job = await db.get(OptimizeJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = _now()
        await db.commit()

        problem = ProblemInput(**job.request["problem"])
        qubo = to_qubo(problem)
        solver = pick_solver(job.mode, job.n)
        if solver is None or not solver.availability().available:
            job.status = "failed"
            job.error = "no available solver for requested mode"
            job.finished_at = _now()
            await db.commit()
            return

        result = await asyncio.to_thread(solver.solve, qubo, job.n)
        exec_row = Execution(
            job_id=job_id,
            solver_id=solver.spec.id,
            mode=solver.spec.mode,
            runtime_ms=int((time.time() - t0) * 1000),
            objective=result.objective,
            quality_note=result.quality_note,
            error=result.error,
            meta={"backend": solver.spec.id},
        )
        db.add(exec_row)
        if result.status == "succeeded":
            job.status = "succeeded"
            job.result = result.to_dict()
            job.backend = solver.spec.id
            job.algorithm = solver.spec.name
            db.add(
                Benchmark(
                    problem_type=problem.problem_type,
                    n=job.n,
                    mode=solver.spec.mode,
                    solver_id=solver.spec.id,
                    runtime_ms=int((time.time() - t0) * 1000),
                    objective=result.objective,
                )
            )
        else:
            job.status = "failed"
            job.error = result.error
        job.finished_at = _now()
        await db.commit()


async def requeue_stale_jobs() -> int:
    """At boot: anything stuck in queued/running (dead worker) -> requeued
    and scheduled again so the queue drains. Returns rescheduled count."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(OptimizeJob.id).where(
                    OptimizeJob.status.in_(["queued", "running"])
                )
            )
        ).scalars().all()
        for jid in rows:
            job = await db.get(OptimizeJob, jid)
            if job:
                job.status = "queued"
        await db.commit()
    for jid in rows:
        schedule(jid)
    return len(rows)