"""Shared fixtures — real PostgreSQL (new tables only, truncated per test)."""

import asyncio

import pytest
import pytest_asyncio

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.main import create_app


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _clean_tables():
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        for t in ("x402_nonces", "benchmarks", "x402_payments", "opt_executions", "opt_jobs"):
            await db.execute(text(f"TRUNCATE {t} RESTART IDENTITY CASCADE"))
        await db.commit()
    yield


@pytest_asyncio.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=create_app(True))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def qb_small():
    return {
        "problem_type": "qubo",
        "n": 4,
        "data": {
            "linear": [1.0, -2.0, 3.0, -4.0],
            "quadratic": {"0,1": -1.5, "1,2": 0.5, "2,3": -2.0},
        },
    }


@pytest.fixture
def ising_small():
    return {
        "problem_type": "ising",
        "n": 3,
        "data": {"h": [0.5, -1.0, 2.0], "J": {"0,1": 1.5, "1,2": -0.5}},
    }