import os
from collections.abc import AsyncGenerator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./data/app.db"

# Use connection pool sizing appropriate for async usage
_pool_args = {}
if DATABASE_URL.startswith("postgresql"):
    _pool_args = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,       # seconds to wait for a connection from the pool
        "pool_recycle": 1800,     # recycle connections after 30 minutes
    }

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    future=True,
    echo=False,
    pool_pre_ping=True,
    **_pool_args,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
