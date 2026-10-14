"""x402-list ownership verification token endpoint.

Serves /.well-known/x402list.txt. The token is set via env (X402LIST_TOKEN) and
the file is deployed by the operator after submitting an update request — this
route just makes it publicly fetchable so x402-list can verify ownership.
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import settings

router = APIRouter()


@router.get("/.well-known/x402list.txt", tags=["x402 Discovery"])
async def x402list_txt():
    """One-time ownership token for x402-list update verification."""
    token = os.getenv("X402LIST_TOKEN", "")
    if not token:
        return PlainTextResponse("# no verification token configured\n", status_code=404)
    return PlainTextResponse(token + "\n", media_type="text/plain; charset=utf-8")
