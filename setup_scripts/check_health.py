"""
Pre-test health check: verify backend API is reachable.

Runs before test execution to ensure the system under test is online.
"""

import sys
import urllib.request
import urllib.error

HEALTH_URL = "http://localhost:8000/api/health"
TIMEOUT = 10  # seconds


def main() -> int:
    print(f"[HealthCheck] Pinging {HEALTH_URL} ...")
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.getcode()
            body = resp.read().decode()
            print(f"[HealthCheck] Response {status}: {body}")
            if status == 200:
                print("[HealthCheck] PASSED — backend is healthy")
                return 0
            else:
                print(f"[HealthCheck] FAILED — unexpected status {status}")
                return 1
    except urllib.error.URLError as exc:
        print(f"[HealthCheck] FAILED — {exc.reason}")
        return 1
    except Exception as exc:
        print(f"[HealthCheck] FAILED — {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
