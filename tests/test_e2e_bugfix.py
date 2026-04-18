"""End-to-end test for the 4 reported bugs."""
import requests
import time

BASE = "http://localhost:8000/api"

def test_run_lifecycle():
    # 1. Register a test client
    r = requests.post(f"{BASE}/clients/register", json={"name": "bugfix-test", "email": "test@test.com"})
    assert r.status_code == 200, f"Register failed: {r.text}"
    client = r.json()
    client_key = client["client_key"]
    print(f"Client: {client['name']}, key: {client_key}")

    # 2. Create a run with a single passing test
    r = requests.post(f"{BASE}/runs", json={
        "client_key": client_key,
        "selected_tests": ["tests/test_dummy1.py::test_pass"]
    })
    assert r.status_code in (200, 201), f"Create run failed: {r.text}"
    run = r.json()
    run_id = run["id"]
    print(f"Created run {run_id}, initial status: {run['status']}")

    # 3. Poll for status changes (BUG #3: status should NOT stay running)
    final_status = None
    for i in range(30):
        time.sleep(1)
        r = requests.get(f"{BASE}/runs/{run_id}")
        data = r.json()
        print(f"  Poll {i+1}: status={data['status']}, finished_at={data.get('finished_at')}")
        if data["status"] in ("completed", "failed", "cancelled"):
            final_status = data["status"]
            break

    assert final_status is not None, "BUG #3 STILL PRESENT: Status stuck as RUNNING!"
    print(f"PASS: Run reached terminal status: {final_status}")

    # 4. Check reports (BUG #1: JUnit XML should be available)
    r = requests.get(f"{BASE}/runs/{run_id}/reports")
