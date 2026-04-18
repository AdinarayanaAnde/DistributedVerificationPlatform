"""
Verify required Python packages are installed.

Checks that the test runner dependencies are available
in the current Python environment.
"""

import importlib
import sys

REQUIRED_PACKAGES = [
    ("pytest", "pytest"),
    ("sqlalchemy", "SQLAlchemy"),
    ("fastapi", "FastAPI"),
    ("uvicorn", "uvicorn"),
    ("httpx", "httpx"),
]


def main() -> int:
    print("[DepsCheck] Verifying required packages ...")
    missing = []
    for module_name, display_name in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", "unknown")
            print(f"  ✓ {display_name} ({version})")
        except ImportError:
            print(f"  ✗ {display_name} — NOT FOUND")
            missing.append(display_name)

    if missing:
        print(f"[DepsCheck] FAILED — missing packages: {', '.join(missing)}")
        return 1

    print(f"[DepsCheck] PASSED — all {len(REQUIRED_PACKAGES)} packages available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
