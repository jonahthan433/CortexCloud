"""Optimization Network ORM models.

Only what the product needs: jobs, executions (per-run records),
payments/usage ledger (one table serves both), nonce replay guards, and
benchmark evidence. Everything else was dropped with the registry.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OptimizeJob(Base):
    __tablename__ = "opt_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_type: Mapped[str] = mapped_column(String(16))
    n: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16), default="auto")       # auto|classical|hybrid|quantum
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    request: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    backend: Mapped[str | None] = mapped_column(String(64), nullable=True)
    algorithm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Execution(Base):
    __tablename__ = "opt_executions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("opt_jobs.id", ondelete="CASCADE"), index=True)
    solver_id: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    runtime_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    objective: Mapped[float | None] = mapped_column(Numeric(24, 12), nullable=True)
    quality_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Payment(Base):
    """x402 payments & usage ledger in one table (per settled request).

    Recorded by the x402 middleware right after a successful CDP
    settle. Endpoint + amount + payer is everything the analytics
    endpoints and the daily brief need.
    """

    __tablename__ = "x402_payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    endpoint: Mapped[str] = mapped_column(String(128), index=True)
    payer: Mapped[str | None] = mapped_column(String(64), index=True)      # hex address (lower)
    amount_atomic: Mapped[int] = mapped_column(BigInteger)                  # USDC base-6 units
    amount_usd: Mapped[float] = mapped_column(Numeric(18, 10))
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)     # for /v1/optimize
    n_vars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nonce: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="settled")


class Nonce(Base):
    """PG-backed replay guard (survives restarts; no TTL rows).

    Claimed before settle; a replay of the same nonce is rejected by the
    unique constraint even across process restarts.
    """

    __tablename__ = "x402_nonces"

    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(128))
    valid_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Benchmark(Base):
    """Every real run (classical or hardware) records honest numbers so
    /v1/estimate recommendations can be evidence-based, never claimed
    from marketing material."""

    __tablename__ = "benchmarks"
    __table_args__ = (Index("ix_bench_lookup", "problem_type", "n", "solver_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    problem_type: Mapped[str] = mapped_column(String(16))
    n: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    solver_id: Mapped[str] = mapped_column(String(64))
    runtime_ms: Mapped[int] = mapped_column(BigInteger)
    objective: Mapped[float | None] = mapped_column(Numeric(24, 12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)