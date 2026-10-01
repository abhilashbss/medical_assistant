# Medication Tracker

A structured medicine tracker that enables users to manage prescribed medications with dosage schedules, track adherence through timestamped dose records, and view medication history.

## Overview

The medication tracker provides:
- **Medication Management**: Add, edit, and delete prescribed medications
- **Dosage Tracking**: Record name, dosage, frequency, and treatment duration
- **Status Management**: Track medications as active or completed
- **Dose Records**: Timestamped records of when doses are taken
- **Dose Tracking**: Mark medications as taken/skipped with idempotency handling
- **Data Persistence**: All data persists across application restarts

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```python
from medication_tracker import (
    Database, 
    MedicationRepository, 
    Medication, 
    MedicationStatus,
    DoseRecord,
    DoseStatus,
)
from medication_tracker.dose_service import DoseService
from datetime import date

# Initialize database
db = Database("medications.db")
db.init_schema()
repository = MedicationRepository(db)
dose_service = DoseService(db)

# Create a medication
medication = Medication(
    name="Amoxicillin",
    dosage="500mg",
    frequency="twice daily",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 14),
)
repository.create(medication)

# Retrieve medications
all_meds = repository.get_all()
active_meds = repository.get_all(status=MedicationStatus.ACTIVE)

# Update a medication
medication.status = MedicationStatus.COMPLETED
repository.update(medication)

# Mark a dose as taken (with idempotency handling)
try:
    dose_record = dose_service.mark_dose_taken(medication.id)
    print(f"Dose recorded at {dose_record.timestamp}")
except ConflictError:
    print("Dose already recorded for today")

# Get dose history
history = dose_service.get_dose_history(
    medication.id,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 14),
)

# Delete a medication
repository.delete(medication.id)
```

## Medication Entity Structure

### Medication

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Auto | Unique identifier |
| `name` | Text | Yes | Medication name (e.g., "Amoxicillin") |
| `dosage` | Text | Yes | Dosage amount and unit (e.g., "500mg", "10ml") |
| `frequency` | Text | Yes | How often to take (e.g., "twice daily", "every 8 hours") |
| `start_date` | Date | No | Treatment start date |
| `end_date` | Date | No | Treatment end date |
| `status` | Enum | Yes | `active` or `completed` (default: `active`) |
| `created_at` | DateTime | Auto | Record creation timestamp |
| `updated_at` | DateTime | Auto | Last update timestamp |

### DoseRecord

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Auto | Unique identifier |
| `medication_id` | UUID | Yes | Reference to medication |
| `date` | Date | Yes | Date dose was taken (cannot be future) |
| `timestamp` | DateTime | Auto | Exact timestamp of dose record |
| `status` | Enum | Yes | `taken`, `skipped`, or `missed` |

### DoseStatus

| Value | Description |
|-------|-------------|
| `taken` | Dose was taken as prescribed |
| `skipped` | Dose was intentionally skipped |
| `missed` | Dose was forgotten/missed |

## Validation Rules

- **name**: Must be a non-empty string
- **dosage**: Must be a non-empty string
- **frequency**: Must be a non-empty string
- **status**: Must be either "active" or "completed"

## Database Schema

### medications table

| Column      | Type      | Constraints                        | Description                                                  |
|-------------|-----------|------------------------------------|--------------------------------------------------------------|
| id          | UUID      | PRIMARY KEY                        | Unique identifier for the medication record                  |
| name        | TEXT      | NOT NULL, CHECK (name <> '')       | Name of the medication (required)                            |
| dosage      | TEXT      | NOT NULL, CHECK (dosage <> '')     | Dosage amount and unit e.g., "500mg", "10ml" (required)      |
| frequency   | TEXT      | NOT NULL, CHECK (frequency <> '')  | How often to take the medication e.g., "twice daily"         |
| start_date  | DATE      | NULLABLE                           | Date when medication treatment started (optional)            |
| end_date    | DATE      | NULLABLE                           | Date when medication treatment ended or should end           |
| status      | TEXT      | NOT NULL, DEFAULT 'active'         | Current status: `active` or `completed`                      |
| created_at  | TIMESTAMP | NOT NULL, DEFAULT NOW()            | Timestamp when record was created                            |
| updated_at  | TIMESTAMP | NOT NULL, DEFAULT NOW()            | Timestamp when record was last updated                       |

#### Indexes

- `idx_medications_status` - Efficient filtering by status (active/completed)
- `idx_medications_created_at` - Sorting by most recently added (DESC)

#### Constraints

- `chk_status` - Status must be either 'active' or 'completed'
- `chk_name_not_empty` - Name cannot be empty or NULL
- `chk_dosage_not_empty` - Dosage cannot be empty or NULL
- `chk_frequency_not_empty` - Frequency cannot be empty or NULL

### dose_records table

| Column        | Type      | Constraints      | Description                                      |
|---------------|-----------|------------------|--------------------------------------------------|
| id            | UUID      | PRIMARY KEY      | Unique identifier for the dose record            |
| medication_id | UUID      | NOT NULL, FK     | Reference to medications.id (CASCADE DELETE)     |
| date          | DATE      | NOT NULL         | Date the dose was taken (cannot be future)       |
| timestamp     | TIMESTAMP | NULLABLE         | Exact timestamp when dose was recorded           |
| status        | TEXT      | DEFAULT 'taken'  | Dose status: taken, skipped, or missed           |

#### Indexes

- `idx_dose_records_medication_id` - Efficient lookup by medication
- `idx_dose_records_date` - Efficient filtering by date range
- `idx_dose_records_medication_date` - Composite index for medication + date range queries

