"""Service layer: CRUD operations, validation, and dose tracking for medications.

This implements Unit #1's CRUD API and Unit #2's dose tracking against the
Unit #0 schema, so the persistence/edge-case logic in ``persistence.py`` has
real operations to verify. Validation enforces the hard constraints from the
REQ_SPEC: name and dosage required, dosage/frequency must be non-empty strings,
and start_date <= end_date when both are present.
"""

from datetime import datetime, date
from typing import List, Optional

from medication_tracker.db import Database
from medication_tracker.models import Medication, DoseRecord


class ValidationError(ValueError):
    """Raised when a medication entry fails validation."""


def _is_nonempty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_date_format(value: str, field: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValidationError(f"{field} must be a valid ISO date string (YYYY-MM-DD)")


class MedicationService:
    def __init__(self, db: Database):
        self.db = db

    def create(self, name, dosage, frequency, start_date=None, end_date=None, status="active") -> Medication:
        if not _is_nonempty_str(name):
            raise ValidationError("name is required and must be a non-empty string")
        if not _is_nonempty_str(dosage):
            raise ValidationError("dosage is required and must be a non-empty string")
        if not _is_nonempty_str(frequency):
            raise ValidationError("frequency is required and must be a non-empty string")
        if status not in ("active", "completed"):
            raise ValidationError("status must be 'active' or 'completed'")

        if start_date is not None:
            _validate_date_format(start_date, "start_date")
        if end_date is not None:
            _validate_date_format(end_date, "end_date")

        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValidationError("start_date must be on or before end_date")

        now = _now_iso()
        conn = self.db.connect()
        try:
            cur = conn.execute(
                """INSERT INTO medications
                   (name, dosage, frequency, start_date, end_date, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, dosage, frequency, start_date, end_date, status, now, now),
            )
            conn.commit()
            med_id = cur.lastrowid
        finally:
            conn.close()
        return self.get(med_id)

    def get(self, med_id: int) -> Optional[Medication]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM medications WHERE id = ?", (med_id,)
            ).fetchone()
        finally:
            conn.close()
        return Medication.from_row(row) if row else None

    def list(self, status_filter: Optional[str] = None) -> List[Medication]:
        """Return medications sorted by most recently added (created_at desc).

        Overlapping schedules display chronologically by created_at without
        duplication — each medication appears exactly once in the list.
        """
        conn = self.db.connect()
        try:
            if status_filter is not None and status_filter != "all":
                rows = conn.execute(
                    "SELECT * FROM medications WHERE status = ? ORDER BY created_at DESC, id DESC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM medications ORDER BY created_at DESC, id DESC"
                ).fetchall()
        finally:
            conn.close()
        return [Medication.from_row(r) for r in rows]

    def update(self, med_id: int, **fields) -> Medication:
        existing = self.get(med_id)
        if existing is None:
            raise ValidationError(f"medication {med_id} not found")

        merged = existing.to_dict()
        merged.update({k: v for k, v in fields.items() if v is not None})

        if not _is_nonempty_str(merged["name"]):
            raise ValidationError("name is required and must be a non-empty string")
        if not _is_nonempty_str(merged["dosage"]):
            raise ValidationError("dosage is required and must be a non-empty string")
        if not _is_nonempty_str(merged.get("frequency") or ""):
            raise ValidationError("frequency is required and must be a non-empty string")
        if merged.get("status") not in ("active", "completed"):
            raise ValidationError("status must be 'active' or 'completed'")

        sd = merged.get("start_date")
        ed = merged.get("end_date")
        if sd:
            _validate_date_format(sd, "start_date")
        if ed:
            _validate_date_format(ed, "end_date")
        if sd and ed and sd > ed:
            raise ValidationError("start_date must be on or before end_date")

        now = _now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """UPDATE medications
                   SET name=?, dosage=?, frequency=?, start_date=?, end_date=?, status=?, updated_at=?
                   WHERE id=?""",
                (
                    merged["name"], merged["dosage"], merged["frequency"],
                    sd, ed, merged["status"], now, med_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(med_id)

    def delete(self, med_id: int) -> bool:
        conn = self.db.connect()
        try:
            cur = conn.execute("DELETE FROM medications WHERE id = ?", (med_id,))
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()
        return deleted

    def mark_as_taken(self, med_id: int, when: Optional[datetime] = None) -> DoseRecord:
        """Record a taken dose for the current day (or ``when``).

        Idempotent within a day: a second call for the same medication on the
        same date returns the existing record rather than creating a duplicate.
        """
        if self.get(med_id) is None:
            raise ValidationError(f"medication {med_id} not found")

        ts = when or datetime.utcnow()
        day = ts.strftime("%Y-%m-%d")
        iso_ts = ts.isoformat()

        conn = self.db.connect()
        try:
            existing = conn.execute(
                "SELECT * FROM dose_records WHERE medication_id=? AND date=?",
                (med_id, day),
            ).fetchone()
            if existing:
                return DoseRecord.from_row(existing)
            cur = conn.execute(
                "INSERT INTO dose_records (medication_id, date, timestamp, status) VALUES (?, ?, ?, ?)",
                (med_id, day, iso_ts, "taken"),
            )
            conn.commit()
            return DoseRecord(
                medication_id=med_id, date=day, timestamp=iso_ts,
                status="taken", id=cur.lastrowid,
            )
        finally:
            conn.close()

    def dose_history(self, med_id: int, start_date=None, end_date=None) -> List[DoseRecord]:
        conn = self.db.connect()
        try:
            query = "SELECT * FROM dose_records WHERE medication_id = ?"
            params: list = [med_id]
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            query += " ORDER BY timestamp ASC"
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        return [DoseRecord.from_row(r) for r in rows]

    def set_status(self, med_id: int, status: str) -> Medication:
        if status not in ("active", "completed"):
            raise ValidationError("status must be 'active' or 'completed'")
        existing = self.get(med_id)
        if existing is None:
            raise ValidationError(f"medication {med_id} not found")
        return self.update(med_id, status=status)


def _now_iso() -> str:
    return datetime.utcnow().isoformat()