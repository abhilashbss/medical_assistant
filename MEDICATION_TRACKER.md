# Medication Tracker

Prescription tracking for a single patient: structured dosage, status
lifecycle, and dose-adherence history, backed by SQLite.

## Modules

- `medication_tracker/models.py` — `Prescription` dataclass and
  `PrescriptionStatus` enum. Patient and doctor are stored as foreign-key
  references (`patient_id`, `doctor_id`), never duplicated inline. Dosage is a
  structured pair: `dosage_amount` (positive number) + `dosage_unit`
  (non-empty string).
- `medication_tracker/validators.py` — `validate_prescription(data)` validates
  a raw dict and returns a `Prescription`, or raises `ValidationError` carrying
  every per-field error found.
- `medication_tracker/repository.py` — `PrescriptionRepository` persists and
  retrieves prescriptions via parameterized SQL (`?` binding only). No generic
  update method is exposed.
- `medication_tracker/errors.py` — `ValidationError` exception.
- `migrations/001_schema.sql` — schema: `patients`, `doctors`, `prescriptions`,
  `status_transitions`, `dose_logs`, with FK references, CHECK constraints, a
  partial unique index on active prescriptions, and supporting indexes.

## Validation contract

`validate_prescription(data)` enforces:

1. **Required fields.** `patient_id`, `doctor_id`, `medicine_name`,
   `dosage_amount`, `dosage_unit`, `frequency`, and `start_date` must be
   present and non-null. All missing-field errors are collected and reported
   together — the caller sees every problem in one `ValidationError`.
2. **Non-empty strings.** `medicine_name`, `dosage_unit`, `frequency`,
   `patient_id`, and `doctor_id` must be non-empty strings when present.
3. **Structured dosage.** `dosage_amount` must be a positive number
   (`> 0`, booleans rejected); `dosage_unit` must be a non-empty string.
4. **ISO 8601 datetimes with timezone.** `start_date` and (optional) `end_date`
   are parsed with `datetime.fromisoformat`. A trailing `Z` is accepted as UTC.
   Naive datetimes (no `tzinfo` / offset) are **rejected** — the hard
   constraint is that every date/time field carries timezone information to
   avoid ambiguity across patient locations.
5. **End date after start date.** When both are present and timezone-aware,
   `end_date` must not precede `start_date`.
6. **Status.** Optional; one of `active` (default), `completed`,
   `discontinued`. Unknown values are rejected.

On any failure, `ValidationError.errors` holds a list of `(field, message)`
tuples.

## Immutability rule

Prescription rows are **immutable after creation** except for explicit status
transitions. `PrescriptionRepository` deliberately exposes no `update` /
`patch` / `update_fields` method, so there is no code path to mutate arbitrary
columns.

The only permitted mutations are:

- `complete(prescription_id)` — active → completed.
- `discontinue(prescription_id, reason)` — active → discontinued. A non-empty
  `reason` is mandatory; this is the audit escape hatch for data-entry errors
  or treatment changes, preserving the historical record rather than editing it.

Both transition methods append a timestamped row to `status_transitions`
(`from_status`, `to_status`, `reason`, `transitioned_at`), and the partial
unique index `idx_rx_active_unique` moves with the row so that a completed or
discontinued prescription no longer blocks a new active prescription for the
same medicine and patient.

## Usage

```python
import sqlite3
from medication_tracker.repository import PrescriptionRepository, init_schema
from medication_tracker.validators import validate_prescription

conn = sqlite3.connect(":memory:")
init_schema(conn)
repo = PrescriptionRepository(conn)
repo.add_patient("patient-uuid")
repo.add_doctor("doctor-uuid")

rx = validate_prescription({
    "patient_id": "patient-uuid",
    "doctor_id": "doctor-uuid",
    "medicine_name": "Amoxicillin",
    "dosage_amount": 500,
    "dosage_unit": "mg",
    "frequency": "twice daily",
    "start_date": "2026-01-01T08:00:00+00:00",
})
repo.create(rx)
repo.complete(rx.id)
```

## Tests

```sh
pytest tests/test_prescription_repository.py -v --cov=medication_tracker
pytest tests/test_prescription_functional.py -v --cov
```