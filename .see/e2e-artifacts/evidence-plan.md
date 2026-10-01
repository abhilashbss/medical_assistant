# Evidence Plan — Build Unit #2: Dose Tracking

## Evidence type: Console transcript (HTTP request/response)

**Chosen artifact:** `console-transcript.txt` — a readable log of real HTTP
requests and their responses, captured by the functional gate test
(`tests/functional/test_medicine_tracker.py::TestDoseTrackingEvidence`).

**Why this matches the milestone.** Build unit #2 is a dose-tracking *API
service*, not a browser UI. Its milestone behaviour — mark-as-taken creates a
timestamped dose record, idempotency rejects duplicates with 409, dose history
returns date-range-filtered results sorted descending, future dates are rejected
with 400, and doses are isolated per medication — is entirely observable through
HTTP request/response pairs. A console transcript of those pairs is the most
direct evidence that the milestone works: a reader can see each request body,
the status code, and the JSON payload returned, without needing a running server
or a browser. Screenshots would prove nothing here because there is no UI in this
unit's scope; the transcript captures exactly what the functional test asserts,
so the evidence and the gate cannot diverge.

**How it is captured.** The evidence test runs inside the existing functional
gate command (`pytest tests/functional/test_medicine_tracker.py -v --cov`). It
uses the Flask test client to issue real requests, asserts on every response
(strict — the test fails if behaviour breaks), and writes the formatted
request/response transcript to `.see/e2e-artifacts/console-transcript.txt` on
each run. The transcript is regenerated from scratch on every gate run, so it
always reflects the current behaviour.