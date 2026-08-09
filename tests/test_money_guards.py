"""Money-path regression tests: an unavailable paid mode must never settle,
create a job, or write a payment ledger row. Runs on the isolated
cortexcloud_test database (see conftest.py)."""
import base64
import json

import pytest

from app.database.session import AsyncSessionLocal
from sqlalchemy import text

HEADERS = {
    "content-type": "application/json",
    # Any header present routes into the paid branch; validity is irrelevant
    # because the guards under test run before signature verification.
    "payment-signature": base64.b64encode(b"not-a-real-signature").decode(),
}


class _Unavailable:
    def availability(self):
        from app.solvers.base import SolverAvailability

        return SolverAvailability(available=False)


@pytest.fixture
def quantum_offline(monkeypatch):
    """Simulate no executable quantum backend."""
    import app.solvers.registry as registry

    monkeypatch.setattr(
        registry,
        "for_mode",
        lambda mode: [_Unavailable()] if mode == "quantum" else registry.solvers() and [],
    )


async def _count(table: str) -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar() or 0


@pytest.mark.asyncio
async def test_unavailable_quantum_mode_409_no_settle_no_job(client, quantum_offline):
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        before_p = (await db.execute(text("SELECT count(*) FROM x402_payments"))).scalar()
        before_j = (await db.execute(text("SELECT count(*) FROM opt_jobs"))).scalar()

    payload = {
        "mode": "quantum",
        "problem": {"problem_type": "qubo", "n": 4, "data": {"linear": [1, -2, 3, -4], "quadratic": {"0,1": -1.5}}},
    }
    r = await client.post("/v1/optimize", json=payload, headers=HEADERS)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "no available solver for requested mode"
    assert body["mode"] == "quantum"
    # nothing may have settled or been queued
    async with AsyncSessionLocal() as db:
        p = (await db.execute(text("SELECT count(*) FROM x402_payments"))).scalar()
        j = (await db.execute(text("SELECT count(*) FROM opt_jobs"))).scalar()
    assert p == before_p, "payment ledger must stay unchanged"
    assert j == before_j, "no job may be created"


@pytest.mark.asyncio
async def test_available_mode_not_blocked_by_guard(client):
    """Classical is executable: the guard must pass it through (402 = invalid
    signature reached, NOT 409)."""
    payload = {
        "mode": "classical",
        "problem": {"problem_type": "qubo", "n": 4, "data": {"linear": [1, -2, 3, -4], "quadratic": {"0,1": -1.5}}},
    }
    r = await client.post("/v1/optimize", json=payload, headers=HEADERS)
    assert r.status_code != 409, r.text
    # signature is junk -> challenge re-issued; proves we got past the guard
    assert r.status_code == 402, r.text


@pytest.mark.asyncio
async def test_invalid_mode_rejected_422_before_settle(client):
    payload = {
        "mode": "banana",
        "problem": {"problem_type": "qubo", "n": 4, "data": {"linear": [1, -2, 3, -4], "quadratic": {"0,1": -1.5}}},
    }
    r = await client.post("/v1/optimize", json=payload, headers=HEADERS)
    assert r.status_code == 422, r.text
    assert any(e.get("loc") == ["body", "mode"] for e in r.json()["detail"])
    async with AsyncSessionLocal() as db:
        p = (await db.execute(text("SELECT count(*) FROM x402_payments"))).scalar()
    assert p == 0
