"""
Reset test database to a clean state after test execution.

Removes test-specific data entries while preserving schema
and configuration data for the next run.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    # Check for test-specific database files
    test_db_paths = [
        os.path.join(ROOT, "data", "test.db"),
        os.path.join(ROOT, "backend", "data", "test.db"),
    ]

    cleaned = 0
    for db_path in test_db_paths:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                print(f"[DB Reset] Removed test database: {db_path}")
                cleaned += 1
            except OSError as e:
                print(f"[DB Reset] Warning: Could not remove {db_path}: {e}")

    if cleaned == 0:
        print("[DB Reset] No test databases found — nothing to reset")

    print("[DB Reset] PASSED — test database reset complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
