# Phase One: Evidence and Offline Boundaries

Approved scope: the user's request of 2026-10-20, implementing the first phase of the audit. Preserve readability for a first-project owner. No new framework or dependency is needed.

## Design

Keep the existing parser/provider/service/CLI/MCP split. Providers collect facts and source records; a small pure decision function decides reference status. The service adds optional claim alignment. CLI and MCP render the service result rather than reinterpret provider dictionaries. Matching a paper does not establish that a manuscript claim is correct.

Retraction evidence has four states: confirmed, suspected, no record found, and not checked. Confirmed positive evidence only applies after paper identity is resolved. Title keywords are weak signals. Evidence records retain source, identifier, kind, and description. Candidate merging preserves all same-DOI retraction evidence.

Offline is explicit (`--offline` / `offline=True`). It skips online provider initialization and calls, checks the configured local retraction database, and uses local reference files when identity is reliable. Semantic model download/loading is disabled in this mode. HTML uses inline CSS/JS only, with no remote resources.

## Implementation checklist

- [x] Write failing tests for conflicting/ambiguous retraction evidence, provider failures, identity mismatches and source preservation.
- [x] Fix provider collection, DOI candidate merge and weak-signal handling; preserve public provider mapping API.
- [x] Add source/retraction models and one pure reference-decision function; test every decision branch.
- [x] Use that function from AuditService, CLI and MCP; retain useful errors and source identifiers.
- [x] Add offline tests that fail on HTTP/model initialization, then implement an offline service path and entrypoint options.
- [x] Replace CDN-dependent reporting with a small self-contained report, preserving escaping, filters and readable evidence.
- [x] Test local match ambiguity and remove fulltext substring identity fallback.
- [x] Run old and new tests, build the wheel, inspect generated HTML structure and script behavior, review the patch (browser visual check blocked by file URL policy).
- [x] Write a Chinese reading guide with module responsibilities, decision table, worked examples, test commands and remaining limitations.
- [x] Verify the original checkout has not changed since baseline, then copy only reviewed changed files back; retain untracked scratch files.

## Verification

Use `D:\Anaconda\envs\pytorch\python.exe`; existing audit dependencies are available in `D:\Internship\Academic code\audit_guardrail_20261019\deps`. Tests must not call real providers or download models. Add tests first, record expected failures, then implement and rerun. All changes stay uncommitted for the user to inspect. Parsing completeness, semantic inference quality and historical benchmark reconstruction remain later phases.

## Handoff

Implementation and validation details: `docs/phase_one_validation.md`. Browser visual QA remains unverified; this is not a blocker for the offline data-flow fixes. Source changes are copied selectively to the original checkout after hash verification and remain uncommitted.
