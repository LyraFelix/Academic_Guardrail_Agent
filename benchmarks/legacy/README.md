# Historical evaluation source archive

These files are exact byte copies of the scripts at commit `9e9365d13296cb0bc9f40da13dce275c7c8d753a`, saved as `.py.txt` to avoid accidental import/execution. `manifest.json` records each SHA-256. Git history also retains the originals. Prior downloaded data, predictions and evaluation outputs remain untouched.

They are **not a supported evaluation path**. The current entry point is `python -m benchmarks`; see [the workflow](../README.md).

| Historical file | Why it was retired |
| --- | --- |
| `benchmark_claims`, `benchmark_baselines` | Handwritten tiny cases labeled as SciFact; obsolete tuple unpacking; similarity thresholds treated as scientific support |
| `benchmark_scifact_official` | Obsolete interface; omits some cited non-evidence documents; automatic unpinned download; not the official leaderboard scoring procedure |
| `prepare_scifact_batches` | Machine-specific output path; gold mixed into inference batches; selected excerpt rather than full abstract |
| `evaluate_llm_scifact_results` | Machine-specific paths, missing predictions default to NEUTRAL, no validated model call traces |
| `benchmark_runner`, `benchmark_submodules_async` | Mixed tasks/denominators, unverified hand labels, provider availability conflated with correctness |
| `benchmark_offline` | Inserts synthetic records then looks them up; cannot measure external retraction coverage; unmeasured memory claim |
| `synthetic_demo_benchmark` | Synthetic pipeline demonstration, not real scholarly effectiveness |
| `benchmark_reference_resolution` | Eight handwritten provided-candidate fixtures; retained at the root only for the existing unit-test import contract |

These limitations do not establish that every historical prediction was wrong. They mean old headline metrics lack the required evidence for current capability claims. No legacy model score is reproduced by the new offline rule evaluation.
