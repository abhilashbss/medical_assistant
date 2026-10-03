"""Unit tests for the prescription validation + repository layers.

Covers the build-unit #1 Definition of Done:
  - create persists all required fields and is retrievable by patient ID
  - validation rejects missing required fields / end date before start date
  - status transitions recorded with ISO 8601 timestamps; immutable post-creation
  - two concurrent active prescriptions for the same medicine per patient rejected
  - single-patient history query returns entries sorted by start_date descending
"""

import sqlite3
import time

import pytest

from medication_tracker.errors import ValidationError
from medication_tracker.models import Prescription, PrescriptionStatus
from medication_tracker.repository import PrescriptionRepository, init_schema
from medication_tracker.validators import validate_prescription

PATIENT_ID = "11111111-1111-1111-1111-111111111111"
DOCTOR_ID = "22222222-2222-2222-2222-222222222222"


def valid_data(**overrides):
    """Return a baseline valid prescription dict with optional overrides."""
    base = {
        "patient_id": PATIENT_ID,
        "doctor_id": DOCTOR_ID,
        "medicine_name": "Amoxicillin",
        "dosage_amount": 500,
        "dosage_unit": "mg",
        "frequency": "twice daily",
        "start_date": "2026-01-01T08:00:00+00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    init_schema(conn)
    r = PrescriptionRepository(conn)
    r.add_patient(PATIENT_ID)
    r.add_doctor(DOCTOR_ID)
    return r


# --------------------------------------------------------------------------
# Validation: valid prescription passes
# --------------------------------------------------------------------------

class TestValidationValid:
    def test_valid_prescription_passes(self):
        rx = validate_prescription(valid_data())
        assert rx.patient_id == PATIENT_ID
        assert rx.doctor_id == DOCTOR_ID
        assert rx.medicine_name == "Amoxicillin"
        assert rx.dosage_amount == 500.0
        assert rx.dosage_unit == "mg"
        assert rx.frequency == "twice daily"
        assert rx.status == PrescriptionStatus.ACTIVE

    def test_valid_prescription_with_end_date_passes(self):
        rx = validate_prescription(valid_data(end_date="2026-01-10T08:00:00+00:00"))
        assert rx.end_date == "2026-01-10T08:00:00+00:00"

    def test_z_suffix_datetime_accepted(self):
        rx = validate_prescription(valid_data(start_date="2026-01-01T08:00:00Z"))
        assert rx.start_date == "2026-01-01T08:00:00Z"

    def test_explicit_status_accepted(self):
        rx = validate_prescription(valid_data(status="completed"))
        assert rx.status == PrescriptionStatus.COMPLETED


# --------------------------------------------------------------------------
# Validation: missing required fields
# --------------------------------------------------------------------------

class TestValidationMissingFields:
    @pytest.mark.parametrize(
        "missing_field",
        [
            "patient_id",
            "doctor_id",
            "medicine_name",
            "dosage_amount",
            "dosage_unit",
            "frequency",
            "start_date",
        ],
    )
    def test_missing_required_field_rejected(self, missing_field):
        data = valid_data()
        data.pop(missing_field)
        with pytest.raises(ValidationError) as exc:
            validate_prescription(data)
        fields = [f for f, _ in exc.value.errors]
        assert missing_field in fields, f"{missing_field} should be flagged: {exc.value.errors}"

    def test_all_missing_fields_collected_at_once(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription({})
        fields = {f for f, _ in exc.value.errors}
        for required in (
            "patient_id",
            "doctor_id",
            "medicine_name",
            "dosage_amount",
            "dosage_unit",
            "frequency",
            "start_date",
        ):
            assert required in fields

    def test_none_value_treated_as_missing(self):
        data = valid_data()
        data["patient_id"] = None
        with pytest.raises(ValidationError) as exc:
            validate_prescription(data)
        assert "patient_id" in {f for f, _ in exc.value.errors}


# --------------------------------------------------------------------------
# Validation: malformed / naive datetimes
# --------------------------------------------------------------------------

class TestValidationDatetimes:
    @pytest.mark.parametrize(
        "bad_date",
        [
            "2026-01-01",            # date only, no time
            "2026-01-01 08:00:00",   # space separator, no tz -> naive
            "not-a-date",
            "2026-13-40T99:99:99+00:00",
        ],
    )
    def test_non_iso8601_datetime_rejected(self, bad_date):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(start_date=bad_date))
        assert "start_date" in {f for f, _ in exc.value.errors}

    def test_naive_start_date_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(start_date="2026-01-01T08:00:00"))
        msgs = [m for f, m in exc.value.errors if f == "start_date"]
        assert any("timezone" in m for m in msgs)

    def test_naive_end_date_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(
                valid_data(
                    start_date="2026-01-01T08:00:00+00:00",
                    end_date="2026-01-10T08:00:00",
                )
            )
        assert "end_date" in {f for f, _ in exc.value.errors}

    def test_end_date_before_start_date_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(
                valid_data(
                    start_date="2026-02-01T08:00:00+00:00",
                    end_date="2026-01-01T08:00:00+00:00",
                )
            )
        msgs = [m for f, m in exc.value.errors if f == "end_date"]
        assert any("precede" in m for m in msgs)

    def test_end_date_equal_start_date_not_rejected_for_ordering(self):
        # Equal datetimes do not precede the start; only earlier does.
        rx = validate_prescription(
            valid_data(
                start_date="2026-01-01T08:00:00+00:00",
                end_date="2026-01-01T08:00:00+00:00",
            )
        )
        assert rx.end_date is not None


