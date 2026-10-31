# Academic Guardrail Agent

English | [中文](README_CN.md)

A Python CLI and MCP server for reviewing academic citations. It retrieves reference metadata, preserves retraction evidence, and provides heuristic comparisons between manuscript claims and available reference text. It is a learning and engineering project, not an automated scientific truth judge.

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
| `verification_scope` | `REFERENCE_METADATA` or `HEURISTIC_ALIGNMENT` |

Identity is resolved before retraction facts are assigned to a citation. An ambiguous candidate does not establish that the cited paper is retracted. Title keywords are only suspected signals. Explicit retraction evidence for the same DOI is retained when merging providers.

`PASS` means the current check did not trigger a risk; it does not establish scientific correctness. `NO_RECORD` is limited to consulted sources, never an assertion of normal status. Failures are kept distinct from empty results. Local matching uses extracted metadata; a title appearing in another paper's bibliography is not identity evidence.

## MCP

Configure an MCP client to launch the installed executable:

```json
{"mcpServers": {"academic-guardrail": {"command": "academic-guardrail-mcp"}}}
```

Tools: `verify_single_citation`, `check_paper_retraction`, `audit_document_claims`, `generate_audit_html_report`. All accept `offline: true`. Citation verification and document audit support `detail: compact | detailed | debug`. Other network tools used by the host agent remain outside this server's control.

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

Historical scripts and data remain in `benchmarks/` for later reconstruction. Historical accuracy, latency and small-fixture metrics are not presented as verified capabilities of this version; evaluator compatibility, sampling and original model traces still need independent review.

## Limitations

Parsing covers common numbered references, repeated/grouped citations, literal BibTeX fields and common LaTeX citation commands. It does not expand arbitrary TeX macros, cover every author-year style or perform OCR. DOCX extraction covers body paragraphs and tables; complex PDF layout and cross-page sentence order remain limited. Local metadata extraction is heuristic. Matching scores are not calibrated probabilities. Lexical/embedding similarity does not reliably handle numerical, causal or scope differences. Online and local retraction coverage may be incomplete or stale. Human review remains necessary.
