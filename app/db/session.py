
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.settings import settings
from typing import AsyncGenerator

# Create Async Engine
engine = create_async_engine(
    settings.db.url,
    echo=settings.log_level == "DEBUG",
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
)

# Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
