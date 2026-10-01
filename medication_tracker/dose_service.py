"""Dose service for medication dose tracking."""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from .database import Database
from .models import DoseRecord, DoseStatus


class DoseService:
    """Service for managing dose records with business logic."""

    def __init__(self, database: Database):
        """Initialize dose service with database connection.

        Args:
            database: Database instance
        """
        self.db = database

    def mark_dose_taken(self, medication_id: UUID, dose_date: Optional[date] = None) -> DoseRecord:
        """Mark a dose as taken for a medication.

        Args:
            medication_id: UUID of the medication
            dose_date: Date for the dose record (defaults to today)

        Returns:
            Created dose record

        Raises:
            ValueError: If dose_date is in the future
            ConflictError: If dose already exists for the medication on the given date
        """
        if dose_date is None:
            dose_date = date.today()

        # Validate date is not in the future
        if dose_date > date.today():
            raise ValueError("Cannot mark dose for a future date")

        # Check if dose already exists for this medication on this date (idempotency check)
        existing = self._get_dose_for_date(medication_id, dose_date)
        if existing is not None:
            raise ConflictError(f"Dose already recorded for medication {medication_id} on {dose_date}")

        # Create new dose record
        dose = DoseRecord(
            medication_id=medication_id,
            date=dose_date,
            status=DoseStatus.TAKEN.value,
        )

        return self._save_dose_record(dose)

    def mark_dose_skipped(self, medication_id: UUID, dose_date: date) -> DoseRecord:
        """Mark a dose as skipped for a medication.

        Args:
            medication_id: UUID of the medication
            dose_date: Date for the dose record

        Returns:
            Created dose record

        Raises:
            ValueError: If dose_date is in the future
            ConflictError: If dose already exists for the medication on the given date
        """
        if dose_date > date.today():
            raise ValueError("Cannot mark dose for a future date")

        existing = self._get_dose_for_date(medication_id, dose_date)
        if existing is not None:
            raise ConflictError(f"Dose already recorded for medication {medication_id} on {dose_date}")

        dose = DoseRecord(
            medication_id=medication_id,
            date=dose_date,
            status=DoseStatus.SKIPPED.value,
        )

        return self._save_dose_record(dose)

    def get_dose_history(
        self,
        medication_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[DoseRecord]:
        """Get dose history for a medication within a date range.

        Args:
            medication_id: UUID of the medication
            start_date: Optional start date filter (inclusive)
            end_date: Optional end date filter (inclusive)

        Returns:
            List of dose records sorted by date descending, then timestamp descending
        """
        query = "SELECT * FROM dose_records WHERE medication_id = ?"
        params = [str(medication_id)]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY date DESC, timestamp DESC"

        cursor = self.db.execute(query, params)
        return [self._row_to_dose_record(row) for row in cursor.fetchall()]

    def get_dose_for_date(self, medication_id: UUID, dose_date: date) -> Optional[DoseRecord]:
        """Get a dose record for a specific medication on a specific date.

        Args:
            medication_id: UUID of the medication
            dose_date: Date to look up

        Returns:
            DoseRecord if found, None otherwise
        """
        return self._get_dose_for_date(medication_id, dose_date)

    def _get_dose_for_date(self, medication_id: UUID, dose_date: date) -> Optional[DoseRecord]:
        """Internal method to get dose for a specific date."""
        cursor = self.db.execute(
            "SELECT * FROM dose_records WHERE medication_id = ? AND date = ?",
            (str(medication_id), dose_date.isoformat()),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dose_record(row)

    def _save_dose_record(self, dose: DoseRecord) -> DoseRecord:
        """Save a dose record to the database.

        Args:
            dose: DoseRecord to save

        Returns:
            Saved dose record with generated ID and timestamp
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO dose_records (id, medication_id, date, timestamp, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(dose.id),
                    str(dose.medication_id),
                    dose.date.isoformat(),
                    dose.timestamp.isoformat() if dose.timestamp else now,
                    dose.status,
                ),
            )
            conn.commit()

        if dose.timestamp is None:
            dose.timestamp = datetime.fromisoformat(now)
        return dose

    def _row_to_dose_record(self, row) -> DoseRecord:
        """Convert a database row to a DoseRecord object."""
        from uuid import UUID

        return DoseRecord(
            id=UUID(row["id"]),
            medication_id=UUID(row["medication_id"]),
            date=date.fromisoformat(row["date"]),
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
            status=row["status"],
        )


class ConflictError(Exception):
    """Raised when a dose record already exists for a medication on a given date."""

    pass
