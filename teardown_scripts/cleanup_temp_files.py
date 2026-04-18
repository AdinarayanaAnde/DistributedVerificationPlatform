"""
Clean up temporary files and test artifacts after a test run.

Removes __pycache__, .pytest_cache, temporary output directories,
and other ephemeral files generated during test execution.
"""

import os
import shutil
import sys

DIRS_TO_CLEAN = ["__pycache__", ".pytest_cache", "tmp_test_output", ".hypothesis"]
FILES_TO_CLEAN = ["*.pyc", "*.pyo", ".coverage"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    cleaned_dirs = 0
    cleaned_files = 0

    for dirpath, dirnames, filenames in os.walk(ROOT):
        for d in dirnames:
            if d in DIRS_TO_CLEAN:
                target = os.path.join(dirpath, d)
                print(f"[Cleanup] Removing directory: {target}")
                shutil.rmtree(target, ignore_errors=True)
                cleaned_dirs += 1

    # Clean individual files
    import glob
    for pattern in FILES_TO_CLEAN:
        for filepath in glob.glob(os.path.join(ROOT, "**", pattern), recursive=True):
            try:
                os.remove(filepath)
                print(f"[Cleanup] Removed file: {filepath}")
                cleaned_files += 1
            except OSError:
                pass

    print(f"[Cleanup] Removed {cleaned_dirs} directories and {cleaned_files} files")
    print("[Cleanup] PASSED — workspace cleaned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
