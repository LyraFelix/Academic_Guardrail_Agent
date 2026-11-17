# Expanded terra/max evaluation implementation plan

> For agentic workers: use superpowers:subagent-driven-development for independent implementation and requesting-code-review before release.

**Goal:** Execute the user-approved 90-case source-grounded comparison with gpt-6.1-terra/max and identify measured benefits or regressions without changing historical evidence.

**Architecture:** Keep the existing prepare/run/score separation. Extend the frozen protocol with one independent single-call full-text control and honest per-arm cost accounting. Author and verify source materials separately from execution. Preserve simple explicit helpers and all failures.

**Tech stack:** Existing Python interpreter/venv, official MCP 2.3.0, installed Codex CLI 0.169.0-alpha.11.1, existing PDF extraction, standard-library metrics.

- [ ] Extend adapter, shared prompts and protocol to terra/max and four arms. Add focused regression tests for the single-call input, budgets, actual/effective costs and hash checks.
- [ ] Add readable cross-batch summary with refutation recall, avoidable insufficiency, paired changes, per-paper rows and token categories. Reject mixed model/protocol or overlapping cases/papers across declared partitions.
- [ ] Fetch fifteen primary sources, preserve hashes/positions, prepare ninety claims and evidence-grounded reference labels. Independently review material integrity before freezing.
- [ ] Run appropriate offline tests and real MCP acceptance; review code and commit clean runtime.
- [ ] Freeze all three thirty-case plans with sealed gold hashes before formal model calls. Verify requested CLI flags and provenance at each call.
- [ ] Run with at most 360 formal calls and no harness retries. Observe until complete or a concrete external block. Preserve failures and missing usage.
- [ ] Score immutable outputs, audit exact quotations and discrepancies, generate comparison tables and readable reports.
- [ ] Write Chinese methods/results/reading guide, preserve existing benchmark claims, commit/push normal master and observe actual CI.
- [ ] Record this session and evidence boundaries in the research workspace without staging unrelated changes.
