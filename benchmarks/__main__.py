"""Prepare -> run -> score -> compare. Run/score never download anything."""

import argparse
import json
from pathlib import Path
import sys

from benchmarks.datasets import download_scifact, prepare_regression, prepare_scifact
from benchmarks.predictors import METHOD_CONFIGS
from benchmarks.runner import compare_runs, rescore_run, run_benchmark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download-scifact", help="Explicitly download the checksum-pinned public archive")
    download.add_argument("--output", type=Path, required=True)
    prepare = commands.add_parser("prepare-scifact", help="Prepare every cited dev claim-document pair")
    prepare.add_argument("--archive", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    regression = commands.add_parser("prepare-regression", help="Prepare development-only synthetic checks")
    regression.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Predict offline, save all cases, then score")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--method", choices=METHOD_CONFIGS, default="guardrail")
    run.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("score", help="Verify files and reproduce metrics without prediction")
    score.add_argument("--dataset", type=Path, required=True)
    score.add_argument("--run", type=Path, required=True)
    compare = commands.add_parser("compare", help="Compare runs with identical prepared inputs and labels")
    compare.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "download-scifact":
            download_scifact(args.output)
            result = {"archive": str(args.output)}
        elif args.command == "prepare-scifact":
            prepare_scifact(args.archive, args.output)
            result = {"prepared": str(args.output)}
        elif args.command == "prepare-regression":
            prepare_regression(args.output)
            result = {"prepared": str(args.output), "boundary": "development regression"}
        elif args.command == "run":
            result = run_benchmark(args.dataset, args.output, args.method)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
            return 0 if manifest["status"] == "completed" else 1
        elif args.command == "score":
            result = rescore_run(args.dataset, args.run)
        else:
            result = compare_runs(args.runs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f"Evaluation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
