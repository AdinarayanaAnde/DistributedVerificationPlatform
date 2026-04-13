"""
Regression tests for automatic data purge.

Covers:
  POST /api/admin/purge           (manual purge endpoint)
  purge_old_runs()                (service function directly)
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, LogEntry, QueueEntry, ResourceLock, Run


# ── Helpers ──

async def _create_old_run(db: AsyncSession, client_id: int, age_days: int, status: str = "completed") -> int:
    """Insert a run with created_at set *age_days* in the past. Returns run id."""
    old_time = datetime.now(timezone.utc) - timedelta(days=age_days)
    run = Run(
        client_id=client_id,
        selected_tests=["tests/test_dummy1.py::test_dummy_pass_1"],
        status=status,
        created_at=old_time,
        started_at=old_time,
        finished_at=old_time + timedelta(seconds=10),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    # Add a log entry
    db.add(LogEntry(run_id=run.id, client_id=client_id, message="test log"))
    await db.commit()
    return run.id


async def _get_client_id(db: AsyncSession) -> int:
    """Return the first client id, creating one if needed."""
    result = await db.execute(select(Client.id).limit(1))
    row = result.first()
    if row:
        return row[0]
    from app.auth import get_password_hash
    c = Client(name="purge-test", client_key="purge-key-001", secret=get_password_hash("s"))
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c.id


# ── Endpoint tests ──

@pytest.mark.asyncio
async def test_purge_endpoint_defaults(client: AsyncClient, registered_client):
    """POST /admin/purge with defaults returns purge stats."""
    resp = await client.post("/api/admin/purge")
    assert resp.status_code == 200
    data = resp.json()
    assert "purged_runs" in data
    assert "purged_logs" in data
    assert "purged_locks" in data
    assert "purged_queue_entries" in data
    assert "purged_report_dirs" in data


@pytest.mark.asyncio
async def test_purge_endpoint_custom_retention(client: AsyncClient):
    """POST /admin/purge?retention_days=30 accepts custom retention."""
    resp = await client.post("/api/admin/purge?retention_days=30")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_purge_endpoint_bad_retention(client: AsyncClient):
    """retention_days < 1 is rejected."""
    resp = await client.post("/api/admin/purge?retention_days=0")
    assert resp.status_code == 400


# ── Service-level tests ──

@pytest.mark.asyncio
async def test_purge_deletes_old_completed_runs(db_session: AsyncSession):
    """Completed runs older than retention are purged."""
    from app.services.purge import purge_old_runs

    cid = await _get_client_id(db_session)
    old_id = await _create_old_run(db_session, cid, age_days=10, status="completed")

    result = await purge_old_runs(db_session, retention_days=7)
    assert result["purged_runs"] >= 1

    # Verify run is gone
    run = await db_session.get(Run, old_id)
    assert run is None


@pytest.mark.asyncio
async def test_purge_deletes_old_failed_runs(db_session: AsyncSession):
    """Failed runs older than retention are purged."""
    from app.services.purge import purge_old_runs

    cid = await _get_client_id(db_session)
    old_id = await _create_old_run(db_session, cid, age_days=10, status="failed")

    result = await purge_old_runs(db_session, retention_days=7)
    assert result["purged_runs"] >= 1

    run = await db_session.get(Run, old_id)
    assert run is None


@pytest.mark.asyncio
async def test_purge_keeps_recent_runs(db_session: AsyncSession):
    """Runs newer than retention period are NOT purged."""
    from app.services.purge import purge_old_runs

    cid = await _get_client_id(db_session)
    recent_id = await _create_old_run(db_session, cid, age_days=3, status="completed")

    await purge_old_runs(db_session, retention_days=7)

    run = await db_session.get(Run, recent_id)
    assert run is not None


@pytest.mark.asyncio
async def test_purge_keeps_running_runs(db_session: AsyncSession):
    """Running runs are never purged regardless of age."""
    from app.services.purge import purge_old_runs

    cid = await _get_client_id(db_session)
    running_id = await _create_old_run(db_session, cid, age_days=30, status="running")

    await purge_old_runs(db_session, retention_days=7)

    run = await db_session.get(Run, running_id)
    assert run is not None


@pytest.mark.asyncio
async def test_purge_deletes_associated_logs(db_session: AsyncSession):
    """Log entries for purged runs are also deleted."""
    from app.services.purge import purge_old_runs

    cid = await _get_client_id(db_session)
    old_id = await _create_old_run(db_session, cid, age_days=10, status="completed")

    result = await purge_old_runs(db_session, retention_days=7)
    assert result["purged_logs"] >= 1

    logs = (await db_session.execute(
        select(LogEntry).where(LogEntry.run_id == old_id)
    )).scalars().all()
    assert len(logs) == 0


@pytest.mark.asyncio
async def test_purge_no_op_when_nothing_old(db_session: AsyncSession):
    """Purge returns zeros when no runs exceed the retention window."""
    from app.services.purge import purge_old_runs

    result = await purge_old_runs(db_session, retention_days=9999)
    assert result["purged_runs"] == 0
    assert result["purged_logs"] == 0
