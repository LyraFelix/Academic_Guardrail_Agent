"""Replay the 90 authored local reviews against their frozen paper and query bytes.

Run from a source checkout with its src directory on PYTHONPATH. All rankings
receive only the parser's passages and the historical search terms. Archived
judgments and witness offsets are used only for checking the returned evidence.
"""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
from importlib.util import find_spec
from io import StringIO
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from academic_guardrail.core.claim_checks.text import sentence_units
from academic_guardrail.core import local_evidence
from academic_guardrail.core.local_review import _already_covered, _evidence_key
from academic_guardrail.core.models import EvidencePassage, PaperRecord
from academic_guardrail.core.passages import locate_excerpt
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.review_models import ReviewEvidence
from academic_guardrail.core.review_store import content_digest


CONFIG = Path(__file__).with_name("manuscript_retrieval_witnesses.json")
PARTITIONS = ("development", "validation_a", "validation_b")
NEI = "NOT_ENOUGH_EVIDENCE"


def require(value, message):
    if not value:
        raise ValueError(message)


def index_by_id(rows):
    indexed = {row["id"]: row for row in rows}
    require(len(indexed) == len(rows), "Duplicate case ID")
    return indexed


class Archive:
    """Check the original delivery chain, retaining the digest of every input read."""

    def __init__(self, root, manifest_digest):
        self.root = root
        self.expected = {"final_delivery_manifest_02.json": manifest_digest}
        self.used = {}
        self.expected.update(self.json("final_delivery_manifest_02.json")["evidence_sha256"])

    def read(self, name):
        raw = (self.root / name).read_bytes()
        digest = sha256(raw).hexdigest()
        expected = self.expected.get(name)
        require(expected is None or digest == expected, f"Archive hash differs: {name}")
        self.used[name] = digest
        return raw

    def json(self, name):
        return json.loads(self.read(name))

    def packet(self, partition, row):
        identifier = row["packet_id"]
        path = f"runs_02/{partition}/runtime/stored/{identifier}.packet.json"
        envelope = self.json(path)
        value = envelope["packet"]
        require(value["packet_id"] == identifier and
                content_digest(value) == envelope["sha256"] == row["packet_sha256"],
                f"Different stored packet: {path}")
        return value


@dataclass
class Paper:
    record: PaperRecord
    extracted: str
    mapping: dict
    identity: dict

    def span(self, start, end):
        """Map one exact nonempty source span to canonical lines and PDF pages."""
        text = self.record.fulltext
        require(0 <= start < end <= len(text), "Invalid source coordinates")
        for block in self.mapping["copied_blocks"]:
            if block["canonical_start"] <= start and end <= block["canonical_end"]:
                pdf_start = block["pdf_text_start"] + start - block["canonical_start"]
                pdf_end = pdf_start + end - start
                require(self.extracted[pdf_start:pdf_end] == text[start:end],
                        "Source span differs from the copied PDF text")
                pages = self.mapping["page_starts_in_pdf_text"]
                return {"canonical_start": start, "canonical_end": end,
                        "line_start": text.count("\n", 0, start) + 1,
                        "line_end": text.count("\n", 0, end - 1) + 1,
                        "pdf_text_start": pdf_start, "pdf_text_end": pdf_end,
                        "pdf_page_start": bisect_right(pages, pdf_start),
                        "pdf_page_end": bisect_right(pages, pdf_end - 1)}
        raise ValueError("Span crosses an unmapped canonical separator")


