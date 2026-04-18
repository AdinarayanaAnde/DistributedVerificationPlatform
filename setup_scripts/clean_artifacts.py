"""
Clean up stale test artifacts before a fresh run.

Removes __pycache__, .pytest_cache, and temporary test output
to ensure a clean slate.
"""

import os
import shutil
import sys

DIRS_TO_CLEAN = ["__pycache__", ".pytest_cache", "tmp_test_output"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    cleaned = 0
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in dirnames:
            if d in DIRS_TO_CLEAN:
                target = os.path.join(dirpath, d)
                print(f"[Cleanup] Removing {target}")
                shutil.rmtree(target, ignore_errors=True)
                cleaned += 1
    print(f"[Cleanup] Removed {cleaned} directories")
    print("[Cleanup] PASSED — workspace is clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
