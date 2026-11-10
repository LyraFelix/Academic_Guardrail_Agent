# Local evidence follow-up implementation plan

> For agentic workers: use subagent-driven-development for bounded implementation and independent review. Complete this already authorized plan without another approval gate.

**Goal:** Let an existing model client explain a missing fact, search the same local paper once, rejudge against an extended immutable evidence packet, and export a traceable before/after report.

**Architecture:** Keep legacy ReviewPacket v1 unchanged so frozen packet digests still replay. Store the local source snapshot and parent-review link in a separate checked context. The server retrieves text and validates links; the client owns the semantic conclusion. One MCP server exposes the existing tools plus local preparation, one follow-up, and HTML export.

**Tech stack:** Existing Python/Pydantic/MCP/pypdf/python-docx; standard-library hashing, HTML escaping and files. No new dependencies, embedding downloads or server model calls.

## Scope and contracts

The user approved the missing-evidence -> local targeted lookup -> rejudgment -> report direction. Start with the same identity-matched local paper, not a web search or silent cross-paper substitution. Preserve old packets/reviews. Reject changed/missing sources at rejudgment; show source status in a later report. A changed verdict is not automatically an improvement.

```python
class MissingEvidence(ReviewModel):
    kind: Literal['ENTITY_MAPPING', 'RESULT', 'POPULATION', 'COMPARATOR', 'TIME', 'OTHER']
    claim_part: str  # exact original substring
    question: str
    search_terms: list[str]  # bounded literal terms; no invented alias resolution

# Existing ClientJudgment gains an optional list with a backward-compatible default.
# Existing ReviewPacket is unchanged.
```

Three tools, within the existing MCP server:

```python
async def prepare_local_claim_review(claim: str, citation_str_or_doi: str,
                                     refs_dir: str, initial_scope: str = 'abstract') -> dict: ...
async def follow_up_local_claim(review_id: str, expected_review_sha256: str,
                                gap_index: int = 0) -> dict: ...
async def generate_claim_review_report(review_ids: list[str], output_path: str) -> dict: ...
```

The first tool defaults to a real local abstract with its exact location; absent abstracts stay empty. A full-text option is explicit. The existing record tool saves missing-evidence descriptions and returns a record digest. Follow-up accepts a previously recorded NEI/UNCERTAIN result, one selected gap, and a matching record digest. Its new packet contains old evidence plus at most three lexical hits and adjacent context, within a fixed character budget. A no-match attempt is still recorded; no second follow-up is allowed on the child packet. The report includes both versions, client identity, quotes/locations, missing facts, query, retrieval outcome, and current source status.

## Task 1 — Explicit missing-evidence and immutable linkage

Files: modify `core/review_models.py`, `core/claim_review.py`, `core/review_store.py`; create `core/followup_models.py`, `tests/test_local_followup.py`.

- [x] Add bounded missing-evidence descriptions; reject invented claim substrings and empty/duplicate search terms.
- [x] Add independent checked local-context records, leaving packet serialization untouched.
- [x] Load a saved review by ID, check its packet binding and stored digest; return a digest to clients for future follow-up.
- [x] Test stale review/packet binding, unsupported positive conclusions and legacy packet digest compatibility.

Meaningful acceptance example:

```python
before = store.record(packet.packet_id, incomplete_judgment, packet_digest)
child = follow_up_local_claim(before['review_id'], before['review_sha256'])
assert child['claim'] == packet.claim
assert store.load_packet(packet.packet_id) == packet
# Editing the original local file must block a subsequent recorded judgment.
```

## Task 2 — Exact-byte local source snapshots and targeted retrieval

Files: `core/local_evidence.py`, extraction/ref-store source hash support, `tests/test_local_evidence.py`.

- [x] Parse the exact bytes hashed for PDF/DOCX/text; propagate the raw source hash into local paper metadata.
- [x] Reuse local identity matching and reject path escapes, ambiguity, absent/changed sources and ineligible references.
- [x] Rank bounded literal search terms against body passages; retain adjacent context and exact locations, exclude bibliography.
- [x] Test relevant body-only results, neighboring counterevidence, numeric terms, no-match, duplicate evidence and byte changes.

