# Evidence Plan — Build Unit #3: Medication List UI with Filtering & Edit/Delete

## Evidence type: readable console transcript (`console-transcript.txt`)

This milestone is a medication list UI whose behaviour is defined by its backend
HTTP contract — GET (list with status filter), PUT (edit), and DELETE (remove) —
driven through the Flask app's test client. The most faithful evidence is a
readable console transcript of the real HTTP request/response pairs the
functional gate performs, because it shows exactly the inputs and outputs the
component-based frontend depends on: the list sorted by most-recently-added,
status-filter re-querying returning only matching rows, the edit PUT changing
fields (including active↔completed) and persisting, and the delete returning 204
and removing the entry from the list. A transcript was chosen over screenshots
because the gate exercises the API layer (not a browser), and the
request/response pairs are the load-bearing proof that the list, filter,
edit, and delete flows work end-to-end. The transcript is captured into
`.see/e2e-artifacts/console-transcript.txt` by a test-client wrapper that logs
every exchange, and is flushed at session end by a session-scoped fixture —
without weakening any assertion in the functional gate.