# --------------------------------------------------------------------------
# Validation: dosage constraints
# --------------------------------------------------------------------------

class TestValidationDosage:
    @pytest.mark.parametrize("amount", [0, -5, -0.1])
    def test_non_positive_dosage_amount_rejected(self, amount):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(dosage_amount=amount))
        assert "dosage_amount" in {f for f, _ in exc.value.errors}

    def test_empty_dosage_unit_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(dosage_unit="   "))
        assert "dosage_unit" in {f for f, _ in exc.value.errors}

    def test_empty_medicine_name_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(medicine_name=""))
        assert "medicine_name" in {f for f, _ in exc.value.errors}

    def test_empty_frequency_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(frequency=""))
        assert "frequency" in {f for f, _ in exc.value.errors}

    def test_non_string_medicine_name_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(medicine_name=123))
        assert "medicine_name" in {f for f, _ in exc.value.errors}

    def test_non_string_patient_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(patient_id=42))
        assert "patient_id" in {f for f, _ in exc.value.errors}

    def test_empty_patient_id_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(patient_id="  "))
        assert "patient_id" in {f for f, _ in exc.value.errors}

    def test_bool_dosage_amount_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(dosage_amount=True))
        assert "dosage_amount" in {f for f, _ in exc.value.errors}


class TestValidationEdgeCases:
    def test_non_dict_input_rejected(self):
        with pytest.raises(ValidationError):
            validate_prescription("not a dict")

    def test_empty_string_start_date_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(start_date="   "))
        assert "start_date" in {f for f, _ in exc.value.errors}

    def test_non_string_start_date_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(start_date=12345))
        assert "start_date" in {f for f, _ in exc.value.errors}

    def test_malformed_end_date_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(
                valid_data(
                    start_date="2026-01-01T08:00:00+00:00",
                    end_date="not-a-date",
                )
            )
        assert "end_date" in {f for f, _ in exc.value.errors}

    def test_none_status_defaults_to_active(self):
        rx = validate_prescription(valid_data(status=None))
        assert rx.status == PrescriptionStatus.ACTIVE

    def test_validation_error_carries_field_errors(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription({})
        assert isinstance(exc.value.field_errors, list)
        assert len(exc.value.field_errors) >= 1

    def test_non_numeric_dosage_amount_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(dosage_amount="500"))
        assert "dosage_amount" in {f for f, _ in exc.value.errors}

    def test_unknown_status_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_prescription(valid_data(status="paused"))
        assert "status" in {f for f, _ in exc.value.errors}


# --------------------------------------------------------------------------
# Repository: create / get round-trip
# --------------------------------------------------------------------------

