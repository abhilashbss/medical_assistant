"""Unit tests for the prescription repository, lifecycle, and dose logs.

Covers the build-unit #1 Definition of Done:
  - create persists all required fields and is retrievable by patient ID
  - validation rejects missing required fields / end date before start date
  - status transitions recorded with ISO 8601 timestamps; immutable post-creation
  - two concurrent active prescriptions for the same medicine per patient rejected
  - single-patient history query returns entries sorted by start_date descending

Also covers:
  - Dose logs append timestamped adherence records queryable per medication ordered by time
  - Service-layer validation and coordination
"""

import sqlite3
import time
import uuid
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
from medication_tracker.errors import ValidationError
from medication_tracker.repository import (
    PrescriptionNotFoundError,
    ValidationError as RepoValidationError,
    complete_prescription,
    create_prescription,
    discontinue_prescription,
    ensure_doctor,
    ensure_patient,
    get_prescription,
    init_schema,
    list_by_patient,
)
from medication_tracker.validators import validate_prescription

PATIENT_ID = "11111111-1111-1111-1111-111111111111"
DOCTOR_ID = "22222222-2222-2222-2222-222222222222"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


# --------------------------------------------------------------------------
# Repository class: remaining branches (not-found, non-active transitions,
# convenience wrapper, dose logging)
# --------------------------------------------------------------------------

class TestRepositoryBranches:
    def test_complete_missing_returns_none(self, repo):
        assert repo.complete("no-such-id") is None

    def test_discontinue_missing_returns_none(self, repo):
        assert repo.discontinue("no-such-id", "reason") is None

    def test_discontinue_non_string_reason_rejected(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        with pytest.raises(ValueError):
            repo.discontinue(rx.id, 123)  # type: ignore[arg-type]

    def test_discontinue_non_active_rejected(self, repo):
        rx = validate_prescription(valid_data())
        repo.create(rx)
        repo.complete(rx.id)
        with pytest.raises(ValueError):
            repo.discontinue(rx.id, "late reason")

    def test_create_prescription_convenience_wrapper_round_trips(self, repo):
        rx = repo.create_prescription(valid_data(medicine_name="WrapperDrug"))
        assert rx.id is not None
        got = repo.get_by_id(rx.id)
        assert got is not None
        assert got.medicine_name == "WrapperDrug"

    def test_log_dose_round_trips_and_list_orders_ascending(self, repo):
        rx = repo.create_prescription(valid_data(medicine_name="DoseDrug"))
        repo.log_dose(rx.id, "taken", "2026-01-01T08:00:00+00:00")
        repo.log_dose(rx.id, "skipped", "2026-01-01T20:00:00+00:00")
        logs = repo.list_dose_logs(rx.id)
        assert len(logs) == 2
        assert logs[0]["event"] == "taken"
        assert logs[1]["event"] == "skipped"
        assert logs[0]["logged_at"] <= logs[1]["logged_at"]

    def test_log_dose_unknown_event_rejected(self, repo):
        rx = repo.create_prescription(valid_data())
        with pytest.raises(ValueError):
            repo.log_dose(rx.id, "maybe", "2026-01-01T08:00:00+00:00")

    def test_log_dose_missing_prescription_rejected(self, repo):
        with pytest.raises(ValueError):
            repo.log_dose("no-such-id", "taken", "2026-01-01T08:00:00+00:00")

    def test_log_dose_completed_prescription_rejected(self, repo):
        rx = repo.create_prescription(valid_data())
        repo.complete(rx.id)
        with pytest.raises(ValueError):
            repo.log_dose(rx.id, "taken", "2026-01-01T08:00:00+00:00")

    def test_prescription_not_found_error_behavior(self):
        """Verify that PrescriptionNotFoundError stores the missing ID correctly."""
        missing_id = "not-found-123"
        err = PrescriptionNotFoundError(missing_id)
        assert err.prescription_id == missing_id
        assert f"Prescription not found: {missing_id}" in str(err)


# --------------------------------------------------------------------------
# Free-function data-access API path (module-level functions over dicts).
# These exercise the parameterized INSERT/SELECT/UPDATE SQL the
# data-access layer exposes to the HTTP layer.
# --------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON;")
    init_schema(c)
    ensure_patient(c, PATIENT_ID)
    ensure_doctor(c, DOCTOR_ID)
    return c


def _valid_create_payload(**overrides):
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


class TestFreeFunctionCreateGetList:
    def test_create_persists_and_get_round_trips(self, conn):
        row = create_prescription(conn, _valid_create_payload())
        assert row["medicine_name"] == "Amoxicillin"
        assert row["dosage_amount"] == 500.0
        assert row["status"] == "active"
        fetched = get_prescription(conn, row["id"])
        assert fetched["id"] == row["id"]
        assert fetched["patient_id"] == PATIENT_ID

    def test_get_missing_returns_none(self, conn):
        assert get_prescription(conn, "no-such-id") is None

    def test_list_by_patient_sorted_desc(self, conn):
        create_prescription(conn, _valid_create_payload(
            medicine_name="OldDrug", start_date="2025-01-01T08:00:00+00:00"))
        create_prescription(conn, _valid_create_payload(
            medicine_name="NewDrug", start_date="2026-06-01T08:00:00+00:00"))
        rows = list_by_patient(conn, PATIENT_ID)
        assert len(rows) == 2
        assert rows[0]["medicine_name"] == "NewDrug"
        assert rows[1]["medicine_name"] == "OldDrug"

    def test_list_empty_for_unknown_patient(self, conn):
        assert list_by_patient(conn, "no-such-patient") == []


class TestFreeFunctionValidation:
    def test_missing_required_field_rejected(self, conn):
        payload = _valid_create_payload()
        del payload["medicine_name"]
        with pytest.raises(RepoValidationError) as exc:
            create_prescription(conn, payload)
        assert exc.value.field == "medicine_name"

    def test_non_numeric_dosage_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(dosage_amount="500"))

    def test_non_positive_dosage_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(dosage_amount=-10))

    def test_empty_dosage_unit_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(dosage_unit="   "))

    def test_non_string_dosage_unit_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(dosage_unit=123))

    def test_naive_start_date_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(start_date="2026-01-01T08:00:00"))

    def test_non_iso8601_start_date_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(start_date="not-a-date"))

    def test_end_date_before_start_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(
                start_date="2026-02-01T08:00:00+00:00",
                end_date="2026-01-01T08:00:00+00:00"))

    def test_end_date_naive_rejected(self, conn):
        with pytest.raises(RepoValidationError):
            create_prescription(conn, _valid_create_payload(
                end_date="2026-01-10T08:00:00"))

    def test_explicit_id_used_when_provided(self, conn):
        rx_id = str(uuid.uuid4())
        row = create_prescription(conn, _valid_create_payload(id=rx_id))
        assert row["id"] == rx_id


