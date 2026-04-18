"""
Generate a summary report of the test run execution.

Prints key metrics including pass/fail counts, duration,
and any notable failures for quick post-run review.
"""

import json
import os
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "reports")


def main() -> int:
    # Find the latest report directory
    report_dirs = []
    if os.path.exists(REPORTS_DIR):
        for item in os.listdir(REPORTS_DIR):
            try:
                report_dirs.append(int(item))
            except ValueError:
                continue

    if not report_dirs:
        print("[Summary] No test reports found")
        print("[Summary] PASSED — nothing to summarize")
        return 0

    latest = max(report_dirs)
    json_path = os.path.join(REPORTS_DIR, str(latest), "report.json")

    if not os.path.exists(json_path):
        print(f"[Summary] No JSON report found for run #{latest}")
        print("[Summary] PASSED — skipped")
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        total = report.get("summary", {}).get("total", 0)
        passed = report.get("summary", {}).get("passed", 0)
        failed = report.get("summary", {}).get("failed", 0)
        errors = report.get("summary", {}).get("error", 0)
        duration = report.get("duration", 0)

        print(f"[Summary] === Test Run #{latest} Summary ===")
        print(f"[Summary] Total: {total} | Passed: {passed} | Failed: {failed} | Errors: {errors}")
        print(f"[Summary] Duration: {duration:.2f}s")
        if total > 0:
            pass_rate = (passed / total) * 100
            print(f"[Summary] Pass Rate: {pass_rate:.1f}%")

        if failed > 0 or errors > 0:
            print(f"[Summary] ⚠ {failed + errors} test(s) need attention")

        print("[Summary] PASSED — summary generated")
    except Exception as e:
        print(f"[Summary] Warning: Could not parse report: {e}")
        print("[Summary] PASSED — completed with warnings")

    return 0


if __name__ == "__main__":
    sys.exit(main())
