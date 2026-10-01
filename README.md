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

## Medicine Tracker — Dose Tracking

The medicine tracker records prescribed medications and tracks daily adherence
through timestamped dose records. Each medication can have one dose record per
day; marking a dose as taken is idempotent — a second attempt for the same date
returns `409 Conflict`.

### Mark a dose as taken

`POST /medications/<id>/doses`

Request body (optional):

```json
{ "date": "2026-09-20", "status": "taken" }
```

- `date` defaults to today when omitted.
- `status` may be `taken` (default) or `skipped`.
- Returns `201` with the created dose record, `409` if a dose was already
  recorded for that date, `400` for a future date or invalid input, and `404`
  if the medication does not exist.

Response:

```json
{
  "id": "uuid",
  "medication_id": "uuid",
  "date": "2026-09-20",
  "timestamp": "2026-09-20T08:30:00",
  "status": "taken"
}
```

### Get dose history

`GET /medications/<id>/doses?start=YYYY-MM-DD&end=YYYY-MM-DD`

Returns dose records for the medication, sorted by date descending then
timestamp descending. `start` and `end` are inclusive and optional.

### Configuration

`DATE_TIMEZONE` (default `UTC`) controls which timezone "today" is resolved in
for default-date dose marking. The `dose_records` table has a unique constraint
on `(medication_id, date)` and indexes on `medication_id`, `date`, and the
composite `(medication_id, date DESC)` for query performance.