class TestFreeFunctionEnsurePatientDoctor:
    def test_ensure_patient_rejects_empty(self, conn):
        with pytest.raises(RepoValidationError):
            ensure_patient(conn, "   ")

    def test_ensure_doctor_rejects_empty(self, conn):
        with pytest.raises(RepoValidationError):
            ensure_doctor(conn, "   ")

    def test_ensure_patient_idempotent(self, conn):
        ensure_patient(conn, "new-patient")
        ensure_patient(conn, "new-patient")  # second call is a no-op
        assert get_prescription(conn, "new-patient") is None  # not a prescription

    def test_ensure_doctor_idempotent(self, conn):
        ensure_doctor(conn, "new-doctor", "Dr. Smith")
        ensure_doctor(conn, "new-doctor", "Dr. Smith")
        row = conn.execute("SELECT * FROM doctors WHERE id = ?", ("new-doctor",)).fetchone()
        assert row["name"] == "Dr. Smith"


class TestFreeFunctionTransitions:
    def test_discontinue_requires_reason(self, conn):
        row = create_prescription(conn, _valid_create_payload())
        with pytest.raises(RepoValidationError):
            discontinue_prescription(conn, row["id"], "")
        with pytest.raises(RepoValidationError):
            discontinue_prescription(conn, row["id"], "   ")

    def test_discontinue_missing_prescription_raises_keyerror(self, conn):
        with pytest.raises(KeyError):
            discontinue_prescription(conn, "no-such-id", "reason")

    def test_discontinue_non_active_rejected(self, conn):
        row = create_prescription(conn, _valid_create_payload())
        complete_prescription(conn, row["id"])
        with pytest.raises(RepoValidationError):
            discontinue_prescription(conn, row["id"], "late")

    def test_complete_missing_prescription_raises_keyerror(self, conn):
        with pytest.raises(KeyError):
            complete_prescription(conn, "no-such-id")

    def test_complete_non_active_rejected(self, conn):
        row = create_prescription(conn, _valid_create_payload())
        discontinue_prescription(conn, row["id"], "switched therapy")
        with pytest.raises(RepoValidationError):
            complete_prescription(conn, row["id"])

    def test_complete_then_discontinue_blocked(self, conn):
        row = create_prescription(conn, _valid_create_payload())
        complete_prescription(conn, row["id"])
        with pytest.raises(RepoValidationError):
            discontinue_prescription(conn, row["id"], "reason")

    def test_transition_recorded_in_status_transitions(self, conn):
        row = create_prescription(conn, _valid_create_payload())
        discontinue_prescription(conn, row["id"], "adverse reaction")
        transitions = conn.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ? ORDER BY transitioned_at",
            (row["id"],),
        ).fetchall()
        assert len(transitions) == 1
        assert transitions[0]["from_status"] == "active"
        assert transitions[0]["to_status"] == "discontinued"
        assert transitions[0]["reason"] == "adverse reaction"


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
        import medication_tracker.dose_log_repository as mod
        assert not hasattr(mod.PrescriptionDoseLogRepository, "update")

    def test_duplicate_timestamp_append_allowed(self, dose_log_repository, repository):
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
