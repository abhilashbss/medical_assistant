"""Unit tests for the prescription repository, lifecycle, and dose logs.

Covers the gate success criteria for the unit test command:
  - Create prescription persists all fields and is retrievable by patient ID
  - Validation rejects missing required fields and end date before start date
  - Status transitions append timestamped audit rows and enforce immutability
  - Discontinuation requires a non-empty reason and blocks accidental record deletion
  - Partial unique index prevents two concurrent active prescriptions
  - Dose logs append timestamped adherence records queryable per medication ordered by time
"""

import sqlite3
from datetime import datetime, timezone

import pytest

from medication_tracker import (
    DoseEvent,
    DoseLog,
    Prescription,
    PrescriptionRepository,
    PrescriptionService,
    PrescriptionStatus,
)
from medication_tracker.repository import PrescriptionNotFoundError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_valid_prescription(**overrides) -> Prescription:
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
    return Prescription(**defaults)


# ---------------------------------------------------------------------------
# Create persists all fields and is retrievable by patient ID
# ---------------------------------------------------------------------------


class TestCreateAndRetrieve:
    def test_create_persists_all_fields(self, repository):
        rx = make_valid_prescription(medicine_name="Metformin", dosage_amount=850.0)
        created = repository.create(rx)
        fetched = repository.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.patient_id == "patient-1"
        assert fetched.doctor_id == "doctor-1"
        assert fetched.medicine_name == "Metformin"
        assert fetched.dosage_amount == 850.0
        assert fetched.dosage_unit == "mg"
        assert fetched.frequency == "three times daily"
        assert fetched.status == PrescriptionStatus.ACTIVE
        assert fetched.start_date == created.start_date

    def test_retrieve_by_patient_id(self, repository):
        rx1 = repository.create(make_valid_prescription(medicine_name="Drug A"))
        rx2 = repository.create(
            make_valid_prescription(medicine_name="Drug B", patient_id="patient-2")
        )
        patient1 = repository.list_by_patient("patient-1")
        patient2 = repository.list_by_patient("patient-2")
        assert {p.id for p in patient1} == {rx1.id}
        assert {p.id for p in patient2} == {rx2.id}

    def test_get_by_id_missing_returns_none(self, repository):
        assert repository.get_by_id("does-not-exist") is None


# ---------------------------------------------------------------------------
# Validation rejects missing required fields and end date before start date
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        "field",
        [
            "patient_id",
            "doctor_id",
            "medicine_name",
            "dosage_unit",
            "frequency",
            "start_date",
        ],
    )
    def test_missing_required_field_raises(self, field):
        kwargs = dict(
            patient_id="patient-1",
            doctor_id="doctor-1",
            medicine_name="Amoxicillin",
            dosage_amount=500.0,
            dosage_unit="mg",
            frequency="daily",
            start_date=_now_iso(),
        )
        kwargs[field] = ""
        with pytest.raises(ValueError):
            Prescription(**kwargs)

    def test_dosage_amount_must_be_positive(self):
        with pytest.raises(ValueError):
            make_valid_prescription(dosage_amount=0)
        with pytest.raises(ValueError):
            make_valid_prescription(dosage_amount=-5.0)

    def test_end_date_before_start_date_raises(self):
        start = _now_iso()
        end = "2020-01-01T00:00:00+00:00"
        with pytest.raises(ValueError):
            make_valid_prescription(start_date=start, end_date=end)

    def test_end_date_after_start_date_allowed(self):
        start = "2026-01-01T00:00:00+00:00"
        end = "2026-06-01T00:00:00+00:00"
        rx = make_valid_prescription(start_date=start, end_date=end)
        assert rx.end_date == end

    def test_naive_start_date_without_timezone_rejected(self):
        with pytest.raises(ValueError):
            make_valid_prescription(start_date="2026-01-01T00:00:00")

    def test_non_iso8601_start_date_rejected(self):
        with pytest.raises(ValueError):
            make_valid_prescription(start_date="not-a-date")

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            make_valid_prescription(status="bogus")


