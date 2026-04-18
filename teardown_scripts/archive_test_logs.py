"""
Archive test logs and reports for historical analysis.

Copies test artifacts to a timestamped archive directory
for post-run review and long-term storage.
"""

import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "reports")
ARCHIVE_DIR = os.path.join(ROOT, "data", "archives")


def main() -> int:
    if not os.path.exists(REPORTS_DIR):
        print("[Archive] No reports directory found — nothing to archive")
        print("[Archive] PASSED — skipped")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(ARCHIVE_DIR, f"run_{timestamp}")

    os.makedirs(archive_path, exist_ok=True)

    archived = 0
    for item in os.listdir(REPORTS_DIR):
        src = os.path.join(REPORTS_DIR, item)
        if os.path.isdir(src):
            # Only archive the latest run directory (highest numbered)
            try:
                int(item)
            except ValueError:
                continue
            dst = os.path.join(archive_path, item)
            shutil.copytree(src, dst, dirs_exist_ok=True)
            archived += 1

    print(f"[Archive] Archived {archived} report(s) to {archive_path}")
    print("[Archive] PASSED — logs archived successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