def read_papers(archive, freeze):
    manifest_path = "materials/canonical_manifest.json"
    archive.expected[manifest_path] = freeze["canonical_manifest_sha256"]
    papers, corpus = {}, []
    for item in archive.json(manifest_path):
        paper_id = item["paper_id"]
        canonical = f"materials/refs/{paper_id}.txt"
        extracted = f"materials/extracted/{paper_id}.txt"
        pdf = f"materials/originals/{paper_id}.pdf"
        for name, field in [(canonical, "canonical"), (extracted, "extraction"), (pdf, "pdf")]:
            archive.expected[name] = item[field]["sha256"]
        archive.read(pdf)
        raw = archive.read(canonical)
        extracted_text = archive.read(extracted).decode("utf-8")
        mapping = archive.json(f"materials/maps/{paper_id}_map.json")
        require(mapping["paper_id"] == paper_id and
                mapping["page_starts_in_pdf_text"] == item["extraction"]["page_starts"],
                "Incorrect page map")
        record = LocalRefStore().extract_paper_record(str(archive.root / canonical), source_bytes=raw)
        require(record and record.title == item["title"] and record.doi == item["doi"].lower()
                and record.fulltext == raw.decode("utf-8"), f"Paper binding differs for {paper_id}")
        # A relocated archive still has its historical path in every stored evidence record.
        archived_path = item["canonical"]["path"]
        for location in [record.abstract_location, *(p.location for p in record.passages)]:
            location.file_path = archived_path
        identity = {"paper_id": paper_id, "version": item["version"], "doi": item["doi"],
                    "canonical_sha256": archive.used[canonical], "pdf_sha256": archive.used[pdf]}
        paper = papers[paper_id] = Paper(record, extracted_text, mapping, identity)
        passages = []
        for i, p in enumerate(record.passages):
            span = paper.span(p.location.char_start, p.location.char_end)
            require(record.fulltext[p.location.char_start:p.location.char_end] == p.text,
                    f"Passage differs from source: {paper_id}:{i}")
            passages.append({"index": i, **span, "text": p.text})
        corpus.append({**identity, "canonical_file": canonical, "passages": passages})
    require(len(papers) == freeze["papers"] == 15, "Incomplete corpus")
    return papers, corpus


def merge_evidence(parent, passages):
    """Apply the service's source sentence boundaries and parent-span deduplication."""
    result = list(parent)
    seen = {_evidence_key(unit) for unit in parent}
    for passage in passages:
        for sentence in sentence_units(passage.text, split_semicolons=False):
            unit = ReviewEvidence(id=f"e{len(result) + 1}", text=sentence.text,
                                  source_kind=passage.source_kind,
                                  location=locate_excerpt(passage, sentence.text, offset=sentence.start))
            key = _evidence_key(unit)
            if key not in seen and not _already_covered(unit, parent):
                result.append(unit)
                seen.add(key)
    return result


def dump_evidence(units):
    return [unit.model_dump(mode="json") for unit in units]


def span_covered(text, units, span):
    """Count all nonwhitespace characters, permitting adjacent source sentence units."""
    start, end = span["canonical_start"], span["canonical_end"]
    covered = bytearray(end - start)
    for unit in units:
        left, right = max(start, unit.location.char_start), min(end, unit.location.char_end)
        if left < right:
            covered[left - start:right - start] = b"\x01" * (right - left)
    return all(flag or char.isspace() for flag, char in zip(covered, text[start:end]))


def witnesses(case_id, gold, paper, audit, prior, detail, config):
    def checked(start, end, quote):
        span = paper.span(start, end)
        require(paper.record.fulltext[start:end] == quote, f"Wrong witness: {case_id}")
        return {**span, "text": quote}

    start, end = gold["canonical_start"], gold["canonical_end"]
    anchor = checked(start, end, gold["evidence_quote"])
    require((anchor["pdf_page_start"], anchor["pdf_text_start"], anchor["pdf_text_end"]) ==
            (gold["pdf_page"], gold["pdf_text_start"], gold["pdf_text_end"]), "Wrong gold PDF range")
    all_spans = {"anchor": anchor}
    if gold["fulltext_label"] == NEI:
        return all_spans, []
    if case_id in config["primary_loss_groups"]:
        groups = config["primary_loss_groups"][case_id]
        all_spans["decision"] = checked(prior["deciding_canonical_start"], prior["deciding_canonical_end"],
                                        prior["deciding_exact_quote"])
    else:
        groups = [["anchor"], *config["old_alternative_groups"].get(case_id, [])]
    for key in sorted({key for group in groups for key in group} - all_spans.keys()):
        arm, unit_id = key.split(":")
        if arm == "local":
            unit = next(v for v in audit["packet_evidence"] if v["id"] == unit_id)
            location = unit["location"]
            all_spans[key] = checked(location["char_start"], location["char_end"], unit["text"])
        else:
            quote = next(v for v in detail["responses"][arm]["quotes"] if v["evidence_id"] == unit_id)
            location = quote["provenance"]
            all_spans[key] = checked(location["canonical_start"], location["canonical_end"], quote["quote"])
    return all_spans, groups


