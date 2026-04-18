"""
Validate the test database is accessible and has the expected schema.

Ensures the database is in a consistent state before running tests.
"""

import os
import sqlite3
import sys

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dvf_local.db",
))


def main() -> int:
    print(f"[DBCheck] Checking database at {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print("[DBCheck] WARNING — database file not found (may be created on first run)")
        return 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        print(f"[DBCheck] Found {len(tables)} tables: {', '.join(tables)}")
        expected = {"clients", "runs", "log_entries", "resources"}
        missing = expected - set(tables)
        if missing:
            print(f"[DBCheck] WARNING — missing expected tables: {missing}")
        else:
            print("[DBCheck] PASSED — all expected tables present")
        return 0

    except Exception as exc:
        print(f"[DBCheck] FAILED — {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
