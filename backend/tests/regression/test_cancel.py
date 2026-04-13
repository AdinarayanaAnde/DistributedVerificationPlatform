"""
Regression tests for Cancel / Kill endpoints.

Covers:
  POST /api/runs/{id}/cancel                 (cancel entire run)
  POST /api/runs/{id}/cancel/{file_path}     (cancel single file)
  GET  /api/runs/{id}/active-files           (list active file processes)

This is the critical regression suite for the cancel bug that was fixed:
- cancel_run_file now returns 'killed', 'already_finished', or 'not_found'
- The endpoint returns graceful responses instead of 404 for finished processes
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch
import subprocess


@pytest.mark.asyncio
async def test_cancel_run_not_found(client: AsyncClient):
    """Cancelling a nonexistent run returns 404."""
    resp = await client.post("/api/runs/99999/cancel")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_run_completed(client: AsyncClient, registered_client):
    """Cancelling a completed/failed run returns 409 Conflict."""
    # Create a run
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    # Force the status to 'completed' directly in DB
    from tests.regression.conftest import _TestSessionLocal
    from app.models import Run

    async with _TestSessionLocal() as session:
        run = await session.get(Run, run_id)
        run.status = "completed"
        await session.commit()

    resp = await client.post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 409
    assert "already completed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_run_success(client: AsyncClient, registered_client):
    """Cancelling a running run returns success with processes_killed count."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    # Force status to 'running' so the cancel endpoint accepts it
    from tests.regression.conftest import _TestSessionLocal
    from app.models import Run

    async with _TestSessionLocal() as session:
        run = await session.get(Run, run_id)
        run.status = "running"
        await session.commit()

    with patch("app.api.routes.cancel_run", return_value=2):
        resp = await client.post(f"/api/runs/{run_id}/cancel")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"
    assert data["processes_killed"] == 2


@pytest.mark.asyncio
async def test_cancel_file_killed(client: AsyncClient, registered_client):
    """Cancelling a running file returns cancelled=True."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    from tests.regression.conftest import _TestSessionLocal
    from app.models import Run

    async with _TestSessionLocal() as session:
        run = await session.get(Run, run_id)
        run.status = "running"
        await session.commit()

    with patch("app.api.routes.cancel_run_file", return_value="killed"):
        resp = await client.post(f"/api/runs/{run_id}/cancel/tests/test_dummy1.py")

    assert resp.status_code == 200
    data = resp.json()
    assert data["cancelled"] is True
    assert data["file"] == "tests/test_dummy1.py"


@pytest.mark.asyncio
async def test_cancel_file_already_finished(client: AsyncClient, registered_client):
    """
    Cancelling a file that already finished returns cancelled=False
    with a graceful 'already finished' detail (NOT 404).

    This is the exact bug that was fixed.
    """
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    from tests.regression.conftest import _TestSessionLocal
    from app.models import Run

    async with _TestSessionLocal() as session:
        run = await session.get(Run, run_id)
        run.status = "running"
        await session.commit()

    with patch("app.api.routes.cancel_run_file", return_value="already_finished"):
        resp = await client.post(f"/api/runs/{run_id}/cancel/tests/test_dummy1.py")

    assert resp.status_code == 200
    data = resp.json()
    assert data["cancelled"] is False
    assert "already finished" in data["detail"]


@pytest.mark.asyncio
async def test_cancel_file_not_found(client: AsyncClient, registered_client):
    """Cancelling a file with no matching process returns 404."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    from tests.regression.conftest import _TestSessionLocal
    from app.models import Run

    async with _TestSessionLocal() as session:
        run = await session.get(Run, run_id)
        run.status = "running"
        await session.commit()

    with patch("app.api.routes.cancel_run_file", return_value="not_found"), \
         patch("app.api.routes.get_active_files", return_value=[]):
        resp = await client.post(f"/api/runs/{run_id}/cancel/tests/nonexistent.py")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_file_run_not_running(client: AsyncClient, registered_client):
    """Trying to cancel a file on a non-running run returns 409."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    from tests.regression.conftest import _TestSessionLocal
    from app.models import Run

    async with _TestSessionLocal() as session:
        run = await session.get(Run, run_id)
        run.status = "completed"
        await session.commit()

    resp = await client.post(f"/api/runs/{run_id}/cancel/tests/test_dummy1.py")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_active_files_endpoint(client: AsyncClient, registered_client):
    """GET /runs/{id}/active-files returns list of active file tags."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    with patch("app.api.routes.get_active_files", return_value=["tests/test_dummy1.py", "tests/test_dummy2.py"]):
        resp = await client.get(f"/api/runs/{run_id}/active-files")

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert "tests/test_dummy1.py" in data["active_files"]
    assert len(data["active_files"]) == 2