class TestRepositoryCreateGet:
    def test_create_persists_all_required_fields(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        assert rx.id is not None and rx.created_at is not None

        got = repo.get_by_id(rx.id)
        assert got is not None
        assert got.id == rx.id
        assert got.patient_id == PATIENT_ID
        assert got.doctor_id == DOCTOR_ID
        assert got.medicine_name == "Amoxicillin"
        assert got.dosage_amount == 500.0
        assert got.dosage_unit == "mg"
        assert got.frequency == "twice daily"
        assert got.start_date == "2026-01-01T08:00:00+00:00"
        assert got.status == PrescriptionStatus.ACTIVE

    def test_get_by_id_missing_returns_none(self, repo):
        assert repo.get_by_id("does-not-exist") is None


# --------------------------------------------------------------------------
# Repository: list by patient, sorted by start_date DESC
# --------------------------------------------------------------------------

class TestRepositoryListByPatient:
    def test_list_returns_history_sorted_desc(self, repo):
        older = validate_prescription(valid_data(medicine_name="Ibuprofen", start_date="2025-12-01T08:00:00+00:00"))
        newer = validate_prescription(valid_data(medicine_name="Amoxicillin", start_date="2026-01-01T08:00:00+00:00"))
        repo.create(older)
        repo.create(newer)

        history = repo.list_by_patient(PATIENT_ID)
        assert len(history) == 2
        assert history[0].medicine_name == "Amoxicillin"
        assert history[1].medicine_name == "Ibuprofen"
        assert history[0].start_date >= history[1].start_date

    def test_list_empty_for_unknown_patient(self, repo):
        assert repo.list_by_patient("no-such-patient") == []


# --------------------------------------------------------------------------
# Repository: immutability + status transitions
# --------------------------------------------------------------------------

class TestRepositoryStatusTransitions:
    def test_complete_records_transition_with_timestamp(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        completed = repo.complete(rx.id)
        assert completed.status == PrescriptionStatus.COMPLETED

        transitions = repo.list_transitions(rx.id)
        assert len(transitions) == 1
        t = transitions[0]
        assert t["from_status"] == "active"
        assert t["to_status"] == "completed"
        # ISO 8601 timestamp present.
        assert t["transitioned_at"] is not None
        assert "T" in t["transitioned_at"]
        assert ("+" in t["transitioned_at"]) or ("Z" in t["transitioned_at"])

    def test_discontinue_requires_reason(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        with pytest.raises(ValueError):
            repo.discontinue(rx.id, "")
        with pytest.raises(ValueError):
            repo.discontinue(rx.id, "   ")

    def test_discontinue_records_reason_and_timestamp(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        discontinued = repo.discontinue(rx.id, "adverse reaction")
        assert discontinued.status == PrescriptionStatus.DISCONTINUED

        transitions = repo.list_transitions(rx.id)
        assert len(transitions) == 1
        t = transitions[0]
        assert t["to_status"] == "discontinued"
        assert t["reason"] == "adverse reaction"
        assert "T" in t["transitioned_at"]

        # The discontinued row must remain in the patient's history
        # (immutability — discontinuation is an audit transition, not a
        # deletion), still retrievable by id with its status preserved.
        fetched = repo.get_by_id(rx.id)
        assert fetched is not None
        assert fetched.status == PrescriptionStatus.DISCONTINUED
        history = repo.list_by_patient(PATIENT_ID)
        assert any(p.id == rx.id for p in history), (
            "discontinued prescription must remain in patient history"
        )

    def test_no_generic_update_method_exposed(self):
        """The repository must not expose an arbitrary column-update path."""
        assert not hasattr(PrescriptionRepository, "update")
        assert not hasattr(PrescriptionRepository, "patch")
        assert not hasattr(PrescriptionRepository, "update_fields")

    def test_prescription_immutable_after_creation(self, repo):
        """Only status may change; other fields round-trip untouched after a transition."""
        rx = validate_prescription(valid_data(dosage_amount=250, medicine_name="Cephalexin"))
        repo.create(rx)
        repo.complete(rx.id)
        got = repo.get_by_id(rx.id)
        assert got.medicine_name == "Cephalexin"
        assert got.dosage_amount == 250.0
        assert got.patient_id == PATIENT_ID
        assert got.status == PrescriptionStatus.COMPLETED

    def test_cannot_complete_already_completed(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        repo.complete(rx.id)
        with pytest.raises(ValueError):
            repo.complete(rx.id)


# --------------------------------------------------------------------------
# Repository: concurrent active prescription uniqueness
# --------------------------------------------------------------------------

class TestRepositoryDuplicateActive:
    def test_two_concurrent_active_same_medicine_rejected(self, repo):
        first = validate_prescription(valid_data(start_date="2026-01-01T08:00:00+00:00"))
        repo.create(first)

        second = validate_prescription(
            valid_data(start_date="2026-01-05T08:00:00+00:00")
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.create(second)

    def test_historical_duplicate_allowed_after_completion(self, repo):
        first = validate_prescription(valid_data(start_date="2025-01-01T08:00:00+00:00"))
        repo.create(first)
        repo.complete(first.id)

        second = validate_prescription(valid_data(start_date="2026-01-01T08:00:00+00:00"))
        repo.create(second)  # should succeed: the first is no longer active
        assert repo.get_by_id(second.id) is not None

    def test_different_medicines_same_patient_both_active(self, repo):
        a = validate_prescription(valid_data(medicine_name="Amoxicillin"))
        repo.create(a)
        b = validate_prescription(valid_data(medicine_name="Ibuprofen"))
        repo.create(b)
        assert len(repo.list_by_patient(PATIENT_ID)) == 2


# --------------------------------------------------------------------------
# Performance: single-patient operations under 500ms
# --------------------------------------------------------------------------

class TestRepositoryPerformance:
    def test_create_and_history_under_500ms(self, repo):
        start = time.perf_counter()
        rx = validate_prescription(valid_data())
        repo.create(rx)
        repo.list_by_patient(PATIENT_ID)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"operation took {elapsed_ms:.1f}ms"