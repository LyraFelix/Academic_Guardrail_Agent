# Academic Guardrail Context

Academic Guardrail is a lightweight, zero-LLM infrastructure providing citation metadata validation, retraction alerts, candidate entity resolution, and sentence-level evidence context provisioning for AI coding agents.

## Domain Terms

### Citation & Claim

**Manuscript Claim (Claim)**:
A scientific assertion or factual statement extracted from a manuscript body text requiring verification against reference literature.
_Avoid_: Sentence, statement, assertion text

**Citation**:
A formal reference in manuscript text linked to a bibliographic entry or external paper (e.g. `[1]` or DOI).
_Avoid_: Reference link, bib entry

**Reference Paper**:
A target academic document (online via DOI/API or local PDF/DOCX) cited by a manuscript.
_Avoid_: Source paper, cited document

### Verification & Alignment

**Entity Resolution (Reference Resolution)**:
The multi-stage process of mapping a raw citation string/DOI to a canonical paper record across multiple providers.
_Avoid_: Paper searching, DOI lookup

**Claim Alignment (Evidence Provisioning)**:
The two-stage semantic evaluation comparing a Manuscript Claim against a Reference Paper's abstract or full-text.
_Avoid_: Fact checking, NLI scoring

**Fact Atom (Clause Evidence Candidate)**:
The minimal sub-clause unit containing a single isolated factual finding, carrying logical metadata (e.g. negation, scope). Evaluated during Top-K clause-level reranking to eliminate compound sentence polarity contamination.
_Avoid_: Substring slice, partial sentence

**Evidence Text**:
The exact extracted text snippet from a Reference Paper that confirms or contradicts a Manuscript Claim.
_Avoid_: Match text, excerpt snippet

**Evidence Granularity**:
The scope level of the extracted evidence text (`SENTENCE`, `CLAUSE`, `EXPANDED_WINDOW`).
_Avoid_: Text type, match level

**Progressive Disclosure Payload**:
The tiered MCP response contract governed by the `detail` parameter (`compact` | `detailed` | `debug`). Controls token budget efficiency by disclosing deeper score breakdowns and diagnostics only when explicitly requested.
_Avoid_: Output mode, verbose flag

**Verification Status**:
The qualitative resolution outcome for a citation (`VALID`, `CLAIM_MISMATCH`, `RETRACTED`, `UNVERIFIED`).
_Avoid_: Result code, state label

**Evidence Status (EvidenceStatus)**:
The fine-grained infrastructural or evidence acquisition state (`ARTICLE_MATCHED`, `JOURNAL_MATCHED_ARTICLE_UNVERIFIED`, `PROVIDER_UNAVAILABLE`, `NOT_FOUND`). Differentiates data-level non-existence from infrastructure-level query failures.
_Avoid_: Execution state, fetch result

**Risk Level**:
The operational alert severity assigned to a verification result (`PASS`, `NOTICE`, `WARNING`, `DANGER`).
_Avoid_: Severity, danger tier

**Retraction Interception**:
The evidence provenance-based detection of officially withdrawn or invalidated literature using a one-vote veto precedence rule.
_Avoid_: Invalid paper check, bad DOI alert

**Retraction Precedence Rule**:
The strict safety rule governing retraction conflicts: an explicit `true` from any high-trust source (Offline DB, API `is_retracted=True`) triggers a `RETRACTED` (`DANGER`) verdict regardless of negative flags from other providers. Weak signals (title keywords alone) trigger `RETRACTION_SUSPECTED` (`WARNING`).
_Avoid_: Retraction voting, consensus scoring

**Evidence Provenance**:
The verifiable origin and confidence tier of retrieved evidence (e.g. `HIGH_TRUST_DB`, `OFFICIAL_API_METADATA`, `WEAK_HEURISTIC_SIGNAL`).
_Avoid_: Source score, origin tag

### Execution Modes & Infrastructure

**Semantic Mode**:
The engine execution profile (`CORE` vs `FULL`). `CORE` runs pure CPU lexical/syntactic logic (<35MB footprint); `FULL` dynamically loads local Transformer embeddings via lazy thread-locked singletons.
_Avoid_: Execution tier, ML flag

**Core Fallback**:
The graceful degradation state where Full Mode vector loading fails or is unavailable, automatically falling back to Core Mode logic while annotating `semantic_mode: CORE_FALLBACK` in response metadata.
_Avoid_: Model failure, fallback error
