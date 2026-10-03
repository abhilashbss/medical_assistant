"""Repo-root conftest.

Ensures the repository root is on ``sys.path`` so that the
``medication_tracker`` package is importable when tests are run with a
bare ``pytest`` invocation (no ``python -m pytest`` and no installed
package). Pytest inserts this file's directory onto ``sys.path`` at
collection time.
"""