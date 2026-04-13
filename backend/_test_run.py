"""Quick script to test runner_cancel via API and check results."""
import httpx
import time

c = httpx.Client(base_url="http://localhost:8000/api", timeout=30)
ck = c.get("/clients").json()[0]["client_key"]
tests = [t["nodeid"] for t in c.get("/tests/discover").json() if "runner_cancel" in t["nodeid"]]

print("Sending nodeids:")
for t in tests:
    print(f"  {t}")

r = c.post("/runs", json={"client_key": ck, "selected_tests": tests})
run = r.json()
rid = run["id"]
print(f"\nRun #{rid} status: {run['status']}")

# Wait for completion
for _ in range(30):
    status = c.get(f"/runs/{rid}").json()["status"]
    if status not in ("running", "pending", "queued"):
        break
    time.sleep(2)

final = c.get(f"/runs/{rid}").json()
print(f"Final status: {final['status']}")

logs = c.get(f"/runs/{rid}/logs").json()
print(f"Log entries: {len(logs)}")
for l in logs[-15:]:
    print(f"  {l['level']:7s} {l['message'][:150]}")

# Check reports
reps = c.get(f"/runs/{rid}/reports").json()
print(f"\nReports: {reps}")
