"""Scripted client decisions exercise provenance and HTML, not the accuracy of a model."""

import hashlib
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from academic_guardrail import mcp_server as mcp
from academic_guardrail.core.manuscript_report import save_manuscript_report
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.review_store import ReviewStore
from tests.test_claim_review import judgment
from tests.test_local_followup import PAPER


@pytest.fixture
def draft(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    source = refs / "study.txt"
    source.write_text(PAPER, encoding="utf-8")
    document = tmp_path / "draft.md"
    document.write_text("The treatment reduced mortality by 25% [1].\n\n" * 2
                        + "This marker has no bibliography entry [3].\n\nAn earlier study [2].\n\n"
                        + "A paper without a local file [4].\n\n## References\n"
                        + "[1] Jane Doe. Local Follow-up Study[J]. 2024. doi: 10.1234/local-study\n"
                        + "[2] H Obokata. Stimulus-triggered fate conversion of somatic cells into pluripotency[J]. 2014. doi: 10.1038/nature12968\n"
                        + "[4] Smith. Missing Paper[J]. 2024. doi: 10.4321/not-here\n"
                        + "[5] Smith. Uncited Bibliography Item[J]. 2024. doi: 10.4321/uncited\n", encoding="utf-8")
    return document, refs, source


async def save_row(row, **changes):
    packet = ReviewStore().load_packet(row["packet_id"])
    unit = next((item for item in packet.evidence if "mortality was reduced" in item.text), packet.evidence[0])
    fields = {"quotes": [{"evidence_id": unit.id, "quote": unit.text}], **changes}
    return await mcp.record_claim_review(packet.packet_id, judgment(packet, **fields), row["packet_sha256"])


@pytest.mark.asyncio
async def test_invalid_report_target_leaves_no_manuscript_packets(draft, tmp_path):
    document, refs, _ = draft
    existing = tmp_path / "previous.html"
    existing.write_text("First report", encoding="utf-8")
    for target in (tmp_path / "report.txt", existing, tmp_path / "absent" / "report.html"):
        with pytest.raises(ToolError):
            await mcp.audit_document_claims(str(document), str(refs), output_html_path=str(target),
                                            offline=True, client_review=True)
    assert existing.read_text(encoding="utf-8") == "First report"
    assert not list((tmp_path / "claim_reviews").rglob("*.json"))


@pytest.mark.asyncio
async def test_default_full_text_queue_and_mixed_report(draft, tmp_path, monkeypatch):
    document, refs, source = draft
    scanned = []
    extract = LocalRefStore.extract_paper_record

    def count_extract(self, path, **kwargs):
        scanned.append(Path(path))
        return extract(self, path, **kwargs)

    monkeypatch.setattr(LocalRefStore, "extract_paper_record", count_extract)
    output = tmp_path / "final.html"
    queue = json.loads(await mcp.audit_document_claims(str(document), str(refs), output_html_path=str(output),
                                                      offline=True, client_review=True))
    assert scanned == [source]
    assert not output.exists() and queue["initial_scope"] == "full_text"
    assert queue["manuscript_sha256"] == hashlib.sha256(document.read_bytes()).hexdigest()
    one, two, missing, retracted, no_file = queue["occurrences"]
    assert one["claim"] == two["claim"] and one["location"] != two["location"] and one["packet_id"] != two["packet_id"]
    assert retracted["state"] == "BLOCKED" and retracted["retraction_status"] == "CONFIRMED"
    assert "MISSING" in missing["reason"] and "OFFLINE_NO_MATCH" in no_file["reason"]
    assert retracted["packet_id"] is None and missing["packet_id"] is None
    saved = await save_row(one, rationale="Fixture <script>client()</script>.")
    result = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(output))
    assert (result["reviewed_count"], result["pending_count"], result["blocked_count"]) == (1, 1, 3)
    assert [row["state"] for row in result["occurrences"]] == ["REVIEWED", "PENDING", "BLOCKED", "BLOCKED", "BLOCKED"]
    assert result["occurrences"][0]["review_id"] == saved["review_id"]
    html = output.read_text(encoding="utf-8")
    quote = saved["quotes"][0]
    span = quote["location"]
    assert source.read_text(encoding="utf-8")[span["char_start"]:span["char_end"]] == quote["quote"]
    for value in (quote["quote"], f"字符 [{span['char_start']}, {span['char_end']})", "SUPPORTED", "CONFIRMED",
                  "UNRESOLVED_CITATION", "Uncited Bibliography Item", "&lt;script&gt;client()&lt;/script&gt;"):
        assert value in html
    assert "<script>client()</script>" not in html
    for row in queue["occurrences"]:
        assert html.count(f"data-occurrence-id='{row['occurrence_id']}'") == 1
    with pytest.raises(ToolError):
        await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(output))
    for unsafe in (document, source, tmp_path / "paper.txt:report.html"):
        with pytest.raises(ToolError):
            await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(unsafe))


