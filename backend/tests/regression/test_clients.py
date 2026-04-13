"""
Regression tests for Client endpoints.

Covers:
  POST /api/clients/register
  GET  /api/clients
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_client(client: AsyncClient):
    """Registering a new client returns 200 with a client_key."""
    resp = await client.post("/api/clients/register", json={"name": "reg-test-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "client_key" in data
    assert data["name"] == "reg-test-1"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_client_with_email(client: AsyncClient):
    """Registration accepts optional email and webhook_url."""
    resp = await client.post(
        "/api/clients/register",
        json={"name": "email-client", "email": "test@example.com", "webhook_url": "https://hook.example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["webhook_url"] == "https://hook.example.com"


@pytest.mark.asyncio
async def test_register_client_missing_name(client: AsyncClient):
    """Registration without name returns 422."""
    resp = await client.post("/api/clients/register", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_clients(client: AsyncClient):
    """GET /clients returns a list containing previously registered clients."""
    # Register one first
    await client.post("/api/clients/register", json={"name": "list-test"})
    resp = await client.get("/api/clients")
    assert resp.status_code == 200
    clients = resp.json()
    assert isinstance(clients, list)
    assert any(c["name"] == "list-test" for c in clients)
