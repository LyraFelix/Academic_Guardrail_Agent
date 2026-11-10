"""Saved report snapshots preserve provenance without certifying client reasoning."""

from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from uuid import uuid4

import pytest

from academic_guardrail.core.claim_review import build_review_packet
from academic_guardrail.core.followup_models import LocalReviewContext, LocalSource
from academic_guardrail.core.followup_report import (
    build_review_chains, generate_review_html, save_review_report,
)
from academic_guardrail.core.models import (
    Citation, EvidencePassage, RiskLevel, SourceLocation, VerificationResult, VerificationStatus,
)
from academic_guardrail.core.review_models import ClientJudgment, MissingEvidence, ReviewEvidence
from academic_guardrail.core.review_store import ReviewStore, content_digest


def _judgment(packet, conclusion, *, gap=None):
    return ClientJudgment(
        conclusion=conclusion,
        rationale=("测试夹具：摘要只说明成年人参加了试验，没有报告死亡率结果，因此原断言证据不足。"
                   if gap else "测试夹具：新增正文直接报告治疗降低成年人的死亡率。此结论用于检查报告展示，并非真实模型结果。"),
        reviewed_evidence_ids=[item.id for item in packet.evidence],
        quotes=[{"evidence_id": item.id, "quote": item.text} for item in packet.evidence],
        checks={"subject": "Treatment", "relation": "Reduced mortality", "numbers": "None",
                "scope": "Studied adults", "counterevidence": "No other statement in this fixture"},
        client_model="fixture_client_before" if gap else "fixture_client_after",
        missing_evidence=[gap] if gap else [],
    )


