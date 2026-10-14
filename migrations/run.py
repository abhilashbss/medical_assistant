"""Command-line entry point to apply migrations to a database file.

Usage:
    python migrations/run.py [path_to_sqlite_file]

When no path is given the value of the MEDICATION_TRACKER_DB environment
variable is used, falling back to an in-memory database (useful only for
smoke testing).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running both as `python migrations/run.py` and as a module.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medication_tracker.db import connect  # noqa: E402
from medication_tracker.migrations.runner import run_migrations  # noqa: E402


def main(argv) -> int:
    path = argv[1] if len(argv) > 1 else None
    conn = connect(path)
    try:
        applied = run_migrations(conn)
        if applied:
            print("Applied migrations:")
            for name in applied:
                print(f"  - {name}")
        else:
            print("Database is up to date.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))