#### Constraints

- `chk_dose_status` - Status must be one of 'taken', 'skipped', or 'missed'
- `unique_medication_date` - Unique constraint preventing duplicate dose records for same medication on same date (enforces idempotency)

## Running Tests

```bash
# Run all tests
pytest tests/test_medication_tracker.py -v

# Run with coverage
pytest tests/test_medication_tracker.py -v --cov=medication_tracker --cov-report=term-missing
```

## Migration

To apply the database schema:

```bash
# The schema is applied automatically when initializing the Database
# For SQL migration, see migrations/create_medications_table.sql
```

## API Endpoints

### Medication Endpoints

- `POST /medications` - Create a new medication
- `GET /medications` - List all medications (with optional status filter)
- `GET /medications/:id` - Get a specific medication
- `PUT /medications/:id` - Update a medication
- `DELETE /medications/:id` - Delete a medication

### Dose Tracking Endpoints

#### POST /medications/:id/doses

Mark a dose as taken for a medication.

**Request body:**
```json
{
  "date": "2026-09-24"  // Optional, defaults to today
}
```

**Response (201 Created):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "medication_id": "550e8400-e29b-41d4-a716-446655440000",
  "date": "2026-09-24",
  "timestamp": "2026-09-24T08:00:00Z",
  "status": "taken"
}
```

**Error responses:**
- `400 Bad Request` - Invalid date format or future date
- `404 Not Found` - Medication not found
- `409 Conflict` - Dose already recorded for this medication on this date (idempotency)

#### GET /medications/:id/doses

Get dose history for a medication filtered by date range.

**Query parameters:**
- `start` - Start date filter (ISO format, optional)
- `end` - End date filter (ISO format, optional)

**Response (200 OK):**
```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "medication_id": "550e8400-e29b-41d4-a716-446655440000",
    "date": "2026-09-24",
    "timestamp": "2026-09-24T08:00:00Z",
    "status": "taken"
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440002",
    "medication_id": "550e8400-e29b-41d4-a716-446655440000",
    "date": "2026-09-23",
    "timestamp": "2026-09-23T09:00:00Z",
    "status": "taken"
  }
]
```

**Note:** Results are sorted by date descending (most recent first).

#### POST /medications/:id/dose

Alias for `/medications/:id/doses` - maintained for backward compatibility.

#### GET /medications/:id/dose-records

Alias for `/medications/:id/doses` - maintained for backward compatibility.

## Frontend Integration Notes

### Expected JSON Response Format

**Medication object:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Amoxicillin",
  "dosage": "500mg",
  "frequency": "twice daily",
  "start_date": "2026-01-01",
  "end_date": "2026-01-14",
  "status": "active",
  "created_at": "2026-09-24T10:00:00Z",
  "updated_at": "2026-09-24T10:00:00Z"
}
```

**DoseRecord object:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "medication_id": "550e8400-e29b-41d4-a716-446655440000",
  "date": "2026-09-24",
  "timestamp": "2026-09-24T08:00:00Z",
  "status": "taken"
}
```

### Status Values

- `active` - Medication is currently being taken
- `completed` - Medication course has finished or been discontinued

### Common Operations

**List active medications sorted by most recent:**
```
GET /medications?status=active
```

**Mark medication as completed:**
```
PUT /medications/:id
{
  "status": "completed"
}
```

**Record a dose taken:**
```
POST /medications/:id/doses
{
  "date": "2026-09-24"
}
```

## Dose Tracking Workflow

### Mark-as-Taken Flow

1. User initiates "mark as taken" action for a medication
2. System creates a dose record with:
   - Current date (or specified date)
   - Current timestamp
   - Status: "taken"
3. System checks for existing dose record (idempotency check)
4. If duplicate exists, returns 409 Conflict
5. If unique, returns 201 Created with dose record

### Idempotency Behavior

The dose tracking system enforces idempotency through a unique constraint on `(medication_id, date)`:

- **First call**: Creates dose record and returns 201 Created
- **Subsequent calls same day**: Returns 409 Conflict with error message
- **Different dates**: Creates new dose record for each date

This ensures:
- Users cannot accidentally record multiple doses for the same medication on the same day
- The API is idempotent - calling it multiple times with the same parameters has the same effect as calling it once
- Dose history accurately reflects adherence without duplicates

### Dose Status Values

| Status | Description | Use Case |
|--------|-------------|----------|
| `taken` | Dose was taken as prescribed | User confirms they took their medication |
| `skipped` | Dose was intentionally skipped | User decides to skip a dose (e.g., due to side effects) |
| `missed` | Dose was forgotten/missed | Retrospective entry for forgotten doses |

### Date Validation

- **Future dates rejected**: Cannot record doses for dates after today
- **Past dates allowed**: Can record historical doses for adherence tracking
- **Default date**: If no date provided, defaults to today

### Example: Handling Idempotency

```python
from medication_tracker import Database, MedicationRepository, Medication
from medication_tracker.dose_service import DoseService, ConflictError
from datetime import date

db = Database("medications.db")
db.init_schema()
repository = MedicationRepository(db)
dose_service = DoseService(db)

# Create medication
medication = Medication(name="Amoxicillin", dosage="500mg", frequency="twice daily")
repository.create(medication)

# First call - succeeds
try:
    dose = dose_service.mark_dose_taken(medication.id)
    print(f"Dose recorded at {dose.timestamp}")
except ConflictError:
    print("Already recorded today")

# Second call same day - raises ConflictError
try:
    dose_service.mark_dose_taken(medication.id)  # Raises ConflictError
except ConflictError as e:
    print(f"Idempotency check: {e}")
```
