"""
Regression tests for Run lifecycle endpoints.

Covers:
  POST /api/runs              (create)
  GET  /api/runs              (list)
  GET  /api/runs/{id}         (detail)
  GET  /api/runs/{id}/logs    (logs)
  GET  /api/runs/{id}/reports (reports listing)
"""

import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_run(client: AsyncClient, registered_client):
    """Creating a run returns 201 with run details."""
    resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("pending", "running")
    assert "id" in data
    assert data["selected_tests"] == ["tests/test_dummy1.py::test_dummy_pass_1"]


@pytest.mark.asyncio
async def test_create_run_invalid_client(client: AsyncClient):
    """Creating a run with a bad client_key returns 404."""
    resp = await client.post(
        "/api/runs",
        json={
            "client_key": "nonexistent-key",
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_missing_fields(client: AsyncClient):
    """Creating a run without required fields returns 422."""
    resp = await client.post("/api/runs", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs(client: AsyncClient, registered_client):
    """GET /runs returns a list of runs."""
    # Create a run first so there's at least one
    await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    resp = await client.get("/api/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert isinstance(runs, list)
    assert len(runs) >= 1


@pytest.mark.asyncio
async def test_get_run_detail(client: AsyncClient, registered_client):
    """GET /runs/{id} returns the run detail."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    resp = await client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == run_id


@pytest.mark.asyncio
async def test_get_run_not_found(client: AsyncClient):
    """GET /runs/{id} for a nonexistent run returns 404."""
    resp = await client.get("/api/runs/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_run_logs(client: AsyncClient, registered_client):
    """GET /runs/{id}/logs returns a list (may be empty for fresh run)."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    resp = await client.get(f"/api/runs/{run_id}/logs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_run_with_resource(client: AsyncClient, registered_client):
    """Creating a run with a resource_name auto-creates the resource and queues."""
    resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
            "resource_name": "auto-resource",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["resource_id"] is not None


@pytest.mark.asyncio
async def test_reports_listing_no_reports(client: AsyncClient, registered_client):
    """GET /runs/{id}/reports for a fresh run returns an empty available dict."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    resp = await client.get(f"/api/runs/{run_id}/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert "available" in data
