"""Problem conversion + solver correctness."""

import pytest

from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers.classical import BruteForceSolver, SimulatedAnnealingSolver
from app.solvers.hybrid import QaoaLocalSolver


def _energies(q):
    n = q["n"]
    lin = q["linear"]
    out = []
    for bits in range(1 << n):
        x = [(bits >> i) & 1 for i in range(n)]
        e = sum(lin[i] * x[i] for i in range(n))
        for key, c in q["quadratic"].items():
            i, j = map(int, key.split(","))
            e += c * x[i] * x[j]
        out.append(e)
    return out


def test_ising_to_qubo(ising_small):
    qubo = to_qubo(ProblemInput(**ising_small))
    assert qubo["n"] == 3
    assert set(qubo) == {"n", "linear", "quadratic"}
    assert len(_energies(qubo)) == 8


def test_problem_validation_bad_n():
    with pytest.raises(Exception):
        ProblemInput(problem_type="qubo", n=0, data={"linear": [0.0]})


def test_bruteforce_finds_global_min(qb_small):
    qubo = to_qubo(ProblemInput(**qb_small))
    res = BruteForceSolver().solve(qubo, qb_small["n"])
    assert res.status == "succeeded"
    assert res.objective == pytest.approx(min(_energies(qubo)), abs=1e-9)


def test_sa_matches_brute(qb_small):
    qubo = to_qubo(ProblemInput(**qb_small))
    brute = BruteForceSolver().solve(qubo, qb_small["n"])
    sa = SimulatedAnnealingSolver(seed=42).solve(qubo, qb_small["n"])
    assert sa.status == "succeeded"
    assert sa.objective == pytest.approx(brute.objective, abs=1e-9)


def test_qaoa_local_runs_on_tiny(qb_small):
    qubo = to_qubo(ProblemInput(**qb_small))
    n = 3
    tiny = {"n": n, "linear": qubo["linear"][:n],
            "quadratic": {k: v for k, v in qubo["quadratic"].items() if all(int(t) < n for t in k.split(","))}}
    res = QaoaLocalSolver().solve(tiny, n)
    assert res.status == "succeeded"
    # QAOA p=1 grid search is a heuristic: within one energy unit of the
    # exact optimum on a tiny problem (grid coarseness, not correctness).
    assert res.objective <= min(_energies(tiny)) + 1.0


def test_origin_adapter_unavailable_without_token():
    from app.solvers.origin import OriginWukongAdapter

    a = OriginWukongAdapter(api_token=None, backend=None)
    av = a.availability()
    assert av.available is False
    assert "token" in av.reason.lower()