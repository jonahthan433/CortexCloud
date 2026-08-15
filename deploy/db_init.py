import asyncio
import os
import sys

# `python deploy/db_init.py` puts deploy/ on sys.path, not the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.database.session import Base
import app.models  # noqa: F401  (register all ORM tables)


async def main() -> None:
    url = settings.DATABASE_URL or (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("schema ready")


if __name__ == "__main__":
    asyncio.run(main())
