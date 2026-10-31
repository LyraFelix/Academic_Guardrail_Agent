# Academic Guardrail Context

This project provides citation metadata lookup, source-backed retraction alerts, local reference matching and heuristic text alignment through CLI and MCP.

## Boundaries

- The entry points call AuditService; they do not independently interpret provider dictionaries.
- Providers collect facts. `core/reference_decision.py` assigns reference status. `ClaimEvaluator` optionally adds heuristic text comparison.
- Identity ambiguity takes precedence over retraction. Confirmed same-DOI evidence is retained across sources; title keywords alone remain suspected.
- `RetractionStatus` has CONFIRMED, SUSPECTED, NO_RECORD and NOT_CHECKED. Neither of the latter means a paper is normal.
- `EvidenceSource` records source, kind, identifier, detail and an optional source flag. A final verdict and a source observation are separate concepts.
- `REFERENCE_METADATA`, `TEXT_RETRIEVAL` and `HEURISTIC_ALIGNMENT` describe different scopes. Alignment scores and labels are not calibrated entailment judgments.
- Offline mode does not initialize online providers or embedding models. `--refs-dir` alone does not enable offline mode.
- The built-in retraction index has three historical demo records. It is not complete or automatically synchronized.

## Development

Read `docs/learning_guide.md`, `docs/phase_two_guide.md` and `docs/plans/phase_two.md`. Preserve simple module responsibilities and explicit failure states. Unit tests block external HTTP, isolate caches and disable model downloads. Do not represent unit tests, synthetic fixtures or historical prediction files as current live-provider or LLM benchmark results.

Phase two separates bibliography entries from occurrences, reuses reference decisions, preserves parsing diagnostics and retrieves local body passages with exact file/page/character positions. Known DOI targets require corresponding local DOI identity. Uncited entries are metadata-only. Retrieval status remains separate from identity/retraction status; failed upstream queries are retained alongside successful local fallbacks.

Complex layout/OCR, arbitrary citation styles and TeX macros, numerical/causal claim reasoning, and benchmark reconstruction remain follow-up work. `scripts/validate_phase_two.py` replays a synthetic service/MCP example with HTTP/provider/model guards; it is engineering evidence, not a model benchmark.
