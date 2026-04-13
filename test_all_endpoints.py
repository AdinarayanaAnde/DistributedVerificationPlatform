"""Quick smoke test for all API endpoints."""
import httpx
import time
import json

c = httpx.Client(base_url="http://localhost:8000/api", timeout=30)
results = []


def check(label, r, expect_code=200):
    ok = r.status_code == expect_code
    results.append((label, ok, r.status_code))
    if not ok:
        print(f"  FAIL {label}: expected {expect_code}, got {r.status_code} - {r.text[:200]}")
    else:
        print(f"  OK   {label}")
    return r


# 1. Client registration
r = check("POST /clients/register", c.post("/clients/register", json={"name": "regression-client"}))
client_key = r.json()["client_key"]

# 2. List clients
check("GET /clients", c.get("/clients"))

# 3. Discover tests
r = check("GET /tests/discover", c.get("/tests/discover"))
tests = r.json()
print(f"       Discovered {len(tests)} tests")

# 4. List test suites
check("GET /test-suites", c.get("/test-suites"))

# 5. Create resource
check("POST /resources", c.post("/resources", params={"name": "reg-resource"}))

# 6. List resources
check("GET /resources", c.get("/resources"))

# 7. Create a run with slow tests
r = check(
    "POST /runs",
    c.post(
        "/runs",
        json={
            "client_key": client_key,
            "selected_tests": [
                "tests/test_dummy1.py::test_dummy_pass_1",
                "tests/test_dummy2.py::test_dummy_pass_3",
            ],
        },
    ),
    201,
)
run_id = r.json()["id"]
print(f"       Created run {run_id}")

time.sleep(2)

# 8. Get run
r = check("GET /runs/{id}", c.get(f"/runs/{run_id}"))
status = r.json()["status"]
print(f"       Run status: {status}")

# 9. List runs
check("GET /runs", c.get("/runs"))

# 10. Get active files
r = check("GET /runs/{id}/active-files", c.get(f"/runs/{run_id}/active-files"))
active = r.json().get("active_files", [])
print(f"       Active files: {active}")

# 11. Cancel a file (may be already finished)
r = check(
    "POST /runs/{id}/cancel/{file}",
    c.post(f"/runs/{run_id}/cancel/tests/test_dummy1.py"),
)
print(f"       Cancel response: {r.json()}")

# 12. Cancel entire run
r = check("POST /runs/{id}/cancel", c.post(f"/runs/{run_id}/cancel"))
print(f"       Cancel run response: {r.json()}")

# Wait for run to settle
time.sleep(3)

# 13. Get logs
r = check("GET /runs/{id}/logs", c.get(f"/runs/{run_id}/logs"))
logs = r.json()
print(f"       Log entries: {len(logs) if isinstance(logs, list) else 'dict'}")

# 14. Get metrics
r = check("GET /metrics", c.get("/metrics"))
print(f"       Metrics: {json.dumps(r.json(), indent=2)[:200]}")

# 15. List reports
r = check("GET /runs/{id}/reports", c.get(f"/runs/{run_id}/reports"))
report_data = r.json()
print(f"       Report keys: {list(report_data.keys())}")

# 16. Get queue status
check("GET /queue", c.get("/queue"))

# Summary
print("\n" + "=" * 50)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"Results: {passed}/{total} passed")
for label, ok, code in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label} -> {code}")
