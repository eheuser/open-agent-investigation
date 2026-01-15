from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from .config import settings

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    future=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Base class for ORM models
Base = declarative_base()


async def init_db():
    """
    Initialize the database schema.

    This asynchronous function is retained for backward-compatibility purposes but performs no actions at runtime. The actual tables are created externally (e.g., by a Docker entrypoint script that runs `schema.sql`).
    """
    # Tables are created by docker-entrypoint-initdb.d/01-schema.sql
    # This function is kept for compatibility but does nothing
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides an asynchronous SQLAlchemy session for dependency injection.

    This generator creates a new :class:`AsyncSession` using the configured `async_session_factory` and ensures it is properly closed after use.

    Yields
        AsyncSession: An active asynchronous database session that can be used to execute queries within the request lifecycle.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


__all__ = ["engine", "async_session_factory", "Base", "init_db", "get_db"]
