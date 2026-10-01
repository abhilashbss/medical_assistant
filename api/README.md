# Medication Tracker API Documentation

RESTful API for managing prescribed medications with dosage schedules.

## Base URL

When running locally: `http://localhost:8000`

## Endpoints

### Create Medication

**POST** `/medications`

Create a new medication entry.

#### Request Body

```json
{
  "name": "Amoxicillin",
  "dosage": "500mg",
  "frequency": "twice daily",
  "start_date": "2026-01-01",
  "end_date": "2026-01-14",
  "status": "active"
}
```

**Required fields:**
- `name` (string, non-empty): Medication name
- `dosage` (string, non-empty): Dosage amount and unit, e.g., "500mg"
- `frequency` (string, non-empty): How often to take, e.g., "twice daily"

**Optional fields:**
- `start_date` (string, ISO date format YYYY-MM-DD): Treatment start date
- `end_date` (string, ISO date format YYYY-MM-DD): Treatment end date
- `status` (string): Either "active" or "completed" (default: "active")

#### Response

**Status 201 Created**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Amoxicillin",
  "dosage": "500mg",
  "frequency": "twice daily",
  "start_date": "2026-01-01",
  "end_date": "2026-01-14",
  "status": "active",
  "created_at": "2026-09-24T10:30:00Z",
  "updated_at": "2026-09-24T10:30:00Z"
}
```

#### Error Responses

**Status 400 Bad Request** - Validation error

```json
{
  "detail": {
    "error": "name must be a non-empty string"
  }
}
```

---

### Get All Medications

**GET** `/medications`

Retrieve all medications sorted by created_at descending.

#### Query Parameters

- `status` (string, optional): Filter by status ("active" or "completed")

#### Response

**Status 200 OK**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Ibuprofen",
    "dosage": "400mg",
    "frequency": "every 6 hours",
    "start_date": null,
    "end_date": null,
    "status": "active",
    "created_at": "2026-09-24T11:00:00Z",
    "updated_at": "2026-09-24T11:00:00Z"
  },
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Amoxicillin",
    "dosage": "500mg",
    "frequency": "twice daily",
    "start_date": "2026-01-01",
    "end_date": "2026-01-14",
    "status": "completed",
    "created_at": "2026-09-24T10:30:00Z",
    "updated_at": "2026-09-24T10:30:00Z"
  }
]
```

---

### Get Medication by ID

**GET** `/medications/{medication_id}`

Retrieve a specific medication by UUID.

#### Path Parameters

- `medication_id` (string, UUID): The medication's unique identifier

#### Response

**Status 200 OK**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Amoxicillin",
  "dosage": "500mg",
  "frequency": "twice daily",
  "start_date": "2026-01-01",
  "end_date": "2026-01-14",
  "status": "active",
  "created_at": "2026-09-24T10:30:00Z",
  "updated_at": "2026-09-24T10:30:00Z"
}
```

#### Error Responses

**Status 404 Not Found**

```json
{
  "detail": {
    "error": "Medication with ID 550e8400-e29b-41d4-a716-446655440000 not found"
  }
}
```

**Status 400 Bad Request** - Invalid UUID format

```json
{
  "detail": {
    "error": "Invalid medication ID format: invalid-uuid"
  }
}
```

---

### Update Medication

**PUT** `/medications/{medication_id}`

Update an existing medication.

#### Path Parameters

- `medication_id` (string, UUID): The medication's unique identifier

#### Request Body

All fields are optional. Only provided fields will be updated.

```json
{
  "name": "Amoxicillin Extended Release",
  "dosage": "750mg",
  "frequency": "once daily",
  "start_date": "2026-01-01",
  "end_date": "2026-02-01",
  "status": "completed"
}
```

#### Response

**Status 200 OK**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Amoxicillin Extended Release",
  "dosage": "750mg",
  "frequency": "once daily",
  "start_date": "2026-01-01",
  "end_date": "2026-02-01",
  "status": "completed",
  "created_at": "2026-09-24T10:30:00Z",
  "updated_at": "2026-09-24T12:00:00Z"
}
```

#### Error Responses

**Status 404 Not Found** - Medication not found

**Status 400 Bad Request** - Validation error or invalid UUID format

---

### Delete Medication

**DELETE** `/medications/{medication_id}`

Delete a medication.

#### Path Parameters

- `medication_id` (string, UUID): The medication's unique identifier

#### Response

**Status 204 No Content**

#### Error Responses

**Status 404 Not Found**

```json
{
  "detail": {
    "error": "Medication with ID 550e8400-e29b-41d4-a716-446655440000 not found"
  }
}
```

---

## Error Response Format

All errors return a JSON object with a `detail` field:

```json
{
  "detail": {
    "error": "Error message describing what went wrong"
  }
}
```

## HTTP Status Codes

| Code | Description |
|------|-------------|
| 200  | Success (GET, PUT) |
| 201  | Created (POST) |
| 204  | No Content (DELETE) |
| 400  | Bad Request (validation error, invalid UUID) |
| 404  | Not Found (medication doesn't exist) |

## Running the API Server

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Examples

### cURL

```bash
# Create a medication
curl -X POST http://localhost:8000/medications \
  -H "Content-Type: application/json" \
  -d '{"name":"Amoxicillin","dosage":"500mg","frequency":"twice daily"}'

# Get all medications
curl http://localhost:8000/medications

# Get a specific medication
curl http://localhost:8000/medications/550e8400-e29b-41d4-a716-446655440000

# Update a medication
curl -X PUT http://localhost:8000/medications/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{"status":"completed"}'

# Delete a medication
curl -X DELETE http://localhost:8000/medications/550e8400-e29b-41d4-a716-446655440000
```

### Python

```python
import requests

BASE_URL = "http://localhost:8000"

# Create a medication
response = requests.post(
    f"{BASE_URL}/medications",
    json={
        "name": "Amoxicillin",
        "dosage": "500mg",
        "frequency": "twice daily"
    }
)
medication = response.json()
print(f"Created: {medication['name']}")

# Get all medications
response = requests.get(f"{BASE_URL}/medications")
medications = response.json()
print(f"Total medications: {len(medications)}")

# Update a medication
response = requests.put(
    f"{BASE_URL}/medications/{medication['id']}",
    json={"status": "completed"}
)
updated = response.json()
print(f"Updated status: {updated['status']}")

# Delete a medication
response = requests.delete(f"{BASE_URL}/medications/{medication['id']}")
print(f"Delete status: {response.status_code}")
```
