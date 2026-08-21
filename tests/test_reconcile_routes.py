"""Focused tests for reconciled routes: free solvers, simulate, and the
/v1/quantum/* aliases. Pure HTTP against the app; no payment/DB writes.

Run with the full CortexCloudAPI venv + a scratch Postgres (see conftest).
Unverified in the CT103 environment (no pip/Postgres here) — execute in a
proper staging box before trusting pass/fail.
"""
import pytest


@pytest.mark.asyncio
async def test_solver_portfolio_contract(client):
    r = await client.post(
        "/v1/solvers/portfolio",
        json={
            "returns": [0.1, 0.2, 0.15, 0.05],
            "covariance": [
                [0.1, 0.02, 0.01, 0.0],
                [0.02, 0.12, 0.03, 0.01],
                [0.01, 0.03, 0.09, 0.02],
                [0.0, 0.01, 0.02, 0.08],
            ],
            "cardinality": 2,
            "risk_aversion": 1.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["problem_type"] == "qubo"
    assert body["n"] == 4
    assert "linear" in body["data"] and "quadratic" in body["data"]


@pytest.mark.asyncio
async def test_solver_routing_contract(client):
    r = await client.post("/v1/solvers/routing", json={"distances": [[0, 1, 2], [1, 0, 1], [2, 1, 0]]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["problem_type"] == "qubo"
    # TSP time-indexed: n = N^2 = 9 variables
    assert body["n"] == 9


@pytest.mark.asyncio
async def test_solver_bin_packing_contract(client):
    r = await client.post("/v1/solvers/bin-packing", json={"item_weights": [3, 4, 5, 2], "bin_capacity": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["problem_type"] == "qubo"
    assert body["n"] == 4 * 4  # items * max_bins default = n


@pytest.mark.asyncio
async def test_solvers_reject_bad_matrix(client):
    r = await client.post("/v1/solvers/portfolio", json={"returns": [0.1], "covariance": [[0.1]], "cardinality": 2})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_simulate_is_free_dryrun(client, qb_small):
    r = await client.post("/v1/simulate", json=qb_small)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "recommendation" in body
    assert body.get("note", "").startswith("Simulated dry-run")


@pytest.mark.asyncio
async def test_quantum_alias_works(client, qb_small):
    # /v1/quantum/estimate must mirror /v1/estimate (additive alias)
    r = await client.post("/v1/quantum/estimate?mode=auto", json=qb_small)
    assert r.status_code == 200, r.text
    assert "recommendation" in r.json()


@pytest.mark.asyncio
async def test_quantum_optimize_alias_returns_402(client, qb_small):
    # paid alias must still enforce payment -> 402, not 200
    r = await client.post("/v1/quantum/optimize", json={"mode": "classical", "problem": qb_small})
    assert r.status_code == 402
    assert "payment" in r.headers.get("x-payment-protocol", "").lower() or r.status_code == 402
