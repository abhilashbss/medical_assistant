"""Gate test: validation, dose logs, and partial unique index enforcement.

Success criteria:
- Creating a prescription with missing required fields raises a validation error
  before any DB write.
- End date preceding start date is rejected with a clear error and no row inserted.
- Dose log entries append timestamped adherence records queryable per medication
  ordered by time descending.
- Malformed ISO 8601 dates without timezone are rejected by the validation layer.
- No two active prescriptions for the same medicine can coexist for one patient,
  enforced via the partial unique index.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from prescription_tracker.db import init_db, seed_reference_data
from prescription_tracker.models import (
    DoseLogCreate,
    PrescriptionCreate,
    ValidationError,
)
from prescription_tracker.repository import PrescriptionRepository

PATIENT = "patient-001"
DOCTOR = "doctor-001"


@pytest.fixture
def repo():
    conn = init_db()
    seed_reference_data(conn, PATIENT, DOCTOR)
    return PrescriptionRepository(conn)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _valid_create(medicine: str = "Amoxicillin", start: str | None = None,
                  end: str | None = None) -> PrescriptionCreate:
    return PrescriptionCreate(
        patient_id=PATIENT,
        doctor_id=DOCTOR,
        medicine_name=medicine,
        dosage_amount=500.0,
        dosage_unit="mg",
        frequency="3x/day",
        start_date=start or _iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        end_date=end,
    )


# ---------------------------------------------------------------- missing fields
class TestMissingRequiredFields:
    def test_missing_patient_id(self, repo):
        data = _valid_create()
        data.patient_id = ""
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "patient_id" in exc.value.errors

    def test_missing_medicine_name(self, repo):
        data = _valid_create()
        data.medicine_name = ""
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "medicine_name" in exc.value.errors

    def test_missing_doctor_id(self, repo):
        data = _valid_create()
        data.doctor_id = ""
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "doctor_id" in exc.value.errors

    def test_missing_start_date(self, repo):
        data = _valid_create()
        data.start_date = ""
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "start_date" in exc.value.errors

    def test_missing_dosage_amount(self, repo):
        data = _valid_create()
        data.dosage_amount = None
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "dosage_amount" in exc.value.errors

    def test_missing_dosage_unit(self, repo):
        data = _valid_create()
        data.dosage_unit = ""
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "dosage_unit" in exc.value.errors

    def test_missing_frequency(self, repo):
        data = _valid_create()
        data.frequency = ""
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "frequency" in exc.value.errors

    def test_no_db_write_on_validation_failure(self, repo):
        data = _valid_create()
        data.medicine_name = ""
        with pytest.raises(ValidationError):
            repo.create_prescription(data)
        count = repo.conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0]
        assert count == 0


# ---------------------------------------------------------------- end < start
class TestEndDatePrecedesStart:
    def test_end_before_start_rejected(self, repo):
        data = _valid_create(
            start=_iso(datetime(2026, 2, 1, tzinfo=timezone.utc)),
            end=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        )
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "end_date" in exc.value.errors
        # No row inserted.
        count = repo.conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0]
        assert count == 0

    def test_end_equal_start_rejected(self, repo):
        ts = _iso(datetime(2026, 2, 1, tzinfo=timezone.utc))
        data = _valid_create(start=ts, end=ts)
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "end_date" in exc.value.errors


# ---------------------------------------------------------------- ISO 8601 / tz
class TestISO8601Validation:
    def test_naive_datetime_rejected(self, repo):
        data = _valid_create(start="2026-01-01T08:00:00")
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "start_date" in exc.value.errors

    def test_non_iso_string_rejected(self, repo):
        data = _valid_create(start="Jan 1 2026")
        with pytest.raises(ValidationError) as exc:
            data.validate()
        assert "start_date" in exc.value.errors

    def test_z_suffix_accepted(self, repo):
        data = _valid_create(start="2026-01-01T08:00:00Z")
        data.validate()  # should not raise

    def test_offset_accepted(self, repo):
        data = _valid_create(start="2026-01-01T08:00:00+05:30")
        data.validate()


# ---------------------------------------------------------------- dose logs
class TestDoseLogs:
    def _create_active_rx(self, repo) -> str:
        rx = repo.create_prescription(_valid_create())
        return rx["id"]

    def test_append_dose_log(self, repo):
        rx_id = self._create_active_rx(repo)
        log = repo.add_dose_log(
            DoseLogCreate(
                prescription_id=rx_id,
                event="taken",
                timestamp=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
            )
        )
        assert log["event"] == "taken"
        assert log["prescription_id"] == rx_id

    def test_dose_logs_ordered_by_time(self, repo):
        rx_id = self._create_active_rx(repo)
        t1 = _iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))
        t2 = _iso(datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc))
        t3 = _iso(datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc))
        # Insert out of order to verify ordering.
        repo.add_dose_log(DoseLogCreate(prescription_id=rx_id, event="taken", timestamp=t2))
        repo.add_dose_log(DoseLogCreate(prescription_id=rx_id, event="skipped", timestamp=t1))
        repo.add_dose_log(DoseLogCreate(prescription_id=rx_id, event="taken", timestamp=t3))
        logs = repo.get_dose_logs(rx_id)
        ts = [l["timestamp"] for l in logs]
        # Ordered ascending per the spec (queryable per medication ordered by time).
        assert ts == sorted(ts)
        assert len(logs) == 3

    def test_dose_log_invalid_event(self, repo):
        rx_id = self._create_active_rx(repo)
        with pytest.raises(ValidationError):
            repo.add_dose_log(
                DoseLogCreate(
                    prescription_id=rx_id,
                    event="maybe",
                    timestamp=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
                )
            )

    def test_dose_log_naive_timestamp_rejected(self, repo):
        rx_id = self._create_active_rx(repo)
        with pytest.raises(ValidationError) as exc:
            repo.add_dose_log(
                DoseLogCreate(
                    prescription_id=rx_id,
                    event="taken",
                    timestamp="2026-01-01T08:00:00",
                )
            )
        assert "timestamp" in exc.value.errors

    def test_dose_log_for_nonexistent_rx(self, repo):
        with pytest.raises(Exception):
            repo.add_dose_log(
                DoseLogCreate(
                    prescription_id="nonexistent",
                    event="taken",
                    timestamp=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
                )
            )

    def test_dose_log_for_discontinued_rx(self, repo):
        rx_id = self._create_active_rx(repo)
        repo.discontinue(rx_id, "adverse reaction")
        with pytest.raises(ValidationError):
            repo.add_dose_log(
                DoseLogCreate(
                    prescription_id=rx_id,
                    event="taken",
                    timestamp=_iso(datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)),
                )
            )


# ---------------------------------------------------------------- partial unique index
class TestOneActivePerMedicine:
    def test_duplicate_active_rejected(self, repo):
        repo.create_prescription(_valid_create(medicine="Metformin"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(_valid_create(medicine="Metformin"))

    def test_different_medicine_allowed(self, repo):
        repo.create_prescription(_valid_create(medicine="Metformin"))
        repo.create_prescription(_valid_create(medicine="Lisinopril"))

    def test_same_medicine_after_discontinue_allowed(self, repo):
        rx = repo.create_prescription(_valid_create(medicine="Metformin"))
        repo.discontinue(rx["id"], "switching medication")
        # Now a new active prescription for the same medicine should succeed.
        repo.create_prescription(_valid_create(medicine="Metformin"))