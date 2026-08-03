"""S5: Agent-native async jobs — POST /jobs (pay at submit) + GET /jobs/{id} (free poll).

Job lifecycle in Redis (TTL 24h): status queued -> running -> succeeded|failed.
The x402 middleware gates POST /jobs by path, so payment is charged at submit.
Results are cached under x402:job:{id} until expiry.
"""
import asyncio
import json
import uuid
import time
import logging

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.database.session import get_db
from app.routing.router import ModelRouter
from app.schemas.openai import ChatCompletionRequest

logger = logging.getLogger("cortexcloud.x402.jobs")
router = APIRouter()

_JOB_TTL = 24 * 3600  # spec: 24h


def _job_key(job_id: str) -> str:
    return f"x402:job:{job_id}"


@router.post("/jobs")
async def create_job(
    request: ChatCompletionRequest,
    req_http: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit an async chat-completion job. Payment charged at submit (x402 gate)."""
    if request.stream:
        raise HTTPException(status_code=400, detail="async jobs do not support stream=true")
    job_id = f"job_{int(time.time() * 1000)}_{hex(id(request))[2:]}"
    job = {
        "id": job_id,
        "model": request.model,
        "status": "queued",
        "created_at": int(time.time()),
        "result": None,
        "error": None,
    }
    try:
        r = get_redis()
        await r.set(_job_key(job_id), json.dumps(job), ex=_JOB_TTL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"job store unavailable: {exc}")
    asyncio.create_task(_run_job(job_id, request.model_dump(), db))
    return JSONResponse({"job_id": job_id, "status": "queued", "poll": f"/x402/v1/jobs/{job_id}"})


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Free: poll an async job's status + result."""
    try:
        r = get_redis()
        raw = await r.get(_job_key(job_id))
    except Exception as exc:
        return JSONResponse(status_code=503, content={"error": "job_store_unavailable", "detail": str(exc)})
    if not raw:
        return JSONResponse(status_code=404, content={"error": "job_not_found"})
    return JSONResponse(json.loads(raw))


async def _run_job(job_id: str, payload: dict, db: AsyncSession) -> None:
    rid = job_id
    try:
        r = get_redis()
        await _set_status(r, job_id, "running")
        request = ChatCompletionRequest(**payload)
        router_engine = ModelRouter(db)
        response, model, latency = await router_engine.route_chat_completion(request, rid)
        result = response.model_dump(mode="json")
        doc = {
            "id": job_id,
            "model": request.model,
            "status": "succeeded",
            "created_at": int(time.time()),
            "result": result,
            "latency_ms": latency,
        }
        await r.set(_job_key(job_id), json.dumps(doc), ex=_JOB_TTL)
    except Exception as exc:
        logger.error(f"job {job_id} failed: {exc}")
        try:
            r = get_redis()
            doc = {"id": job_id, "status": "failed", "error": str(exc), "created_at": int(time.time()), "result": None}
            await r.set(_job_key(job_id), json.dumps(doc), ex=_JOB_TTL)
        except Exception:
            pass


async def _update_status(r, job_id: str, status: str) -> None:
    try:
        raw = await r.get(_job_key(job_id))
        if raw:
            doc = json.loads(raw)
            doc["status"] = status
            await r.set(_job_key(job_id), json.dumps(doc), ex=_JOB_TTL)
    except Exception:
        pass