def mode_result(parent, paper, terms, mode, max_hits, cap, spans, groups, old_quotes):
    source = paper.record
    if terms:
        selection = local_evidence.select_local_passages(source.passages, terms, mode=mode, max_hits=max_hits)
        ranked, hits, context = (list(selection.ranked_indices), list(selection.hit_indices),
                                  list(selection.context_indices))
        selected = [source.passages[i] for i in context]
        chars = sum(len(p.text) for p in selected)
        require(len(hits) <= max_hits and chars == selection.character_count <= cap and
                set(hits) <= set(context) and context == sorted(set(context)),
                "Lookup exceeded the agreed budget or repeated its context")
        units = merge_evidence(parent, selected)
    else:
        ranked, hits, context, chars, units = [], [], [], 0, parent
    coverage = {key: span_covered(source.fulltext, units, span) for key, span in spans.items()}
    anchor = spans["anchor"]
    anchor_passages = [i for i, p in enumerate(source.passages)
                       if max(anchor["canonical_start"], p.location.char_start) <
                       min(anchor["canonical_end"], p.location.char_end)]
    old_quote_flags = [span_covered(source.fulltext, units, q) for q in old_quotes]
    old_alternatives = [g for g in groups if all(k.startswith("local:") for k in g)]
    alternative = any(all(coverage[k] for k in g) for g in old_alternatives)
    added = units[len(parent):]
    return {"ranked_indices": ranked, "hit_indices": hits, "context_indices": context,
            "anchor_passage_ranks": {i: ranked.index(i) + 1 if i in ranked else None for i in anchor_passages},
            "context_characters": chars, "added_unit_characters": sum(len(u.text) for u in added),
            "packet_unit_characters": sum(len(u.text) for u in units),
            "packet_units": len(units), "added_units": len(added),
            "packet_evidence_sha256": content_digest(dump_evidence(units)),
            "witness_covered": coverage,
            "audited_old_alternative_group": alternative if old_alternatives else None,
            "anchor_or_audited_old_alternative": (coverage["anchor"] or alternative) if groups else None,
            "complete_witness_group": any(all(coverage[k] for k in g) for g in groups) if groups else None,
            "old_citation_covered": old_quote_flags}, units


