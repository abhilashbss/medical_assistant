# Medicine Tracker Feature

## Overview

A structured medicine tracker that enables users to manage prescribed medications with dosage schedules, track adherence through timestamped dose records, and view medication history.

## Build Unit #0: Database Schema

### Files Created

- `migrations/create_medications_table.sql` - SQL migration script
- `medication_tracker/` - Python module with database layer
  - `__init__.py` - Module exports
  - `models.py` - Medication and DoseRecord data models
  - `database.py` - SQLite database connection and schema initialization
  - `repository.py` - CRUD operations for medications and dose records
  - `README.md` - API documentation
- `tests/test_medication_tracker.py` - Comprehensive test suite
- `requirements.txt` - Python dependencies

### Database Schema

```sql
CREATE TABLE medications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,                    -- Medication name (required)
    dosage TEXT NOT NULL,                  -- Dosage e.g., "500mg" (required)
    frequency TEXT NOT NULL,               -- Frequency e.g., "twice daily" (required)
    start_date DATE,                       -- Treatment start date (optional)
    end_date DATE,                         -- Treatment end date (optional)
    status TEXT DEFAULT 'active' NOT NULL, -- 'active' or 'completed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_status CHECK (status IN ('active', 'completed')),
    CONSTRAINT chk_name_not_empty CHECK (name <> ''),
    CONSTRAINT chk_dosage_not_empty CHECK (dosage <> ''),
    CONSTRAINT chk_frequency_not_empty CHECK (frequency <> '')
);

CREATE INDEX idx_medications_status ON medications(status);
CREATE INDEX idx_medications_created_at ON medications(created_at DESC);
```

### Validation Rules

1. **Required fields**: `name`, `dosage`, `frequency` must be non-empty strings
2. **Status values**: Only `active` or `completed` are valid
3. **Database constraints**: CHECK constraints enforce non-empty strings at database level

### Test Results

```
43 passed in 0.15s
Coverage: 90%
```

All gate tests pass:
- Unit tests: Medication creation, validation, CRUD operations, constraints
- Functional tests: Add/edit/delete medications, mark-as-taken, status filtering

## Usage Example

```python
from medication_tracker import Database, MedicationRepository, Medication, DoseRecord
from datetime import date

# Initialize
db = Database("medications.db")
db.init_schema()
repo = MedicationRepository(db)

# Create medication
med = Medication(name="Amoxicillin", dosage="500mg", frequency="twice daily")
repo.create(med)

# Mark dose as taken
dose = DoseRecord(medication_id=med.id, date=date.today())
repo.create_dose_record(dose)

# List active medications
active = repo.get_all(status=MedicationStatus.ACTIVE)
```

## Running Tests

```bash
# Unit tests
pytest tests/test_medication_tracker.py -v --cov=medication_tracker

# Functional tests
pytest tests/test_medication_tracker.py -v -k 'functional'
```
