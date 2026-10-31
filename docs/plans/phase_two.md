# Phase two: reference occurrences and traceable local evidence

> Execution: use the writing-plans / test-driven-development workflow, with a code review before delivery. The user authorized phase two on 2026-11-01. Continue from phase-one commit `5dae029` in an isolated local clone; preserve all earlier evidence.

**Goal:** Every recognized citation occurrence is audited, and every local evidence excerpt is attached to the matched paper and a recoverable position.

**Architecture:** Keep bibliography entries (`Citation`) separate from body occurrences (`ContextClaim`). A structured parse result carries both plus diagnostics. Read documents into text with page spans, retain offsets while masking code/math, and reuse each reference decision across its occurrences. Local identity selection precedes passage retrieval. The existing heuristic evaluator remains a review aid.

**Tech stack:** Existing Python 3.10+ dependencies only: Pydantic, pypdf, python-docx, pytest. No new runtime package or online model run.

## Contracts and choices

- One bibliography key owns one `Citation`; repeated markers own separate occurrence IDs and exact marker offsets. A grouped marker yields one occurrence per referenced key. Duplicate keys and missing references produce explicit diagnostics and cannot be queried as invented titles.
- Uncited bibliography entries receive metadata checks with `claim=None`. A BibTeX file is a bibliography, not a set of manufactured body claims.
- Count recognized reference entries, body-to-reference occurrences, and result rows separately. Keep `total_citations` as the legacy result-row count and explain the definition.
- Supported minimum: numbered references (including wrapped entries), direct DOI, literal BibTeX fields with balanced braces/quotes, common LaTeX cite commands and bibitem / relative bibliography files. Unsupported macros/includes and unreadable or partially extracted content are surfaced. Do not claim arbitrary TeX or layout/OCR support.
- Page numbers are metadata, not injected strings. Character offsets use the extracted text (PDF pages joined by two newlines), not PDF bytes; DOCX line positions refer to extracted paragraph/table order.
- Local DOI conflicts always reject a candidate. A DOI appearing in the reference list is never the local paper's identity. Ambiguous files do not supply claim text. When online metadata identifies a paper, use that identity for local matching.
- Local evidence is searched across paragraph chunks of the body, with no fabricated abstract and no reference-list evidence. Selected excerpts preserve file, page if available, and offsets. Matching metadata, unavailable providers, ambiguous local files, missing text, and low retrieval relevance stay distinct.
- Offline invariants from phase one remain in force. Retrieval scores do not establish support, causation, or semantic correctness; improvements to those rules belong to phase three.

## File responsibilities

| File | Responsibility |
| --- | --- |
| `core/models.py` | Locations, parse diagnostics, occurrences, retrieval fields and counts |
| `core/text_extraction.py`, `core/pdf_extractor.py` | Ordered extracted text and page spans; extraction warnings |
| `core/bibliography.py`, `core/identifiers.py` | Small literal BibTeX reader and shared DOI cleanup |
| `core/parser.py` | Bibliography identity, body markers, source positions and compatibility pairs |
| `core/ref_store.py`, `core/passages.py` | Local identity and traceable paragraph retrieval |
| `core/service.py` | One metadata lookup per entry, independent occurrence results |
| `core/result_formatter.py`, `core/reporter.py`, CLI/MCP | Consistent counts, locations, diagnostics and evidence states |

## Tasks

- [x] Baseline: run the existing suite with external HTTP and model loading disabled; preserve JUnit evidence.
- [x] Parser red tests: repeated/opposed claims, grouped ranges, uncited entries, missing/duplicate keys, DOI parentheses, wrapped references, nested BibTeX, TeX linkage and unknown URLs. Implement only after observing those failures.
- [x] Extraction red tests: real multi-page PDF title/page offsets, DOCX table order, blank/unreadable pages. Implement shared structured extraction.
- [x] Evidence red tests: conflicting DOI, DOI only in references, local ambiguity, late-page evidence, exact text/offset equality and absent abstract. Implement identity gates and chunk retrieval.
- [x] Service/entrypoint red tests: one lookup for repeated occurrences, independent results, distinct counts, warnings for unavailable content, and offline CLI/MCP document output. Preserve phase-one checks.
- [x] Update Chinese reading guidance, format support boundaries, examples and validation notes. Include a small deterministic multi-occurrence demo.
- [x] Run the complete suite, real MCP stdio smoke check and package build. Review the final diff; fix material findings, record evidence paths and focused commits.
- [x] Recheck the original repository for drift. Transfer only reviewed phase-two commits, validate the original checkout, record the research worklog and engineering findings. No remote push is requested.

## Acceptance evidence

Store raw validation output in `D:/Internship/Academic code/audit_guardrail_20261101/`. Record this session in `docs/worklogs/20261101_guardrail_phase_two.md` in the research workspace. Any finding appended to `docs/research_findings.md` must be labeled engineering/offline evidence, not a benchmark or LLM accuracy result.
