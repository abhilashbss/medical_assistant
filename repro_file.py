"""Simulate the E2E running against a persistent file DB twice (idempotency)."""
import os, sys
sys.path.insert(0, ".vendor")
from fastapi.testclient import TestClient
from api.app import create_app

db = "/tmp/repro_unit3_persist.db"
if os.path.exists(db):
    os.remove(db)

# First run: full lifecycle
app = create_app(db_path=db)
with TestClient(app) as c:
    r = c.post("/prescriptions", json={
        "patient_id": "p1", "doctor_id": "d1", "medicine_name": "Amox",
        "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
        "start_date": "2026-01-01T08:00:00+00:00"})
    print("run1 create ->", r.status_code)
    rx = r.json()["id"]
    r = c.post(f"/prescriptions/{rx}/dose-logs", json={"event": "taken"})
    print("run1 dose-log ->", r.status_code)

# Second run on SAME file db (simulates E2E re-run or server restart)
app2 = create_app(db_path=db)
with TestClient(app2) as c:
    # history should still show the dose log
    r = c.get(f"/prescriptions/{rx}/dose-logs")
    print("run2 dose-log history ->", r.status_code, len(r.json()) if r.status_code==200 else r.text[:120])
    # create the same medicine again -> should 409 (active still exists)
    r = c.post("/prescriptions", json={
        "patient_id": "p1", "doctor_id": "d1", "medicine_name": "Amox",
        "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
        "start_date": "2026-02-01T08:00:00+00:00"})
    print("run2 dup active ->", r.status_code)

os.remove(db)