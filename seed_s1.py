"""S1: seed new model coverage (Anthropic, Mistral, Meta 405B via OpenRouter).
Upsert semantics — existing models are left untouched. Run from /opt/CortexCloudAPI
with the venv python: cd /opt/CortexCloudAPI && /opt/cortexcloud-venv/bin/python /tmp/seed_s1.py
"""
import asyncio

from app.database.session import AsyncSessionLocal
from app.models.registry import ModelRegistry
from sqlalchemy import select

NEW_MODELS = [
    dict(
        name="claude-sonnet-4-6",
        provider="anthropic",
        provider_model_name="claude-sonnet-4-6",
        context_length=200000,
        prompt_token_price=3.0,
        completion_token_price=15.0,
        capabilities={"vision": True, "tool_calling": True, "streaming": True, "fallback_model": "gemini-2.5-flash"},
    ),
    dict(
        name="claude-haiku-4-5",
        provider="anthropic",
        provider_model_name="claude-haiku-4-5",
        context_length=200000,
        prompt_token_price=1.0,
        completion_token_price=5.0,
        capabilities={"vision": True, "tool_calling": True, "streaming": True, "fallback_model": "gemini-2.5-flash"},
    ),
    dict(
        name="mistral-small-latest",
        provider="openrouter",
        provider_model_name="mistral/mistral-small-latest",
        context_length=128000,
        prompt_token_price=0.2,
        completion_token_price=0.6,
        capabilities={"vision": False, "tool_calling": True, "streaming": True, "fallback_model": "llama-3.3-70b-versatile"},
    ),
    dict(
        name="mistral-large-latest",
        provider="openrouter",
        provider_model_name="mistral/mistral-large-latest",
        context_length=131072,
        prompt_token_price=2.0,
        completion_token_price=6.0,
        capabilities={"vision": False, "tool_calling": True, "streaming": True, "fallback_model": "llama-3.3-70b-versatile"},
    ),
    dict(
        name="meta-llama/llama-3.1-405b-instruct",
        provider="openrouter",
        provider_model_name="meta-llama/llama-3.1-405b-instruct",
        context_length=131072,
        prompt_token_price=3.5,
        completion_token_price=3.5,
        capabilities={"vision": False, "tool_calling": True, "streaming": True, "fallback_model": "llama-3.3-70b-instruct"},
    ),
]


async def main():
    async with AsyncSessionLocal() as db:
        existing = set((await db.execute(select(ModelRegistry.name))).scalars().all())
        added, skipped = 0, 0
        for m in NEW_MODELS:
            if m["name"] in existing:
                skipped += 1
                continue
            db.add(ModelRegistry(**m))
            added += 1
        await db.commit()
        print(f"added={added} skipped={skipped} (already present)")


asyncio.run(main())
