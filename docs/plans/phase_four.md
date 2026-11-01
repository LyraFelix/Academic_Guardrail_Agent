# Phase four: reproducible evaluation implementation plan

**Goal:** Run the frozen phase-three implementation on versioned inputs, preserve every prediction and failure, and explain observed usefulness without treating review states as scientific truth labels.

**Architecture:** Separate dataset preparation, label-free prediction, scoring and reporting. All evaluation runs are offline after an explicit public-data download. A run records data hashes, code hashes, environment, configuration and raw outputs; scoring can be replayed without invoking the evaluator. Small modules and Chinese documentation keep the flow learnable.

**Tech stack:** Existing Python/Pydantic/pytest stack plus standard-library JSON, tarfile, hashlib, argparse and CSV. No new model, dependency or paid API.

## Frozen protocol

- Production source is frozen at `9e9365d13296cb0bc9f40da13dce275c7c8d753a`. This phase may repair evaluation code but must not tune semantic rules using evaluation outcomes.
- SciFact archive: official S3 download, SHA-256 `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`, 3,115,079 bytes. Fresh download and historical local cache are identical.
- Use all 300 dev claims and **all 339 unique cited claim-document pairs**: 138 SUPPORT, 71 CONTRADICT, 130 NEI. The archive has 340 citation occurrences: claim 1245 lists document 7662395 twice. Preserve the archive and explicitly record this duplicate normalization in the prepared manifest. Choosing only labeled evidence documents for positive claims would omit 17 NEI pairs. No sample selection by evaluator outcome.
- Inputs contain stable pair/claim/document IDs, claim text and the full abstract sentences. Gold labels/rationale sentence IDs live in a separate file and are loaded only after predictions. Missing, duplicate, extra or invalid prepared rows cause an explicit error; missing predictions never become NEI. Repeated source citations are normalized explicitly before prepared rows are written.
- This is a given-cited-document diagnostic, not open-corpus retrieval or the official SciFact leaderboard task. No oracle rationale is shown to the evaluator. The dev set has appeared in historical project evaluation, so it is not an untouched holdout.
- Report native state distribution by gold label, concrete contradiction-alert precision/recall, alert rate on SUPPORT and NEI, support fraction within TEXT_ALIGNED, ERROR counts and primary-excerpt rationale coverage. Keep explicit numerators/denominators and use null for undefined ratios. Do not report a manufactured three-way overall accuracy.
- Compare with two disclosed controls: always request review, and lexical similarity alone with a fixed 0.50 threshold. Baselines receive identical full abstracts and never read labels. They are diagnostics, not published NLI models.
- Existing 50 synthetic phase-three examples remain development regression evidence, reported separately from SciFact. No combined accuracy across datasets or components.
- Preserve historical scripts and records, retire broken/misleading root entrypoints with an actionable migration message, and retain the existing reference-resolution fixture/test import contract.

## Tasks

1. **Preparation and models** (`benchmarks/schema.py`, `benchmarks/datasets.py`, `benchmarks/scifact_source.json`, `tests/test_evaluation_data.py`). First test all cited pairs, separated gold, duplicate/missing documents, conflicting gold, file hashes and safe archive reads. Implement deterministic preparation and explicit checked download.
2. **Prediction and metrics** (`benchmarks/predictors.py`, `benchmarks/metrics.py`, `tests/test_evaluation_metrics.py`). Test hand-calculated confusion counts, zero denominators, errors in denominators, incomplete/duplicate prediction rejection, rationale span matching, and label-independent input. Implement native-state diagnostics and two fixed controls.
3. **Runner and CLI** (`benchmarks/runner.py`, `benchmarks/reporting.py`, `benchmarks/__main__.py`, `tests/test_evaluation_workflow.py`). Test fresh-directory enforcement, interrupted/error runs, offline boundary, scoring replay, same-input comparability and deterministic semantic outputs. Write predictions before loading gold. Preserve all rows, metrics, manifest, TSV and failure examples.
4. **Legacy migration and learning docs** (`benchmarks/legacy/`, `benchmarks/README.md`, `docs/phase_four_guide.md`, project READMEs). Archive originals, explain historical issues and retain old raw evidence. Document one concrete prepare/run/score/compare path and the distinction between a rule diagnostic and official scientific fact verification.
5. **Actual evaluation and review**. Run full 264-test baseline and new tests. Freeze the harness, run all SciFact pairs and controls, replay the same configuration independently, and inspect all rare/conflict outputs plus systematic missed cases. Independent code review must inspect leakage, denominator, provenance and reproducibility. Fix harness bugs only and preserve failed runs.
6. **Completion**. Full tests, original-path workflow verification, wheel build, source-freeze diff, worklog and research findings. Use ordinary `phase-four`, Felix attribution, fast-forward master and normal push after verification, as already authorized.

## Acceptance commands

```text
python -m benchmarks prepare-scifact --archive <official-tar> --output <new-dataset-dir>
python -m benchmarks prepare-regression --output <new-dataset-dir>
python -m benchmarks run --dataset <prepared-dir> --method guardrail --output <new-run-dir>
python -m benchmarks run --dataset <prepared-dir> --method overlap --output <new-run-dir>
python -m benchmarks run --dataset <prepared-dir> --method always_review --output <new-run-dir>
python -m benchmarks score --dataset <prepared-dir> --run <run-dir>
python -m benchmarks compare <run-dir> <repeat-run-dir>
python -m pytest tests -q
```

Each output directory must be new. Raw downloads and run artifacts remain local and ignored. Evidence root: `D:/Internship/Academic code/audit_guardrail_20261101_phase_four/`. The selected approach provides honest native-state measurements; simply repairing old unpacking would preserve invalid label mappings, while adding a new model would change the system being evaluated.

Sources: [SciFact schema](https://github.com/allenai/scifact/blob/master/doc/data.md), [official evaluation](https://github.com/allenai/scifact/blob/master/doc/evaluation.md), [data licenses](https://github.com/allenai/scifact/blob/master/LICENSE.md). Claims/annotations are CC BY 4.0; corpus abstracts are ODC-By 1.0 per the upstream license file. Attribution and license URLs accompany prepared data.