@pytest.fixture
def saved_chain(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    source_path = refs / "paper.txt"
    abstract = "Adults participated in a trial."
    body = "Treatment reduced mortality in adults."
    text = f"Title: Fixture Treatment Study\nAbstract: {abstract}\nResults\n{body}\n"
    source_path.write_text(text, encoding="utf-8", newline="\n")
    source = LocalSource(path=str(source_path.resolve()), sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                         text_sha256=hashlib.sha256(text.encode()).hexdigest(), title="Fixture Treatment Study")
    citation = Citation(id="test", raw_text="Fixture Treatment Study", title="Fixture Treatment Study", year=2024)
    reference = VerificationResult(citation=citation, status=VerificationStatus.VALID, risk_level=RiskLevel.NOTICE,
                                   message="Synthetic local match", verification_scope="LOCAL_REFERENCE_METADATA",
                                   retraction_status="NOT_CHECKED")
    packet = build_review_packet("Treatment reduced mortality in adults.", [EvidencePassage(
        text=abstract, source_kind="LOCAL_ABSTRACT", location=SourceLocation(
            file_path=str(source_path), page=1, line=2, char_start=text.index(abstract),
            char_end=text.index(abstract) + len(abstract)))], reference)
    packet.reference["local_source_binding"] = source.model_dump(mode="json")
    store = ReviewStore(tmp_path / "reviews")
    digest = store.save_packet(packet)
    context = LocalReviewContext(packet_id=packet.packet_id, packet_sha256=digest, source=source,
                                 refs_root=str(refs.resolve()), citation=citation, initial_scope="abstract")
    store.save_context(context)
    gap = MissingEvidence(kind="RESULT", claim_part="reduced mortality", question="What happened to mortality?",
                          search_terms=["mortality", "Treatment"])
    before = store.record(packet.packet_id, _judgment(packet, "NOT_ENOUGH_EVIDENCE", gap=gap), digest)
    extra = ReviewEvidence(id="e2", text=body, source_kind="LOCAL_FULLTEXT", location=SourceLocation(
        file_path=str(source_path), page=2, line=4, char_start=text.index(body), char_end=text.index(body) + len(body)))
    child = packet.model_copy(deep=True, update={"packet_id": uuid4().hex, "evidence": packet.evidence + [extra]})
    child_digest = store.save_packet(child)
    child_context = context.model_copy(deep=True, update={
        "packet_id": child.packet_id, "packet_sha256": child_digest, "round": 1,
        "parent_review_id": before["review_id"], "parent_review_sha256": before["review_sha256"],
        "gap": gap, "retrieval_status": "ADDED", "query_terms": ["mortality", "Treatment"],
        "added_evidence_ids": ["e2"], "matched_passages": 1, "total_passages": 3,
    })
    store.save_context(child_context)
    after = store.record(child.packet_id, _judgment(child, "SUPPORTED"), child_digest)
    return {"store": store, "before": before, "after": after, "packet": packet,
            "child": child, "context": context, "child_context": child_context,
            "source_path": source_path, "tmp_path": tmp_path}


def test_real_store_chain_retains_both_snapshots_and_readable_evidence(saved_chain):
    case = saved_chain
    chains = build_review_chains(case["store"], [case["after"]["review_id"]])
    assert len(chains) == 1
    chain = chains[0]
    assert chain["before"]["record"]["review_id"] == case["before"]["review_id"]
    assert chain["after"]["record"]["review_id"] == case["after"]["review_id"]
    assert chain["before"]["packet"] == case["packet"]
    assert chain["after"]["packet"] == case["child"]
    assert chain["before"]["context"] == case["context"]
    assert chain["after"]["context"] == case["child_context"]
    assert chain["source_status"] == "CURRENT"
    document = generate_review_html(chains)
    for expected in ("本地证据追补与断言审查报告", "Treatment reduced mortality in adults.",
                     "初次审查", "追补后审查", "fixture_client_before", "fixture_client_after",
                     "What happened to mortality?", "NOT_ENOUGH_EVIDENCE", "SUPPORTED",
                     "未认证语义判断", "标签变化", "NOT_CHECKED", "CURRENT",
                     "第 2 页", "提取文本第 4 行", "1 / 3", "same_local_paper_body_excluding_bibliography",
                     case["before"]["recorded_utc"], case["after"]["recorded_utc"],
                     case["context"].source.sha256, case["before"]["review_sha256"]):
        assert expected in document
    assert "已解决" not in document


def test_explicit_initial_record_does_not_implicitly_choose_child(saved_chain):
    case = saved_chain
    chains = build_review_chains(case["store"], [case["before"]["review_id"]])
    assert len(chains) == 1 and chains[0]["after"] is None
    document = generate_review_html(chains)
    assert "fixture_client_before" in document
    assert "fixture_client_after" not in document
    assert "NOT_REQUESTED" in document


@pytest.mark.parametrize("status", ["CHANGED", "MISSING"])
def test_changed_or_missing_source_still_displays_historical_chain(saved_chain, status):
    case = saved_chain
    if status == "CHANGED":
        case["source_path"].write_text("A replaced paper.", encoding="utf-8")
    else:
        case["source_path"].unlink()
    chains = build_review_chains(case["store"], [case["after"]["review_id"]])
    assert chains[0]["source_status"] == status
    document = generate_review_html(chains)
    assert status in document and "警告：" in document
    assert "Treatment reduced mortality in adults." in document
    assert "CURRENT" not in document


def test_unreadable_source_is_reported_without_a_current_claim(saved_chain, monkeypatch):
    monkeypatch.setattr("academic_guardrail.core.local_evidence.source_status", lambda source: "UNREADABLE")
    case = saved_chain
    document = generate_review_html(build_review_chains(case["store"], [case["after"]["review_id"]]))
    assert "UNREADABLE" in document and "不可读取" in document
    assert "CURRENT" not in document


def test_duplicate_requested_ids_and_parent_child_pair_render_once(saved_chain):
    case = saved_chain
    parent, child = case["before"]["review_id"], case["after"]["review_id"]
    for ids in ([parent, child, parent, child], [child, parent], [child, child]):
        chains = build_review_chains(case["store"], ids)
        assert len(chains) == 1
        assert chains[0]["before"]["record"]["review_id"] == parent
        assert chains[0]["after"]["record"]["review_id"] == child


@pytest.mark.parametrize("review_ids", [[], [""], ["  "], [None], "a" * 32, [str(i) for i in range(51)]])
def test_empty_invalid_or_over_limit_selection_is_rejected_before_loading(tmp_path, review_ids):
    with pytest.raises(ValueError):
        build_review_chains(ReviewStore(tmp_path), review_ids)


class _SnapshotStore:
    """Already-loaded snapshots let tests isolate link checks from checksum checks."""

    def __init__(self, case):
        store = case["store"]
        self.records = {case[name]["review_id"]: store.load_review(case[name]["review_id"])
                        for name in ("before", "after")}
        self.packets = {packet.packet_id: packet.model_copy(deep=True) for packet in (case["packet"], case["child"])}
        self.contexts = {context.packet_id: context.model_copy(deep=True)
                         for context in (case["context"], case["child_context"])}

    def load_review(self, identifier):
        return deepcopy(self.records[identifier])

    def load_packet(self, identifier):
        return self.packets[identifier]

    def load_context(self, identifier):
        return self.contexts[identifier]


@pytest.mark.parametrize("mismatch", ["digest", "claim", "source", "root", "citation", "scope",
                                      "old_evidence", "added_ids", "gap", "parent_conclusion", "cycle"])
def test_broken_parent_chain_is_rejected(saved_chain, mismatch):
    case = saved_chain
    store = _SnapshotStore(case)
    before_id, after_id = case["before"]["review_id"], case["after"]["review_id"]
    context = store.contexts[case["child"].packet_id]
    packet = store.packets[context.packet_id]
    if mismatch == "digest":
        context.parent_review_sha256 = "0" * 64
    elif mismatch == "claim":
        packet.claim = "Another claim."
    elif mismatch == "source":
        context.source.sha256 = "0" * 64
    elif mismatch == "root":
        context.refs_root = str(case["tmp_path"])
    elif mismatch == "citation":
        context.citation.title = "Another citation"
    elif mismatch == "scope":
        context.initial_scope = "full_text"
    elif mismatch == "old_evidence":
        packet.evidence[0].text = "Changed inherited evidence."
    elif mismatch == "added_ids":
        context.added_evidence_ids = []
    elif mismatch == "gap":
        context.gap.question = "An unrequested question?"
    elif mismatch == "parent_conclusion":
        store.records[before_id]["judgment"]["conclusion"] = "SUPPORTED"
    else:
        context.parent_review_id = after_id
    # Model a separately valid saved packet; the cross-record link must still fail.
    store.records[after_id]["packet_sha256"] = content_digest(packet.model_dump(mode="json"))
    with pytest.raises(ValueError):
        build_review_chains(store, [after_id])


def test_round_one_parent_or_missing_local_parent_cannot_form_chain(saved_chain):
    case = saved_chain
    store = _SnapshotStore(case)
    parent_context = store.contexts[case["packet"].packet_id]
    parent_context.round = 1
    parent_context.parent_review_id = case["after"]["review_id"]
    with pytest.raises(ValueError, match="round-0"):
        build_review_chains(store, [case["after"]["review_id"]])
    store.contexts[case["packet"].packet_id] = None
    with pytest.raises(ValueError, match="without a local source snapshot"):
        build_review_chains(store, [case["after"]["review_id"]])


@pytest.mark.parametrize("status,added,hits,total", [
    ("NOT_REQUESTED", True, 1, 3), ("ADDED", False, 1, 3),
    ("NO_NEW_EVIDENCE", True, 1, 3), ("NO_MATCH", False, 1, 3), ("ADDED", True, 4, 3),
])
def test_inconsistent_retrieval_outcome_is_rejected(saved_chain, status, added, hits, total):
    case = saved_chain
    store = _SnapshotStore(case)
    context = store.contexts[case["child"].packet_id]
    packet = store.packets[context.packet_id]
    context.retrieval_status, context.matched_passages, context.total_passages = status, hits, total
    if not added:
        packet.evidence = packet.evidence[:1]
        context.added_evidence_ids = []
    store.records[case["after"]["review_id"]]["packet_sha256"] = content_digest(packet.model_dump(mode="json"))
    with pytest.raises(ValueError):
        build_review_chains(store, [case["after"]["review_id"]])


def test_real_saved_review_checksum_is_checked(saved_chain):
    case = saved_chain
    path = case["store"]._path(case["after"]["review_id"], "review")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["judgment"]["rationale"] = "Tampered after recording."
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        build_review_chains(case["store"], [case["after"]["review_id"]])


def test_legacy_without_context_has_explicit_unknown_scope(tmp_path):
    packet = build_review_packet("A claim.", [EvidencePassage(text="A source sentence.", source_kind="PROVIDED_TEXT")])
    store = ReviewStore(tmp_path / "reviews")
    digest = store.save_packet(packet)
    record = store.record(packet.packet_id, _judgment(packet, "NOT_ENOUGH_EVIDENCE"), digest)
    chains = build_review_chains(store, [record["review_id"]])
    assert chains[0]["source_status"] == "UNKNOWN"
    document = generate_review_html(chains)
    assert "旧记录没有本地源文件快照" in document
    assert "独立历史审查" in document
    assert "PROVIDED_TEXT_NOT_IDENTITY_VERIFIED" in document
    assert "检索范围、命中数与新增证据数未知" in document
    assert "CURRENT" not in document


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_all_imported_text_is_escaped_and_no_active_or_remote_assets(saved_chain):
    case = saved_chain
    chains = build_review_chains(case["store"], [case["after"]["review_id"]])
    payload = '<script src="https://example.test/x.js">alert("x")</script><img src=x onerror=alert(1)>'
    chain = chains[0]
    for snapshot in (chain["before"], chain["after"]):
        snapshot["packet"].claim = payload
        snapshot["context"].source.title = payload
        snapshot["context"].source.path = payload
        snapshot["context"].citation.raw_text = payload
        snapshot["context"].citation.title = payload
        snapshot["record"]["judgment"]["client_model"] = payload
        snapshot["record"]["judgment"]["rationale"] = payload
        snapshot["record"]["quotes"][0]["quote"] = payload
        snapshot["record"]["quotes"][0]["location"]["file_path"] = payload
    chain["after"]["context"].query_terms = [payload]
    chain["after"]["context"].gap.question = payload
    document = generate_review_html(chains)
    assert payload not in document
    assert "&lt;script src=&quot;https://example.test/x.js&quot;&gt;" in document
    assert "&lt;img src=x onerror=alert(1)&gt;" in document
    parsed = _Tags()
    parsed.feed(document)
    assert not {tag for tag, _ in parsed.tags} & {"script", "link", "img", "iframe", "object", "embed"}
    assert not any(name in attrs for _, attrs in parsed.tags for name in ("src", "href", "onerror", "onclick"))
    csp = next(attrs["content"] for tag, attrs in parsed.tags if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
    assert "default-src 'none'" in csp
    assert "script-src 'unsafe-inline'" not in csp


def test_save_is_exclusive_and_reports_exact_selected_chain(saved_chain):
    case = saved_chain
    output = case["tmp_path"] / "review_report.html"
    result = save_review_report(case["store"], [case["after"]["review_id"]], output)
    original = output.read_bytes()
    assert result["output_path"] == str(output.resolve())
    assert result["review_ids"] == [case["before"]["review_id"], case["after"]["review_id"]]
    assert result["semantic_judgment_verified"] is False
    assert result["chain_count"] == 1
    with pytest.raises(FileExistsError):
        save_review_report(case["store"], [case["after"]["review_id"]], output)
    assert output.read_bytes() == original


@pytest.mark.parametrize("output", ["paper.txt", "report.json", "directory", "paper.txt:report.html"])
def test_report_rejects_non_html_and_directory_outputs(saved_chain, output):
    case = saved_chain
    path = case["tmp_path"] / output
    if output == "directory":
        path.mkdir()
    with pytest.raises(ValueError):
        save_review_report(case["store"], [case["after"]["review_id"]], path)


@pytest.mark.parametrize("source_exists", [False, True])
def test_source_path_with_html_suffix_cannot_be_used_as_report(saved_chain, source_exists):
    case = saved_chain
    store = _SnapshotStore(case)
    source_path = case["tmp_path"] / "missing_source.html"
    if source_exists:
        source_path.write_text("An existing source, never an output report.", encoding="utf-8")
    for context in store.contexts.values():
        context.source.path = str(source_path)
    with pytest.raises(ValueError, match="source path"):
        save_review_report(store, [case["after"]["review_id"]], source_path)
    if source_exists:
        assert source_path.read_text(encoding="utf-8") == "An existing source, never an output report."
    else:
        assert not source_path.exists()


def test_empty_render_is_not_a_success_report():
    with pytest.raises(ValueError):
        generate_review_html([])
