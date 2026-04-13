"""
Shared fixtures for regression tests.

Uses httpx.AsyncClient with FastAPI's TestClient pattern so tests
run against the real ASGI app with an in-memory SQLite database.
"""

import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force an isolated in-memory DB before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.db import engine, AsyncSessionLocal, get_db, Base  # noqa: E402
from app.main import app  # noqa: E402


# ── Isolated database per test session ──

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_TestSessionLocal = async_sessionmaker(bind=_test_engine, expire_on_commit=False, class_=AsyncSession)


async def _override_get_db():
    async with _TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once before tests run."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Raw async DB session for direct queries in tests."""
    async with _TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def registered_client(client: AsyncClient):
    """Register a client and return the response JSON (includes client_key)."""
    resp = await client.post("/api/clients/register", json={"name": "test-client"})
    assert resp.status_code == 200
    return resp.json()
