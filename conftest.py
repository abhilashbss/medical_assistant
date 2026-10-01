"""Root pytest config: make vendored pure-Python deps (e.g. httpx) importable
for environments where they are not installed system-wide.

Starlette's TestClient requires httpx, which may not be installed in the gate
runner's interpreter. We vendor it locally and prepend the vendor dir to
sys.path so `from fastapi.testclient import TestClient` works.
"""

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / ".vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))