def replay_case(archive, paper, case, gold, audit, initial_row, final_row, historical, config):
    case_id, partition = case["id"], audit["partition"]
    prior, detail, quotes = historical
    terms = case["query_terms"]
    parent_packet = archive.packet(partition, initial_row)
    final = archive.packet(partition, final_row)
    require(final["claim"] == parent_packet["claim"] == audit["claim"] and
            final["evidence"] == audit["packet_evidence"] and
            final_row["prediction"] == audit["prediction"] and
            gold["source_pdf_sha256"] == paper.identity["pdf_sha256"] and
            gold["source_version"] == paper.identity["version"] and
            audit["gold"] == gold["fulltext_label"] and terms == audit["query_terms"],
            f"Archived joins disagree for {case_id}")
    context_path = f"runs_02/{partition}/runtime/stored/{final_row['packet_id']}.context.json"
    envelope = archive.json(context_path)
    context = envelope["context"]
    require(content_digest(context) == envelope["sha256"] and
            context["packet_sha256"] == final_row["packet_sha256"] and
            context["source"]["sha256"] == paper.identity["canonical_sha256"] and
            context["source"]["text_sha256"] == sha256(paper.record.fulltext.encode()).hexdigest() and
            bool(terms) == case["lookup_requested"] == bool(context["round"]),
            f"Source or lookup status differs for {case_id}")
    if terms:
        require(terms == context["gap"]["search_terms"] == context["query_terms"] and
                context["gap"] in case["initial_record"]["judgment"]["missing_evidence"] and
                context["parent_review_id"] == case["initial_record"]["review_id"],
                f"Query does not come from the saved gap for {case_id}")
    else:
        require(parent_packet["packet_id"] == final["packet_id"], f"Carried packet changed: {case_id}")
    parent = merge_evidence([], [EvidencePassage(text=paper.record.abstract, source_kind="LOCAL_ABSTRACT",
                                                 location=paper.record.abstract_location)])
    require(dump_evidence(parent) == parent_packet["evidence"], f"Abstract evidence drift: {case_id}")
    old_quotes = []
    require(len(quotes) == len(audit["quotes"]), f"Missing historical citations: {case_id}")
    for q in quotes:
        start, end = q["canonical_start"], q["canonical_end"]
        span = paper.span(start, end)
        require(q["quote"] == paper.record.fulltext[start:end] and
                (q["pdf_text_start"], q["pdf_text_end"]) == (span["pdf_text_start"], span["pdf_text_end"]),
                f"Historical citation failed provenance: {case_id}")
        old_quotes.append({**span, "evidence_id": q["evidence_id"], "text": q["quote"]})
    spans, groups = witnesses(case_id, gold, paper, audit, prior, detail, config)
    modes = {}
    for mode in config["modes"]:
        result, evidence = mode_result(parent, paper, terms, mode, config["max_hits"],
                                       config["character_cap"], spans, groups, old_quotes)
        modes[mode] = result
        if mode == "original":
            added = [unit.id for unit in evidence[len(parent):]]
            require(dump_evidence(evidence) == final["evidence"] and
                    added == case["added_evidence_ids"] == audit["added_evidence_ids"] and
                    all(result["old_citation_covered"]) and
                    result["witness_covered"]["anchor"] == audit["reference_anchor_currently_covered"],
                    f"Original packet replay drift: {case_id}")
            if terms:
                status = "ADDED" if added else "NO_NEW_EVIDENCE" if result["hit_indices"] else "NO_MATCH"
                require(len(result["hit_indices"]) == context["matched_passages"] and
                        len(paper.record.passages) == context["total_passages"] and
                        status == context["retrieval_status"] == case["retrieval_status"],
                        f"Original search count or status drift: {case_id}")
                if detail:
                    historic = detail["frozen_rank_diagnostic"]
                    require(result["hit_indices"] == historic["selected_hit_indices"] and
                            result["context_indices"] == historic["selected_context_indices"],
                            f"Historic reconstructed context differs: {case_id}")
    return {"id": case_id, "partition": partition, **paper.identity, "claim": audit["claim"],
            "fulltext_reference": gold["fulltext_label"], "abstract_reference": gold["abstract_only_label"],
            "reference_evidence_role": gold["evidence_role"], "query_terms": terms,
            "lookup_requested": case["lookup_requested"], "old_lookup_status": case["retrieval_status"],
            "historical_prediction": audit["prediction"], "historical_raw_correct": audit["raw_correct"],
            "historical_usable": audit["usable"], "historical_error": audit["validation_error"],
            "historical_audit_group": prior.get("group"), "historical_audit_cause": prior.get("cause"),
            "stored_parent_id": parent_packet["packet_id"], "stored_parent_sha256": initial_row["packet_sha256"],
            "stored_final_id": final["packet_id"], "stored_final_sha256": final_row["packet_sha256"],
            "original_evidence_identical": True, "stored_evidence_sha256": content_digest(final["evidence"]),
            "witnesses": spans, "sufficient_groups_for_proxy": groups, "old_citations": old_quotes,
            "modes": modes}


