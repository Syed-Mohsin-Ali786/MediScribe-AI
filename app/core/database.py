from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import AsyncGenerator, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on an event loop psycopg can use.

    Windows defaults to the ProactorEventLoop, which psycopg async cannot run on.
    Uvicorn already selects a compatible loop for the API, but standalone entry
    points (seed, Alembic) need this explicit factory.
    """
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    return asyncio.run(coro)

_settings = get_settings()

# Normalise the DATABASE_URL for the async engine:
#  - postgresql+psycopg://  -> postgresql+psycopg_async:// (Supabase)
#  - sqlite://  -> sqlite+aiosqlite:// (offline demo)
DATABASE_URL = str(_settings.database_url)
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg_async://", 1)
elif DATABASE_URL.startswith("sqlite://"):
    DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=_settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
