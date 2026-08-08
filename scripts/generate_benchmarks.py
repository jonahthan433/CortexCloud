"""Deterministic benchmark suite -> PostgreSQL `benchmarks` table.

Families: portfolio, assignment, scheduling, routing, generic-qubo.
Every run records: problem size, solver, provider, backend, runtime_ms,
objective, quality note, provider cost, CortexCloud price, margin.

Quantum solvers only when they report available (live execution + creds);
never a fake hardware run.
"""
import asyncio
import random
import time

from app.database.session import AsyncSessionLocal
from app.models import Benchmark
from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers import registry
from app.x402.pricing import MODE_PRICE_USD

_SEED = 20260808


def _random_qubo(n, seed):
    rng = random.Random(seed)
    linear = [rng.uniform(-2.0, 2.0) for _ in range(n)]
    quadratic = {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.25:
                quadratic[f"{i},{j}"] = rng.uniform(-1.5, 1.5)
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": quadratic}}


def _portfolio(n, seed):
    rng = random.Random(seed)
    linear = [-rng.uniform(0.01, 0.15) for _ in range(n)]
    quadratic = {}
    for i in range(n):
        for j in range(i + 1, n):
            quadratic[f"{i},{j}"] = rng.uniform(0.001, 0.05)
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": quadratic}}


def _assignment(n, seed):
    """n = k^2 binary grid; one-hot rows/cols enforced via quadratic penalties."""
    rng = random.Random(seed)
    k = round(n ** 0.5)
    assert k * k == n, f"assignment n={n} must be a perfect square"
    q = {}
    for w in range(n):
        wr, wc = w // k, w % k
        for u in range(w + 1, n):
            ur, uc = u // k, u % k
            if wr == ur or wc == uc:
                q[f"{w},{u}"] = q.get(f"{w},{u}", 0.0) + 4.0
    linear = [rng.uniform(-0.5, 0.5) for _ in range(n)]
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": q}}


def _scheduling(n, seed):
    rng = random.Random(seed)
    linear = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    q = {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.3:
                q[f"{i},{j}"] = rng.uniform(0.5, 2.0)
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": q}}


def _routing(n, seed):
    """TSP-one-hot: x_{i,t} -> visit city i at position t (n = cities^2)."""
    rng = random.Random(seed)
    cities = int(n ** 0.5)
    assert cities * cities == n, f"routing n={n} must be a perfect square"
    q = {}
    # one-hot per position and per city (hard penalties)
    for a in range(n):
        ia, ta = a // cities, a % cities
        for b in range(a + 1, n):
            ib, tb = b // cities, b % cities
            if ta == tb or ia == ib:
                q[f"{a},{b}"] = q.get(f"{a},{b}", 0.0) + 4.0
            elif rng.random() < 0.2:
                q[f"{a},{b}"] = rng.uniform(-1.0, 0.0)  # edge-cost incentive
    linear = [0.0] * n
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": q}}


def _generic(n, seed):
    return _random_qubo(n, seed)


FAMILIES = [
    ("portfolio", _portfolio, [12, 24]),
    ("assignment", _assignment, [9, 16]),
    ("scheduling", _scheduling, [8, 16]),
    ("routing", _routing, [9, 16]),
    ("generic-qubo", _generic, [16, 32]),
]


async def main() -> None:
    done = 0
    async with AsyncSessionLocal() as db:
        for family, gen, sizes in FAMILIES:
            for n in sizes:
                problem = ProblemInput(**gen(n, _SEED + n))
                qubo = to_qubo(problem)
                for solver in registry.solvers():
                    av = solver.availability()
                    if not av.available:
                        print(f"  skip {family:>12} n={n:>3} {solver.spec.id:<20} {av.reason}")
                        continue
                    if solver.spec.mode == "quantum" and n > solver.spec.max_variables:
                        print(f"  skip {family:>12} n={n:>3} {solver.spec.id:<20} n>capacity {solver.spec.max_variables}")
                        continue
                    t0 = time.time()
                    res = solver.solve(qubo, n)
                    rt = int((time.time() - t0) * 1000)
                    if res.status != "succeeded":
                        print(f"  fail {family:>12} n={n:>3} {solver.spec.id:<20} {res.error}")
                        continue
                    est = solver.estimate(qubo, n)
                    price = MODE_PRICE_USD.get(solver.spec.mode, MODE_PRICE_USD["classical"])
                    db.add(Benchmark(
                        problem_type=family,
                        n=n,
                        mode=solver.spec.mode,
                        solver_id=solver.spec.id,
                        provider=getattr(solver, "provider", "local"),
                        backend=solver.spec.id,
                        quality_note=res.quality_note,
                        runtime_ms=rt,
                        objective=res.objective,
                        provider_cost_usd=float(est.price_usd),
                        price_usd=float(price),
                        margin_usd=round(float(price) - float(est.price_usd), 10),
                    ))
                    done += 1
                    print(f"  ok   {family:>12} n={n:>3} {solver.spec.id:<20} obj={res.objective:.4f} {rt}ms cost=${float(est.price_usd):.3f} margin=${float(price) - float(est.price_usd):+.3f}")
        await db.commit()
    print(f"\nrecorded {done} benchmark rows")


if __name__ == "__main__":
    asyncio.run(main())