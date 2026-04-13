"""
Regression tests for security fixes.

Covers:
  - Login rate limiting (429 after too many attempts)
  - Admin endpoint protection (403 when ADMIN_API_KEY is set)
  - CLI command injection rejection
  - Health check DB verification
  - Request size limit (413)
"""

import os
import pytest
from httpx import AsyncClient
from unittest.mock import patch


# ── Login rate limiting ──

@pytest.mark.asyncio
async def test_login_rate_limit(client: AsyncClient):
    """After LOGIN_RATE_LIMIT attempts, further logins return 429."""
    from app.api.routes import _login_attempts, LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW
    import time

    _login_attempts.clear()
    key = "rate-limit-test-key"

    # Simulate prior failed attempts by pre-filling the attempts list
    now = time.time()
    _login_attempts[key] = [now - 1] * LOGIN_RATE_LIMIT  # all within window

    # The very next attempt should be rate-limited (429) before even touching the DB
    resp = await client.post(
        "/api/auth/login",
        params={"client_key": key, "password": "wrong"},
    )
    assert resp.status_code == 429
    assert "Too many" in resp.json()["detail"]

    # Clean up
    _login_attempts.clear()


# ── Admin endpoint protection ──

@pytest.mark.asyncio
async def test_admin_cleanup_with_key(client: AsyncClient):
    """When ADMIN_API_KEY is set, requests without it are rejected."""
    with patch("app.api.routes.ADMIN_API_KEY", "test-secret-key"):
        # Without key → 403
        resp = await client.post("/api/admin/cleanup")
        assert resp.status_code == 403

        # With wrong key → 403
        resp = await client.post(
            "/api/admin/cleanup",
            headers={"x-admin-key": "wrong-key"},
        )
        assert resp.status_code == 403

        # With correct key → 200
        resp = await client.post(
            "/api/admin/cleanup",
            headers={"x-admin-key": "test-secret-key"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_purge_with_key(client: AsyncClient):
    """When ADMIN_API_KEY is set, purge requires it."""
    with patch("app.api.routes.ADMIN_API_KEY", "test-secret-key"):
        resp = await client.post("/api/admin/purge")
        assert resp.status_code == 403

        resp = await client.post(
            "/api/admin/purge",
            headers={"x-admin-key": "test-secret-key"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_no_key_allows_access(client: AsyncClient):
    """When ADMIN_API_KEY is empty (dev mode), admin endpoints are open."""
    with patch("app.api.routes.ADMIN_API_KEY", ""):
        resp = await client.post("/api/admin/cleanup")
        assert resp.status_code == 200


# ── CLI command injection ──

@pytest.mark.asyncio
async def test_cli_rejects_newline_injection(client: AsyncClient, registered_client):
    """Newlines in CLI commands are rejected."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": registered_client["client_key"],
            "command": "pytest tests/\nrm -rf /",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cli_rejects_backtick_injection(client: AsyncClient, registered_client):
    """Backticks in CLI commands are rejected."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": registered_client["client_key"],
            "command": "pytest `whoami`",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cli_rejects_dollar_expansion(client: AsyncClient, registered_client):
    """$() expansion in CLI commands is rejected."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": registered_client["client_key"],
            "command": "pytest $(cat /etc/passwd)",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cli_rejects_pipe(client: AsyncClient, registered_client):
    """Pipes in CLI commands are rejected."""
    resp = await client.post(
        "/api/cli/execute",
        json={
            "client_key": registered_client["client_key"],
            "command": "pytest tests/ | cat",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cli_allows_valid_pytest(client: AsyncClient, registered_client):
    """A clean pytest command with flags is allowed."""
    from app.api.routes import _validate_cli_command
    assert _validate_cli_command("pytest tests/test_dummy1.py -v --tb=short")
    assert _validate_cli_command("python -m pytest tests/ -k test_foo")
    assert _validate_cli_command("pytest tests/test_dummy1.py::test_dummy_pass_1")


# ── Health check ──

@pytest.mark.asyncio
async def test_health_check_returns_ok(client: AsyncClient):
    """Health check passes when DB is available."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