# ---------------------------------------------------------------------------
# Status transitions append timestamped audit rows and enforce immutability
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    def test_complete_appends_audit_row(self, repository):
        rx = repository.create(make_valid_prescription())
        repository.complete(rx.id)
        fetched = repository.get_by_id(rx.id)
        assert fetched.status == PrescriptionStatus.COMPLETED
        transitions = repository.list_transitions(rx.id)
        assert len(transitions) == 1
        assert transitions[0].from_status == PrescriptionStatus.ACTIVE
        assert transitions[0].to_status == PrescriptionStatus.COMPLETED
        assert transitions[0].timestamp is not None

    def test_discontinue_appends_audit_row_with_reason(self, repository):
        rx = repository.create(make_valid_prescription())
        repository.discontinue(rx.id, "Adverse reaction")
        fetched = repository.get_by_id(rx.id)
        assert fetched.status == PrescriptionStatus.DISCONTINUED
        transitions = repository.list_transitions(rx.id)
        assert len(transitions) == 1
        assert transitions[0].reason == "Adverse reaction"

    def test_transition_on_non_active_rejected(self, repository):
        rx = repository.create(make_valid_prescription())
        repository.complete(rx.id)
        with pytest.raises(ValueError):
            repository.complete(rx.id)
        with pytest.raises(ValueError):
            repository.discontinue(rx.id, "late reason")

    def test_transition_timestamps_are_iso8601(self, repository):
        rx = repository.create(make_valid_prescription())
        repository.discontinue(rx.id, "side effects")
        transitions = repository.list_transitions(rx.id)
        ts = transitions[0].timestamp
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_immutable_except_status_transition(self, repository):
        """No general update path exists; the only mutation is a status
        transition, which changes status only."""
        rx = repository.create(make_valid_prescription(medicine_name="Original"))
        # No update method is exposed on the repository for fields other than
        # status transitions. Confirm only status changes via complete().
        repository.complete(rx.id)
        fetched = repository.get_by_id(rx.id)
        assert fetched.medicine_name == "Original"
        assert fetched.dosage_amount == 500.0
        assert fetched.status == PrescriptionStatus.COMPLETED

    def test_transition_missing_prescription_raises(self, repository):
        with pytest.raises(PrescriptionNotFoundError):
            repository.complete("missing-id")
        with pytest.raises(PrescriptionNotFoundError):
            repository.discontinue("missing-id", "reason")


# ---------------------------------------------------------------------------
# Discontinuation requires a non-empty reason and blocks accidental deletion
# ---------------------------------------------------------------------------


class TestDiscontinuation:
    def test_empty_reason_rejected(self, repository):
        rx = repository.create(make_valid_prescription())
        with pytest.raises(ValueError):
            repository.discontinue(rx.id, "")
        with pytest.raises(ValueError):
            repository.discontinue(rx.id, "   ")

    def test_no_delete_method_exposed(self):
        """The repository intentionally exposes no delete() for prescriptions
        so historical records cannot be accidentally removed."""
        assert not hasattr(PrescriptionRepository, "delete")

    def test_cascade_blocked_by_restrict_fk(self, database, repository):
        """Deleting a patient with a prescription is blocked by ON DELETE
        RESTRICT, preserving historical prescription rows."""
        rx = repository.create(make_valid_prescription())
        with pytest.raises(sqlite3.IntegrityError):
            with database.transaction() as conn:
                conn.execute("DELETE FROM patients WHERE id = ?", (rx.patient_id,))


# ---------------------------------------------------------------------------
# Partial unique index prevents two concurrent active prescriptions
# ---------------------------------------------------------------------------


class TestUniqueActivePrescription:
    def test_duplicate_active_same_medicine_rejected(self, repository):
        repository.create(make_valid_prescription(medicine_name="Ibuprofen"))
        with pytest.raises(sqlite3.IntegrityError):
            repository.create(
                make_valid_prescription(medicine_name="Ibuprofen")
            )

    def test_duplicate_active_different_medicine_allowed(self, repository):
        repository.create(make_valid_prescription(medicine_name="Ibuprofen"))
        repository.create(
            make_valid_prescription(medicine_name="Paracetamol")
        )

    def test_historical_duplicate_allowed_after_transition(self, repository):
        rx1 = repository.create(make_valid_prescription(medicine_name="Ibuprofen"))
        repository.complete(rx1.id)
        # A second active prescription for the same medicine is now allowed
        # because the first is no longer active.
        rx2 = repository.create(make_valid_prescription(medicine_name="Ibuprofen"))
        assert rx2.status == PrescriptionStatus.ACTIVE

    def test_duplicate_for_different_patient_allowed(self, repository):
        repository.create(
            make_valid_prescription(patient_id="patient-1", medicine_name="Ibuprofen")
        )
        repository.create(
            make_valid_prescription(patient_id="patient-2", medicine_name="Ibuprofen")
        )


# ---------------------------------------------------------------------------
# Dose logs append timestamped adherence records queryable per medication
# ordered by time
# ---------------------------------------------------------------------------


