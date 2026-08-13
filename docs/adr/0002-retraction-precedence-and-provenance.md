# ADR 0002: Evidence Provenance Precedence Rule for Retraction Interception

## Status
Accepted

## Context
Academic retraction notices suffer from index latency across public bibliographic providers (e.g. Crossref, OpenAlex). An API returning `is_retracted=False` only proves that the provider has not yet indexed a retraction, not that the paper is active. Conversely, weak heuristic signals (such as title keywords like "retraction") can yield false positives.

## Decision
We enforce a **Safety-First One-Vote Veto Precedence Rule** based on **Evidence Provenance**:
1. **High-Trust One-Vote Veto**: If any high-trust source (Offline Retraction DB or official API metadata `is_retracted=True`) flags a paper, the verdict is immediately `RETRACTED` (`DANGER`). Negative flags from other providers cannot override high-trust positive retraction evidence.
2. **Weak Signal Demotion**: Title keyword matches without official API flags yield `RETRACTION_SUSPECTED` (`WARNING`), forcing manual review rather than hard `RETRACTED`.
3. **Absence of Proof Semantics**: When all queried providers report no retraction, the system records `NO_RETRACTION_FOUND` in metadata rather than asserting an absolute `NOT_RETRACTED`.

## Consequences
- Completely eliminates false-negative pass-through of known retracted literature caused by API indexing delays.
- Prevents false-positive hard retractions triggered by title keywords alone.
