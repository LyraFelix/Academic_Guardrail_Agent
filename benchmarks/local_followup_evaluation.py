"""Frozen contracts for a small, authored local-source workflow comparison.

Preparation and execution never need gold. The independent scorer is the only
entry point allowed to read it. Packet hints never enter either model prompt.
"""

import hashlib
import json
from pathlib import Path
import re

from academic_guardrail.core.review_models import ClientJudgment
from academic_guardrail.core.review_store import ReviewStore
from benchmarks.client_comparison import DIRECT_INSTRUCTIONS, OUTPUT_INSTRUCTIONS, shared_evidence
from benchmarks.datasets import sha256
from scripts.codex_review_client import MODEL, REASONING, strict_schema
from scripts.run_paired_review import inspect_answer, load_frozen_packet


PROTOCOL = "local_evidence_followup_v1"
ARMS = ("abstract_only", "fulltext_direct", "local_followup")
PRIOR_TOKEN = "<FROZEN_PRIOR_JUDGMENT_JSON>"
COMMON_INSTRUCTIONS = DIRECT_INSTRUCTIONS + "\n\n" + OUTPUT_INSTRUCTIONS + """
SUPPORTED and CONTRADICTED require at least one exact quote. Do not strengthen
the original claim by adding only, all, or exclusivity conditions it does not state.
For unresolved necessary facts, use missing_evidence (at most four entries).
Each entry requires kind, claim_part, question and search_terms. claim_part must
be an exact substring of the original claim; question states what remains missing.
Use 1-6 distinct literal search terms, each 1-100 characters containing a letter
or number. Do not invent aliases, entity mappings or results. Use [] if no gap is
identified. Preserve the original claim when checking subject, relation, numbers,
population, comparator, time and counterevidence. A lexical hit is not proof.
"""
SECOND_INSTRUCTIONS = """
A previous judgment is supplied as data. Independently judge the original claim
against all CURRENT evidence, including both earlier and additional passages.
The prior judgment may be wrong. Return one complete fresh judgment using the
same output rules. Report unresolved gaps even after considering this evidence.
"""
PROTOCOL_RULES = {
    "arms": list(ARMS),
    "shared_initial": "One independent abstract-only judgment per case, shared by both workflows.",
    "fulltext_direct": "Always one further fresh-context judgment on full local text plus the raw shared judgment.",
    "local_followup": "Only recorded NEI/UNCERTAIN with a gap uses gap 0 once, then one fresh-context judgment.",
    "no_followup": "Carry the initial raw result; missing gap, record rejection or lookup failure stays in the denominator.",
    "budget": "At most 3N actual CLI calls; at most two effective calls per workflow/case; no repair or retry.",
    "common_rules": "Identical schema, semantic instructions and offline validator; no MCP heuristic hints to either arm.",
    "isolation": "Fresh unique CLI thread per invocation; no model tools; abort on unverifiable stream, tool use or duplicate thread.",
    "failure_stop": "Stop after a call group in which every invocation failed; retain an incomplete manifest.",
    "primary": "Raw final labels against full-text gold, including rejected records and failed cases.",
    "cost": "Count the shared first call in each arm; count it once in actual execution totals. Unknown usage is null.",
    "gold": "Prepare/run never open gold; score selected partition only after a complete unchanged run.",
    "boundary": "Purposive assistant-authored claims and reference judgments, not natural benchmark or human gold; held-out papers do not prove absence of pretraining exposure.",
}
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def runtime_code_hashes():
    """Pin source bytes, including imported runtime helpers, rather than Git HEAD alone."""
    root = Path(__file__).resolve().parents[1]
    paths = [path for folder in ("src", "scripts", "benchmarks")
             for path in (root / folder).rglob("*.py")]
    return {path.relative_to(root).as_posix(): sha256(path) for path in sorted(paths)}


def file_hashes(directory):
    root = Path(directory).resolve()
    return {path.relative_to(root).as_posix(): sha256(path) for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"}


def relative_file(directory, name):
    root = Path(directory).resolve()
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root) or path == root:
        raise ValueError("Artifact filename must stay inside its snapshot")
    return path


def check_files(directory, expected):
    for name in expected:
        relative_file(directory, name)
    if file_hashes(directory) != expected:
        raise ValueError("Frozen artifact changed or file inventory differs from its checksum manifest")


def read_inputs(path):
    required = {"id", "partition", "paper_id", "claim", "citation_str_or_doi", "paper_title", "source_path"}
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or any(set(row) != required or any(not isinstance(value, str) or not value.strip()
                                                   for value in row.values()) for row in rows):
        raise ValueError("Inputs require exactly the seven nonempty public input fields")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Input IDs must be unique")
    if len({row["partition"] for row in rows}) != 1:
        raise ValueError("Prepare one partition at a time")
    return rows


def first_prompt(packet):
    return COMMON_INSTRUCTIONS + "\n\nSOURCE_DATA_JSON\n" + json.dumps(shared_evidence(packet), ensure_ascii=False)


def second_template(packet):
    return (COMMON_INSTRUCTIONS + SECOND_INSTRUCTIONS + "\n\nSOURCE_DATA_JSON\n"
            + json.dumps(shared_evidence(packet), ensure_ascii=False)
            + "\n\nPRIOR_JUDGMENT_JSON\n" + PRIOR_TOKEN)


