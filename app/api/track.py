"""GTM tracking beacon — anonymous landing visit capture (referer + utm)."""
from typing import Optional

from fastapi import APIRouter, Query, Request
from sqlalchemy import insert

from app.database.session import AsyncSessionLocal
from app.models.referral import Referral

router = APIRouter(tags=["Tracking"])


@router.get("/v1/track", status_code=204)
async def track(
    request: Request,
    ref: Optional[str] = Query(default=None, max_length=512),
    src: Optional[str] = Query(default=None, max_length=100),
    med: Optional[str] = Query(default=None, max_length=100),
    cmp: Optional[str] = Query(default=None, max_length=100),
) -> None:
    """Beacon called by the landing page: records where visitors came from."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                insert(Referral).values(
                    referer=(ref or "")[:512],
                    utm_source=(src or "")[:100],
                    utm_medium=(med or "")[:100],
                    utm_campaign=(cmp or "")[:100],
                )
            )
            await db.commit()
    except Exception:
        pass  # tracking must never break the page
