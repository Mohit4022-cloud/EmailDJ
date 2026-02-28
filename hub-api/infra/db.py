"""
Database Client — PostgreSQL connection via SQLAlchemy async.

IMPLEMENTATION INSTRUCTIONS:
Exports: get_db() → AsyncSession (FastAPI dependency)

1. Use SQLAlchemy 2.0 async engine:
   from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
   engine = create_async_engine(
     DATABASE_URL,  # postgresql+asyncpg://...
     pool_size=10,
     max_overflow=20,
     pool_pre_ping=True,  # detect stale connections
   )
   Note: DATABASE_URL must use asyncpg driver: postgresql+asyncpg://...
   (not psycopg2) for async compatibility.

2. Session factory:
   AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

3. FastAPI dependency:
   async def get_db() -> AsyncGenerator[AsyncSession, None]:
     async with AsyncSessionLocal() as session:
       yield session

4. Database tables (create via Alembic migrations or raw SQL in infra/schema.sql):
   - account_contexts: id, account_id (unique), context_json, created_at, updated_at
   - assignments: id, campaign_id, sdr_id, account_id, status, pre_drafted_sequences,
     vp_rationale, created_at, updated_at, sent_at
   - edit_signals: id, assignment_id, original_draft, final_edit, diff_json,
     prompt_evolution_flag, created_at
   - campaigns: id, name, vp_user_id, status, vp_command, audience_count,
     thread_id (LangGraph checkpoint), created_at, updated_at

5. For MVP: you can use SQLite with aiosqlite for local dev if PostgreSQL is
   not available. Switch via DATABASE_URL=sqlite+aiosqlite:///./emaildj.db.
"""

import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./emaildj.db")

# TODO: initialize engine and session factory per instructions above
engine = None
AsyncSessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # TODO: implement per instructions above
    raise NotImplementedError("get_db not yet implemented")
    yield  # make it a generator
