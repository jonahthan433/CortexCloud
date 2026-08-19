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
from app.core.config import settings
from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers import registry
from app.x402.pricing import MODE_PRICE_USD

logger = logging.getLogger("cortexcloud.optimizer.runner")

_TASKS: set[asyncio.Task] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_mode(mode: str) -> str:
    return mode if mode in ("classical", "hybrid", "quantum") else "auto"


def _pick_classic(mode: str, n: int):
    """Explicit classical/hybrid modes: same rule as before the router."""
    if mode == "hybrid":
        ordered = registry.for_mode("hybrid")
        return ordered[0] if ordered else None
    cls = registry.for_mode("classical")
    # exact when cheap, else annealing
    for s in cls:
        if s.spec.id == "brute-force" and n <= s.spec.max_variables:
            return s
    for s in cls:
        if s.spec.id != "brute-force":
            return s
    return cls[0] if cls else None


async def pick_solver(mode: str, problem, qubo):
    """auto/quantum delegate to the backend router (single decision
    point); explicit classical/hybrid keep their pre-router behavior."""
    if mode in ("classical", "hybrid"):
        return _pick_classic(mode, problem.n)
    from app.optimizer.estimator import benchmark_evidence
    from app.solvers.quantum import router

    bench = 0 if mode == "quantum" else await benchmark_evidence(problem)
    # router.select() is sync and may initialize quantum providers (Qiskit
    # account discovery takes ~15s on first call) — run it off the event
    # loop so a cold provider never blocks polling/health.
    sel = await asyncio.to_thread(
        router.select,
        problem_type=problem.problem_type,
        qubo=qubo,
        n=problem.n,
        bench_count=bench,
        force_mode="quantum" if mode == "quantum" else None,
    )
    if sel["recommended"] is None:
        return None
    return registry.by_id(sel["recommended"]["solver_id"])


async def create_job(problem: ProblemInput, mode: str, price_usd: float | None,
                  webhook_url: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        db.add(
            OptimizeJob(
                id=job_id,
                problem_type=problem.problem_type,
                n=problem.n,
                mode=_clean_mode(mode),
                request={"problem": problem.model_dump(), "mode": mode,
             **( {"webhook_url": webhook_url} if webhook_url else {} )},
                price_usd=price_usd,
            )
        )
        await db.commit()
    return job_id


def _fire_webhook(job) -> None:
    """Fire-and-forget completion webhook. One retry, then drop.

    ponytail: no retry queue/backoff; the signed receipt inside the payload
    is the audit trail, not delivery. Add at-least-once when a customer
    needs guaranteed delivery.
    """
    url = (job.request or {}).get("webhook_url")
    if not url:
        return
    from app.core.http import shared_client
    from app.core.receipt import job_payload

    async def _post() -> None:
        payload = job_payload(job)
        client = shared_client("webhook", timeout=10.0)
        for attempt in (1, 2):
            try:
                r = await client.post(
                    url, json=payload,
                    headers={"X-Cortexcloud-Event": f"job.{job.status}"},
                )
                if r.status_code < 400:
                    return
                logger.warning(f"webhook {url} -> {r.status_code} (attempt {attempt})")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"webhook {url} failed (attempt {attempt}): {e}")

    import asyncio
    asyncio.get_event_loop().create_task(_post())


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
        solver = await pick_solver(job.mode, problem, qubo)
        if solver is None or not solver.availability().available:
            job.status = "failed"
            job.error = "no available solver for requested mode"
            job.finished_at = _now()
            await db.commit()
            _fire_webhook(job)
            return

        # Hard quantum spending cap: an autonomous agent must never be able
        # to trigger uncontrolled quantum-cloud charges. Enforced here, at
        # the single dispatch point, BEFORE any QPU submission. The
        # QUANTUM_LIVE_EXECUTION gate is enforced inside solve() as well.
        cap_error = quantum_cost_cap_error(solver, qubo, job.n)
        if cap_error:
            job.status = "failed"
            job.error = cap_error
            job.finished_at = _now()
            await db.commit()
            _fire_webhook(job)
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
            p_cost, p_price = _cost_ledger(solver, qubo)
            db.add(
                Benchmark(
                    problem_type=problem.problem_type,
                    n=job.n,
                    mode=solver.spec.mode,
                    solver_id=solver.spec.id,
                    provider=getattr(solver, "provider", "local"),
                    backend=solver.spec.id,
                    quality_note=result.quality_note,
                    runtime_ms=int((time.time() - t0) * 1000),
                    objective=result.objective,
                    provider_cost_usd=p_cost,
                    price_usd=p_price,
                    margin_usd=round(p_price - p_cost, 10),
                )
            )
        else:
            job.status = "failed"
            job.error = result.error
        job.finished_at = _now()
        await db.commit()
        _fire_webhook(job)


def quantum_cost_cap_error(solver, qubo, n: int) -> str | None:
    """Blocking reason when a quantum run would exceed QUANTUM_MAX_COST_USD
    or be sold below estimated provider cost (unless QUANTUM_ALLOW_SUBSIDY),
    else None. Pure + testable; called before ANY QPU submission."""
    if solver.spec.mode != "quantum" or settings.QUANTUM_MAX_COST_USD <= 0:
        return None
    est = solver.estimate(qubo, n)
    cost = float(est.price_usd)
    if cost > settings.QUANTUM_MAX_COST_USD:
        return (
            f"quantum cost cap exceeded: est ${cost:.2f} "
            f"> QUANTUM_MAX_COST_USD ${settings.QUANTUM_MAX_COST_USD:.2f}"
        )
    from app.x402.pricing import effective_price_usd
    price = effective_price_usd("quantum")
    if cost > price and not settings.QUANTUM_ALLOW_SUBSIDY:
        return (
            f"quantum margin guard: est provider cost ${cost:.2f} > "
            f"cortexcloud price ${price:.2f} "
            f"(set QUANTUM_ALLOW_SUBSIDY=true to sell below cost)"
        )
    return None


def _cost_ledger(solver, qubo):
    """provider cost vs CortexCloud x402 price used for benchmark rows."""
    est = solver.estimate(qubo, qubo.get("n", 0))
    return (
        float(est.price_usd),
        MODE_PRICE_USD.get(solver.spec.mode, MODE_PRICE_USD["classical"]),
    )


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