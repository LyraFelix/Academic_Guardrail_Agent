# Academic Guardrail Context

This project provides citation metadata lookup, source-backed retraction alerts, local reference matching and source-linked client review through CLI and one MCP server.

## Boundaries

- Reference entry points call AuditService; raw-text review packets explicitly skip identity verification.
- Providers collect facts. `core/reference_decision.py` assigns reference status. `ClaimEvaluator` optionally adds heuristic text comparison.
- Identity ambiguity takes precedence over retraction. Confirmed same-DOI evidence is retained across sources; title keywords alone remain suspected.
- `RetractionStatus` has CONFIRMED, SUSPECTED, NO_RECORD and NOT_CHECKED. Neither of the latter means a paper is normal.
- `EvidenceSource` records source, kind, identifier, detail and an optional source flag. A final verdict and a source observation are separate concepts.
- `REFERENCE_METADATA`, `TEXT_RETRIEVAL` and `RULE_BASED_REVIEW` describe different scopes. Alignment scores and labels are not calibrated entailment judgments.
- Offline mode does not initialize online providers or embedding models. `--refs-dir` alone does not enable offline mode.
- The built-in retraction index has three historical demo records. It is not complete or automatically synchronized.
- The client model supplies semantic conclusions. `prepare_claim_review` / `read_claim_evidence` / `record_claim_review` preserve source evidence, check its digest and exact quotes, and append records. `EVIDENCE_LINKS_VALID` is mechanical validation, never semantic certification. There is no server-side model API.
- Evidence coverage is a client declaration, not proof that a model considered every sentence. Local reference extraction can already have truncated source units. Legacy HTML remains rule-only; client results are saved separately.

## Development

Read `docs/learning_guide.md`, `docs/phase_two_guide.md` and `docs/plans/phase_two.md`. Preserve simple module responsibilities and explicit failure states. Unit tests block external HTTP, isolate caches and disable model downloads. Do not represent unit tests, synthetic fixtures or historical prediction files as current live-provider or LLM benchmark results.

Phase two separates bibliography entries from occurrences, reuses reference decisions, preserves parsing diagnostics and retrieves local body passages with exact file/page/character positions. Known DOI targets require corresponding local DOI identity. Uncited entries are metadata-only. Retrieval status remains separate from identity/retraction status; failed upstream queries are retained alongside successful local fallbacks.

Phase three adds inspectable number, negation, causality and scope rules; phase four separates evaluation inputs, labels, predictions and scoring. Read `docs/client_review_guide.md` and `docs/semantic_coverage_results.md` for the client workflow and current evidence boundaries. Rules remain unresolved on all 339 SciFact dev pairs after the context fixes. The separate 12-pair public-train interactive pilot is not a general benchmark or evidence of improvement over a bare model.

Complex layout/OCR, arbitrary citation styles/TeX macros, general semantic accuracy and online coverage remain limitations. `scripts/validate_phase_two.py`, `validate_phase_three.py` and `validate_client_review.py` use synthetic scripted fixtures with HTTP/model guards; those runs are engineering evidence, not model-accuracy experiments.