def load_cases(archive, papers, freeze, config):
    provenance_receipt = archive.json("review/results_source_audit_02_receipt.json")
    archive.expected.update({f"review/{k}": v for k, v in provenance_receipt["artifacts_sha256"].items()})
    review = archive.json("review/results_source_audit_02_data.json")
    verdicts = index_by_id(archive.json("review/results_source_audit_02_verdicts.json")["verdicts"])
    details = index_by_id(review["selected_cases"])
    for group, key in [("primary_loss", "primary_loss_groups"),
                       ("correct_concrete_without_authored_anchor", "old_alternative_groups")]:
        require({k for k, row in verdicts.items() if row["group"] == group} == set(config[key]),
                f"Witness map disagrees with archived adjudication: {group}")
    quotes = defaultdict(list)
    for quote in review["all_local_quote_provenance"]:
        quotes[quote["id"]].append(quote)
    audit = index_by_id(archive.json("scores_02/local_source_audit.json"))
    table = index_by_id(list(csv.DictReader(StringIO(archive.read("presentation_02/case_review.csv")
                                                      .decode("utf-8-sig")))))
    result = []
    for partition in PARTITIONS:
        path = f"runs_02/{partition}"
        manifest = archive.json(f"{path}/manifest.json")
        require(manifest["status"] == "completed" and manifest["completed_cases"] == 30,
                f"Incomplete archived run: {partition}")
        archive.expected.update({f"{path}/{k}": v for k, v in manifest["files"].items()})
        plan = archive.json(f"{path}/plan.json")
        require(plan["partition"] == partition and plan["code"]["git_commit"] == freeze["git_commit"],
                "Wrong original runtime")
        gold_path = f"materials/sealed/{partition}_gold.jsonl"
        archive.expected[gold_path] = plan["expected_gold_sha256"]
        gold = index_by_id([json.loads(line) for line in archive.read(gold_path).splitlines()])
        rows = archive.json(f"{path}/rows.json")
        initial = index_by_id([r for r in rows if r["arm"] == "abstract_only"])
        local = index_by_id([r for r in rows if r["arm"] == "local_followup"])
        cases = index_by_id(archive.json(f"{path}/cases.json"))
        require(cases.keys() == gold.keys() == initial.keys() == local.keys() == index_by_id(plan["cases"]).keys(),
                f"Unequal case IDs: {partition}")
        for case_id, case in cases.items():
            source_audit, reference, table_row = audit[case_id], gold[case_id], table[case_id]
            require(source_audit["paper_id"] == reference["paper_id"] == table_row["paper_id"] and
                    table_row["claim"] == source_audit["claim"] and table_row["partition"] == partition and
                    table_row["local_followup"] == source_audit["prediction"], f"Case table differs: {case_id}")
            historical = verdicts.get(case_id, {}), details.get(case_id, {}), quotes[case_id]
            result.append(replay_case(archive, papers[reference["paper_id"]], case, reference,
                                      source_audit, initial[case_id], local[case_id], historical, config))
    require(index_by_id(result).keys() == table.keys() == audit.keys() and
            len(result) == freeze["cases"] == 90, "Wrong 90-case cohort")
    return result


def summarize_slice(rows, mode):
    decidable = [r for r in rows if r["fulltext_reference"] != NEI]
    old_alternatives = [r for r in rows if r["modes"]["original"]["audited_old_alternative_group"] is not None]

    def diff(key, cohort):
        gains, losses = [], []
        for r in cohort:
            before, after = key(r["modes"]["original"]), key(r["modes"][mode])
            if before != after:
                (gains if after else losses).append(r["id"])
        return {"count": sum(bool(key(r["modes"][mode])) for r in cohort), "denominator": len(cohort),
                "gained_ids": gains, "lost_ids": losses}

    selected = [r["modes"][mode] for r in rows]
    lookup_chars = [r["modes"][mode]["context_characters"] for r in rows if r["lookup_requested"]]
    deltas = [r["modes"][mode]["context_characters"] - r["modes"]["original"]["context_characters"]
              for r in rows if r["lookup_requested"]]
    return {"cases": len(rows),
            "authored_anchor_any_label": diff(lambda m: m["witness_covered"]["anchor"], rows),
            "authored_decidable_anchor": diff(lambda m: m["witness_covered"]["anchor"], decidable),
            "audited_old_alternative_group": diff(lambda m: m["audited_old_alternative_group"], old_alternatives),
            "anchor_or_audited_old_alternative": diff(lambda m: m["anchor_or_audited_old_alternative"], decidable),
            "decidable_witness": diff(lambda m: m["complete_witness_group"], decidable),
            "all_old_citations": diff(lambda m: all(m["old_citation_covered"]), rows),
            "old_citations_covered": sum(sum(m["old_citation_covered"]) for m in selected),
            "old_citations_total": sum(len(m["old_citation_covered"]) for m in selected),
            "context_characters": sum(lookup_chars),
            "median_characters_per_lookup": median(lookup_chars) if lookup_chars else None,
            "max_characters_per_lookup": max(lookup_chars, default=0),
            "character_change_vs_original": {"total": sum(deltas), "increased": sum(x > 0 for x in deltas),
                                             "unchanged": deltas.count(0), "decreased": sum(x < 0 for x in deltas)},
            "added_unit_characters": sum(m["added_unit_characters"] for m in selected),
            "packet_unit_characters": sum(m["packet_unit_characters"] for m in selected)}


