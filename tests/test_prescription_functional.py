"""Functional tests for the prescription tracker across the full stack.

Gate criteria covered:
- Creating a prescription with all required fields persists and is retrievable by patient ID.
- Prescription history returns entries sorted by start date descending including discontinued/completed.
- Discontinuing a prescription requires a reason and prevents deletion of the historical record.
- Validation rejects prescriptions missing required fields or with end date preceding start date.
- Concurrent active prescriptions for the same medicine per patient are rejected by the partial unique index.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from prescription_tracker.models import Prescription, PrescriptionStatus
from prescription_tracker.service import ConflictError, PrescriptionService


# ----------------------------------------------------------------------
# Fixtures local to the functional suite
# ----------------------------------------------------------------------
@pytest.fixture
def app():
    from prescription_tracker.api import create_app

    application = create_app(db_path=":memory:")
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def api_service(app):
    """Reach the service wired into the Flask app for cross-checking."""
    # The service is created inside create_app; re-create on the same in-memory
    # DB is not possible, so expose via the app's service by constructing one
    # that shares the app's database connection through the test client only.
    # For direct data-layer assertions we use the standalone service fixture.
    from prescription_tracker.database import Database
    from prescription_tracker.service import PrescriptionService

    db = Database(":memory:")
    db.init_schema()
    service = PrescriptionService(db)
    service._database = db
    return service


def _payload(patient_id, doctor_id, **overrides):
    base = {
        "patient_id": str(patient_id),
        "doctor_id": str(doctor_id),
        "medicine_name": "Amoxicillin",
        "dosage_amount": "500",
        "dosage_unit": "mg",
        "frequency": "three times daily",
        "start_date": "2026-01-01T08:00:00+00:00",
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------
# Create + retrieve
# ----------------------------------------------------------------------
class TestCreateAndRetrieve:
    def test_create_with_all_required_fields_persists_and_is_retrievable(self, service, patient_id, doctor_id):
        rx = Prescription(
            patient_id=patient_id,
            doctor_id=doctor_id,
            medicine_name="Amoxicillin",
            dosage_amount="500",
            dosage_unit="mg",
            frequency="three times daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        created = service.create_prescription(rx)
        assert created.id is not None

        fetched = service.get_prescription(created.id)
        assert fetched is not None
        assert fetched.patient_id == patient_id
        assert fetched.doctor_id == doctor_id
        assert fetched.medicine_name == "Amoxicillin"
        assert fetched.dosage_amount == "500"
        assert fetched.dosage_unit == "mg"
        assert fetched.frequency == "three times daily"
        assert fetched.status == PrescriptionStatus.ACTIVE

    def test_create_via_api_returns_201_and_is_retrievable(self, client, patient_id, doctor_id):
        response = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        assert response.status_code == 201
        body = response.get_json()
        assert body["medicine_name"] == "Amoxicillin"
        assert body["status"] == "active"

        fetch = client.get(f"/prescriptions/{body['id']}")
        assert fetch.status_code == 200
        assert fetch.get_json()["id"] == body["id"]

    def test_get_missing_prescription_returns_404(self, client):
        response = client.get(f"/prescriptions/{uuid4()}")
        assert response.status_code == 404


# ----------------------------------------------------------------------
# Validation rejections
# ----------------------------------------------------------------------
class TestValidationRejections:
    @pytest.mark.parametrize("missing_field", [
        "patient_id",
        "doctor_id",
        "medicine_name",
        "dosage_amount",
        "dosage_unit",
        "frequency",
        "start_date",
    ])
    def test_missing_required_field_rejected(self, client, patient_id, doctor_id, missing_field):
        payload = _payload(patient_id, doctor_id)
        del payload[missing_field]
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400

    def test_end_date_preceding_start_date_rejected(self, client, patient_id, doctor_id):
        payload = _payload(
            patient_id,
            doctor_id,
            end_date="2025-12-31T08:00:00+00:00",
        )
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400
        assert "end_date" in response.get_json()["error"]

    def test_empty_medicine_name_rejected(self, client, patient_id, doctor_id):
        payload = _payload(patient_id, doctor_id, medicine_name="   ")
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400

    def test_naive_start_date_rejected(self, client, patient_id, doctor_id):
        payload = _payload(patient_id, doctor_id, start_date="2026-01-01T08:00:00")
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400


# ----------------------------------------------------------------------
# History sorted by start_date DESC, active separated, including terminal
# ----------------------------------------------------------------------
class TestHistorySortingAndPartitioning:
    def test_history_sorted_start_date_desc_with_active_separated(self, service, patient_id, doctor_id):
        older = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        newer = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedB",
            dosage_amount="200", dosage_unit="mg", frequency="daily",
            start_date="2026-06-01T08:00:00+00:00",
        )
        middle = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedC",
            dosage_amount="300", dosage_unit="mg", frequency="daily",
            start_date="2026-03-01T08:00:00+00:00",
        )

        service.create_prescription(older)
        service.create_prescription(newer)
        created_middle = service.create_prescription(middle)
        service.complete_prescription(created_middle.id)

        history = service.get_patient_history(patient_id)
        active = history["active"]
        historical = history["historical"]

        # Active partition holds the two still-active prescriptions, sorted DESC.
        active_starts = [datetime.fromisoformat(rx.start_date.isoformat()) for rx in active]
        assert active_starts == sorted(active_starts, reverse=True)
        assert all(rx.status == PrescriptionStatus.ACTIVE for rx in active)
        assert len(active) == 2

        # Historical partition holds the completed entry.
        assert len(historical) == 1
        assert historical[0].status == PrescriptionStatus.COMPLETED

    def test_history_includes_discontinued_and_completed(self, service, patient_id, doctor_id):
        rx1 = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        rx2 = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedB",
            dosage_amount="200", dosage_unit="mg", frequency="daily",
            start_date="2026-02-01T08:00:00+00:00",
        ))

        service.discontinue_prescription(rx1.id, reason="Side effects")
        service.complete_prescription(rx2.id)

        history = service.get_patient_history(patient_id)
        statuses = {rx.status for rx in history["historical"]}
        assert PrescriptionStatus.DISCONTINUED in statuses
        assert PrescriptionStatus.COMPLETED in statuses

    def test_history_via_api_partitions_active_and_historical(self, client, patient_id, doctor_id):
        first = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="MedA",
                                                              start_date="2026-01-01T08:00:00+00:00"))
        second = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="MedB",
                                                              start_date="2026-06-01T08:00:00+00:00"))
        client.patch(f"/prescriptions/{first.get_json()['id']}/complete")

        response = client.get(f"/patients/{patient_id}/prescriptions")
        assert response.status_code == 200
        body = response.get_json()
        assert len(body["active"]) == 1
        assert len(body["historical"]) == 1
        assert body["historical"][0]["status"] == "completed"


# ----------------------------------------------------------------------
# Discontinue requires reason, prevents deletion of historical record
# ----------------------------------------------------------------------
class TestDiscontinueReasonAndImmutability:
    def test_discontinue_without_reason_returns_400(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        response = client.patch(f"/prescriptions/{rx_id}/discontinue", json={})
        assert response.status_code == 400
        assert "reason" in response.get_json()["error"]

    def test_discontinue_with_reason_succeeds_and_records_reason(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        response = client.patch(
            f"/prescriptions/{rx_id}/discontinue",
            json={"reason": "Patient experienced nausea"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "discontinued"

    def test_discontinue_prevents_deletion_of_historical_record(self, service, patient_id, doctor_id):
        rx = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        service.discontinue_prescription(rx.id, reason="No longer needed")

        # The row must still exist (immutability: no deletion permitted).
        fetched = service.get_prescription(rx.id)
        assert fetched is not None
        assert fetched.status == PrescriptionStatus.DISCONTINUED

    def test_no_put_or_delete_endpoints_on_prescriptions(self, client, patient_id, doctor_id):
        """Immutability: PUT and DELETE must not be supported on prescriptions."""
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        put_resp = client.put(f"/prescriptions/{rx_id}", json={"medicine_name": "Changed"})
        assert put_resp.status_code == 405

        delete_resp = client.delete(f"/prescriptions/{rx_id}")
        assert delete_resp.status_code == 405


# ----------------------------------------------------------------------
# Concurrent active prescription uniqueness (partial index)
# ----------------------------------------------------------------------
class TestOneActivePerMedicine:
    def test_duplicate_active_for_same_patient_medicine_rejected(self, service, patient_id, doctor_id):
        first = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="500", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        service.create_prescription(first)

        second = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="250", dosage_unit="mg", frequency="daily",
            start_date="2026-02-01T08:00:00+00:00",
        )
        with pytest.raises(ConflictError):
            service.create_prescription(second)

    def test_duplicate_active_via_api_returns_409(self, client, patient_id, doctor_id):
        first = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="Amoxicillin"))
        assert first.status_code == 201

        second = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="Amoxicillin",
                                                              start_date="2026-06-01T08:00:00+00:00"))
        assert second.status_code == 409

    def test_allows_second_active_after_first_completed(self, service, patient_id, doctor_id):
        first = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="500", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        service.complete_prescription(first.id)

        second = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="250", dosage_unit="mg", frequency="daily",
            start_date="2026-06-01T08:00:00+00:00",
        ))
        assert second.status == PrescriptionStatus.ACTIVE

    def test_partial_unique_index_exists(self, database):
        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_one_active_per_medicine'"
        )
        row = cursor.fetchone()
        assert row is not None, "partial unique index idx_one_active_per_medicine must exist"


# ----------------------------------------------------------------------
# Evidence capture: console transcript of the real API lifecycle
# ----------------------------------------------------------------------
class TestEvidenceTranscript:
    """Drive the full milestone lifecycle through the real Flask test client
    and capture a readable console transcript of every request/response into
    .see/e2e-artifacts/console-transcript.txt.

    The assertions here are genuine lifecycle checks — the test still fails if
    any gate-relevant behaviour breaks. The transcript is a side effect.
    """

    @pytest.fixture(autouse=True)
    def _transcript_writer(self):
        lines: list = []
        self._lines = lines
        yield lines
        artifact_dir = Path(os.environ.get("EVIDENCE_DIR", ".see/e2e-artifacts"))
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "console-transcript.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _record(self, client, method, path, json_body=None, label=""):
        """Issue a request, append a transcript block, return the response."""
        self._lines.append("")
        if label:
            self._lines.append(f"# --- {label} ---")
        self._lines.append(f"> {method.upper()} {path}")
        if json_body is not None:
            self._lines.append(f"> body: {json.dumps(json_body)}")
        response = getattr(client, method)(path, json=json_body)
        self._lines.append(f"< HTTP {response.status_code}")
        try:
            body = response.get_json()
            self._lines.append(f"< body: {json.dumps(body)}")
        except Exception:
            self._lines.append(f"< body: {response.data.decode('utf-8', errors='replace')}")
        return response

    def test_lifecycle_transcript(self, client, patient_id, doctor_id):
        self._lines.append(
            "console-transcript: prescription tracker lifecycle "
            "(create, retrieve, list, complete, discontinue, immutability, duplicate-active)"
        )

        # 1. Create a valid prescription -> 201
        created = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Amoxicillin"),
            label="Create valid prescription",
        )
        assert created.status_code == 201
        rx_id = created.get_json()["id"]

        # 2. Retrieve it by ID -> 200
        fetched = self._record(
            client, "get", f"/prescriptions/{rx_id}",
            label="Retrieve by ID",
        )
        assert fetched.status_code == 200
        assert fetched.get_json()["status"] == "active"

        # 3. Missing required field -> 400
        bad = _payload(patient_id, doctor_id)
        del bad["medicine_name"]
        invalid = self._record(
            client, "post", "/prescriptions", bad,
            label="Validation: missing required field",
        )
        assert invalid.status_code == 400

        # 4. end_date before start_date -> 400
        inverted = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="BadMed",
                     end_date="2025-12-31T08:00:00+00:00"),
            label="Validation: end_date precedes start_date",
        )
        assert inverted.status_code == 400

        # 5. Create a second prescription to exercise history sorting
        second = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Metformin",
                     start_date="2026-06-01T08:00:00+00:00"),
            label="Create second prescription (newer start_date)",
        )
        assert second.status_code == 201
        second_id = second.get_json()["id"]

        # 6. Complete the first prescription
        completed = self._record(
            client, "patch", f"/prescriptions/{rx_id}/complete",
            label="Status transition: complete",
        )
        assert completed.status_code == 200
        assert completed.get_json()["status"] == "completed"

        # 7. Discontinue the second without reason -> 400
        no_reason = self._record(
            client, "patch", f"/prescriptions/{second_id}/discontinue", {},
            label="Discontinue without reason (rejected)",
        )
        assert no_reason.status_code == 400

        # 8. Discontinue with reason -> 200
        discontinued = self._record(
            client, "patch", f"/prescriptions/{second_id}/discontinue",
            {"reason": "Patient experienced nausea"},
            label="Discontinue with reason",
        )
        assert discontinued.status_code == 200
        assert discontinued.get_json()["status"] == "discontinued"

        # 9. Immutability: re-completing a completed prescription -> 400
        recomplete = self._record(
            client, "patch", f"/prescriptions/{rx_id}/complete",
            label="Immutability: re-complete a completed prescription (rejected)",
        )
        assert recomplete.status_code == 400

        # 10. PUT on a prescription -> 405 (mutation blocked)
        put_resp = self._record(
            client, "put", f"/prescriptions/{rx_id}",
            {"medicine_name": "Changed"}, label="Immutability: PUT rejected (405)",
        )
        assert put_resp.status_code == 405

        # 11. DELETE on a prescription -> 405 (no deletion of historical record)
        del_resp = self._record(
            client, "delete", f"/prescriptions/{rx_id}",
            label="Immutability: DELETE rejected (405)",
        )
        assert del_resp.status_code == 405

        # 12. List patient history -> active separated from historical, sorted DESC
        history = self._record(
            client, "get", f"/patients/{patient_id}/prescriptions",
            label="List patient history (sorted start_date DESC, active separated)",
        )
        assert history.status_code == 200
        body = history.get_json()
        assert len(body["historical"]) == 2
        starts = [datetime.fromisoformat(h["start_date"]) for h in body["historical"]]
        assert starts == sorted(starts, reverse=True)

        # 13. Create a fresh active prescription, then attempt a duplicate
        #     for the same patient+medicine while the first is still active -> 409
        active_rx = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Ibuprofen",
                     start_date="2026-08-01T08:00:00+00:00"),
            label="Create a fresh active prescription (Ibuprofen)",
        )
        assert active_rx.status_code == 201

        dup = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Ibuprofen",
                     start_date="2026-09-01T08:00:00+00:00"),
            label="Duplicate active prescription for same medicine (409)",
        )
        assert dup.status_code == 409

        self._lines.append("")
        self._lines.append("# end of transcript")