## Task 3 — Local workflow integration

Files: `core/local_review.py`, `mcp_server.py`, `core/review_instructions.py`, `tests/test_local_followup.py`.

- [x] Prepare abstract/full-text local packets through the existing offline identity/retraction decision.
- [x] Store parent record/hash, selected gap, source fingerprint and search details separately from packet v1.
- [x] Preserve original evidence IDs when appending new exact units; recompute rule hints without treating them as answers.
- [x] Reject bypass via raw text, another source, stale file, unsupported review or repeated follow-up.
- [x] Run focused tests, then actual MCP stdio with HTTP/embedding guards.

## Task 4 — Human-readable report

Files: `core/followup_report.py`, existing reporter entrypoint if useful, `tests/test_followup_report.py`.

- [x] Render one or multiple review chains to self-contained HTML with escaped source/model text.
- [x] Display before/after, quote coordinates, missing evidence and retrieval scope, semantic-not-certified labels.
- [x] Mark changed/missing source files and prevent reporting across broken chains.
- [x] Save new output without overwriting source or existing report. Validate a rendered example.

## Task 5 — Bounded real-source evaluation

Files: `scripts/run_local_followup_evaluation.py`, `docs/local_followup_guide.md`, `docs/local_followup_results.md`; raw material stays outside Git.

- [x] Freeze 3 development papers / 9 authored source-specific claims and 2 validation papers / 6 claims, if source quality supports this scope. Preserve original PDFs, canonical local text, provenance, hashes, independent gold and ambiguity notes.
- [x] Use the existing isolated Codex CLI adapter with an explicit model and one shared initial abstract judgment. For unresolved cases execute the actual MCP query and rejudge; compare with the same client seeing the full local paper under a two-call budget. Abstract-only is a diagnostic baseline, not a fair full-workflow competitor.
- [x] Freeze protocol/prompts/code before model judgments and read the corresponding gold only after results are saved. Keep all failures and NEI in denominators. No model answer repair/retry, no claim of human gold or natural benchmark.
- [x] Report correct concrete judgments, false conclusions, remaining gaps, quote/source validity, costs and paired differences. Separate abstract and full-text reference judgments. Do not infer gains merely from changing NEI to a definite label.

## Task 6 — Review, release and learning records

- [x] Independent specification and code-quality review; fix actionable findings.
- [x] Full test suite once integration is stable, actual offline MCP entrypoint, original-checkout verification and wheel build.
- [x] Chinese reading guide, runnable example, honest result report and updated README/CONTEXT.
- [x] Focused Felix-authored commits on `local-evidence-followup`, normal fast-forward/push of original master as previously authorized.
- [x] Research worklog and finding; preserve unrelated modifications already present in the research workspace.

## Execution

Interpreter: `D:/Anaconda/envs/pytorch/python.exe`. Existing dependency overlay: `D:/Internship/Academic code/audit_guardrail_20261019/deps`. Work checkout: `D:/Internship/Academic code/guardrail_local_followup`. Evidence root: `D:/Internship/Academic code/audit_guardrail_20261110_local_followup`.

Tests use explicit writable TEMP/TMP, `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `-p pytest_asyncio.plugin`. Example focused command: `python -m pytest tests/test_local_followup.py tests/test_local_evidence.py tests/test_followup_report.py -q -p pytest_asyncio.plugin`. Baseline is `5acfd012b64189278d442f428dcd8ed8433c64d3`; historical 376-test pass and paired results are not fresh validation for this change.

## Completion evidence

Core and evaluation runtime froze at `7108a4be`. The complete suite passed 500 tests in the work checkout and 500 again in the original project; actual MCP transport and the wheel build passed. The completed 45-call comparison yielded ten correct concrete verdicts and five remaining NEI in each final path, with 28.08% fewer input tokens for local follow-up and no paired semantic gain. See `docs/local_followup_results.md` for the sample and scope limits.

The original master was fast-forwarded and normally pushed through results commit `57ae4a3`. The audit root retains both immutable runs, independent reviews, a fifteen-chain combined HTML report and final publication receipts. The research workspace records this session in `docs/worklogs/20261110_guardrail_local_followup.md` and finding F084 without staging unrelated research changes.
