# Semantic coverage and client review implementation plan

**Goal:** Stop treating local rule abstention as the end of an MCP task. Repair reproducible text-handling defects and let the existing client model complete a source-linked review.

**Architecture:** The server collects and preserves source evidence, runs bounded rules, and stores an immutable review packet. The client model reads the packet, judges the claim and returns structured reasoning/quotes. The server validates packet identity, evidence IDs, exact quotes and review coverage, then saves an append-only review record. It does not certify the model's reasoning. No nested model API or new dependency is required.

**Baseline:** `1ed45ef07019b52bbe578f40dfdcd73dfbbc1235`; 301 tests pass. Phase-four data/results remain unchanged. Its 258 review + 81 insufficient rows mean **339/339 unresolved by rules**, not 76.11% human workload.

## Authorized design and alternatives

The owner selected an existing LLM client with MCP evidence and validation tools. Rule-only expansion cannot cover arbitrary scientific paraphrases. A server-side model would add configuration/cost and duplicate the existing client. The selected design keeps local rules inspectable and delegates language reasoning to the client without requiring protocol sampling support.

## Tasks and acceptance

1. **Repair bounded text handling.** Modify `core/claim_checks/text.py`, `numbers.py`, `providers/claim_eval.py`, and the evidence granularity in `core/service.py`. Preserve complete context in returned evidence; avoid splitting an appositive into subjectless fragments; exclude digits embedded in Unicode/hyphenated identifiers. An explicit aligned candidate must not be overridden by a weaker unconfirmed candidate, while two explicitly opposing candidates still require review. Add `tests/test_semantic_coverage.py` first, including apposition, entity digits, different metrics/populations, unrelated context and actual conflicting evidence. Run it red, then the existing semantic tests and full suite.
2. **Measure unresolved work honestly.** Add `rule_unresolved_rate = (REVIEW_REQUIRED + INSUFFICIENT_EVIDENCE + ERROR) / total` and `concrete_rule_result_rate` to `benchmarks/metrics.py`, explain them in the report/README, and test their hand-calculated denominators. Neither measures human time or scientific accuracy. Keep all old runs immutable; rescore old rows in a separate diagnostic artifact when adding these fields.
3. **Typed review packets.** Add `core/review_models.py` for packet evidence, client judgment, quote and dimension-check contracts. Add `core/claim_review.py` for packet construction, pagination and pure validation. Packet evidence retains full sentence context, source kind and coordinates. Validate duplicate/unknown IDs, stale packet identity, empty/invented quotes, incomplete declared coverage, missing dimensions and empty evidence. Save the model's conclusion separately from mechanical link-validation status.
4. **Local storage and MCP.** Add `core/review_store.py` with UUID-only paths, content checksums and exclusive creation of packet/review files. Default to the existing local cache root; tests override `ACADEMIC_GUARDRAIL_REVIEW_DIR`. Add `prepare_claim_review`, `read_claim_evidence`, `record_claim_review` to the existing MCP server. Preparation accepts either provided text or a citation resolved through AuditService, not both; ambiguous/retracted references cannot yield a support judgment. All model-independent operations work offline. Update audit output with an actionable client continuation and provide an MCP prompt for the complete workflow.
5. **Integration and readable docs.** Add unit/transport tests for valid and invalid submissions, local citation identity, quote locations, persistence, pagination, no provider/model access and prompt discovery. Existing phase-two/three validators should accept additional tools while still checking their own tools. Add a Chinese guide with a concrete client prompt and explain that offline server behavior does not make the external client model offline.
6. **Measure the changed system.** Re-run the frozen phase-four SciFact inputs with the repaired rule path without choosing samples by outcome. Report this as exposed-development comparison. Separately exercise the actual MCP prepare/read/record flow with the current client assistant on a fixed small sample of previously unread public train inputs; save raw tool outputs and client decisions before opening labels. This is a small interactive workflow pilot, not a general benchmark, proof of improvement over a bare LLM, or a result transferable to all client models.
7. **Review and integrate.** Request independent code/result review, fix important findings, run the full suite and actual stdio workflow, build the wheel, integrate only onto a clean original master and normal-push with Felix attribution. Record scope, commands, artifacts, checkpoints and evidence boundaries in the research worklog and findings.

## Core review contract

```text
prepare_claim_review(claim, reference_text OR citation_str_or_doi, refs_dir, offline)
  -> packet_id, packet_sha256, claim, reference status, local rule result, evidence page, next_offset
read_claim_evidence(packet_id, offset, limit)
  -> available source units with stable IDs, coordinates and the same digest
record_claim_review(packet_id, judgment, expected_packet_sha256)
  -> saved client judgment + EVIDENCE_LINKS_VALID (not semantic certification)
```

Client conclusions: `SUPPORTED`, `CONTRADICTED`, `NOT_ENOUGH_EVIDENCE`, `UNCERTAIN`. Required reasoning dimensions: subject, relation, numbers, scope, counterevidence. Resolved submissions must declare all packet evidence IDs as considered; the server can validate the declaration, not inspect the client's cognition. SUPPORT/CONTRADICT need at least one exact quote. Empty or blocked evidence can only yield insufficient/uncertain. Each correction creates a new record rather than replacing a prior one.

## Verification commands

```text
python -m pytest tests/test_semantic_coverage.py tests/test_claim_review.py -q
python -m pytest tests -q -p pytest_asyncio.plugin --basetemp <new-dir> --junitxml=<new-xml>
python -m benchmarks run --dataset <phase-four-prepared-data> --output <new-run>
python scripts/validate_client_review.py --output-dir <new-dir>
python -m pip wheel . --no-index --no-deps --no-build-isolation --wheel-dir <new-dir>
```

Evidence root: `D:/Internship/Academic code/audit_guardrail_20261101_semantic_coverage/`. Baseline probes reproduce comma fragmentation, entity-number confusion and weak-candidate veto; exact simple alignment and explicit conflicting-evidence controls already pass and must remain so.

## Outcome

Implemented and independently reviewed. See `../client_review_guide.md` for the readable workflow and `../semantic_coverage_results.md` for results. The rules still leave all 339 dev pairs unresolved. The separate 12-pair interactive client pilot provides six support/refutation decisions and six NEI decisions; it is not a general accuracy estimate. Review tightened actual-counterevidence handling, prepare-to-submit snapshot binding, predeclared gold hashes, and NEI coverage accounting. Source units retain available context; upstream chunking can still cut a sentence.
