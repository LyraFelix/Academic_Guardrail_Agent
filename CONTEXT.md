# Academic Guardrail Context

This project provides citation metadata lookup, source-backed retraction alerts, local reference matching and heuristic text alignment through CLI and MCP.

## Boundaries

- The entry points call AuditService; they do not independently interpret provider dictionaries.
- Providers collect facts. `core/reference_decision.py` assigns reference status. `ClaimEvaluator` optionally adds heuristic text comparison.
- Identity ambiguity takes precedence over retraction. Confirmed same-DOI evidence is retained across sources; title keywords alone remain suspected.
- `RetractionStatus` has CONFIRMED, SUSPECTED, NO_RECORD and NOT_CHECKED. Neither of the latter means a paper is normal.
- `EvidenceSource` records source, kind, identifier, detail and an optional source flag. A final verdict and a source observation are separate concepts.
- `REFERENCE_METADATA` and `HEURISTIC_ALIGNMENT` describe different scopes. Alignment scores and labels are not calibrated entailment judgments.
- Offline mode does not initialize online providers or embedding models. `--refs-dir` alone does not enable offline mode.
- The built-in retraction index has three historical demo records. It is not complete or automatically synchronized.

## Development

Read `docs/learning_guide.md` and `docs/plans/phase_one.md`. Preserve simple module responsibilities and explicit failure states. Unit tests block external HTTP, isolate caches and disable model downloads. Do not represent unit tests, synthetic fixtures or historical prediction files as current live-provider or LLM benchmark results.

Parser coverage, repeated-citation handling, numerical/causal claim reasoning, and benchmark reconstruction remain separate follow-up work.
