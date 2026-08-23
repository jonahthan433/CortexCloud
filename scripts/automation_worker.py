#!/usr/bin/env python3
"""Automation scheduled-job worker (Tier 1).

Lightweight loop: poll due auto_jobs, fire the signed webhook to the
caller's url, record attempts, reschedule recurring jobs. Reuses the app's
AsyncSessionLocal + the same HMAC scheme as the webhook endpoint.

Run: python3 scripts/automation_worker.py   (one process; cron or systemd)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os

import httpx
from sqlalchemy import select, update

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.automation import AutoJob


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _deliver(job: AutoJob) -> tuple[int, str | None]:
    body = json.dumps(job.payload or {}).encode()
    sig = _sign(job.signature_secret or settings.AUTOMATION_WEBHOOK_SECRET, body)
    headers = {k: str(v) for k, v in (job.headers or {}).items()}
    headers.update({"Content-Type": "application/json", "X-Cortex-Signature": f"sha256={sig}"})
    # SSRF guard reuse
    from app.api.automation import is_safe_url
    ok, why = is_safe_url(job.url)
    if not ok:
        return 400, f"ssrf:{why}"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as c:
            r = await c.post(job.url, headers=headers, content=body)
        return r.status_code, None
    except Exception as e:  # transient -> retry
        return 0, str(e)[:200]


async def tick() -> None:
    async with AsyncSessionLocal() as db:
        due = (await db.execute(
            select(AutoJob).where(AutoJob.status == "scheduled",
                                  AutoJob.run_at <= _now())
        )).scalars().all()
        for job in due:
            status, err = await _deliver(job)
            job.attempts += 1
            job.last_run_at = _now()
            if 200 <= status < 300:
                if job.kind == "recurring":
                    # naive next-run: +1 day placeholder; cron parsing added later.
                    job.run_at = _now() + __import__("datetime").timedelta(days=1)
                else:
                    job.status = "done"
                job.last_error = None
            else:
                if job.attempts >= job.max_retries:
                    job.status = "failed"
                job.last_error = f"status={status} {err}" if err else f"status={status}"
        await db.commit()


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


async def main() -> None:
    while True:
        try:
            await tick()
        except Exception as e:  # noqa: BLE001
            print("worker tick error:", e)
        await asyncio.sleep(int(os.environ.get("AUTOMATION_WORKER_POLL_S", "10")))


if __name__ == "__main__":
    asyncio.run(main())
