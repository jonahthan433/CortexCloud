import asyncio
import os

# CRITICAL: tests run against a dedicated scratch database — NEVER production
# data. Set DATABASE_URL before importing app settings so the app binds to
# the test DB. The DB itself must exist (created once via psql, see ops notes).
_DB_NAME = "cortexcloud_test"
if "DATABASE_URL" not in os.environ:
    _pw = os.environ.get("POSTGRES_PASSWORD", "")
    if not _pw:
        # pytest doesn't export .env — read the real password from the app env file.
        for _l in open("/opt/CortexCloudAPI/.env"):
            if _l.startswith("POSTGRES_PASSWORD="):
                _pw = _l.split("=", 1)[1].strip()
                break
    os.environ["DATABASE_URL"] = (
        "postgresql+asyncpg://"
        f"{os.environ.get('POSTGRES_USER', 'postgres')}:{_pw}@127.0.0.1:5432/{_DB_NAME}"
    )

import pytest
import pytest_asyncio

from app.core.config import settings  # noqa: E402
from app.database.session import AsyncSessionLocal  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_test_tables():
    """Create schema in the scratch DB once per session."""
    import app.models  # noqa: F401  (populate Base.metadata before create_all)
    from app.database.session import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


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
