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
