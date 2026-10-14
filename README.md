# NIX

Nix is great.  

For tutorials see:  https://nix.dev/tutorials/first-steps/

A decent read --> https://rgoswami.me/posts/ccon-tut-nix/

??? https://marketplace.visualstudio.com/items?itemName=arrterian.nix-env-selector


To update the dependencies run --> 
`nix-shell -p niv --run "niv update"`


Un-Installing Nix : follow - https://nixos.org/manual/nix/stable/installation/uninstall.html
Install Nix : sh <(curl -L https://nixos.org/nix/install)
and direnv : brew install direnv# medical_assistant

---

# Prescription Tracker

Tracks patient medicine prescriptions with a structured dosage, lifecycle status
transitions, and an immutable audit trail. Backed by SQLite with foreign keys,
CHECK constraints, and a partial unique index that enforces **one active
prescription per medicine per patient**.

## Running

```bash
pip install -r requirements.txt
python -m prescription_tracker.api   # serves on http://0.0.0.0:5001
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/prescriptions` | Create a prescription (201). |
| GET    | `/prescriptions/{id}` | Retrieve a single prescription (200 / 404). |
| GET    | `/patients/{patient_id}/prescriptions` | Full history sorted by `start_date` DESC, active separated from historical. |
| PATCH  | `/prescriptions/{id}/complete` | Transition active → completed (200). |
| PATCH  | `/prescriptions/{id}/discontinue` | Transition active → discontinued; requires a `reason` (400 if missing). |
| POST   | `/prescriptions/{id}/doses` | Append a dose-adherence log entry (201). |
| GET    | `/prescriptions/{id}/doses` | Dose logs ordered by `taken_at` ascending. |
| GET    | `/prescriptions/{id}/transitions` | Audit trail of status transitions. |

There is deliberately **no PUT or DELETE** on `/prescriptions/{id}` — prescription
rows are immutable after creation except for the two explicit lifecycle
transitions above.

### Example: create

```http
POST /prescriptions
Content-Type: application/json

{
  "patient_id": "8f86700d-8caf-430b-9011-c3d4b4cd83ee",
  "doctor_id": "91a5dd5c-d8ca-451f-baa0-5c80c353d25a",
  "medicine_name": "Amoxicillin",
  "dosage_amount": "500",
  "dosage_unit": "mg",
  "frequency": "three times daily",
  "start_date": "2026-01-01T08:00:00+00:00"
}
```

Response `201`:

```json
{
  "id": "82320661-d68e-40a8-b898-467838165572",
  "patient_id": "8f86700d-8caf-430b-9011-c3d4b4cd83ee",
  "doctor_id": "91a5dd5c-d8ca-451f-baa0-5c80c353d25a",
  "medicine_name": "Amoxicillin",
  "dosage_amount": "500",
  "dosage_unit": "mg",
  "frequency": "three times daily",
  "start_date": "2026-01-01T08:00:00+00:00",
  "end_date": null,
  "status": "active",
  "created_at": "2026-10-01T09:07:14.105225+00:00",
  "updated_at": "2026-10-01T09:07:14.105225+00:00"
}
```

### Example: discontinue (mandatory reason)

```http
PATCH /prescriptions/{id}/discontinue
Content-Type: application/json

{ "reason": "Patient experienced nausea" }
```

A request without a non-empty `reason` returns `400`:

```json
{ "error": "a non-empty reason is required to discontinue a prescription" }
```

### Example: patient history (active separated from historical)

```http
GET /patients/{patient_id}/prescriptions
```

```json
{
  "active": [ { "id": "...", "status": "active", "start_date": "...", ... } ],
  "historical": [ { "id": "...", "status": "completed", ... }, { "id": "...", "status": "discontinued", ... } ]
}
```

Both partitions are sorted by `start_date` descending.

## Immutability & one-active-per-medicine guarantees

- **Immutability**: After creation a prescription row can only change via
  `PATCH .../complete` or `PATCH .../discontinue`. Both insert a timestamped
  `status_transitions` audit row and update `status` in one transaction. Any
  other mutation (PUT, DELETE, re-transitioning a terminal prescription) is
  rejected — completed/discontinued prescriptions never accept further
  transitions, so the audit trail is closed.
- **One active per medicine per patient**: A partial unique index
  `idx_one_active_per_medicine ON prescriptions(patient_id, medicine_name)
  WHERE status = 'active'` rejects a second concurrent active prescription for
  the same patient + medicine with `409`. Completing or discontinuing the
  existing active prescription frees the slot, so a new active prescription for
  the same medicine is then allowed.
- **Discontinuation requires a reason**: The data layer rejects discontinue
  calls with an empty/missing reason; the reason is recorded on the audit row.
- **Timestamps**: All date/time fields are stored in ISO 8601 with timezone.
  Each status transition records a timezone-aware `transitioned_at` timestamp.
