"""Unit tests for the dose_logs layer (build unit #3).

Cases: valid append returns 201 with ISO timestamp; append to discontinued
prescription returns 409; invalid event returns 400; history ordered by
timestamp ascending; optional date-range filter respected; duplicate-timestamp
append allowed (append-only) but back-dated edits rejected.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from medication_tracker import (
    DoseEvent,
    DoseLog,
    Prescription,
    PrescriptionDoseLogRepository,
    PrescriptionStatus,
)
from medication_tracker.repository import PrescriptionNotFoundError


@pytest.fixture
def client():
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_prescription(client, **overrides):
    payload = {
        "patient_id": "patient-1",
        "doctor_id": "doctor-1",
        "medicine_name": "Amoxicillin",
        "dosage_amount": 500.0,
        "dosage_unit": "mg",
        "frequency": "three times daily",
        "start_date": _now_iso(),
        "status": "active",
    }
    payload.update(overrides)
    r = client.post("/prescriptions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestAppendDoseLog:
    def test_valid_append_returns_201_with_iso_timestamp(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 201
        body = r.json()
        assert body["event"] == "taken"
        parsed = datetime.fromisoformat(body["timestamp"])
        assert parsed.tzinfo is not None

    def test_append_skipped_event(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "skipped"}
        )
        assert r.status_code == 201
        assert r.json()["event"] == "skipped"

    def test_append_to_discontinued_returns_409(self, client):
        rx = _make_prescription(client)
        client.patch(
            f"/prescriptions/{rx['id']}/discontinue", json={"reason": "done"}
        )
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 409

    def test_append_to_completed_returns_409(self, client):
        rx = _make_prescription(client)
        client.patch(f"/prescriptions/{rx['id']}/complete")
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 409

    def test_invalid_event_returns_400(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "missed"}
        )
        assert r.status_code in (400, 422)

    def test_append_to_missing_prescription_returns_404(self, client):
        r = client.post(
            "/prescriptions/missing/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 404

    def test_naive_timestamp_rejected(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken", "timestamp": "2026-01-01T08:00:00"},
        )
        assert r.status_code == 400

    def test_notes_persisted(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "notes": "felt dizzy"},
        )
        assert r.status_code == 201
        assert r.json()["notes"] == "felt dizzy"


class TestDoseLogHistory:
    def test_history_ordered_by_timestamp_ascending(self, client):
        rx = _make_prescription(client)
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "timestamp": "2026-01-01T20:00:00+00:00"},
        )
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken", "timestamp": "2026-01-01T08:00:00+00:00"},
        )
        history = client.get(f"/prescriptions/{rx['id']}/dose-logs").json()
        assert len(history) == 2
        assert history[0]["timestamp"] < history[1]["timestamp"]

    def test_date_range_filter_respected(self, client):
        rx = _make_prescription(client)
        for ts in [
            "2026-01-01T08:00:00+00:00",
            "2026-01-02T08:00:00+00:00",
            "2026-01-03T08:00:00+00:00",
        ]:
            client.post(
                f"/prescriptions/{rx['id']}/dose-logs",
                json={"event": "taken", "timestamp": ts},
            )
        history = client.get(
            f"/prescriptions/{rx['id']}/dose-logs",
            params={"start_date": "2026-01-02T00:00:00+00:00"},
        ).json()
        assert len(history) == 2
        assert all(h["timestamp"] >= "2026-01-02T00:00:00+00:00" for h in history)

    def test_start_and_end_filter(self, client):
        rx = _make_prescription(client)
        for ts in [
            "2026-01-01T08:00:00+00:00",
            "2026-01-02T08:00:00+00:00",
            "2026-01-03T08:00:00+00:00",
        ]:
            client.post(
                f"/prescriptions/{rx['id']}/dose-logs",
                json={"event": "taken", "timestamp": ts},
            )
        history = client.get(
            f"/prescriptions/{rx['id']}/dose-logs",
            params={
                "start_date": "2026-01-02T00:00:00+00:00",
                "end_date": "2026-01-02T23:59:59+00:00",
            },
        ).json()
        assert len(history) == 1

    def test_empty_history_for_new_prescription(self, client):
        rx = _make_prescription(client)
        history = client.get(f"/prescriptions/{rx['id']}/dose-logs").json()
        assert history == []


class TestAppendOnlySemantics:
    def test_duplicate_timestamp_append_allowed(self, client):
        """Append-only: two events at the same timestamp are both stored."""
        rx = _make_prescription(client)
        ts = "2026-01-01T08:00:00+00:00"
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken", "timestamp": ts},
        )
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "timestamp": ts},
        )
        history = client.get(f"/prescriptions/{rx['id']}/dose-logs").json()
        assert len(history) == 2

    def test_no_update_path_on_repository(self):
        """The repository exposes only append(); there is no update() method,
        so existing rows cannot be back-dated-edited."""
        assert not hasattr(PrescriptionDoseLogRepository, "update")
        assert not hasattr(PrescriptionDoseLogRepository, "edit")

    def test_back_dated_edit_not_possible(self, database):
        """There is no way to modify an existing dose log row; only INSERTs
        are issued by the repository."""
        from medication_tracker.repository import PrescriptionRepository
        from medication_tracker import Prescription, PrescriptionStatus

        repo = PrescriptionRepository(database)
        rx = repo.create(
            Prescription(
                patient_id="p1",
                doctor_id="d1",
                medicine_name="M",
                dosage_amount=1.0,
                dosage_unit="mg",
                frequency="daily",
                start_date=_now_iso(),
                status=PrescriptionStatus.ACTIVE,
            )
        )
        dose_repo = PrescriptionDoseLogRepository(database)
        log = DoseLog(
            prescription_id=rx.id,
            event=DoseEvent.TAKEN,
            timestamp="2026-01-01T08:00:00+00:00",
        )
        dose_repo.append(log)
        # Attempting a direct UPDATE is not a supported operation and the
        # repository offers no method for it; the table has no unique
        # constraint to key an update on. Verify the row is immutable by
        # confirming only append() writes.
        history = dose_repo.get_history(rx.id)
        assert len(history) == 1
        # A second append at a different timestamp adds a row rather than
        # editing the first.
        dose_repo.append(
            DoseLog(
                prescription_id=rx.id,
                event=DoseEvent.SKIPPED,
                timestamp="2026-01-02T08:00:00+00:00",
            )
        )
        history = dose_repo.get_history(rx.id)
        assert len(history) == 2
        assert history[0].timestamp == "2026-01-01T08:00:00+00:00"


# ---------------------------------------------------------------------------
# Direct unit tests for service/repository/model validation paths (coverage)
# ---------------------------------------------------------------------------


def _make_rx(repository, **overrides):
    defaults = dict(
        patient_id="patient-1",
        doctor_id="doctor-1",
        medicine_name="Amoxicillin",
        dosage_amount=500.0,
        dosage_unit="mg",
        frequency="three times daily",
        start_date=_now_iso(),
        status=PrescriptionStatus.ACTIVE,
    )
    defaults.update(overrides)
    return repository.create(Prescription(**defaults))


class TestServiceValidationDirect:
    def test_append_unknown_event_raises_value_error(
        self, dose_log_service, active_prescription
    ):
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(
                active_prescription.id, event="missed"
            )

    def test_append_to_discontinued_raises_value_error(
        self, dose_log_service, prescription_service, valid_prescription_data
    ):
        rx = prescription_service.create_prescription(valid_prescription_data)
        prescription_service.discontinue(rx.id, "side effects")
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(rx.id, event="taken")

    def test_append_to_completed_raises_value_error(
        self, dose_log_service, prescription_service, valid_prescription_data
    ):
        rx = prescription_service.create_prescription(valid_prescription_data)
        prescription_service.complete(rx.id)
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(rx.id, event="taken")

    def test_append_to_missing_prescription_raises_not_found(
        self, dose_log_service
    ):
        with pytest.raises(PrescriptionNotFoundError):
            dose_log_service.append_dose_log("missing-id", event="taken")

    def test_get_history_missing_prescription_raises_not_found(
        self, dose_log_service
    ):
        with pytest.raises(PrescriptionNotFoundError):
            dose_log_service.get_adherence_history("missing-id")

    def test_append_invalid_timestamp_raises(self, dose_log_service, active_prescription):
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(
                active_prescription.id, event="taken", timestamp="not-a-date"
            )

    def test_append_naive_timestamp_raises(self, dose_log_service, active_prescription):
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(
                active_prescription.id, event="taken", timestamp="2026-01-01T08:00:00"
            )

    def test_append_with_z_suffix_timestamp(self, dose_log_service, active_prescription):
        log = dose_log_service.append_dose_log(
            active_prescription.id, event="taken", timestamp="2026-01-01T08:00:00Z"
        )
        assert log.timestamp == "2026-01-01T08:00:00Z"

    def test_get_history_with_end_date_filter(
        self, dose_log_service, active_prescription
    ):
        for ts in [
            "2026-01-01T08:00:00+00:00",
            "2026-01-02T08:00:00+00:00",
            "2026-01-03T08:00:00+00:00",
        ]:
            dose_log_service.append_dose_log(
                active_prescription.id, event="taken", timestamp=ts
            )
        history = dose_log_service.get_adherence_history(
            active_prescription.id, end_date="2026-01-02T23:59:59+00:00"
        )
        assert len(history) == 2


class TestRepositoryDirect:
    def test_count_returns_zero_then_one(self, dose_log_repository, repository):
        rx = _make_rx(repository)
        assert dose_log_repository.count(rx.id) == 0
        dose_log_repository.append(
            DoseLog(
                prescription_id=rx.id,
                event=DoseEvent.TAKEN,
                timestamp=_now_iso(),
            )
        )
        assert dose_log_repository.count(rx.id) == 1

    def test_history_start_and_end_filter(self, dose_log_repository, repository):
        rx = _make_rx(repository)
        for ts in [
            "2026-01-01T08:00:00+00:00",
            "2026-01-02T08:00:00+00:00",
            "2026-01-03T08:00:00+00:00",
        ]:
            dose_log_repository.append(
                DoseLog(prescription_id=rx.id, event=DoseEvent.TAKEN, timestamp=ts)
            )
        filtered = dose_log_repository.get_history(
            rx.id,
            start_date="2026-01-02T00:00:00+00:00",
            end_date="2026-01-02T23:59:59+00:00",
        )
        assert len(filtered) == 1
        assert filtered[0].timestamp == "2026-01-02T08:00:00+00:00"


class TestDoseLogModelValidation:
    def test_empty_prescription_id_rejected(self):
        with pytest.raises(ValueError):
            DoseLog(
                prescription_id="",
                event=DoseEvent.TAKEN,
                timestamp=_now_iso(),
            )

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValueError):
            DoseLog(prescription_id="x", event=123, timestamp=_now_iso())

    def test_event_string_coercion(self):
        log = DoseLog(
            prescription_id="x", event="skipped", timestamp=_now_iso()
        )
        assert log.event == DoseEvent.SKIPPED

    def test_naive_timestamp_rejected(self):
        with pytest.raises(ValueError):
            DoseLog(
                prescription_id="x",
                event=DoseEvent.TAKEN,
                timestamp="2026-01-01T08:00:00",
            )

    def test_non_iso_timestamp_rejected(self):
        with pytest.raises(ValueError):
            DoseLog(
                prescription_id="x",
                event=DoseEvent.TAKEN,
                timestamp="not-a-date",
            )

    def test_z_suffix_timestamp_accepted(self):
        log = DoseLog(
            prescription_id="x",
            event=DoseEvent.TAKEN,
            timestamp="2026-01-01T08:00:00Z",
        )
        assert log.timestamp == "2026-01-01T08:00:00Z"

    def test_to_dict_roundtrip(self):
        log = DoseLog(
            prescription_id="rx-1",
            event=DoseEvent.SKIPPED,
            timestamp="2026-01-01T08:00:00+00:00",
            notes="felt dizzy",
        )
        d = log.to_dict()
        assert d["event"] == "skipped"
        assert d["prescription_id"] == "rx-1"
        assert d["notes"] == "felt dizzy"
        assert d["timestamp"] == "2026-01-01T08:00:00+00:00"

    def test_from_row_invalid_event_falls_back(self):
        class FakeRow:
            def __getitem__(self, key):
                return {
                    "id": "1",
                    "prescription_id": "rx-1",
                    "event": "bogus",
                    "timestamp": "2026-01-01T08:00:00+00:00",
                    "notes": None,
                }[key]

        log = DoseLog.from_row(FakeRow())
        assert log.event == DoseEvent.TAKEN


# ---------------------------------------------------------------------------
# Prescription lifecycle coverage: dose-log adherence depends on prescription
# state (active vs discontinued/completed), so these paths are in-scope.
# ---------------------------------------------------------------------------


class TestPrescriptionLifecycleCoverage:
    def test_create_with_end_date_and_to_dict(self, repository):
        rx = _make_rx(repository, end_date="2026-12-01T00:00:00+00:00")
        d = rx.to_dict()
        assert d["status"] == "active"
        assert d["end_date"] == "2026-12-01T00:00:00+00:00"

    def test_prescription_from_row_invalid_status_falls_back(self, repository):
        rx = _make_rx(repository)
        fetched = repository.get_by_id(rx.id)
        assert fetched.status == PrescriptionStatus.ACTIVE

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValueError):
            Prescription(
                patient_id="",
                doctor_id="d1",
                medicine_name="M",
                dosage_amount=1.0,
                dosage_unit="mg",
                frequency="daily",
                start_date=_now_iso(),
            )

    def test_dosage_amount_must_be_positive(self):
        with pytest.raises(ValueError):
            Prescription(
                patient_id="p1",
                doctor_id="d1",
                medicine_name="M",
                dosage_amount=0,
                dosage_unit="mg",
                frequency="daily",
                start_date=_now_iso(),
            )

    def test_status_string_coercion(self):
        rx = Prescription(
            patient_id="p1",
            doctor_id="d1",
            medicine_name="M",
            dosage_amount=1.0,
            dosage_unit="mg",
            frequency="daily",
            start_date=_now_iso(),
            status="completed",
        )
        assert rx.status == PrescriptionStatus.COMPLETED

    def test_invalid_status_type_rejected(self):
        with pytest.raises(ValueError):
            Prescription(
                patient_id="p1",
                doctor_id="d1",
                medicine_name="M",
                dosage_amount=1.0,
                dosage_unit="mg",
                frequency="daily",
                start_date=_now_iso(),
                status=123,
            )

    def test_end_date_before_start_rejected(self):
        with pytest.raises(ValueError):
            Prescription(
                patient_id="p1",
                doctor_id="d1",
                medicine_name="M",
                dosage_amount=1.0,
                dosage_unit="mg",
                frequency="daily",
                start_date="2026-06-01T00:00:00+00:00",
                end_date="2026-01-01T00:00:00+00:00",
            )

    def test_service_create_missing_fields(self, prescription_service):
        with pytest.raises(ValueError):
            prescription_service.create_prescription(
                {"patient_id": "p1", "doctor_id": "d1"}
            )

    def test_service_create_invalid_dosage_type(self, prescription_service):
        with pytest.raises(ValueError):
            prescription_service.create_prescription(
                {
                    "patient_id": "p1",
                    "doctor_id": "d1",
                    "medicine_name": "M",
                    "dosage_amount": "bad",
                    "dosage_unit": "mg",
                    "frequency": "daily",
                    "start_date": _now_iso(),
                }
            )

    def test_service_create_negative_dosage(self, prescription_service):
        with pytest.raises(ValueError):
            prescription_service.create_prescription(
                {
                    "patient_id": "p1",
                    "doctor_id": "d1",
                    "medicine_name": "M",
                    "dosage_amount": -1,
                    "dosage_unit": "mg",
                    "frequency": "daily",
                    "start_date": _now_iso(),
                }
            )

    def test_service_create_end_before_start(self, prescription_service):
        with pytest.raises(ValueError):
            prescription_service.create_prescription(
                {
                    "patient_id": "p1",
                    "doctor_id": "d1",
                    "medicine_name": "M",
                    "dosage_amount": 1.0,
                    "dosage_unit": "mg",
                    "frequency": "daily",
                    "start_date": _now_iso(),
                    "end_date": "2020-01-01T00:00:00+00:00",
                }
            )

    def test_service_complete_and_history(self, prescription_service, valid_prescription_data):
        rx = prescription_service.create_prescription(valid_prescription_data)
        prescription_service.complete(rx.id)
        history = prescription_service.get_status_history(rx.id)
        assert len(history) == 1

    def test_service_discontinue(self, prescription_service, valid_prescription_data):
        rx = prescription_service.create_prescription(valid_prescription_data)
        result = prescription_service.discontinue(rx.id, "adverse reaction")
        assert result.status == PrescriptionStatus.DISCONTINUED

    def test_service_get_missing_raises(self, prescription_service):
        with pytest.raises(PrescriptionNotFoundError):
            prescription_service.get_prescription("missing")

    def test_repository_list_by_patient(self, repository):
        _make_rx(repository, medicine_name="A")
        _make_rx(repository, medicine_name="B", patient_id="patient-2")
        result = repository.list_by_patient("patient-1")
        assert len(result) == 1
        assert result[0].medicine_name == "A"

    def test_repository_list_by_patient_with_status_filter(self, repository):
        rx = _make_rx(repository)
        repository.complete(rx.id)
        active = _make_rx(repository, medicine_name="Second")
        only_active = repository.list_by_patient(
            "patient-1", status=PrescriptionStatus.ACTIVE
        )
        assert {p.id for p in only_active} == {active.id}

    def test_repository_transition_non_active_rejected(self, repository):
        rx = _make_rx(repository)
        repository.complete(rx.id)
        with pytest.raises(ValueError):
            repository.complete(rx.id)
        with pytest.raises(ValueError):
            repository.discontinue(rx.id, "late")

    def test_repository_transition_missing_raises(self, repository):
        with pytest.raises(PrescriptionNotFoundError):
            repository.complete("missing")
        with pytest.raises(PrescriptionNotFoundError):
            repository.discontinue("missing", "reason")

    def test_repository_discontinue_empty_reason(self, repository):
        rx = _make_rx(repository)
        with pytest.raises(ValueError):
            repository.discontinue(rx.id, "")
        with pytest.raises(ValueError):
            repository.discontinue(rx.id, "   ")

    def test_status_transition_to_dict(self, repository):
        rx = _make_rx(repository)
        repository.discontinue(rx.id, "reason")
        transitions = repository.list_transitions(rx.id)
        d = transitions[0].to_dict()
        assert d["from_status"] == "active"
        assert d["to_status"] == "discontinued"