@pytest.mark.asyncio
async def test_active_files_not_found(client: AsyncClient):
    """GET /runs/{id}/active-files for nonexistent run returns 404."""
    resp = await client.get("/api/runs/99999/active-files")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_releases_resource_lock(client: AsyncClient, registered_client):
    """After cancelling a running run, the resource lock is released so the next run is not stuck in queued."""
    from tests.regression.conftest import _TestSessionLocal
    from app.models import Resource, ResourceLock, Run

    # Create a resource
    res_resp = await client.post("/api/resources", params={"name": "lock-test-res"})
    resource_id = res_resp.json()["id"]

    # Create run A with that resource → should acquire the lock
    create_a = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
            "resource_name": "lock-test-res",
        },
    )
    run_a_id = create_a.json()["id"]

    # Ensure run A is 'running' with the resource locked
    async with _TestSessionLocal() as session:
        run_a = await session.get(Run, run_a_id)
        run_a.status = "running"
        run_a.resource_id = resource_id
        await session.commit()

    # Cancel run A
    with patch("app.api.routes.cancel_run", return_value=1):
        cancel_resp = await client.post(f"/api/runs/{run_a_id}/cancel")

    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Verify the resource lock held by run A was released
    from sqlalchemy import select
    async with _TestSessionLocal() as session:
        locks = (await session.execute(
            select(ResourceLock).where(
                ResourceLock.resource_id == resource_id,
                ResourceLock.run_id == run_a_id,
                ResourceLock.released_at.is_(None),
            )
        )).scalars().all()
        assert len(locks) == 0, "Resource lock should be released after cancel"


@pytest.mark.asyncio
async def test_cancel_queued_releases_queue_entry(client: AsyncClient, registered_client):
    """Cancelling a queued run removes it from the queue."""
    from tests.regression.conftest import _TestSessionLocal
    from app.models import QueueEntry, Resource, ResourceLock, Run

    # Create a resource and set up a lock manually (avoids schedule_run_task being spawned)
    async with _TestSessionLocal() as session:
        resource = Resource(name="queue-cancel-res", description="test")
        session.add(resource)
        await session.commit()
        await session.refresh(resource)
        resource_id = resource.id

    # Create run A (will acquire the lock via create_run)
    with patch("app.api.routes.schedule_run_task", return_value=None):
        create_a = await client.post(
            "/api/runs",
            json={
                "client_key": registered_client["client_key"],
                "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
                "resource_name": "queue-cancel-res",
            },
        )
    run_a_id = create_a.json()["id"]
    assert create_a.json()["status"] == "running"

    # Create run B (will be queued behind run A)
    create_b = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy2.py::test_dummy_pass_1"],
            "resource_name": "queue-cancel-res",
        },
    )
    run_b_id = create_b.json()["id"]
    assert create_b.json()["status"] == "queued"

    # Cancel the queued run B
    with patch("app.api.routes.cancel_run", return_value=0):
        cancel_resp = await client.post(f"/api/runs/{run_b_id}/cancel")

    assert cancel_resp.status_code == 200

    # Verify queue entry is removed
    from sqlalchemy import select
    async with _TestSessionLocal() as session:
        entries = (await session.execute(
            select(QueueEntry).where(QueueEntry.run_id == run_b_id)
        )).scalars().all()
        assert len(entries) == 0, "Queue entry should be removed for cancelled queued run"
