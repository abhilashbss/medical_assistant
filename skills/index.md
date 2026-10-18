# Project skill library

What building this project taught. One fact or one procedure per file, linked here with a one-line hook. Nothing that the code or git history already says.

## Kinds

- `fixes/` — symptom, root cause, fix pattern, when it applies
- `traps/` — not bugs, but cost time: things that look broken and are not
- `testing/` — which runner for which tree, fixtures, what each gate should cover
- `system/` — module map, data flow, where state lives (one file per subsystem)
- `ops/` — start each service, ports, env files, where logs are
- `integrations/` — quirks of each external dependency
- `recipes/` — step lists for recurring change shapes
- `decisions/` — why it is this way: context, decision, consequence, date

## Index

## Rules

1. One fact per file, under ~60 lines, with front-matter: kind, applies_to, tags, reader (steward|dev|both), verified (date), refs (paths/flags it depends on).
2. Search the index first; update an existing entry rather than add a sibling.
3. A fix pattern seen three times becomes a test or guardrail; point at it.
- [In-network filter fix](fixes/in_network_filter.md) — ensures only in-network providers are returned
