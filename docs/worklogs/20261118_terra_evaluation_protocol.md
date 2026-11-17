# Terra max four-arm evaluation implementation

## Scope and evidence boundary

Implemented the approved optional evaluation protocol in the `expanded-terra-evaluation` checkout. This session did not inspect the real-source reference labels, invoke a model, edit evaluation materials, or modify server/core code. Synthetic fixture labels and deterministic model receipts were used only for protocol validation. No model-quality result follows from these tests.

The parent independently fixed the abstract heading parser in `7c9bc09`; the final focused checks below used that current checkout source. The starting implementation baseline was `ec4ce09`, after the MCP SDK migration `6514976`.

## Changes

- Centralized `gpt-6.1-terra` / `max` in the optional CLI adapter; shared output instructions use its model constant. Added `multi_agent_v2` to disabled CLI features.
- Versioned the protocol as `local_evidence_followup_v2`. Froze the new independent full-text prompt alongside the abstract prompt and two-stage template.
- Added `fulltext_single` as the primary control: no prior answer and one charged call. Preserved `fulltext_direct` as the secondary two-stage control and the existing local-follow-up eligibility/carry behavior.
- Run at most three final calls concurrently after the shared initial judgment, with results keyed by stage. The maximum actual budget is `4N`; failed responses and rejected records retain their raw outcomes and costs.
- Extended strict scoring to the new stage, prompt, packet, model/reasoning identity, outcome references and arm cost ledger. Primary and secondary paired comparisons are explicit.
- Added `scripts/summarize_local_followup_evaluation.py`: revalidates every completed run before any reference labels are read, rejects mixed configurations and overlapping cases or cross-partition papers/source bytes, then writes JSON and a compact case CSV. Attempt IDs are namespaced across batches before costing.
- Summaries include refutation precision/recall with counts, denominators and descriptive Wilson intervals; all-case NEI/UNCERTAIN/ERROR rates; avoidable NEI among concrete gold; false concrete counts; per-paper rows; separate actual, stage and arm costs. Unknown usage remains null. Uncached input is derived only from known input/cache pairs; reasoning output is never added to output again.
- Updated the Chinese evaluation guide. Historical result documents and frozen runs were left intact; replay requires the matching historical code checkout.

## Validation

Interpreter: `D:/Internship/Academic code/audit_guardrail_20261118_mcp_upgrade/venv/Scripts/python.exe`.

Final command, run from this checkout:

```powershell
$env:PYTHONPATH='D:\Internship\Academic code\guardrail_expanded_evaluation\src'
& 'D:\Internship\Academic code\audit_guardrail_20261118_mcp_upgrade\venv\Scripts\python.exe' -m pytest tests/test_local_followup_summary.py tests/test_local_followup_evaluation.py tests/test_client_comparison.py -q -o asyncio_default_fixture_loop_scope=function --basetemp 'D:\Internship\Academic code\audit_guardrail_20261118_terra_max_evaluation\implementation\final_focused_temp'
```

Result: **53 passed in 90.14 seconds**, exit code 0. Windows asyncio required an approved execution outside the filesystem sandbox to initialize its local event-loop socket pair. The model adapter and transport remained synthetic; no model or external network service was invoked.

Additional checks: summary CLI `--help` succeeded, `git diff --check` passed, and the diff was self-reviewed. Meaningful assertions cover 4/3-call budgets, three concurrent final judgments, no-prior full-text input, each arm's cost identity, raw failure denominators, failed lookup carry, tampered/missing cases and prompts, model/reasoning mismatch, mixed batches, case overlap, paper/source partition leakage, and partially unknown usage.

Evidence directory: `D:/Internship/Academic code/audit_guardrail_20261118_terra_max_evaluation/implementation/`.

- `red_tests.txt`: expected missing single-prompt and uncached-token behavior before implementation.
- `red_async_escalated_tests.txt`: decisive initial case had only two calls before the added independent control.
- `summary_red_fixed_tests.txt`: summary module absent before implementation.
- `four_arm_tests.txt`: initial 42 focused checks passed.
- `summary_green_tests.txt`: 50 protocol/summary/client checks passed before adding the extra failure-path coverage.
- `failure_paths_tests.txt`: four targeted failure paths passed.
- `final_focused_tests.txt`: final 53-check run against current checkout source.

## Git checkpoint and next steps

This log accompanies the focused evaluation implementation commit, after `7c9bc09`; only the owned adapter, benchmark helpers, evaluation scripts/tests and guide are staged. No credentials, runtime artifacts, source materials or real reference labels belong in the commit.

The parent will run independent specification review, code-quality review and the full suite, build the current wheel, then freeze the approved three 30-case plans. The implementation has not executed those real-source batches. The 360-call total remains a planned cap, not an observed model cost. No research finding about refutation recall or token savings is established by this implementation session.

## Specification-review follow-up

