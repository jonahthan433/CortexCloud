from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Referral(Base):
    """Anonymous landing-page visit tracking (GTM funnel). No PII, no org."""
    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    referer: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    utm_source: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_medium: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_campaign: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
