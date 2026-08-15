import asyncio

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