class TestDoseLogs:
    def test_append_and_retrieve_dose_log(self, dose_log_repository, repository):
        rx = repository.create(make_valid_prescription())
        log = DoseLog(
            prescription_id=rx.id,
            event=DoseEvent.TAKEN,
            timestamp=_now_iso(),
        )
        dose_log_repository.append(log)
        history = dose_log_repository.get_history(rx.id)
        assert len(history) == 1
        assert history[0].event == DoseEvent.TAKEN
        assert history[0].prescription_id == rx.id

    def test_history_ordered_by_timestamp_ascending(self, dose_log_repository, repository):
        rx = repository.create(make_valid_prescription())
        early = DoseLog(
            prescription_id=rx.id,
            event=DoseEvent.TAKEN,
            timestamp="2026-01-01T08:00:00+00:00",
        )
        late = DoseLog(
            prescription_id=rx.id,
            event=DoseEvent.SKIPPED,
            timestamp="2026-01-01T20:00:00+00:00",
        )
        # Append out of order to prove ordering happens on read
        dose_log_repository.append(late)
        dose_log_repository.append(early)
        history = dose_log_repository.get_history(rx.id)
        assert [h.timestamp for h in history] == [early.timestamp, late.timestamp]

    def test_history_date_range_filter(self, dose_log_repository, repository):
        rx = repository.create(make_valid_prescription())
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

    def test_append_only_no_update_path(self, dose_log_repository, repository):
        """The repository exposes only append(); there is no update() for
        dose logs, enforcing append-only semantics."""
        import medication_tracker.dose_log_repository as mod

        assert not hasattr(mod.PrescriptionDoseLogRepository, "update")

    def test_duplicate_timestamp_append_allowed(self, dose_log_repository, repository):
        """Two dose logs at the same timestamp are allowed (append-only)."""
        rx = repository.create(make_valid_prescription())
        ts = "2026-01-01T08:00:00+00:00"
        dose_log_repository.append(
            DoseLog(prescription_id=rx.id, event=DoseEvent.TAKEN, timestamp=ts)
        )
        dose_log_repository.append(
            DoseLog(prescription_id=rx.id, event=DoseEvent.SKIPPED, timestamp=ts)
        )
        history = dose_log_repository.get_history(rx.id)
        assert len(history) == 2

    def test_dose_log_invalid_event_rejected(self, repository):
        rx = repository.create(make_valid_prescription())
        with pytest.raises(ValueError):
            DoseLog(prescription_id=rx.id, event="missed", timestamp=_now_iso())

    def test_dose_log_naive_timestamp_rejected(self, repository):
        rx = repository.create(make_valid_prescription())
        with pytest.raises(ValueError):
            DoseLog(
                prescription_id=rx.id,
                event=DoseEvent.TAKEN,
                timestamp="2026-01-01T08:00:00",
            )


# ---------------------------------------------------------------------------
# Service-layer dose log validation (active-only, event validation)
# ---------------------------------------------------------------------------


class TestDoseLogService:
    def test_append_to_active_prescription(self, dose_log_service, active_prescription):
        log = dose_log_service.append_dose_log(
            active_prescription.id, event="taken"
        )
        assert log.event == DoseEvent.TAKEN
        assert log.prescription_id == active_prescription.id
        # timestamp defaults to now with timezone
        parsed = datetime.fromisoformat(log.timestamp)
        assert parsed.tzinfo is not None

    def test_append_to_discontinued_rejected(self, dose_log_service, prescription_service, valid_prescription_data):
        rx = prescription_service.create_prescription(valid_prescription_data)
        prescription_service.discontinue(rx.id, "side effects")
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(rx.id, event="taken")

    def test_append_to_completed_rejected(self, dose_log_service, prescription_service, valid_prescription_data):
        rx = prescription_service.create_prescription(valid_prescription_data)
        prescription_service.complete(rx.id)
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(rx.id, event="taken")

    def test_append_unknown_event_rejected(self, dose_log_service, active_prescription):
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(active_prescription.id, event="missed")

    def test_append_to_missing_prescription_rejected(self, dose_log_service):
        with pytest.raises(PrescriptionNotFoundError):
            dose_log_service.append_dose_log("missing-id", event="taken")

    def test_get_history_for_missing_prescription_rejected(self, dose_log_service):
        with pytest.raises(PrescriptionNotFoundError):
            dose_log_service.get_adherence_history("missing-id")

    def test_append_with_explicit_timestamp(self, dose_log_service, active_prescription):
        log = dose_log_service.append_dose_log(
            active_prescription.id,
            event="skipped",
            timestamp="2026-01-01T08:00:00+00:00",
            notes="felt nauseous",
        )
        assert log.event == DoseEvent.SKIPPED
        assert log.notes == "felt nauseous"
        assert log.timestamp == "2026-01-01T08:00:00+00:00"

    def test_append_invalid_timestamp_rejected(self, dose_log_service, active_prescription):
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(
                active_prescription.id, event="taken", timestamp="not-a-date"
            )

    def test_append_naive_timestamp_rejected(self, dose_log_service, active_prescription):
        with pytest.raises(ValueError):
            dose_log_service.append_dose_log(
                active_prescription.id, event="taken", timestamp="2026-01-01T08:00:00"
            )

    def test_get_history_with_date_filter(self, dose_log_service, active_prescription):
        for ts in [
            "2026-01-01T08:00:00+00:00",
            "2026-01-02T08:00:00+00:00",
        ]:
            dose_log_service.append_dose_log(
                active_prescription.id, event="taken", timestamp=ts
            )
        history = dose_log_service.get_adherence_history(
            active_prescription.id,
            start_date="2026-01-02T00:00:00+00:00",
        )
        assert len(history) == 1


