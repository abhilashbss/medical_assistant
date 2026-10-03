# Evidence plan — Prescription tracker (build unit #1)

## Evidence type chosen: console transcript

**Artifact:** `.see/e2e-artifacts/console-transcript.txt`

This milestone is a Python validation + data-access layer backed by SQLite —
there is no browser, CLI, or HTTP surface to screenshot or curl. The functional
gate exercises the layer by calling real repository/validator operations
(create, retrieve, complete, discontinue-with-reason, dose logging, history
query, validation rejections, duplicate-active uniqueness) and asserting on
their return values. The most faithful readable evidence of that behaviour is a
**console transcript**: each operation the test performs is written, alongside
its real response, as labelled lines (`[create]`, `[transition]`,
`[dose-log]`, `[validation]`, `[uniqueness]`, `[history]`, `[perf]`) into the
transcript file as the test runs. This captures exactly what the milestone
proves — persisted fields, status transitions with timestamps, immutability,
duplicate-active rejection, and start_date-DESC history ordering — in a form a
reviewer can read without re-running the suite. The assertions are unchanged,
so the functional check still fails when the behaviour is broken; the
transcript is a side effect of the same passing run.