# 90-case terra/max evaluation results

## Scope and checkpoints

The user selected 90 new cases and requested `gpt-6.1-terra` with `max` reasoning. This session completed the four-arm study defined in the design and execution guide, reported its negative completeness result, and preserved raw evidence. The project remains one MCP service; the optional evaluation adapter is separate from server operation.

Starting original master: `65149765c5a2d55dc838ba3b29ef11b9f93204b9`. Reviewed and frozen runtime: `89aea1e2848091aec27bdcc71e4dea7f7ebb37e2`. The clean original project was fast-forwarded and normally pushed to this runtime commit before result documentation. This results commit changes Markdown only; it does not tune the evaluated code or labels.

Evidence root: `D:/Internship/Academic code/audit_guardrail_20261118_terra_max_evaluation/`. Isolated checkout: `D:/Internship/Academic code/guardrail_expanded_evaluation/`. The original project is `D:/Github_Project/Academic_Guardrail_Agent/`.

## Execution and evidence

The dedicated Python 3.12.9 venv was created with `D:/Anaconda/envs/pytorch/python.exe`; its installed wheel matched all 43 core Python files. The frozen study used three paper-disjoint batches of 30 authored claims, 15 version-pinned primary papers, separate input/gold files and preserved extraction maps. Gold was opened for scoring after all three runs completed.

The first v2 formal round stopped after two development cases and eight calls because prompt projection omitted verified source identity. These were not preplanned pilot calls. The v3 correction added identical title/DOI fields to every arm and retained all 90 claims, labels, source text and retrieval rules. Both the aborted evidence and its cost remain preserved. No validation output was observed before the v3 freeze.

The reviewed local controller `run_study_02.py` ran with the study venv and checkout on `PYTHONPATH`; `study_freeze_02.json` fixed all plans before calls. Per-invocation timeout was 600 seconds, with at most three final judgments in parallel after each initial judgment. It made no harness retries or answer repairs. Windows asyncio/stdio required approved execution outside the filesystem sandbox.

Completed batches used 110, 111 and 111 calls: **332 new calls**, **340 including the aborted eight**, below the user cap of 360. Every call has a unique thread ID, and no invocation error or model tool use was observed. Execution timestamps were 2026-11-17 18:49:46–21:54:57 UTC (2026-11-18 in Asia/Shanghai). `study_execution_02.json` records completion and manifest hashes.

Deterministic post-run commands used the study venv, `PYTHONPATH` pointing at this checkout, and fresh destinations:

```powershell
$env:PYTHONPATH='D:\Internship\Academic code\guardrail_expanded_evaluation'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:\Internship\Academic code\audit_guardrail_20261118_terra_max_evaluation\venv\Scripts\python.exe' 'D:\Internship\Academic code\audit_guardrail_20261118_terra_max_evaluation\analyze_results_02.py'
$env:PYTHONUTF8='1'
& 'D:\Anaconda\envs\pytorch\python.exe' 'D:\Internship\Academic code\audit_guardrail_20261118_terra_max_evaluation\export_case_review_02.py'
```

These are the executed local commands, not an instruction to overwrite their existing output directories. The scripts require new outputs. For a new scoring replay, use the reusable summary CLI with fresh destination paths as explained in the evaluation guide. Analysis strictly revalidated all runs before scoring, wrote all/development/validation summaries, and then added predeclared strata, output usability and aborted-round expenditure. The case export supplies complete claims and raw/usable distinctions in a 90-row CSV without modifying score/run artifacts. Both operations made zero model calls.

## Results and limits

Full-text single-call and two-stage controls matched all 90 reference labels and yielded 75 correct concrete decisions. Local follow-up matched 82 labels, with 67 correct concrete raw answers, 22 NEI and one uncertain result. One correct refutation failed evidence-ID declaration, leaving **66 valid correct concrete answers** and **39/45 valid refutations**, compared with raw **40/45**. The 60-case validation subset has raw refutation recall 27/30, valid refutation recall 26/30 and 44 valid correct concrete answers.

Against the primary single-call control, local follow-up reduced input tokens 26.11% and output 19.48%, but increased the reasoning-output subset 29.15% and used 152 versus 90 effective calls. Formal-study expenditure including the aborted round was input 7,161,820 and output 920,045, with cached input 2,706,944 and reasoning output 420,223 already included in their respective totals. These figures exclude development/reviewer conversations and do not establish monetary or human-time savings.

Independent arithmetic matched the saved metrics and costs. Source audit traced 4,908 local packet-unit instances and 287 final local quote occurrences to preserved source text/maps. All eight raw losses were analyzed, as were the rejected output and six correct concrete outputs supported by alternatives to the single authored anchor. Source review is unblinded assistant review, not expert certification. The reports contain 90 chains and 151 stored judgment snapshots; a rejected final answer leaves its initial stored judgment visible.

See `docs/expanded_local_followup_results.md` for tables, all source versions, error explanations and practical use advice. The original 15-case and 30-case studies remain unchanged. Different cohorts/models/protocols do not support a causal cross-study improvement claim. Same-paper multi-claim batching and autonomous client tool-selection overhead remain unmeasured.

## Validation and publication

Frozen runtime verification: **545 tests passed in 221.54 seconds** locally; installed-wheel MCP workflow validators passed without model calls. Actual [CI run 44154675037](https://github.com/LyraFelix/Academic_Guardrail_Agent/actions/runs/44154675037) passed all six environments with MCP 2.3.0. The result-documentation changes need link/content and whitespace checks, not another local model or software benchmark.

Independent records are under `review/`: protocol/quality reviews, `results_metrics_audit_02.md`, `results_source_audit_02.md` and `results_report_review_02.md`. Primary outputs are `scores_02/`; readable cases are `presentation_02/case_review.csv`; the three original HTML reports are `runs_02/<partition>/review_report.html`. Old frozen artifacts and unrelated workspace research changes were preserved.

## Next justified work

Prioritize lexical retrieval normalization and ranking/context selection using these now-exposed cases as regressions. Preserve original text and coordinates while changing the search view. Reduce evidence-ID declaration errors without silently fabricating model attestations. Any fallback or retrieval improvement needs new frozen source cases and an equally budgeted full-text comparison, including a multi-claim baseline. No such post-hoc improvement was run or claimed in this session.
