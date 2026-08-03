"""One-off production repair: create and seed only the missing model registry."""
import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.database.session import engine, AsyncSessionLocal
from app.models.registry import ModelRegistry

MODELS = (
    ("gemini-2.5-flash", "gemini", "gemini-2.5-flash", 1_000_000, "0.30", "2.50"),
    ("gemini-2.0-flash", "gemini", "gemini-2.0-flash", 1_000_000, "0.10", "0.40"),
    ("gemini-text-embedding-004", "gemini", "text-embedding-004", 3_072, "0.025", "0"),
    ("llama-3.3-70b-versatile", "groq", "llama-3.3-70b-versatile", 128_000, "0.59", "0.79"),
    ("llama-3.3-70b-instruct", "nvidia", "meta/llama-3.3-70b-instruct", 128_000, "0.25", "0.35"),
)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(ModelRegistry.__table__.create, checkfirst=True)
    async with AsyncSessionLocal() as session:
        for name, provider, upstream, context, prompt, completion in MODELS:
            existing = await session.scalar(select(ModelRegistry).where(ModelRegistry.name == name))
            if existing is None:
                session.add(ModelRegistry(
                    name=name, provider=provider, provider_model_name=upstream,
                    context_length=context, prompt_token_price=Decimal(prompt),
                    completion_token_price=Decimal(completion),
                    capabilities={"vision": provider == "gemini", "streaming": True},
                ))
        await session.commit()
        names = (await session.scalars(select(ModelRegistry.name).where(ModelRegistry.is_active).order_by(ModelRegistry.name))).all()
        assert set(name for name, *_ in MODELS) <= set(names)
        print("active models:", ", ".join(names))


if __name__ == "__main__":
    asyncio.run(main())