@pytest.mark.asyncio
async def test_crosswiring_repeated_claims_sessions_and_followups_is_rejected(draft, tmp_path):
    document, refs, _ = draft
    queue = await mcp.prepare_manuscript_review(str(document), str(refs), "abstract")
    one, two = queue["occurrences"][:2]
    before = await save_row(one, conclusion="NOT_ENOUGH_EVIDENCE", missing_evidence=[{
        "kind": "RESULT", "claim_part": "mortality", "question": "What result was reported?", "search_terms": ["mortality"]}])
    child = await mcp.follow_up_local_claim(before["review_id"], before["review_sha256"])
    midway = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "midway.html"))
    assert midway["pending_followup_count"] == 1 and midway["occurrences"][0]["review_id"] == before["review_id"]
    assert midway["occurrences"][0]["followup"]["packet_id"] == child["packet_id"]
    after = await save_row(child)
    other_queue = await mcp.prepare_manuscript_review(str(document), str(refs), "abstract")
    foreign = await save_row(other_queue["occurrences"][0])
    for selection in ({two["occurrence_id"]: after["review_id"]}, {one["occurrence_id"]: foreign["review_id"]},
                      {"occ_9999": before["review_id"]}):
        with pytest.raises(ToolError, match="occurrence"):
            await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "bad.html"), selection)
    assert not (tmp_path / "bad.html").exists()
    report = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "good.html"))
    row = report["occurrences"][0]
    assert row["review_id"] == after["review_id"] and set(row["review_ids"]) == {before["review_id"], after["review_id"]}
    assert row["followup"]["status"] == "REVIEWED" and report["pending_followup_count"] == 0
    html = Path(report["output_path"]).read_text(encoding="utf-8")
    assert "初次审查" in html and "追补后审查" in html and foreign["review_id"] not in html


@pytest.mark.asyncio
async def test_independent_reviews_require_an_explicit_preference(draft, tmp_path):
    document, refs, _ = draft
    queue = await mcp.prepare_manuscript_review(str(document), str(refs))
    row = queue["occurrences"][0]
    first = await save_row(row)
    second = await save_row(row, conclusion="UNCERTAIN")
    report = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "both.html"))
    competing = report["occurrences"][0]
    assert competing["state"] == "MULTIPLE_REVIEWS" and competing["conclusion"] is None
    assert report["multiple_review_count"] == 1 and report["reviewed_count"] == 0
    report = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "selected.html"),
                                                        {row["occurrence_id"]: first["review_id"]})
    assert report["occurrences"][0]["conclusion"] == "SUPPORTED" and report["reviewed_count"] == 1
    assert second["review_id"] in (tmp_path / "selected.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["manuscript", "paper"])
async def test_changed_files_keep_history_and_block_new_judgments(draft, tmp_path, changed):
    document, refs, source = draft
    queue = await mcp.prepare_manuscript_review(str(document), str(refs))
    one, two = queue["occurrences"][:2]
    saved = await save_row(one)
    (document if changed == "manuscript" else source).write_text("Replaced content.", encoding="utf-8")
    with pytest.raises(ToolError, match="CHANGED"):
        await save_row(two)
    report = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "historical.html"))
    assert report["occurrences"][0]["state"] == "REVIEWED" and report["occurrences"][1]["state"] == "BLOCKED"
    assert (report["manuscript_status"] if changed == "manuscript" else report["occurrences"][0]["source_status"]) == "CHANGED"
    assert saved["quotes"][0]["quote"] in (tmp_path / "historical.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_interrupted_record_is_invisible_to_concurrent_export_and_can_be_retried(draft, tmp_path, monkeypatch):
    document, refs, _ = draft
    queue = await mcp.prepare_manuscript_review(str(document), str(refs))
    store = ReviewStore()

    def interrupt_record(content, handle, **kwargs):
        handle.write('{"incomplete":')
        handle.flush()
        # Observe from another reader while the destination file is being written.
        report = save_manuscript_report(store, queue["manuscript_id"], str(tmp_path / "during.html"))
        assert report["reviewed_count"] == 0 and report["pending_count"] == 2
        raise OSError("interrupted write")

    with monkeypatch.context() as patch:
        patch.setattr("academic_guardrail.core.review_store.json.dump", interrupt_record)
        with pytest.raises(OSError, match="interrupted write"):
            await save_row(queue["occurrences"][0])
    assert not store.manuscript_review_ids(queue["manuscript_id"])
    assert not list(store.directory.rglob("*.tmp"))
    saved = await save_row(queue["occurrences"][0])
    assert store.manuscript_review_ids(queue["manuscript_id"]) == [saved["review_id"]]


@pytest.mark.asyncio
async def test_ambiguous_and_unreadable_sources_remain_visible(draft, tmp_path):
    document, refs, source = draft
    (refs / "duplicate.txt").write_bytes(source.read_bytes())
    (refs / "unreadable.docx").write_bytes(b"invalid document")
    queue = await mcp.prepare_manuscript_review(str(document), str(refs))
    repeated = queue["occurrences"][:2]
    assert all(row["state"] == "BLOCKED" and row["packet_id"] is None and "AMBIGUOUS" in row["reason"] for row in repeated)
    assert "LOCAL_FILE_UNREADABLE" in [item["code"] for item in queue["parse_diagnostics"]]
    result = await mcp.generate_manuscript_review_report(queue["manuscript_id"], str(tmp_path / "blocked.html"))
    assert result["blocked_count"] == result["total_occurrences"]
    assert "LOCAL_FILE_UNREADABLE" in Path(result["output_path"]).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_oversized_paper_only_blocks_its_own_occurrence(draft):
    document, refs, _ = draft
    (refs / "long.txt").write_text("Very Long Paper\nDOI: 10.1234/long\n\nResults\n" + "x" * 241000, encoding="utf-8")
    document.write_text("The long paper [1].\n\nThe shorter study [2].\n\nReferences\n"
                        "[1] Doe. Very Long Paper[J]. 2024. doi: 10.1234/long\n"
                        "[2] Doe. Local Follow-up Study[J]. 2024. doi: 10.1234/local-study\n", encoding="utf-8")
    queue = await mcp.prepare_manuscript_review(str(document), str(refs))
    long, short = queue["occurrences"]
    assert long["state"] == "BLOCKED" and "240000" in long["reason"] and long["packet_id"] is None
    assert short["state"] == "PENDING" and short["total_evidence"] > 0
