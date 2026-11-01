"""Deterministic preparation; downloading is explicit and checksum-pinned."""

import hashlib
import json
from collections import Counter
from pathlib import Path
import shutil
import tarfile
import urllib.request

from benchmarks.schema import GoldCase, InputCase

ROOT = Path(__file__).resolve().parents[1]
SCIFACT_SOURCE = json.loads(Path(__file__).with_name("scifact_source.json").read_text(encoding="utf-8"))
MAX_FILE_BYTES = 20_000_000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_records(path: Path, records):
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")


def read_records(path: Path, model):
    records = [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    unique_by_id(records)
    return records


def unique_by_id(records):
    result = {}
    for record in records:
        if record.id in result:
            raise ValueError(f"Duplicate record ID: {record.id}")
        result[record.id] = record
    return result


def download_scifact(destination: Path):
    """Only this function accesses the network; never called by run/score."""
    if destination.exists():
        raise FileExistsError(destination)
    with urllib.request.urlopen(SCIFACT_SOURCE["url"], timeout=45) as response:
        content = response.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES or hashlib.sha256(content).hexdigest() != SCIFACT_SOURCE["sha256"]:
        raise ValueError("Official archive checksum/size changed; inspect the source before updating the pin")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(content)


def _archive_records(archive, member_name):
    member = archive.getmember(member_name)
    if not member.isfile() or member.size > MAX_FILE_BYTES:
        raise ValueError(f"Invalid archive member: {member_name}")
    # Read only named members; never extract archive paths onto the filesystem.
    with archive.extractfile(member) as handle:
        content = handle.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Oversized archive member")
    return [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]


def _raw_index(records, key):
    indexed = {}
    for record in records:
        identifier = record[key]
        if type(identifier) is not int or identifier in indexed:
            raise ValueError(f"Invalid/duplicate {key}: {identifier}")
        indexed[identifier] = record
    return indexed


def _write_dataset(destination, inputs, gold, protocol, source, *, preparation=None):
    if not inputs or set(unique_by_id(inputs)) != set(unique_by_id(gold)):
        raise ValueError("Empty dataset or unequal input/gold IDs")
    destination.mkdir(parents=True, exist_ok=False)
    write_records(destination / "inputs.jsonl", inputs)
    write_records(destination / "gold.jsonl", gold)
    manifest = {"schema_version": 1, "protocol": protocol, "source": source,
                "counts": {"claims": len({row.claim_id for row in inputs}), "pairs": len(inputs)},
                "files": {name: sha256(destination / name) for name in ("inputs.jsonl", "gold.jsonl")}}
    if preparation is not None:
        manifest["preparation"] = preparation
    write_json(destination / "manifest.json", manifest)


def prepare_scifact(archive_path: Path, destination: Path, *, source=None):
    source = SCIFACT_SOURCE if source is None else source
    if sha256(archive_path) != source["sha256"]:
        raise ValueError("Archive checksum differs from the selected source")
    with tarfile.open(archive_path, "r:gz") as archive:
        corpus = _raw_index(_archive_records(archive, "data/corpus.jsonl"), "doc_id")
        claims = _raw_index(_archive_records(archive, "data/claims_dev.jsonl"), "id")
    inputs, gold = [], []
    preparation = {"raw_citation_occurrences": 0, "duplicate_citations": []}
    for claim_id, claim in sorted(claims.items()):
        cited = claim["cited_doc_ids"]
        if not cited or any(type(doc) is not int for doc in cited):
            raise ValueError(f"Invalid cited document IDs for claim {claim_id}")
        preparation["raw_citation_occurrences"] += len(cited)
        # A repeated source citation is one pair, not two independent examples.
        # Keep the original archive and record every normalization explicitly.
        cited_counts = Counter(cited)
        preparation["duplicate_citations"].extend(
            {"claim_id": claim_id, "doc_id": doc_id, "removed_occurrences": count - 1}
            for doc_id, count in sorted(cited_counts.items()) if count > 1
        )
        if set(claim["evidence"]) - {str(doc) for doc in cited}:
            raise ValueError(f"Annotated document outside cited list for claim {claim_id}")
        for doc_id in sorted(cited_counts):
            if doc_id not in corpus:
                raise ValueError(f"Missing cited document {doc_id}")
            sentences = corpus[doc_id]["abstract"]
            if not sentences or not all(isinstance(s, str) and s.strip() for s in sentences):
                raise ValueError(f"Invalid abstract for document {doc_id}")
            annotations = claim["evidence"].get(str(doc_id), [])
            labels = {annotation["label"] for annotation in annotations}
            if labels - {"SUPPORT", "CONTRADICT"} or len(labels) > 1:
                raise ValueError(f"Invalid/conflicting gold for {claim_id}:{doc_id}")
            rationales = [annotation["sentences"] for annotation in annotations]
            if any(not ids or any(type(i) is not int or i < 0 or i >= len(sentences) for i in ids) for ids in rationales):
                raise ValueError(f"Invalid rationale index for {claim_id}:{doc_id}")
            identifier = f"{claim_id}:{doc_id}"
            inputs.append(InputCase(id=identifier, claim_id=str(claim_id), doc_id=str(doc_id),
                                    claim=claim["claim"], sentences=sentences))
            gold.append(GoldCase(id=identifier, label=next(iter(labels)) if labels else "NEI", rationales=rationales))
    _write_dataset(destination, inputs, gold, "scifact_cited_abstract_v1", source, preparation=preparation)
    shutil.copyfile(archive_path, destination / "source.tar.gz")


def prepare_regression(destination: Path):
    fixture = ROOT / "tests/fixtures/semantic_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
    inputs = [InputCase(id=c["id"], claim_id=c["id"], doc_id=c["id"], claim=c["claim"],
                        sentences=[c["evidence"]] if c["evidence"] else [], category=c["category"]) for c in cases]
    gold = [GoldCase(id=c["id"], expected_state=c["expected_state"], required_codes=c["required_codes"]) for c in cases]
    _write_dataset(destination, inputs, gold, "semantic_regression_v1",
                   {"name": "development synthetic regression", "file": str(fixture.relative_to(ROOT)), "sha256": sha256(fixture)})


def _manifest(destination):
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("protocol") not in {"scifact_cited_abstract_v1", "semantic_regression_v1"}:
        raise ValueError("Unsupported prepared-data schema/protocol")
    return manifest


def _checked_records(destination, name, model, manifest):
    content = (destination / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest["files"][name]:
        raise ValueError(f"Prepared file checksum mismatch: {name}")
    records = [model.model_validate_json(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    unique_by_id(records)
    if len(records) != manifest["counts"]["pairs"]:
        raise ValueError(f"Prepared record count mismatch: {name}")
    return records


def load_inputs(destination):
    # This path deliberately does not open gold.jsonl.
    manifest = _manifest(destination)
    return _checked_records(destination, "inputs.jsonl", InputCase, manifest), manifest


def load_gold(destination):
    return _checked_records(destination, "gold.jsonl", GoldCase, _manifest(destination))
