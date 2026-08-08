"""Nonce replay protection — PostgreSQL (survives worker restarts).

EIP-3009 nonces must be single-use. We claim the nonce atomically
before CDP validation: an INSERT ... ON CONFLICT DO NOTHING either wins
(first use) or loses, in which case the payment is a replay and gets
rejected with 402.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert


async def nonce_seen(nonce: str, valid_before=None) -> bool:
    """True when this nonce was already claimed (replay) — or when the DB
    write failed (fail closed: decline rather than double-spend).
    """
    from app.database.session import AsyncSessionLocal
    from app.models import Nonce

    if valid_before:
        try:
            vb = datetime.fromtimestamp(int(valid_before), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            vb = datetime.now(timezone.utc)
    else:
        vb = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                pg_insert(Nonce)
                .values(nonce=nonce, endpoint="", valid_before=vb)
                .on_conflict_do_nothing(index_elements=[Nonce.nonce])
            )
            res = await db.execute(stmt)
            await db.commit()
            return res.rowcount == 0  # 0 rows inserted => already seen
    except Exception:
        return True  # fail closed on DB errors