"""
Regression tests for Report endpoints.

Covers:
  GET /api/runs/{id}/reports
  GET /api/runs/{id}/reports/{report_type}
  GET /api/runs/{id}/reports/test/{nodeid}
  GET /api/runs/{id}/reports/files/{file_key}
  GET /api/runs/{id}/reports/file/{file_path}
  GET /api/runs/{id}/reports/suite/{suite_id}
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reports_empty_run(client: AsyncClient, registered_client):
    """Reports for a fresh run with no report dir returns empty available."""
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
    assert isinstance(data["available"], dict)


@pytest.mark.asyncio
async def test_reports_with_files(client: AsyncClient, registered_client, tmp_path):
    """Reports listing detects existing report files."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    # Create mock report files in a temp directory
    run_dir = tmp_path / str(run_id)
    run_dir.mkdir()
    (run_dir / "junit.xml").write_text("<testsuites/>")
    (run_dir / "report.html").write_text("<html></html>")
    (run_dir / "report.json").write_text("{}")

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports")

    assert resp.status_code == 200
    available = resp.json()["available"]
    assert available.get("junit_xml") is True
    assert available.get("html") is True
    assert available.get("json") is True


@pytest.mark.asyncio
async def test_get_junit_xml_report(client: AsyncClient, registered_client, tmp_path):
    """GET /reports/junit_xml returns the XML file."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    run_dir = tmp_path / str(run_id)
    run_dir.mkdir()
    (run_dir / "junit.xml").write_text("<testsuites><testsuite/></testsuites>")

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/junit_xml")

    assert resp.status_code == 200
    assert "<testsuites>" in resp.text


@pytest.mark.asyncio
async def test_get_json_report(client: AsyncClient, registered_client, tmp_path):
    """GET /reports/json returns parsed JSON."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    run_dir = tmp_path / str(run_id)
    run_dir.mkdir()
    (run_dir / "report.json").write_text(json.dumps({"tests": 5, "passed": 3}))

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/json")

    assert resp.status_code == 200
    assert resp.json()["tests"] == 5


@pytest.mark.asyncio
async def test_get_html_report(client: AsyncClient, registered_client, tmp_path):
    """GET /reports/html returns HTML content."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    run_dir = tmp_path / str(run_id)
    run_dir.mkdir()
    (run_dir / "report.html").write_text("<html><body>Report</body></html>")

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/html")

    assert resp.status_code == 200
    assert "<html>" in resp.text


@pytest.mark.asyncio
async def test_get_unknown_report_type(client: AsyncClient, registered_client, tmp_path):
    """Requesting an unknown report type returns 400."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    run_dir = tmp_path / str(run_id)
    run_dir.mkdir()

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/foobar")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_missing_report(client: AsyncClient, registered_client, tmp_path):
    """Requesting a report type that doesn't exist returns 404."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    run_dir = tmp_path / str(run_id)
    run_dir.mkdir()
    # Don't create the file

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/junit_xml")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_no_reports_dir(client: AsyncClient, registered_client, tmp_path):
    """Requesting reports when no run_dir exists returns 404 for specific report."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/json")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_per_test_report(client: AsyncClient, registered_client, tmp_path):
    """GET /reports/test/{nodeid} returns test-level report data."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    # Create per-test report structure
    run_dir = tmp_path / str(run_id)
    tests_dir = run_dir / "tests"
    test_data_dir = tests_dir / "test_dummy_pass_1"
    test_data_dir.mkdir(parents=True)

    index = {"tests/test_dummy1.py::test_dummy_pass_1": "test_dummy_pass_1"}
    (tests_dir / "index.json").write_text(json.dumps(index))
    (test_data_dir / "result.json").write_text(
        json.dumps({"nodeid": "tests/test_dummy1.py::test_dummy_pass_1", "status": "passed", "time": 0.1})
    )

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/test/tests/test_dummy1.py::test_dummy_pass_1")

    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert data["result"]["status"] == "passed"


@pytest.mark.asyncio
async def test_per_file_report_by_key(client: AsyncClient, registered_client, tmp_path):
    """GET /reports/files/{file_key} returns pre-generated per-file report."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    # Create per-file report
    file_key = "tests__test_dummy1"
    file_dir = tmp_path / str(run_id) / "files" / file_key
    file_dir.mkdir(parents=True)
    (file_dir / "summary.json").write_text(
        json.dumps({"total": 2, "passed": 2, "failed": 0})
    )

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/files/{file_key}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["file_key"] == file_key


@pytest.mark.asyncio
async def test_per_file_report_by_path(client: AsyncClient, registered_client, tmp_path):
    """GET /reports/file/{file_path} uses pre-generated summary if available."""
    create_resp = await client.post(
        "/api/runs",
        json={
            "client_key": registered_client["client_key"],
            "selected_tests": ["tests/test_dummy1.py::test_dummy_pass_1"],
        },
    )
    run_id = create_resp.json()["id"]

    # Create pre-generated per-file data
    file_key = "tests__test_dummy1"
    file_dir = tmp_path / str(run_id) / "files" / file_key
    file_dir.mkdir(parents=True)
    (file_dir / "summary.json").write_text(
        json.dumps({"total": 3, "passed": 2, "failed": 1})
    )

    with patch("app.api.routes.REPORTS_DIR", tmp_path):
        resp = await client.get(f"/api/runs/{run_id}/reports/file/tests/test_dummy1.py")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["run_id"] == run_id
