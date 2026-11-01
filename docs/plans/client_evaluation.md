# Expanded client evaluation and evidence-guided changes

Date: 2026-11-01. Baseline: `07772eaf3e7bfced58a4c8bf80b27629d140bf08`.

The owner asked which model generated the previous result and requested more samples and continued improvements. The previous judgments were made by the current Codex assistant from actual MCP outputs, not by a model inside this repository or an independently configured API. The underlying model ID/settings are unavailable. The one prior SUPPORT/NEI mismatch establishes disagreement with gold, not a diagnosed cause such as model conservatism.

## Frozen experiment design

1. Prepare 60 new public SciFact train pairs: 36 discovery (12 per class), 24 later validation (8 per class). Label-stratified sampling explicitly uses gold only in preparation; client input remains label-free. Use fixed `client-evaluation-v1` seeds and preserve the archive checksum. Exclude all claims and documents from the prior 12 cases; use at most one pair per claim/document, including across partitions. No resampling after seeing outcomes.
2. Record the client as this interactive Codex conversation, exact model unknown; no separate model API, new dependency or invented cost/settings. Save raw MCP evidence and structured client decisions before opening each partition's labels. Helper scripts may serialize hand-authored decisions and copy chosen evidence strings, not infer labels.
3. Run discovery against the existing prompt, retain every wrong/uncertain/error case, inspect actionable failure mechanisms, and implement justified project changes with focused regression tests. Do not change gold or rewrite the original decisions to improve scores.
4. Freeze the changed workflow and then read/judge the separate validation input. Score only after saving predictions. Do not compare different partition percentages as a causal gain, and do not count NEI as claim verification. This is an expanded interactive diagnostic, not independent-model accuracy, a bare-model ablation, or training of Codex.
5. Record class-wise counts, false support/refutation, insufficient evidence, runtime errors and client identity. Review data/protocol/code independently, test actual MCP transport and original-path packaging, preserve raw evidence, normally push master with Felix attribution, and append the research worklog/findings.

Evidence root: `D:/Internship/Academic code/audit_guardrail_20261101_client_evaluation/`.

## Acceptance and readable implementation

- Separate sampling, client manifest, scoring and evidence validation responsibilities; no opaque inference backend.
- Exact source quotes and evidence links remain distinct from semantic correctness.
- Any prompt improvement derived from discovery must be documented as a hypothesis until independently tested.
- Correct ambiguous wording in the earlier result report without replacing historical data.
- Tests and scripted tool judgments are engineering checks. Only actual assistant-produced judgments count as the interactive pilot.

## Outcome

All 60 new cases were judged and saved before opening each partition's labels. Discovery agreement was 30/36, subsequent validation 18/24; these are different samples, so there is no established causal improvement. Implemented comparison-boundary preservation, clearer comparative reasoning instructions, optional source-linked revision suggestions, client identity records and per-class metrics. The validation group produced 11 suggestions, separate from original-claim correctness. All 349 tests passed. Preserve all errors and annotation/text tensions; see `../client_evaluation_results.md`.
