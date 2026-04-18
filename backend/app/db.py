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
        # Auto-migrate: add new columns to existing tables if missing
        await _add_column_if_missing(conn, "runs", "run_name", "VARCHAR(64)")
        await _add_column_if_missing(conn, "runs", "setup_config_id", "INTEGER")
        await _add_column_if_missing(conn, "runs", "setup_status", "VARCHAR(32)")
        await _add_column_if_missing(conn, "runs", "teardown_config_id", "INTEGER")
        await _add_column_if_missing(conn, "runs", "teardown_status", "VARCHAR(32)")
        # Backfill run_name for existing runs that don't have one
        await _backfill_run_names(conn)


async def _add_column_if_missing(conn, table: str, column: str, col_type: str) -> None:
    """Safely add a column to an existing table (SQLite compatible)."""
    import sqlalchemy
    try:
        result = await conn.execute(sqlalchemy.text(f"PRAGMA table_info({table})"))
        columns = [row[1] for row in result.fetchall()]
        if column not in columns:
            await conn.execute(sqlalchemy.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    except Exception:
        pass  # Non-SQLite or column already exists


async def _backfill_run_names(conn) -> None:
    """Assign run_name (RUN-YYYYMMDD-NNN) to any existing runs that lack one."""
    import sqlalchemy
    from collections import Counter
    try:
        result = await conn.execute(
            sqlalchemy.text("SELECT id, created_at FROM runs WHERE run_name IS NULL ORDER BY created_at, id")
        )
        rows = result.fetchall()
        if not rows:
            return
        day_counter: Counter = Counter()
        for run_id, created_at in rows:
            if created_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(created_at))
                    day_key = dt.strftime("%Y%m%d")
                except Exception:
                    day_key = "19700101"
            else:
                day_key = "19700101"
            day_counter[day_key] += 1
            run_name = f"RUN-{day_key}-{day_counter[day_key]:03d}"
            await conn.execute(
                sqlalchemy.text("UPDATE runs SET run_name = :name WHERE id = :id"),
                {"name": run_name, "id": run_id},
            )
    except Exception:
        pass
