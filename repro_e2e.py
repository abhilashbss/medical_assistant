"""Probe: does the E2E send dosage_amount as a number? Many API clients do."""
from uuid import uuid4
from prescription_tracker.api import create_app

app = create_app(db_path=":memory:")
c = app.test_client()
pid = str(uuid4()); doc = str(uuid4())

# dosage_amount as a NUMBER (JSON number), not a string. A real user/E2E
# client would naturally send 500 or 500.0, not "500".
payload = {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Amoxicillin",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-01-01T08:00:00+00:00",
}
r = c.post("/prescriptions", json=payload)
print("numeric dosage_amount ->", r.status_code, r.get_json())

# dosage_amount as int
payload["dosage_amount"] = 500
r = c.post("/prescriptions", json=payload)
print("int dosage_amount ->", r.status_code)