"""
Regression tests for Test Discovery and Test Suite endpoints.

Covers:
  GET /api/tests/discover
  GET /api/test-suites
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_discover_tests(client: AsyncClient):
    """GET /tests/discover returns a list of test items with expected fields."""
    resp = await client.get("/api/tests/discover")
    assert resp.status_code == 200
    tests = resp.json()
    assert isinstance(tests, list)
    assert len(tests) > 0

    # Validate structure of a test item
    item = tests[0]
    assert "nodeid" in item
    assert "path" in item
    assert "function" in item
    assert "::" in item["nodeid"]


@pytest.mark.asyncio
async def test_discover_tests_contains_known_tests(client: AsyncClient):
    """Discovered tests should include known dummy tests."""
    resp = await client.get("/api/tests/discover")
    tests = resp.json()
    nodeids = [t["nodeid"] for t in tests]
    assert any("test_dummy_1" in nid for nid in nodeids)


@pytest.mark.asyncio
async def test_list_test_suites(client: AsyncClient):
    """GET /test-suites returns a list of suite definitions."""
    resp = await client.get("/api/test-suites")
    assert resp.status_code == 200
    suites = resp.json()
    assert isinstance(suites, list)
    assert len(suites) >= 1

    # 'all' suite should always exist
    suite_ids = [s["id"] for s in suites]
    assert "all" in suite_ids


@pytest.mark.asyncio
async def test_suite_structure(client: AsyncClient):
    """Each suite has required fields: id, name, description, tests, tags."""
    resp = await client.get("/api/test-suites")
    suites = resp.json()
    for suite in suites:
        assert "id" in suite
        assert "name" in suite
        assert "description" in suite
        assert "tests" in suite
        assert isinstance(suite["tests"], list)
        assert "tags" in suite


@pytest.mark.asyncio
async def test_all_suite_contains_all_discovered(client: AsyncClient):
    """The 'all' suite should contain every discovered test."""
    discover_resp = await client.get("/api/tests/discover")
    all_nodeids = {t["nodeid"] for t in discover_resp.json()}

    suites_resp = await client.get("/api/test-suites")
    all_suite = next(s for s in suites_resp.json() if s["id"] == "all")

    # Every discovered test should be in the 'all' suite
    assert set(all_suite["tests"]) == all_nodeids
