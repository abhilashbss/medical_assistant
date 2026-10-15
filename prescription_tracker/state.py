"""Global state for the prescription tracker application."""
from __future__ import annotations

import os
from .db import init_db
from .repository import PrescriptionRepository

DB_PATH = os.environ.get("PRESCRIPTION_DB_PATH", ":memory:")
conn = init_db(DB_PATH)
repo = PrescriptionRepository(conn)
