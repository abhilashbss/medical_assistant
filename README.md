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

# Medicine Tracker

Tracks prescribed medications (name, dosage, frequency, start/end date, status)
with timestamped dose records. All data persists to a SQLite file so entries
survive app restarts.

## Data persistence guarantees

- **Storage**: Medication data lives in a SQLite file (`medication_tracker/medications.db`,
  or the path in `MEDICATION_DB_PATH`). Opening a fresh `Database` at the same
  path re-reads it from disk, so entries are retrievable after a restart.
- **Required fields**: `name`, `dosage`, and `frequency` are enforced at write
  time (validation rejects empty or non-string inputs) and re-verified on load
  by `verify_persistence`, which reports any rows missing required fields.
- **Date ranges**: `start_date` must be on or before `end_date` when both are
  set; this is validated on create/update and re-checked during integrity
  verification.
- **Integrity on load**: `load_and_reconcile` runs on startup to (1) verify all
  rows are intact, (2) remove any corrupted/incomplete records that bypassed
  application validation, and (3) auto-complete past end dates.

## Edge case handling

- **Past end dates**: A medication whose `end_date` is before today is
  auto-marked `completed` on app load (`auto_complete_past_end_dates`), so the
  active list always reflects current prescriptions. Medications with no
  `end_date`, or a future `end_date`, are left untouched.
- **Overlapping schedules**: Medications with overlapping date ranges each
  appear exactly once in the list, sorted by most recently added
  (`created_at` descending) — no deduplication or merging is performed.
- **Corrupted records**: Records missing a required field, with an invalid
  status, or an impossible date range are removed by `recover_corrupted` so
  they cannot poison the list view.

## Running the tests

```
pip install -r requirements.txt
pytest tests/test_medication_tracker.py -v --cov=medication_tracker
pytest tests/functional/test_medicine_tracker.py -v --cov
```
