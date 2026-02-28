"""Async DB client and dependency helpers."""

from __future__ import annotations

import os
from typing import AsyncGenerator

try:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
except Exception:  # pragma: no cover
    AsyncSession = object  # type: ignore[assignment]
    async_sessionmaker = None  # type: ignore[assignment]
    create_async_engine = None  # type: ignore[assignment]

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./emaildj.db")

engine = None
AsyncSessionLocal = None


def init_engine() -> None:
    global engine, AsyncSessionLocal
    if create_async_engine is None or async_sessionmaker is None:
        return
    if engine is not None and AsyncSessionLocal is not None:
        return
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def shutdown_engine() -> None:
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        init_engine()
    if AsyncSessionLocal is None:
        yield None  # type: ignore[misc]
        return
    async with AsyncSessionLocal() as session:
        yield session
