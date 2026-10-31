# Phase-two validation record

Date: 2026-11-01. Baseline: `5dae029b85a9135b7f96955cf6d7503cdfbca9c9` (phase one). Work was implemented in an isolated development branch, now named `phase-two`. The original phase-one audit snapshot and remediation clone were preserved.

## Evidence scope

This is offline engineering validation with synthetic text, generated text-layer PDFs, generated Word tables and mocked provider responses. No live scholarly API or model call was made. No accuracy or benchmark improvement is claimed. The heuristic semantic engine is unchanged.

## Executed checks

| Check | Observed result |
| --- | --- |
| Original phase-one suite before implementation | 127 passed in 18.72 s |
| Completed phase-two suite in isolated clone | 172 passed in 23.32 s |
| Full suite from the user's original project path | 172 passed in 22.81 s |
| Actual MCP stdio initialize / list / call | All four tools listed and called successfully |
| Synthetic document through service and MCP | 1 reference entry, 3 body occurrences, 3 result rows; unresolved `[2]` remains explicit |
| Offline boundary guards | 0 provider constructions, external HTTP send attempts or model-initialization attempts |
| Local excerpt positions | Exact substring round-trip passed; unit tests also cover physical PDF page 3 |
| Saved HTML | Imported content escaped; no active external assets; inline filtering retained |
| Distribution wheel | Built successfully with existing dependencies, version unchanged at 0.1.0 |
| Git diff whitespace | `git diff --check` passed |

Tests were run with `D:/Anaconda/envs/pytorch/python.exe`, the existing isolated dependency directory `D:/Internship/Academic code/audit_guardrail_20261019/deps`, `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and the explicit pytest-asyncio plugin. Windows asyncio needed the environment's local-socket permission; external HTTP remained blocked by the test fixture.

The first baseline invocation failed at fixture setup because its temporary parent directory did not yet exist (127 setup errors); it did not execute product tests. That record is retained separately from the successful baseline retry. Later red-test artifacts are expected failing regression demonstrations, not passing validation evidence.

## Regression coverage

- Repeated/opposed claims, same-line and wrapped sentences, post-sentence citation attachment, grouped/range markers, missing/duplicate keys and collision-free generated DOI IDs.
- Wrapped numbered references, balanced DOI parentheses, literal/nested BibTeX, grouped organization authors, LaTeX bibitem and local bibliography linkage, unsupported macros and unknown URL rejection.
- Word paragraph/table order; real multi-page PDF extraction with blank pages; unreadable local-file diagnostics.
- DOI conflicts, multiple local DOI candidates, conflicting DOI across blank lines, unheaded bibliography DOI leakage, ambiguous local files and known-DOI abstention when local identity is absent.
- Full-body retrieval despite available abstracts, no fabricated abstract, exact excerpt locations, online/offline newly discovered DOI retraction rechecks and retained upstream failures.
- Per-entry query reuse, independent per-occurrence results, separate counts, escaped parsing diagnostics and matching CLI/MCP/HTML/Markdown presentation.

A dedicated read-only review supplied additional counterexamples. Each material finding was reproduced before fixing it. The reviewer inspected the final DOI correction and reported no remaining finding from that issue. The primary agent independently ran the full suite and actual transport check.

## Saved local evidence

Evidence root: `D:/Internship/Academic code/audit_guardrail_20261101/`.

- `baseline.xml`: initial setup failure; `baseline_verified.xml`: successful baseline.
- `parser_red.xml`, `extraction_red.xml`, `chain_red.xml`, `review_red.xml`, `entrypoints_red.xml`, `evidence_review_red.xml`: retained failing regression demonstrations.
- `phase_two_tests.xml`: full clone test results.
- `phase_two_original_tests.xml`: full suite from `D:/Github_Project/Academic_Guardrail_Agent`.
- `smoke_clone/validation.json`, `mcp_transcript.json`, `mcp_boundary_attempts.json`, `report.json`, `report.html`, `report.md`: successful service/transport output and guarded boundary counts.
- `smoke_original/`: the same successful check executed from the original project, including all four MCP tool calls and guarded boundary counts.
- `wheels/mcp_academic_guardrail-0.1.0-py3-none-any.whl`: built distribution.

Reproduce the transport check with `python scripts/validate_phase_two.py --output-dir <new-directory>`. It refuses to overwrite an existing run directory. Browser visual rendering was not performed in this phase; HTML checks cover structure, escaping, resources and content, not screenshot-level layout acceptance.

## Integration checkpoint

Implementation commit: `a1077577855937693114f5704c58ecaa843bb5f4`. Before transfer, the original repository was verified clean at `5dae029`. The reviewed branch was transferred from the local clone and validated from the original project path. The owner subsequently requested publication through the existing `master` branch. Git author and committer attribution remain Felix; branch names do not define authorship. The research workspace worklogs record the validation and publication checkpoints separately.

## Remaining limits

Extraction is a documented format subset, not an arbitrary PDF/Word/TeX interpreter. Title-only identity and sentence boundaries remain heuristic when no strong identifier is supplied. Retrieval relevance and the unchanged alignment labels do not establish factual entailment. Online coverage and failure behavior have not been remeasured against live providers. Benchmark reconstruction belongs to a later phase.