# ---------------------------------------------------------------------------
# Coverage: repository.count, service listing/status-history, model coercion
# ---------------------------------------------------------------------------


class TestCoverageEdgeCases:
    def test_dose_log_repository_count(self, dose_log_repository, repository):
        rx = repository.create(make_valid_prescription())
        assert dose_log_repository.count(rx.id) == 0
        dose_log_repository.append(
            DoseLog(prescription_id=rx.id, event=DoseEvent.TAKEN, timestamp=_now_iso())
        )
        assert dose_log_repository.count(rx.id) == 1

    def test_list_by_patient_no_status_filter(self, repository):
        repository.create(make_valid_prescription(medicine_name="A"))
        repository.create(make_valid_prescription(medicine_name="B", patient_id="p2"))
        result = repository.list_by_patient("patient-1")
        assert len(result) == 1
        assert result[0].medicine_name == "A"

    def test_list_by_patient_with_status_filter(self, repository):
        rx = repository.create(make_valid_prescription())
        repository.complete(rx.id)
        active = repository.create(make_valid_prescription(medicine_name="Second"))
        only_active = repository.list_by_patient(
            "patient-1", status=PrescriptionStatus.ACTIVE
        )
        assert {p.id for p in only_active} == {active.id}

    def test_status_history_empty(self, repository):
        rx = repository.create(make_valid_prescription())
        assert repository.list_transitions(rx.id) == []

    def test_prescription_status_string_coercion(self):
        rx = make_valid_prescription(status="completed")
        assert rx.status == PrescriptionStatus.COMPLETED

    def test_prescription_invalid_status_type_rejected(self):
        with pytest.raises(ValueError):
            make_valid_prescription(status=123)

    def test_dose_log_event_string_coercion(self, repository):
        rx = repository.create(make_valid_prescription())
        log = DoseLog(
            prescription_id=rx.id, event="skipped", timestamp=_now_iso()
        )
        assert log.event == DoseEvent.SKIPPED

    def test_dose_log_empty_prescription_id_rejected(self, repository):
        with pytest.raises(ValueError):
            DoseLog(prescription_id="", event=DoseEvent.TAKEN, timestamp=_now_iso())

    def test_dose_log_invalid_event_type_rejected(self, repository):
        with pytest.raises(ValueError):
            DoseLog(
                prescription_id="x", event=123, timestamp=_now_iso()
            )

    def test_prescription_to_dict_roundtrip(self, repository):
        rx = repository.create(make_valid_prescription(end_date="2026-12-01T00:00:00+00:00"))
        d = rx.to_dict()
        assert d["status"] == "active"
        assert d["end_date"] == "2026-12-01T00:00:00+00:00"
        assert d["id"] == rx.id

    def test_status_transition_to_dict(self, repository):
        rx = repository.create(make_valid_prescription())
        repository.discontinue(rx.id, "reason")
        transitions = repository.list_transitions(rx.id)
        d = transitions[0].to_dict()
        assert d["from_status"] == "active"
        assert d["to_status"] == "discontinued"
        assert d["reason"] == "reason"

    def test_service_create_invalid_dosage_amount(self, prescription_service, valid_prescription_data):
        valid_prescription_data["dosage_amount"] = "not-a-number"
        with pytest.raises(ValueError):
            prescription_service.create_prescription(valid_prescription_data)

    def test_service_create_negative_dosage(self, prescription_service, valid_prescription_data):
        valid_prescription_data["dosage_amount"] = -1
        with pytest.raises(ValueError):
            prescription_service.create_prescription(valid_prescription_data)

    def test_service_get_missing_raises(self, prescription_service):
        with pytest.raises(PrescriptionNotFoundError):
            prescription_service.get_prescription("missing")

    def test_service_status_history(self, prescription_service, valid_prescription_data):
        rx = prescription_service.create_prescription(valid_prescription_data)
        prescription_service.complete(rx.id)
        history = prescription_service.get_status_history(rx.id)
        assert len(history) == 1

    def test_end_date_with_timezone_z(self, repository):
        rx = make_valid_prescription(
            start_date="2026-01-01T00:00:00Z",
            end_date="2026-06-01T00:00:00Z",
        )
        created = repository.create(rx)
        assert created.end_date == "2026-06-01T00:00:00Z"