def summarize(rows, config):
    slices = {"all": rows, "lookup": [r for r in rows if r["lookup_requested"]],
              "carried": [r for r in rows if not r["lookup_requested"]],
              "prior_misses": [r for r in rows if not r["historical_raw_correct"]],
              "prior_correct": [r for r in rows if r["historical_raw_correct"]],
              "prior_usable_correct": [r for r in rows if r["historical_raw_correct"] and r["historical_usable"]],
              "prior_correct_concrete": [r for r in rows if r["historical_raw_correct"] and r["fulltext_reference"] != NEI],
              "prior_usable_correct_concrete": [r for r in rows if r["historical_raw_correct"]
                                                and r["historical_usable"] and r["fulltext_reference"] != NEI],
              "six_alternatives": [r for r in rows if r["id"] in config["old_alternative_groups"]],
              "true_nei": [r for r in rows if r["fulltext_reference"] == NEI],
              "body_required": [r for r in rows if r["abstract_reference"] == NEI and r["fulltext_reference"] != NEI],
              "abstract_decidable": [r for r in rows if r["abstract_reference"] != NEI]}
    slices.update({name: [r for r in rows if r["partition"] == name] for name in PARTITIONS})
    slices["historical_validation"] = slices["validation_a"] + slices["validation_b"]
    summary = {name: {mode: summarize_slice(members, mode) for mode in config["modes"]}
               for name, members in slices.items()}
    return {"model_calls": 0, "new_semantic_judgments": 0,
            "historical_predictions": dict(Counter(r["historical_prediction"] for r in rows)),
            "case_count": len(rows), "original_identical": sum(r["original_evidence_identical"] for r in rows),
            "slices": summary}


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())


def write_rows(path, values):
    with path.open("xb") as out:
        for row in values:
            out.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode())


def runtime_hashes():
    """Bind the source reader, including its lazy Word list/heading helper, without loading it."""
    modules = ("claim_checks.text", "docx_numbering", "local_evidence", "local_review", "models", "passage_ranking",
               "passage_structure", "passages", "ref_store", "review_models", "review_store",
               "search_view", "text_extraction")
    hashes = {}
    for name in modules:
        spec = find_spec(f"academic_guardrail.core.{name}")
        require(spec is not None and spec.origin is not None, f"Missing replay source module: {name}")
        hashes[name] = sha256(Path(spec.origin).read_bytes()).hexdigest()
    return hashes


def run(archive_path, output):
    archive_path, output = archive_path.resolve(), output.resolve()
    if output == archive_path or archive_path in output.parents:
        raise ValueError("Write replay results to a new directory outside the frozen archive")
    if output.exists():
        raise FileExistsError(f"Replay destination already exists: {output}")
    config_bytes = CONFIG.read_bytes()
    config, runtime = json.loads(config_bytes), runtime_hashes()
    runner_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    require(config["character_cap"] == local_evidence.MAX_NEW_CHARACTERS, "Runtime character budget differs")
    archive = Archive(archive_path, config["archive_manifest_sha256"])
    freeze = archive.json("study_freeze_02.json")
    papers, corpus = read_papers(archive, freeze)
    rows = load_cases(archive, papers, freeze, config)
    summary = summarize(rows, config)
    require(runtime == runtime_hashes() and CONFIG.read_bytes() == config_bytes and
            runner_hash == sha256(Path(__file__).read_bytes()).hexdigest(), "Replay code changed during execution")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".retrieval-") as temp:
        staged = Path(temp) / "complete"
        staged.mkdir()
        write_rows(staged / "corpus.jsonl", corpus)
        write_rows(staged / "cases.jsonl", rows)
        write_json(staged / "summary.json", summary)
        outputs = {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(staged.iterdir())}
        write_json(staged / "manifest.json", {"model_calls": 0, "new_semantic_judgments": 0,
                   "original_runtime_commit": freeze["git_commit"], "config": config,
                   "config_sha256": sha256(config_bytes).hexdigest(), "replay_sha256": runner_hash,
                   "runtime": runtime, "inputs": dict(sorted(archive.used.items())), "outputs": outputs})
        staged.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="Completed Terra/max v3 evaluation archive")
    parser.add_argument("--output", type=Path, required=True, help="New directory outside the frozen input archive")
    args = parser.parse_args()
    summary = run(args.archive, args.output)
    print(json.dumps({key: summary[key] for key in ("case_count", "original_identical", "model_calls")}))


if __name__ == "__main__":
    main()
