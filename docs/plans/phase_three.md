# Phase three: readable semantic checks

> Execute the existing approved phase-three scope with writing-plans and test-driven-development. A focused code review precedes integration. The user requested ordinary branch names and normal publication through master; author attribution stays Felix.

**Goal:** Surface numeric, negation, causal and scope discrepancies with traceable text, while abstaining when the rules cannot compare the statements reliably.

**Architecture:** Keep similarity as a retrieval score. Split sentence/clause handling, quantity comparison, polarity checks and causal/scope checks into small modules. A typed assessment records findings and the actual triggering excerpt/location. The service maps assessment states to conservative review levels, independently of metadata/retraction status.

**Tech stack:** Existing Python/Pydantic/pytest stack and standard-library regex/Decimal/dataclasses only. Existing optional embeddings can rank text; they cannot bypass rule checks. No new model, package or live API experiment.

## Design choices

Three routes were considered: keep patching similarity thresholds, add an opaque model/NLI dependency, or introduce explicit bounded checks. Use the third: it directly addresses the audit's known counterexamples, remains offline-capable and is readable for a first project. Models and calibrated benchmark evaluation remain future work.

- No similarity-only `SUPPORTED`/`CONTRADICTED` output. New states: `TEXT_ALIGNED` (wording aligned within checked rules), `POTENTIAL_CONFLICT` (comparable text has a concrete discrepancy), `REVIEW_REQUIRED` (qualifiers/coverage/comparability need review), `INSUFFICIENT_EVIDENCE` (no usable counterpart). None establishes scientific truth.
- Preserve the five-element `evaluate_alignment` adapter for existing Python callers, with explicitly documented new state meanings. New application code uses a named assessment with findings. Historical benchmark score-to-label scripts are not validated by this phase.
- Numeric checks preserve decimals and percentages, normalize a small explicit unit table using Decimal, retain bounds/approximation, and require matching subject/metric/conditions. Unknown dimensions, complex ranges and ambiguous multiple quantities request review rather than guessed comparison. Reference markers are not measurements.
- Negation uses word boundaries and contraction normalization. Polarity comparisons require a common subject and outcome; inspect matched clauses only. `not only`, `no evidence`, nonsignificance, double negation and negated opposite-direction verbs cannot be treated as simple contradiction.
- Causal wording is stronger than association wording. Missing populations, changed observation times, universal quantifiers and removed modality/conditions create explicit review findings. No attempt is made to infer causality from article type alone.
- Compare relevant text across available passages and retain both sides when evidence disagrees. Unrelated clauses must not flip a matched result. Each finding includes its actual evidence excerpt and location where available.
- Text-alignment results are review notices, not green claim passes. Metadata-only passes and confirmed retraction alerts keep their existing behavior. CLI/MCP/HTML/Markdown display the same structured findings.

## File responsibilities

| File | Responsibility |
| --- | --- |
| `core/claim_checks/text.py` | Source-preserving clauses, normalized text and explicit comparison anchors |
| `core/claim_checks/numbers.py` | Quantity extraction, units, bounds and comparable numeric differences |
| `core/claim_checks/polarity.py` | Local negation/direction checks and uncertainty cases |
| `core/claim_checks/scope.py` | Population, modality, conditions and causal-strength changes |
| `core/text_similarity.py` | Existing lexical ranking helpers, separated from semantic conclusions |
| `providers/claim_eval.py` | Candidate ranking, check orchestration, evidence disagreement and adapter |
| `core/models.py`, `core/service.py` | Typed findings and conservative application behavior |
| Shared formatter/reporter | Explain states and show exact triggering evidence |

## Tasks and acceptance

- [x] Re-run the 172-test baseline and preserve the old outputs on synthetic counterexamples.
- [x] Add failing cases for changed/equivalent quantities, negatives/controls, causal overstatements, population/time/range changes, unrelated text and mixed evidence. Fixtures are software examples, not benchmark data.
- [x] Implement the small check modules and typed assessment; ensure unknown or noncomparable cases abstain.
- [x] Integrate across all entrypoints and preserve local evidence coordinates. Migrate old tests that explicitly required misleading support/contradiction semantics, with explanations.
- [x] Add Chinese reading guidance, a deterministic replay script and examples covering each category. Separate similarity scores, rule findings and unverified scientific claims.
- [x] Run focused and complete tests, actual offline MCP stdio validation and wheel build. Request independent code review and reproduce/fix material findings.
- [ ] Record scope, commands, evidence, commits and limitations in the research workspace worklog. Recheck original and remote state, integrate tested commits and push normally without rewriting history.

Evidence root: `D:/Internship/Academic code/audit_guardrail_20261101_phase_three/`. Original repository baseline: `d4f86981c2982aa1afa530f372c70388c9bd949d`. Isolated branch: `phase-three` in `guardrail_phase_three`.
