"""Data persistence verification and edge-case handling (Build unit #4).

Responsibilities:
  * ``verify_persistence`` — on app load, fetch every medication and confirm
    each row is structurally intact (all required columns present and
    non-null). Returns a report describing the intact and corrupted sets.
  * ``auto_complete_past_end_dates`` — edge case: any medication whose
    end_date is before today should be auto-marked 'completed'.
  * Overlapping schedules are handled at the list layer: they display
    chronologically by created_at without duplication (see MedicationService.list).
  * ``recover_corrupted`` — repair/remove incomplete records that cannot be
    salvaged, returning the ids that were removed.

Data persistence guarantees (also documented in README):
  * Medication data lives in a SQLite file on disk; opening a fresh
    Database at the same path re-reads it, so entries survive app restarts.
  * Required fields (name, dosage, frequency) are enforced both at write
    time (validation) and verified on load (integrity check).
  * Date ranges are validated: start_date <= end_date when both are set.
"""

from datetime import date, datetime
from typing import List, Optional, Tuple

from medication_tracker.db import Database
from medication_tracker.models import Medication
from medication_tracker.service import MedicationService, ValidationError

REQUIRED_FIELDS = ("name", "dosage", "frequency")


def _row_is_intact(row) -> Tuple[bool, List[str]]:
    """Return (intact, missing_or_null_fields) for a medication row."""
    problems: List[str] = []
    for field in REQUIRED_FIELDS:
        val = row[field]
        if val is None or (isinstance(val, str) and val.strip() == ""):
            problems.append(field)
    if row["status"] not in ("active", "completed"):
        problems.append("status")
    sd = row["start_date"]
    ed = row["end_date"]
    if sd and ed and sd > ed:
        problems.append("date_range")
    return (len(problems) == 0, problems)


def _today_iso() -> str:
    return date.utcnow().isoformat()


def auto_complete_past_end_dates(service: MedicationService, today: Optional[str] = None) -> List[Medication]:
    """Auto-mark medications whose end_date < today as 'completed'.

    Edge case: a medication with an end_date in the past is no longer being
    taken, so it should not appear in the active list. This runs on app load
    so the active/completed filter always reflects reality. Returns the
    medications that were transitioned.
    """
    today = today or _today_iso()
    changed: List[Medication] = []
    for med in service.list(status_filter="active"):
        if med.end_date and med.end_date < today and med.status == "active":
            updated = service.set_status(med.id, "completed")
            changed.append(updated)
    return changed


def verify_persistence(db: Database) -> dict:
    """On app load, fetch all medications and verify data integrity.

    Returns ``{"intact": [...], "corrupted": [...], "total": N}`` where each
    corrupted entry is ``{"id": ..., "problems": [...]}``. This confirms data
    was persisted and is retrievable after a restart.
    """
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM medications").fetchall()
    finally:
        conn.close()

    intact: List[dict] = []
    corrupted: List[dict] = []
    for row in rows:
        ok, problems = _row_is_intact(row)
        med = Medication.from_row(row).to_dict()
        if ok:
            intact.append(med)
        else:
            corrupted.append({"id": row["id"], "problems": problems, "record": med})
    return {"intact": intact, "corrupted": corrupted, "total": len(rows)}


def recover_corrupted(db: Database) -> List[int]:
    """Remove corrupted/incomplete medication records that can't be salvaged.

    A record missing a required field (name/dosage/frequency), with an invalid
    status, or with an impossible date range is deleted so it can't poison the
    list view. Returns the ids of removed records.
    """
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM medications").fetchall()
        removed: List[int] = []
        for row in rows:
            ok, _problems = _row_is_intact(row)
            if not ok:
                conn.execute("DELETE FROM medications WHERE id = ?", (row["id"],))
                removed.append(row["id"])
        conn.commit()
        return removed
    finally:
        conn.close()


def load_and_reconcile(db: Database, today: Optional[str] = None) -> dict:
    """Full app-load sequence: verify persistence, repair, auto-complete.

    Called on startup to guarantee the persisted data is intact and that past
    end dates are reflected in status before the user sees the list.
    """
    report = verify_persistence(db)
    removed = recover_corrupted(db)
    service = MedicationService(db)
    auto_completed = auto_complete_past_end_dates(service, today=today)
    final_report = verify_persistence(db)
    return {
        "initial": report,
        "removed": removed,
        "auto_completed": [m.to_dict() for m in auto_completed],
        "final": final_report,
    }