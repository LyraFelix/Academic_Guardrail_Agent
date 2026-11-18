"""Check compact coverage declarations against the same saved local judgments."""

import argparse
import json
from pathlib import Path

from academic_guardrail.core.claim_review import validate_client_judgment
from academic_guardrail.core.review_models import ClientJudgment
from academic_guardrail.core.review_store import ReviewStore, content_digest
from benchmarks.datasets import sha256


def compact_ids(ids: list[str]) -> list[str]:
    """Shorten consecutive declared IDs in their original order, preserving gaps."""
    ranges = []
    for evidence_id in ids:
        number = int(evidence_id.removeprefix("e"))
        if evidence_id != f"e{number}" or number < 1:
            raise ValueError(f"Unexpected historical evidence ID {evidence_id!r}")
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1][1] = number
        else:
            ranges.append([number, number])
    return [f"e{start}" if start == end else f"e{start}-e{end}" for start, end in ranges]


def read_archived_json(batch: Path, hashes: dict, name: str):
    path = batch / name
    if sha256(path) != hashes[name]:
        raise ValueError(f"Changed archive file: {path}")
    return json.loads(path.read_bytes())


def check(packet, judgment):
    try:
        result = validate_client_judgment(packet, judgment)
    except ValueError as error:
        return False, str(error), []
    return True, None, result["quotes"]


def replay(runs: Path) -> dict:
    cases = []
    seen = set()
    for partition in ("development", "validation_a", "validation_b"):
        batch = runs / partition
        manifest = json.loads((batch / "manifest.json").read_bytes())
        hashes = manifest["files"]
        store = ReviewStore(batch / "runtime" / "stored")
        rows = read_archived_json(batch, hashes, "rows.json")
        local = [row for row in rows if row["arm"] == "local_followup"]
        if len(local) != manifest["completed_cases"] or manifest["status"] != "completed":
            raise ValueError(f"Incomplete historical batch: {partition}")
        for row in local:
            case_id = row["id"]
            if case_id in seen:
                raise ValueError(f"Duplicate case {case_id}")
            seen.add(case_id)
            packet = store.load_packet(row["packet_id"])
            if content_digest(packet.model_dump(mode="json")) != row["packet_sha256"]:
                raise ValueError(f"Packet mismatch for {case_id}")
            response = read_archived_json(batch, hashes, row["attempt"] + "/response.json")
            original = ClientJudgment.model_validate(response)
            shortened = compact_ids(original.reviewed_evidence_ids)
            compact = original.model_copy(update={"reviewed_evidence_ids": shortened})
            accepted, error, quotes = check(packet, original)
            if accepted != row["record_accepted"] or check(packet, compact) != (accepted, error, quotes):
                raise ValueError(f"Coverage acceptance, rejection or quote coordinates changed for {case_id}")
            cases.append({"id": case_id, "packet_sha256": row["packet_sha256"],
                          "units": len(packet.evidence), "declared": len(original.reviewed_evidence_ids),
                          "compact": shortened, "accepted": accepted, "error": error, "quotes": len(quotes)})
    return {"model_calls": 0, "cases": len(cases), "accepted": sum(row["accepted"] for row in cases),
            "individual_ids": sum(row["declared"] for row in cases),
            "compact_entries": sum(len(row["compact"]) for row in cases), "results": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True, help="Original runs_02 directory")
    parser.add_argument("--output", type=Path, required=True, help="New JSON file for replay results")
    args = parser.parse_args()
    result = replay(args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print({key: value for key, value in result.items() if key != "results"})
