"""Probe dose-log edge cases that tests might miss."""
import sys
sys.path.insert(0, ".vendor")
from fastapi.testclient import TestClient
from api.app import create_app

app = create_app(":memory:")
with TestClient(app) as c:
    # create active prescription
    r = c.post("/prescriptions", json={
        "patient_id": "p1", "doctor_id": "d1", "medicine_name": "Amox",
        "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
        "start_date": "2026-01-01T08:00:00+00:00"})
    rx_id = r.json()["id"]

    # 1. append with NO timestamp -> defaults to now
    r = c.post(f"/prescriptions/{rx_id}/dose-logs", json={"event": "taken"})
    print("no timestamp ->", r.status_code, r.json().get("timestamp"))

    # 2. append with notes=None explicitly
    r = c.post(f"/prescriptions/{rx_id}/dose-logs", json={"event": "taken", "notes": None})
    print("notes null ->", r.status_code)

    # 3. append with Z-suffix timestamp
    r = c.post(f"/prescriptions/{rx_id}/dose-logs", json={"event": "taken", "timestamp": "2026-01-01T08:00:00Z"})
    print("Z timestamp ->", r.status_code, r.text[:150])

    # 4. history after multiple
    r = c.get(f"/prescriptions/{rx_id}/dose-logs")
    print("history count ->", r.status_code, len(r.json()))

    # 5. dose-log to missing prescription (non-uuid string)
    r = c.post("/prescriptions/missing-id/dose-logs", json={"event": "taken"})
    print("missing rx ->", r.status_code, r.text[:120])

    # 6. invalid timestamp format
    r = c.post(f"/prescriptions/{rx_id}/dose-logs", json={"event": "taken", "timestamp": "not-a-date"})
    print("bad timestamp ->", r.status_code, r.text[:120])