"""Replay a short example through the offline MCP server in Markdown and Word."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil

from docx import Document

from academic_guardrail.core.text_extraction import read_document
from scripts.client_review_batch import call, server
from scripts.validate_local_followup import complete_packet


EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "examples"
SETTING = "Default setting."
TRAINING = "We train at batch size 4096 for 100 epochs."


def example_judgment(claim, evidence):
    """Scripted readings of the two authored SimCLR claims in the example draft."""
    if "batch size of 256" in claim:
        conclusion = "CONTRADICTED"
        reason = "The training duration matches, but the default batch size was 4096."
    elif "lasts 100 epochs" in claim:
        conclusion = "SUPPORTED"
        reason = "The duration matches the paper's default setting."
    else:
        raise ValueError(f"No example judgment for {claim!r}")
    quotes = []
    for phrase in (SETTING, TRAINING):
        unit = next(item for item in evidence if phrase in item["text"])
        quotes.append({"evidence_id": unit["id"], "quote": phrase})
    return {
        "client_model": "Scripted SimCLR example (zero model calls)",
        "conclusion": conclusion, "rationale": reason,
        "reviewed_evidence_ids": [f"{evidence[0]['id']}-{evidence[-1]['id']}"],
        "quotes": quotes,
        "checks": {"subject": "SimCLR.", "relation": "Training configuration.",
                   "numbers": "4096 per batch and 100 epochs.", "scope": "Default setting.",
                   "counterevidence": "A batch size tested elsewhere does not establish the default."},
    }


async def review_draft(draft: Path, refs: Path, source: Path, output: Path) -> dict:
    output.mkdir()
    original = read_document(str(source))
    saved = []
    with (output / "transcript.jsonl").open("x", encoding="utf-8") as log:
        async with server(output, output) as session:
            inputs = {"file_path": str(draft), "refs_dir": str(refs), "offline": True}
            if draft.suffix == ".md":
                queue = await call(session, "prepare_manuscript_review", inputs, log)
            else:
                queue = await call(session, "audit_document_claims", {**inputs, "client_review": True}, log)
                if "occurrences" not in queue:
                    queue = json.loads(queue["result"])
            rows = queue["occurrences"]
            assert queue["total_references"] == 3 and len(rows) == 4
            assert [row["citation_id"] for row in rows] == ["cit_1", "cit_1", "cit_2", "cit_3"]
            assert [row["claim"] for row in rows[:2]] == [
                "SimCLR uses a default batch size of 256 for 100 epochs [1].",
                "The default SimCLR training run lasts 100 epochs [1].",
            ]
            assert [row["state"] for row in rows] == ["PENDING", "PENDING", "BLOCKED", "BLOCKED"]
            assert rows[2]["retraction_status"] == "CONFIRMED"
            assert rows[0]["packet_id"] != rows[1]["packet_id"]
            for row in rows[:2]:
                first = await call(session, "read_claim_evidence", {"packet_id": row["packet_id"]}, log)
                assert first["packet_sha256"] == row["packet_sha256"]
                packet = await complete_packet(session, first, log)
                judgment = example_judgment(row["claim"], packet["evidence"])
                record = await call(session, "record_claim_review", {
                    "packet_id": row["packet_id"], "expected_packet_sha256": row["packet_sha256"],
                    "judgment": judgment}, log)
                for quote in record["quotes"]:
                    location = quote["location"]
                    assert Path(location["file_path"]) == source
                    assert original.text[location["char_start"]:location["char_end"]] == quote["quote"]
                    if source.suffix == ".pdf":
                        assert location["page"] == 3
                saved.append({"occurrence_id": row["occurrence_id"], "review_id": record["review_id"],
                              "conclusion": judgment["conclusion"], "quotes": record["quotes"]})
            report = await call(session, "generate_manuscript_review_report", {
                "manuscript_id": queue["manuscript_id"], "output_path": str(output / "report.html")}, log)
    assert report["reviewed_count"] == 2 and report["blocked_count"] == 2 and report["pending_count"] == 0
    html = (output / "report.html").read_text(encoding="utf-8")
    assert TRAINING in html and "10.1038/nature12968" in html
    second = html.split("data-occurrence-id='occ_2'", 1)[1].split("</article>", 1)[0]
    assert second.index("SUPPORTED") < second.index(TRAINING) < second.index("本地规则与文献元数据")
    assert 'id="review-filter"' in html
    return {"format": draft.suffix, "report": report["output_path"], "occurrences": len(rows),
            "reviewed": saved, "blocked": [{"occurrence_id": row["occurrence_id"], "reason": row["reason"]}
                                          for row in rows if row["state"] == "BLOCKED"]}


async def validate(output: Path, pdf: Path | None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    refs = output / "references"
    refs.mkdir()
    reference = pdf if pdf else EXAMPLES / "manuscript_refs" / "simclr.txt"
    source = refs / reference.name
    shutil.copyfile(reference, source)
    markdown = output / "draft.md"
    shutil.copyfile(EXAMPLES / "manuscript_review.md", markdown)
    docx = output / "draft.docx"
    document = Document()
    body, bibliography = markdown.read_text(encoding="utf-8").split("## References\n", 1)
    for line in body.splitlines():
        if line.strip():
            document.add_paragraph(line.lstrip("# "))
    document.add_heading("References", level=2)
    for entry in bibliography.splitlines():
        if entry.strip():
            # Word displays its own list number. Only the reference text is stored in the paragraph.
            _, _, text = entry.partition("] ")
            assert text, f"Expected a numbered reference in the Markdown fixture: {entry}"
            document.add_paragraph(text, style="List Number")
    document.save(docx)
    results = []
    for draft in (markdown, docx):
        results.append(await review_draft(draft, refs, source, output / draft.suffix[1:]))
    summary = {"type": "scripted_workflow_validation", "model_calls": 0, "drafts": results}
    (output / "validation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new directory for reports and transcripts")
    parser.add_argument("--simclr-pdf", type=Path, help="Use the original arXiv:2002.05709v3 PDF instead of the short excerpt")
    args = parser.parse_args()
    result = asyncio.run(validate(args.output.resolve(), args.simclr_pdf))
    for draft_result in result["drafts"]:
        print(draft_result["report"])
