# ADR 0002: Retraction identity and source precedence

## Status

Accepted; implemented during phase-one remediation.

## Context

Sources can disagree or be incomplete. A title containing “retraction” may describe a study about retractions rather than a withdrawn article. A flag on an ambiguous candidate cannot establish that the input citation names a withdrawn paper.

## Decision

1. Resolve reference identity first. Ambiguous identity produces UNVERIFIED/WARNING, preserving candidate sources for review.
2. Merge observations for the same normalized DOI. Retain explicit positive retraction evidence even when another source reports false or has no record.
3. Treat title-only signals as SUSPECTED/WARNING, never confirmed withdrawal.
4. Distinguish CONFIRMED, SUSPECTED, NO_RECORD and NOT_CHECKED. Absence is limited to consulted sources.
5. Keep source, kind, identifier and detail in the final result. Expose retraction reasons in CLI, MCP, HTML and Markdown.

## Consequences

This prevents specific failure modes covered by regression tests. It does not guarantee complete or current coverage. API metadata may be incomplete, and the built-in local database contains only three historical examples. Identity scoring remains heuristic and can abstain. A user must inspect underlying sources before acting on an alert.
