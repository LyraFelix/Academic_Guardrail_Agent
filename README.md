# Academic Guardrail Agent

English | [中文](README_CN.md)

A Python CLI and MCP server for reviewing academic citations. It retrieves reference metadata, preserves retraction evidence and gives an existing client model source-linked evidence for claim review. The client judges meaning; the server checks exact quotes and saves the judgment with its evidence snapshot. Local rules remain review hints rather than a scientific truth judge.

## Install from source

Python 3.10+ is required. In a dedicated environment, from this repository:

```bash
python -m pip install -e ".[dev]"
academic-guardrail verify "10.1038/nature12968" --offline
academic-guardrail audit docs/examples/sample_manuscript.md --offline -o report.html
```

The distribution name is `mcp-academic-guardrail`; the executable is `academic-guardrail`. Source installation does not assume a public PyPI release.

## Online and offline operation

Default operation queries OpenAlex, Crossref and/or Semantic Scholar. Supplying `--refs-dir` adds local references but does not disable online queries.

```bash
academic-guardrail audit manuscript.docx --refs-dir references -o report.html
academic-guardrail audit manuscript.docx --refs-dir references --offline -o report.html
academic-guardrail verify "Attention Is All You Need" --detail detailed
```

`--offline` skips online provider construction and embedding model initialization/download. It consults the local retraction database and supplied reference files only. HTML reports use inline CSS/JavaScript and system fonts; opening/filtering them requires no CDN. Following a DOI link still opens an external website.

The bundled retraction database contains **three historical examples**, not the full Retraction Watch database. `RETRACTION_DB_PATH` may point to a local SQLite database with the same schema. No complete database download/synchronization is implemented. An unknown DOI remains unverified offline.

Optional `python -m pip install -e ".[full]"` enables sentence-transformers. In online mode, first use may download a model. Otherwise lexical rules are used. Both approaches provide review hints rather than entailment proofs.

## Result contract

| Field | Meaning |
| --- | --- |
| `status` | Reference/claim outcome: valid, unverified, retracted or mismatch |
| `risk_level` | Alert level within the check's scope |
| `evidence_status` | Online/local match, ambiguity, unavailable provider or other acquisition state |
| `retraction_status` | `CONFIRMED`, `SUSPECTED`, `NO_RECORD`, `NOT_CHECKED` |
| `sources` | Source, kind, identifier, description and source retraction flag |
| `verification_scope` | `REFERENCE_METADATA`, `TEXT_RETRIEVAL` or `RULE_BASED_REVIEW` |
| `alignment_state` | `TEXT_ALIGNED`, `POTENTIAL_CONFLICT`, `REVIEW_REQUIRED`, `INSUFFICIENT_EVIDENCE` |
| `semantic_findings` | Rule code, explanation, exact claim/evidence text, source and available coordinates |
| `claim_alignment_score` | Retrieval similarity, never a truth probability |

Identity is resolved before retraction facts are assigned to a citation. An ambiguous candidate does not establish that the cited paper is retracted. Title keywords are only suspected signals. Explicit retraction evidence for the same DOI is retained when merging providers.

`PASS` is limited to metadata checks. Claim checks receive at least `NOTICE`, including `TEXT_ALIGNED`; wording agreement does not establish scientific correctness. `NO_RECORD` is limited to consulted sources, never an assertion of normal status. Failures are kept distinct from empty results. Local matching uses extracted metadata; a title appearing in another paper's bibliography is not identity evidence.

## MCP

This project runs **one MCP server**, exposing ten tools and one workflow prompt. The tools are operations on that server, not separate MCP servers.

| Tool | Purpose |
| --- | --- |
| `verify_single_citation` | Check one reference's identity, metadata and retraction evidence |
| `check_paper_retraction` | Query retraction evidence by DOI, reusing single-reference verification |
| `audit_document_claims` | Audit a document, return findings and save an HTML report |
| `generate_audit_html_report` | A convenience entry point whose main output is the HTML report |
| `prepare_claim_review` | Resolve a reference or accept supplied text; save an evidence packet for the client |
| `read_claim_evidence` | Read remaining evidence pages from the same saved snapshot |
| `record_claim_review` | Check snapshot digest, evidence IDs and exact quotes; save the client's judgment |
| `prepare_local_claim_review` | Match one local paper and freeze its real abstract or full text |
| `follow_up_local_claim` | Search that same paper once for a gap recorded by the client; preserve earlier evidence |
| `generate_claim_review_report` | Export selected saved judgments and their before/after evidence to HTML |

Configure an MCP client to launch the installed executable:

```json
{"mcpServers": {"academic-guardrail": {"command": "academic-guardrail-mcp"}}}
```

The four original tools and `prepare_claim_review` accept `offline: true`. Reading and recording packets are always local. Citation verification and document audit support `detail: compact | detailed | debug`. The client's model/network configuration remains outside this server's control; server offline mode does not make a cloud model local.

