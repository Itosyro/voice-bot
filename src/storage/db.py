from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)

AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionMaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