def second_prompt(packet, prior_judgment):
    template = second_template(packet)
    return template[:-len(PRIOR_TOKEN)] + json.dumps(prior_judgment, ensure_ascii=False)


def check_packet(batch, view, item=None, scope=None):
    packet = load_frozen_packet(batch, view)
    if view["claim"] != packet.claim:
        raise ValueError("Packet view claim differs from the stored original claim")
    evidence = [unit.model_dump(mode="json") for unit in packet.evidence]
    if view["evidence"] != evidence or view["next_offset"] is not None or view["total_evidence"] != len(evidence):
        raise ValueError("Packet view does not contain all exact stored evidence units")
    context = ReviewStore(Path(batch) / "stored").load_context(packet.packet_id)
    if context is None or context.model_dump(mode="json") != view["local_review"]:
        raise ValueError("Packet local context differs from its stored snapshot")
    if item is not None:
        if packet.claim != item["claim"] or Path(context.source.path).resolve() != Path(item["source_path"]).resolve():
            raise ValueError("Prepared packet chose a different claim or source_path")
    if scope is not None and (context.initial_scope != scope or context.round != 0):
        raise ValueError("Initial packet has the wrong evidence scope or follow-up round")
    if sha256(Path(context.source.path)) != context.source.sha256:
        raise ValueError("Local source changed since packet preparation")
    return packet


def load_packet_view(directory, filename):
    return json.loads(relative_file(directory, filename).read_bytes())


def load_plan(plan_path):
    """Recheck every immutable input before starting and before each model group."""
    plan_path = Path(plan_path).resolve()
    base = plan_path.parent
    manifest = json.loads((base / "manifest.json").read_bytes())
    if manifest.get("status") != "completed":
        raise ValueError("Incomplete preparation")
    check_files(base, manifest["files"])
    plan = json.loads(plan_path.read_bytes())
    if plan.get("protocol") != PROTOCOL or plan.get("rules") != PROTOCOL_RULES:
        raise ValueError("Frozen protocol differs from this implementation")
    if plan["model"] != MODEL or plan["reasoning"] != REASONING:
        raise ValueError("Frozen model configuration differs from this adapter")
    if plan["runtime_code_sha256"] != runtime_code_hashes():
        raise ValueError("Runtime source code changed after protocol freezing")
    schema = json.loads((base / "schema.json").read_bytes())
    if schema != strict_schema(ClientJudgment.model_json_schema()):
        raise ValueError("Frozen schema differs from the current contract")
    inputs = read_inputs(base / "inputs.jsonl")
    if len(plan["cases"]) != len(inputs) or [row["input"] for row in plan["cases"]] != inputs:
        raise ValueError("Plan must cover every frozen input exactly once")
    if any(row["id"] != row["input"]["id"] for row in plan["cases"]):
        raise ValueError("Plan case ID differs from its frozen input identifier")
    if plan["partition"] != inputs[0]["partition"] or plan["max_actual_cli_calls"] != 3 * len(inputs):
        raise ValueError("Frozen partition or invocation budget differs from its cases")
    sources = {str(Path(row["source_path"]).resolve()): sha256(Path(row["source_path"])) for row in inputs}
    if sources != plan["source_sha256"]:
        raise ValueError("Local source changed after protocol freezing")
    if not re.fullmatch(r"[0-9a-f]{64}", plan["expected_gold_sha256"]):
        raise ValueError("Expected gold checksum is invalid")
    for case in plan["cases"]:
        abstract = load_packet_view(base, case["abstract_packet"])
        full = load_packet_view(base, case["full_text_packet"])
        check_packet(base, abstract, case["input"], "abstract")
        check_packet(base, full, case["input"], "full_text")
        for key, expected in (("initial_prompt", first_prompt(abstract)),
                              ("direct_template", second_template(full))):
            if relative_file(base, case[key]).read_bytes() != expected.encode("utf-8"):
                raise ValueError("Frozen prompt differs from its packet and common rules")
    return plan, manifest, schema


def inspect_receipt(packet, receipt):
    checked = inspect_answer(packet, receipt)
    response = receipt.get("response")
    if checked["validation_error"] is None and response.get("client_model") != MODEL:
        checked["validation_error"] = "client_model differs from the requested frozen model"
    return checked


def cost_summary(attempts):
    """Unknown or partially reported fields stay null, with explicit observed subtotals."""
    values = {key: [row["usage"][key] for row in attempts if isinstance(row.get("usage"), dict)
                    and isinstance(row["usage"].get(key), int) and not isinstance(row["usage"][key], bool)]
              for key in TOKEN_KEYS}
    return {"model_calls": len(attempts),
            "usage_recorded_calls": sum(isinstance(row.get("usage"), dict) for row in attempts),
            "reported_tokens": {key: sum(items) if len(items) == len(attempts) else None
                                for key, items in values.items()},
            "partial_token_subtotals": {key: sum(items) if items else None for key, items in values.items()},
            "token_reporting_calls": {key: len(items) for key, items in values.items()},
            "elapsed_seconds": sum(row["elapsed_seconds"] for row in attempts)}


def bytes_digest(value):
    return hashlib.sha256(value).hexdigest()