After `0edbe2c`, specification review identified two integrity gaps. Both were reproduced before implementing their fixes:

- A caller may now supply the same `seen_threads` set to each `run_async` or synchronous `run` invocation. Reusing a CLI thread from an earlier batch stops the next batch immediately after that receipt, before further calls. Single-batch CLI behavior is unchanged. The strict completed-run loader accepts the same optional set, and the summary uses one across all verified receipts before opening any gold. Synthetic summary fixtures now use unique per-batch thread IDs except in the explicit rejection test.
- `verify_imported_core` compares the actual imported `academic_guardrail` package against this checkout's `src/academic_guardrail`: the complete `.py` inventory and content must match, allowing only CRLF-to-LF normalization. Runtime hash checks invoke this guard before preparation creates its output and before a run starts. Plans and run manifests record the imported path, normalization, matching status and normalized hashes. A matching installed wheel and a source import are both valid. The evaluation MCP child wrapper places the verified parent's package directory first on inherited `PYTHONPATH`; a real subprocess import probe verifies this against a competing stale package.

The final focused command is the same three-file pytest selection above, with `--basetemp` ending in `implementation/integrity_final_temp`. Result: **60 passed in 167.71 seconds**, exit code 0, against checkout source. `git diff --check` also passed. This follows 59 passing checks before the final MCP-child regression was added.

Additional evidence under the same implementation evidence directory:

- `integrity_red_tests.txt`: five failures reproduce absent shared-thread support and absent/mismatched imported-core checks.
- `cross_batch_red_tests.txt`: duplicate cross-batch thread IDs incorrectly reached gold reading before the fix.
- `child_import_red_tests.txt`: an inherited competing `PYTHONPATH` selected a different package in a real Python subprocess before pinning.
- `integrity_green_tests.txt`: 59 passing checks for the initial review fixes.
- `integrity_final_tests.txt`: final 60 passing checks including the child import probe.
- `imported_core_probe.json`: with `PYTHONPATH` empty, the new study venv's installed wheel matched all 43 core Python files; the retained old MCP-upgrade venv was correctly rejected for `core/ref_store.py`. These probes changed neither environment and made no model calls.

No formal model call or real-source gold access occurred in this follow-up. The parent may make a separately scoped parser correction after these checks; that will require rebuilding the installed study wheel and rerunning final validation before freezing. The guard is expected to reject a newly stale wheel until that rebuild succeeds.

## v3 source-identity correction after the aborted initial round

Baseline: `cfe785b`. On resuming this implementation task, the only existing edit was the parent's protocol bump from v2 to v3, used to stop the first formal run at its next frozen-code check. That edit is retained in this focused fix.

The coordinator reported that the first two development cases completed eight formal calls before the run stopped. The first response revealed that the prompt projection had removed the matched paper's title and DOI; the RoBERTa abstract did not itself name RoBERTa, so the response declared an entity-mapping gap. The second case was already in flight. This is an **aborted initial formal round**, not a preplanned pilot. The implementer did not reopen those model answers, study reference labels or source materials; disclosure here uses the coordinator's observation. No validation outputs were inspected.

Minimal implementation changes:

- A local-only payload helper wraps the existing claim/evidence projection with `source_identity` containing exactly the pinned `local_review.source.title` and `.doi`. The generic historical paired-comparison projection is unchanged.
- All four local prompt forms carry that same identity. Instructions say metadata identifies the paper and is not proof of a claim. No path, source status, confidence, rule hints or additional source text enters the payload.
- Strict scoring reconstructs identity from the stored local context, verifies the complete source binding against the frozen original paper, and checks the resulting raw prompt. v2 plans remain rejected by the v3 protocol check.
- The Chinese guide and design specification disclose the observed two development cases, the unchanged 90 claims/reference labels/source corpus, and the need to freeze all new plans after independent review. The coordinator owns new execution drivers and preservation of the old frozen round. All eight aborted calls and their token use remain study costs: the hard total is 360 calls, with at most 352 additional calls available. No old frozen driver or run was edited here.

Validation used `D:/Internship/Academic code/audit_guardrail_20261118_terra_max_evaluation/venv/Scripts/python.exe`, with `PYTHONPATH` pointing to this checkout's `src`, and the same three focused pytest files. **63 passed in 174.23 seconds**, exit code 0. Evidence under the implementation directory:

- `source_identity_red_tests.txt`: the new synthetic regression failed because the payload contained only claim/evidence and omitted source identity.
- `source_identity_final_tests.txt`: final 63 passing checks, including equal identity in all four raw prompt forms, a paper name absent from abstract evidence, no hint/prior leakage, identity tampering, strict scorer replay and v2 rejection.

`git diff --check` passed. This patch changes benchmark prompting/scoring, tests and documentation only; no core package, dependency, model configuration, claim or gold was changed. The implementation made zero actual model calls. Independent re-review and new v3 freezing remain with the coordinator.
