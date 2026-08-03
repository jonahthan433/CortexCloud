"""S5: POST /x402/v1/embeddings/batch — up to 100 texts, one call, all embeddings.
Flat $0.005/call via ROUTE_PRICING (same economics as single-embedding).
Reuses the single-embedding router per text; results normalized to one
OpenAI-compatible "data" array with increasing index.
"""
import time
import uuid
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.routing.router import ModelRouter
from app.schemas.openai import EmbeddingsRequest
from app.usage.tokenizer import count_tokens

router = APIRouter()
logger = logging.getLogger("cortexcloud.x402.embeddings_batch")


class BatchEmbeddingRequest(BaseModel):
    model: str
    input: List[str] = Field(..., min_length=1, max_length=100)
    encoding_format: str = "float"


@router.post("/embeddings/batch")
async def x402_embeddings_batch(
    request: BatchEmbeddingRequest,
    req_http: Request,
    db: AsyncSession = Depends(get_db),
    x_correlation_id: str = Header(None),
):
    """Embed up to 100 texts in one paid call. Returns all embeddings."""
    if len(request.input) > 100:
        raise HTTPException(status_code=422, detail="max 100 texts per batch")
    correlation_id = x_correlation_id or str(uuid.uuid4())
    engine = ModelRouter(db)
    data = []
    total_prompt_tokens = 0
    for idx, text in enumerate(request.input):
        single = EmbeddingsRequest(model=request.model, input=text)
        response, routed_model, latency_ms = await engine.route_embeddings(single, f"{correlation_id}-{idx}")
        total_prompt_tokens += response.usage.prompt_tokens or count_tokens(text, request.model)
        embs = response.data[0].embedding if response.data else []
        data.append({"object": "embedding", "index": idx, "embedding": embs})
    return {
        "object": "list",
        "model": request.model,
        "data": data,
        "usage": {"prompt_tokens": total_prompt_tokens, "total_tokens": total_prompt_tokens},
    }