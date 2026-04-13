"""
Regression tests for Resource endpoints.

Covers:
  POST /api/resources
  GET  /api/resources
  GET  /api/resources/{name}/queue
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_resource(client: AsyncClient):
    resp = await client.post("/api/resources", params={"name": "res-test-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "res-test-1"
    assert data["active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_resource_with_description(client: AsyncClient):
    resp = await client.post(
        "/api/resources", params={"name": "res-desc", "description": "A test resource"}
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "A test resource"


@pytest.mark.asyncio
async def test_create_duplicate_resource(client: AsyncClient):
    """Duplicate resource name should fail (UNIQUE constraint → unhandled exception)."""
    name = "res-dup-test"
    resp1 = await client.post("/api/resources", params={"name": name})
    assert resp1.status_code == 200
    # The IntegrityError currently propagates as a server error
    with pytest.raises(Exception):
        await client.post("/api/resources", params={"name": name})


@pytest.mark.asyncio
async def test_list_resources(client: AsyncClient):
    await client.post("/api/resources", params={"name": "res-list-test"})
    resp = await client.get("/api/resources")
    assert resp.status_code == 200
    resources = resp.json()
    assert isinstance(resources, list)
    assert any(r["name"] == "res-list-test" for r in resources)


@pytest.mark.asyncio
async def test_resource_queue_empty(client: AsyncClient):
    """Getting queue for a resource with no runs returns empty list."""
    await client.post("/api/resources", params={"name": "res-queue-empty"})
    resp = await client.get("/api/resources/res-queue-empty/queue")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_resource_queue_not_found(client: AsyncClient):
    """Getting queue for a nonexistent resource returns 404."""
    resp = await client.get("/api/resources/nonexistent-resource/queue")
    assert resp.status_code == 404
