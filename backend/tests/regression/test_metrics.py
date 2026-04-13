"""
Regression tests for Metrics endpoint.

Covers:
  GET /api/metrics
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_response_structure(client: AsyncClient):
    """GET /metrics returns all expected metric fields."""
    resp = await client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.json()

    expected_keys = {
        "total_runs",
        "completed_runs",
        "failed_runs",
        "running_runs",
        "pending_runs",
        "success_rate",
        "recent_runs",
        "client_stats",
        "resource_stats",
    }
    assert expected_keys.issubset(set(data.keys()))


@pytest.mark.asyncio
async def test_metrics_counts_are_non_negative(client: AsyncClient):
    """All count metrics should be >= 0."""
    resp = await client.get("/api/metrics")
    data = resp.json()

    assert data["total_runs"] >= 0
    assert data["completed_runs"] >= 0
    assert data["failed_runs"] >= 0
    assert data["running_runs"] >= 0
    assert data["pending_runs"] >= 0
    assert 0 <= data["success_rate"] <= 100


@pytest.mark.asyncio
async def test_metrics_after_creating_run(client: AsyncClient, registered_client):
    """Creating a run should increase total_runs."""
    before = await client.get("/api/metrics")
    before_total = before.json()["total_runs"]

    await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )

    after = await client.get("/api/metrics")
    after_total = after.json()["total_runs"]
    assert after_total == before_total + 1


@pytest.mark.asyncio
async def test_metrics_client_stats(client: AsyncClient, registered_client):
    """After creating a run, client_stats should include the client."""
    await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )

    resp = await client.get("/api/metrics")
    data = resp.json()
    assert isinstance(data["client_stats"], list)
    # At least one client should have runs
    assert any(cs["runs"] > 0 for cs in data["client_stats"])