Use the `review_claim_workflow` prompt or ask the client to prepare evidence, read every page, compare subject/relation/numbers/scope/counterevidence, and record its conclusion. Pass the returned `packet_sha256` as `expected_packet_sha256` when recording. A local `REVIEW_REQUIRED` result is a hint for the client to continue, not a final handoff to the user. See the [client workflow and code guide](docs/client_review_guide.md).

For a local paper, the client can now record a specific missing fact, request one bounded literal search of the same source, and judge the extended evidence again. The HTML report preserves both judgments and shows the query, quotes, source locations and file status. Changed sources block new judgments; unresolved gaps remain visible. These three new tools are local and make no model API calls. See the [local follow-up guide](docs/local_followup_guide.md) for a runnable example and code reading order.

Client conclusions are `SUPPORTED`, `CONTRADICTED`, `NOT_ENOUGH_EVIDENCE` or `UNCERTAIN`. `EVIDENCE_LINKS_VALID` only certifies mechanical quote/ID consistency; `semantic_judgment_verified` remains false. The existing CLI/HTML report contains local-rule results; client judgments are separate JSON records and the host client's response.

## Read and test

See the [Chinese code reading guide](docs/learning_guide.md) and [phase-one design](docs/plans/phase_one.md).

The [phase-two guide](docs/phase_two_guide.md) explains separate bibliography entries and body occurrences, source coordinates, and format boundaries. Repeated citations share one metadata lookup but retain separate results. Reports distinguish reference counts, occurrence counts (one per cited key), result rows, parsing diagnostics and text retrieval status.

```bash
academic-guardrail audit docs/examples/phase_two_manuscript.md --refs-dir docs/examples/phase_two_refs --offline -o phase_two_report.html
```

This synthetic fixture has one bibliography entry and three occurrences, including an unresolved `[2]`. Local evidence is retrieved from body passages with file/page/character positions. Abstract and full-text sources remain explicit.

```bash
python -m pytest tests -q
```

Tests isolate caches, block real HTTP and disable embedding models. They validate software behavior, not live provider availability or LLM benchmark accuracy.

Phase four provides a [reproducible evaluation workflow](benchmarks/README.md) and [Chinese evaluation guide](docs/phase_four_guide.md). Inputs, gold labels and predictions are separate; runs record data/code hashes and support scoring replay. All cited SciFact pairs are retained for native-state, conflict-alert and excerpt diagnostics. Development regressions are reported separately. Original scripts are archived under `benchmarks/legacy/`; historical LLM accuracy remains unverified.

The [semantic coverage follow-up](docs/semantic_coverage_results.md) reports the unresolved rule-only result and a small actual client/MCP pilot separately. Neither insufficient evidence nor a valid quote is counted as successful support/refutation. The pilot is not a general accuracy claim or a comparison against a bare model.

The [expanded client evaluation](docs/client_evaluation_results.md) adds 60 public-train cases in separate discovery/validation partitions and explicitly records the interactive Codex client. It reports remaining errors rather than claiming a verified accuracy gain. Optional source-linked revision suggestions help draft narrower statements without changing the original claim's verdict.

The latest [same-evidence comparison](docs/paired_review_results.md) uses 30 new cases and 90 independent Codex CLI judgments, requesting `gpt-6.1-sol` with high reasoning. Direct / guided direct / MCP agree with the official labels on 22/30, 21/30 and 21/30 cases; contradiction recall is 9/10, 8/10 and 8/10. This small experiment does **not** demonstrate a semantic gain from MCP. The [reading and reproduction guide](docs/paired_review_guide.md) explains optional claim-part findings, the three controls and preserved raw evidence. The subsequent v2 protocol clarifies a common storage contract; its model performance is unmeasured.

The [phase-three guide](docs/phase_three_guide.md) explains the separate numeric, negation, causal and scope rules. Each finding retains its triggering evidence. Run the synthetic four-category example or replay the real offline CLI/MCP interfaces:

```bash
academic-guardrail audit docs/examples/phase_three_manuscript.md --refs-dir docs/examples/phase_three_refs --offline -o phase_three_report.html
python scripts/validate_phase_three.py --output-dir phase_three_validation
```

The old five-element `evaluate_alignment()` tuple remains callable, but its state labels now use the review vocabulary above. New Python callers should use `assess()` or `assess_passages()` and named fields. Historical benchmark label mappings require migration before use.

## Limitations

Parsing covers common numbered references, repeated/grouped citations, literal BibTeX fields and common LaTeX citation commands. It does not expand arbitrary TeX macros, cover every author-year style or perform OCR. DOCX extraction covers body paragraphs and tables; complex PDF layout and cross-page sentence order remain limited. Local metadata extraction is heuristic. Matching scores are not calibrated probabilities. Bounded wording checks flag explicit quantities, negation and qualifiers; complex semantics need the client model's analysis, which can still be wrong. Missing sources and unresolved ambiguity need additional evidence or human input. Online and local retraction coverage may be incomplete or stale. No scientific truth or benchmark accuracy claim follows from the regression tests.
