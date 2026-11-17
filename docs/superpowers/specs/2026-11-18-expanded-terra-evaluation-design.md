# Expanded terra/max evaluation design

User authorization: 2026-11-18, 90 cases (chosen over 60), requested gpt-6.1-terra with max reasoning. Normal master push remains authorized. This document makes the agreed scope concrete; no model calls until the inputs, reference labels, prompts, runtime and budget are frozen.

## Question and controls

Does one source-bound local lookup help refutation recall, reduce unresolved cases, or reduce token use versus directly reading the same parser-visible paper text?

- Shared abstract-only judgment: one fresh context, diagnostic starting point.
- Primary control, fulltext_single: one fresh-context judgment over complete parser-visible text, no prior judgment. One effective call.
- Secondary control, fulltext_direct: shared abstract result plus one fresh-context judgment over that text. Two effective calls.
- Local workflow: shared result; only a valid unresolved record with a specific gap may retrieve once and receive one fresh judgment. At most two effective calls.
- Identical client model, max reasoning, semantic instructions, output contract and validation. No heuristic hints to any arm. All client contexts distinct and tool-free.
- Protocol v3 gives every arm the same `source_identity` with only title and DOI from the pinned local source context. This metadata identifies the supplied paper; it is not proof of the claim, methods or results. No additional source status, confidence, rule hints or text is exposed.
- The four-arm structure uses at most 4N calls, but the study-wide hard cap is 360 actual calls including the eight calls in the aborted initial round described below. Thus at most 352 additional v3 calls are available. No harness retries or response repair. Actual combined costs count shared initial calls once; each two-stage workflow's costs include them. Single-call control never inherits that charge.
- Freeze all batches before any formal judgment. Stop on unverifiable isolation, repeated thread ID, or a failed entire concurrent call group; preserve every attempt.

## Materials and interpretation

Fifteen additional versioned, publicly readable ML papers, six authored/perturbed claims per paper. Target per paper: two supports, three contradictions, one insufficient-evidence case; 30 SUPPORT / 45 CONTRADICT / 15 NEI total. At least one support and one contradiction should be answerable from the abstract. Include numeric, negation, scope and causal overstatement checks where the text warrants them.

Thirty development cases from five papers; sixty validation cases from ten other papers, split into two 30-case execution batches. All v3 prompts/retrieval code are frozen together; no further tuning on outputs after that freeze. The disclosed source-identity correction below followed exposure to two development cases, so those cases are not unseen. No validation outputs were inspected. Sources do not overlap the prior five-paper study. This does not prove lack of pretraining exposure. These are source-grounded authored tasks, not human expert gold or natural request prevalence.

Save original PDF and landing-page hashes, exact extracted text, canonical prefix mapping, page/character evidence anchors, label rationale, missing-evidence rationale and parser coverage. Do not infer that parser-visible text includes post-reference appendices. Raw papers and runs stay local.

## Metrics

Report each arm's CONTRADICT precision/recall with denominators and descriptive Wilson intervals; all-case NEI/UNCERTAIN/error fractions; avoidable NEI on gold-decidable cases; false concrete judgments; paired case wins/losses and the exact changed cases. Compute paper-level summaries because cases within a paper are dependent.

Report input, cached-input, uncached-input when fully known, output and reasoning tokens separately, and effective calls. Missing usage stays unknown. Do not sum reasoning twice into output or translate tokens to unmeasured money/human time. Single versus local is primary; two-stage full text versus local is diagnostic.

## Engineering boundaries

Keep retrieval and judgment rules unchanged for this evaluation. A pre-freeze material check found that the abstract parser truncated five of the fifteen PDFs at ordinary wrapped lines beginning with `results`, `methods`, or `introduction`. Fix this shared input bug before freezing: a complete heading line may end an abstract, a sentence continuation may not. Eight focused examples reproduced the truncation before the fix and pass afterward. All arms use the same corrected parser; this is not a result-driven intervention.

Centralize the requested model in the optional evaluation adapter and render client_model from that same setting. Version the four-arm protocol. Preserve old runs/checkouts. Update frozen budgets, scoring integrity checks, tests, Chinese reproduction instructions and actual result documentation. No new package is expected.

## Disclosed v3 amendment after the aborted initial round

The first two development cases in the initial formal round incurred eight calls. The first response exposed an input defect: the local prompt's evidence projection omitted the matched paper title and DOI, while the RoBERTa abstract did not itself name RoBERTa. This led to an entity-mapping gap despite the relevant undertraining text. The second case was already in flight; the runtime source-change check stopped the run before the next case. This was an aborted initial formal round, not a preplanned pilot.

Preserve the original frozen round, all eight raw receipts and all measured usage. Exclude that round from v3 semantic comparisons while including its calls and tokens in total study costs. Keep all 90 claims, reference-label hashes, source corpus and retrieval rules unchanged. The only new prompt data are the same pinned title/DOI for all four prompt forms, with an explicit identification-only instruction. The strict scorer reconstructs and checks that identity from the stored source context. Generic historical paired-comparison prompts remain unchanged.

Freeze all three new v3 plans after the fix and independent review. The study controller starts with the eight prior calls and their thread IDs, reserves each batch's worst-case allowance only when the remaining global budget covers it, and stops with incomplete evidence if needed. Neither the aborted costs nor missing cases may be hidden to claim a complete 90-case result within budget.
