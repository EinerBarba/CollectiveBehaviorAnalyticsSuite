"""Database engine, session factory and the base class for all models.

The schema itself is created from `schema.sql`, not from these models. The
models only describe the existing tables to SQLAlchemy.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
"""Shared async engine. `pool_pre_ping` checks each pooled connection before use,
so connections dropped by the server are replaced instead of failing a request."""

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
"""Session factory. Background jobs use it directly to open their own sessions.
`expire_on_commit=False` keeps loaded objects usable after a commit."""


class Base(DeclarativeBase):
    """Declarative base that every model in `app.models` inherits from."""

    pass


async def get_db():
    """FastAPI dependency that yields one database session per request.

    The session is closed when the request finishes. Endpoints commit
    explicitly; nothing is committed automatically.

    Yields:
        AsyncSession: The request's session.
    """
    async with AsyncSessionLocal() as session:
        yield session
