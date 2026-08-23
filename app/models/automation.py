"""Automation scheduled-job persistence (Tier 1).

One table: auto_jobs. A schedule/delayed task is a row; a lightweight
worker (separate service, reuses the app's session) polls due rows, fires
the signed webhook to the caller's url, and records attempts. Pure Postgres
— no Redis/TTLCache dependency for durable jobs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models import _now


def _uid() -> str:
    return str(uuid.uuid4())


class AutoJob(Base):
    __tablename__ = "auto_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    kind: Mapped[str] = mapped_column(String(16), default="delayed")  # delayed | recurring
    url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    headers: Mapped[dict] = mapped_column(JSONB, default=dict)
    cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)  # next run time
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    signature_secret: Mapped[str | None] = mapped_column(Text, nullable=True)  # HMAC key for delivery
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_auto_jobs_due", "status", "run_at"),
    )
