# Synthetic contract examples — not model outputs

Every asset path, UUID, timestamp, metric and artifact reference here is a fixture.
No Earth Engine run produced these files. `projects/example-project/assets/...`
paths are placeholders and `artifact://` references do not resolve to real maps.
The all-zero engine commit and `fixture-only-not-an-engine-release` version are
explicit example sentinels, not deployed provenance. Production workers must use
their actual engine commit/version and actual results.

- `request.json`: minimal submitted request; optional fields resolve to reference defaults.
- `request-resolved.json`: the identical request after resolving defaults.
- `status-running.json`: seed-search snapshot for that request.
- `status-completed.json`: completed snapshot linked to `result.json`.
- `status-failed.json`: an alternative run failure for the same request configuration,
  demonstrating an error payload; not a transition after completion.
- `result.json`: shape/serialization fixture with a 12×12 diagonal matrix and
  deliberately synthetic numeric values. Do not quote these as Libya map accuracy.

See `docs/assistant-contracts.md` for commands and the distinction between software
contract validation and actual execution. Examples are demonstration data only.
