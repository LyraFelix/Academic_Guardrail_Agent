# Contradiction review and same-evidence comparison

Date: 2026-11-01. Base: `6f6cb0a`. User authorizes implementation and a direct-model control.

## Question and design

Can a clearer contradiction review improve recall without turning missing evidence
into refutation, and what does the MCP workflow add beyond the same model/prompt?

The previous 24 cases are development evidence now. Their labels and predictions
remain unchanged. Four missed CONTRADICT labels have endpoint, treatment/prediction,
or missing-result problems; a higher benchmark recall must not be manufactured by
calling every missing result a contradiction.

Add optional, quoted findings for necessary parts of a claim. Check that the
declared findings and overall conclusion agree; this checks consistency, not the
truth of those findings. Improve the semantic instructions to distinguish explicit
opposition from absence and to recognize that one necessary clause can be refuted
even if other details are unreported. Preserve legacy submissions without findings.

## Frozen comparison protocol

- Select 30 new official SciFact public-train pairs: 10 SUPPORT, 10 CONTRADICT,
  10 NEI. Exclude claim/document IDs from the prior 12 + 36 + 24. Use the existing
  deterministic selector with partition name `contradiction_comparison_v1` and
  archive checksum. Record label-stratified sampling explicitly. No claim of
  semantic independence or absence of model pretraining exposure.
- Three arms: `direct` (short complete task definition), `guided_direct` (same
  semantic instructions as MCP), `mcp` (guided instructions plus packet hints,
  followed by actual MCP record validation). All arms receive identical full
  evidence texts, IDs, ordering, claim and output schema. Baselines also get
  numbered evidence; segmentation is held constant, not evaluated as an advantage.
- Use installed Codex CLI, logged-in ChatGPT, pinned requested model
  `gpt-6.1-sol`, reasoning `high`, fresh ephemeral context for each case/arm.
  Request disabling memory, skills, plugins, tools and web; use an empty temporary cwd.
  Local diagnostic probes show tool schemas and skill catalog metadata can remain
  in this CLI build. Treat this as a controlled Codex-client comparison with common
  base instructions, not a tool-free bare API. Abort/mark error on observed tool use.
  Memory/history result markers were absent from the diagnostic prompt; this probe
  is local debug output, not a captured backend request or complete isolation proof.
  No independent API key. CLI transport retries may be internal; one invocation
  does not prove one HTTP request. Record actual CLI version/config/events and any unknown
  backend snapshot/settings. Never substitute this long developer conversation.
- Synthetic feasibility gate first. Then 90 decisions, no harness retries,
  correction passes or post-score prompt edits. Fix balanced arm order before
  running. Timeouts/invalid outputs remain in the denominator. Abort on a systemic
  connectivity/isolation problem and preserve attempted work.
- MCP versus direct is primary (raw CONTRADICT recall/precision); guided-direct
  comparisons are descriptive attribution controls. All arms use structured
  output, not unstructured chat. Raw conclusions stay primary before rejection.
  Report accuracy, class precision/recall, paired wins/losses/ties and exploratory
  exact McNemar p-values, not confidence intervals for accuracy differences.
  Add descriptive Wilson recall intervals. Apply the identical post-hoc quote
  and finding checker to all arms; report accepted-output accuracy and
  coverage with rejection counts; rejection must never remove a raw semantic error.
- Record per-attempt elapsed time and reported input/cached/output tokens; missing
  usage stays unknown. Server preparation/recording overhead is separate. Do not
  infer dollar cost or human time saved from tokens. No causal claim from previous
  scores on different samples; guided-direct isolates prompt from packet hints.
- Bind input/gold, packet, prompt, schema, code and run outputs by hashes. Freeze
  the complete expected schedule before judging; open gold only for scoring after
  outputs are frozen. Preserve all attempts and source records locally.

## Implementation map and checks

1. Core review models/instructions/validator: small optional finding contract,
   quote linkage and conclusion-consistency tests; no model inside the server.
2. Comparison preparation: reproducible exclusions and shared evidence payloads.
3. Codex CLI adapter: restricted fresh context, raw events and failure recording.
4. Paired scoring: complete denominators, distinct raw/accepted semantics and
   model/scaffold attribution. Unit tests use hand-calculated paired outcomes.
5. Actual CLI/MCP gate, new comparison, independent audit, full suite, original
   checkout verification, Chinese guide/results and normal master push.

Model conclusions may be unchanged or worse. The result must still state what was
measured, what the workflow checks mechanically, and what remains unproven.

## Post-run contract clarification

The completed v1 run is preserved at code `adeaa9a`: 90 judgments are frozen before
gold. A post-run audit found that the short direct prompt did not explain every
custom cross-field storage rule, particularly quoted IDs for all findings. The
current v2 preparation puts the complete contract in common instructions/schema
for all arms. This is a future fairness/readability fix, not a new measured gain;
there are no v2 model results. Raw v1 scores and all rejected outputs remain intact.
