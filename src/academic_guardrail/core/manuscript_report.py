"""Join saved client judgments to their original manuscript occurrences and render one HTML."""

from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from academic_guardrail.core.followup_models import LocalSource
from academic_guardrail.core.followup_report import (
    BOUNDARY, CONCLUSION_LABELS, SOURCE_LABELS, load_review_chains, new_html_path, render_review_stage,
    review_quotes_html, write_new_html,
)
from academic_guardrail.core.local_evidence import snapshot_bytes, source_status
from academic_guardrail.core.models import DocumentAuditReport
from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.review_store import ReviewStore


STATE_LABELS = {"REVIEWED": "已保存客户端判断", "PENDING": "等待客户端判断",
                "BLOCKED": "暂缺可用证据或来源", "MULTIPLE_REVIEWS": "有多条独立判断，未指定采用哪条"}
FOLLOWUP_LABELS = {"NO_SAVED_RESULT": "已保存补查请求，尚无检索结果", "FAILED": "补查执行失败",
                   "PENDING_REVIEW": "补查证据包已准备，等待客户端判断", "REVIEWED": "已保存补查后的判断",
                   "BLOCKED": "文件已发生变化或缺失，补查证据包已转为历史快照"}


def _bind_chains(manuscript: dict, report: DocumentAuditReport, chains: list[dict]) -> dict:
    """Require the exact initial packet even when both the claim text and paper repeat."""
    occurrences = {r.claim.occurrence_id: r for r in report.results if r.claim}
    if set(occurrences) != set(manuscript["packets"]) or len(occurrences) != report.total_occurrences:
        raise ValueError("Manuscript report and saved occurrence list differ")
    by_occurrence = {key: [] for key in occurrences}
    for chain in chains:
        before = chain["before"]
        packet, context = before["packet"], before["context"]
        binding = (packet.reference or {}).get("manuscript_occurrence") or {}
        key = binding.get("occurrence_id")
        if key not in occurrences or context is None:
            raise ValueError("Review is not bound to an occurrence in this manuscript")
        row, result = manuscript["packets"][key], occurrences[key]
        expected = {field: manuscript[field] for field in ("manuscript_id", "document_path", "manuscript_sha256")}
        expected.update(occurrence_id=key, citation_id=result.citation.id, root_packet_id=row["packet_id"])
        if (binding != expected or packet.packet_id != row["packet_id"] or row["state"] != "PENDING"
                or before["record"]["packet_sha256"] != row["packet_sha256"]
                or packet.claim != result.claim.claim_sentence.strip() or context.citation != result.citation
                or context.source.model_dump(mode="json") != manuscript["sources"].get(row["source_path"])
                or context.refs_root != manuscript["refs_dir"] or context.initial_scope != manuscript["initial_scope"]):
            raise ValueError("Review packet, occurrence or cited paper differs from the manuscript snapshot")
        by_occurrence[key].append(chain)
    return by_occurrence


def _resolve_row(original: dict, chains: list[dict], selected_id: str | None, paper_status: str,
                 manuscript_status: str) -> dict:
    row = {**original, "source_status": paper_status, "review_id": None, "conclusion": None}
    records = {stage["record"]["review_id"]: stage["record"]
               for chain in chains for stage in (chain["before"], chain["after"]) if stage}
    row["review_ids"] = list(records)
    if selected_id is not None and selected_id not in records:
        raise ValueError(f"Selected review does not belong to manuscript occurrence {row['occurrence_id']}")
    if selected_id is None and len(chains) == 1:
        # A child has a verified parent link. Independent judgments have no supersession order.
        final_stage = chains[0]["after"] or chains[0]["before"]
        selected_id = final_stage["record"]["review_id"]
    if selected_id:
        row.update(state="REVIEWED", reason="", review_id=selected_id, conclusion=records[selected_id]["judgment"]["conclusion"])
    elif chains:
        row.update(state="MULTIPLE_REVIEWS", reason="Use the optional review_ids map to select a saved judgment.")
    elif row["state"] == "PENDING" and (manuscript_status != "CURRENT" or paper_status != "CURRENT"):
        row.update(state="BLOCKED", reason=f"Manuscript: {manuscript_status}. Local paper: {paper_status}. Prepare a new review for the current files.")
    return row


def _followup_progress(store: ReviewStore, row: dict, chains: list[dict], manuscript_status: str) -> dict | None:
    if not row["packet_id"]:
        return None
    attempt = store.followup_attempt(row["packet_id"])
    if attempt is None:
        return None
    parents = {chain["before"]["record"]["review_id"]: chain["before"] for chain in chains}
    before = parents.get(attempt["review_id"])
    if before is None:
        # A new parent and request can both arrive after export listed the review IDs.
        newer = store.load_review(attempt["review_id"])
        if newer["packet_id"] == row["packet_id"] and newer["review_sha256"] == attempt["review_sha256"]:
            return None
    if before is None or before["record"]["review_sha256"] != attempt["review_sha256"]:
        raise ValueError("Follow-up request does not belong to this occurrence's saved judgment")
    if attempt["status"] in {"FAILED", "NO_SAVED_RESULT"}:
        return attempt
    # Validate an unreviewed child too, so a client can safely resume from its returned packet ID.
    child = store.load_packet(attempt["packet_id"])
    context = store.load_context(child.packet_id)
    if (context is None or context.round != 1 or context.packet_sha256 != attempt["packet_sha256"]
            or context.parent_review_id != attempt["review_id"] or context.parent_review_sha256 != attempt["review_sha256"]
            or context.source != before["context"].source or context.retrieval_status != attempt["status"]
            or child.reference.get("manuscript_occurrence") != before["packet"].reference.get("manuscript_occurrence")):
        raise ValueError("Follow-up packet does not match the saved manuscript request")
    reviewed = any(chain["after"] and chain["after"]["packet"].packet_id == child.packet_id for chain in chains)
    status = "REVIEWED" if reviewed else "PENDING_REVIEW"
    if not reviewed and (row["source_status"] != "CURRENT" or manuscript_status != "CURRENT"):
        status = "BLOCKED"
    return {**attempt, "retrieval_status": attempt["status"], "status": status}


def _occurrence_html(row: dict, chains: list[dict], source: dict) -> str:
    state = row["state"]
    outcome = row["conclusion"] or state
    parts = [f"<section class='scope' data-occurrence-id='{escape(row['occurrence_id'])}' "
             f"data-review-outcome='{escape(outcome)}'>"]
    if row["conclusion"]:
        conclusion = row["conclusion"]
        chosen = next(stage["record"] for chain in chains for stage in (chain["before"], chain["after"])
                      if stage and stage["record"]["review_id"] == row["review_id"])
        parts.extend([f"<h4>客户端判断 · {escape(CONCLUSION_LABELS[conclusion])} ({escape(conclusion)})</h4>",
                      f"<p>{escape(chosen['judgment']['rationale'])}</p>", "<h4>逐字引文与坐标</h4>",
                      review_quotes_html(chosen)])
    else:
        parts.append(f"<h4>客户端语义审查 · {escape(state)} · {STATE_LABELS[state]}</h4>")
    if row["reason"]:
        parts.append(f"<p>{escape(row['reason'])}</p>")
    if row["followup"]:
        progress = row["followup"]
        parts.append(f"<p>本地追补 · <strong>{escape(progress['status'])}</strong> · {FOLLOWUP_LABELS[progress['status']]}"
                     f"<br>初次审查记录 · {escape(progress['review_id'])}</p>")
        if progress.get("packet_id"):
            parts.append(f"<p>补查证据包 · {escape(progress['packet_id'])} · SHA-256 · {escape(progress['packet_sha256'])}</p>")
        if progress.get("error"):
            parts.append(f"<p>{escape(progress['error'])}</p>")
    if row["source_path"]:
        status = row["source_status"]
        parts.append(f"<p>本地原文 · <strong>{escape(status)}</strong> · {escape(SOURCE_LABELS.get(status, ''))}</p>"
                     f"<details><summary>来源快照</summary><p>{escape(row['source_path'])}<br>SHA-256 · "
                     f"{escape(source.get('sha256', '未取得'))}</p></details>")
    if chains:
        parts.append("<details><summary>已保存的判断、缺失证据与补查过程</summary>")
    for index, chain in enumerate(chains, 1):
        if len(chains) > 1:
            parts.append(f"<h4>已保存的审查链 {index}</h4>")
        parts.append(render_review_stage(chain["before"], "初次审查", include_snapshot=False))
        if chain["after"]:
            parts.append(render_review_stage(chain["after"], "追补后审查", include_snapshot=False))
    if chains:
        parts.append("</details>")
    return "\n".join(parts) + "</section>"


def save_manuscript_report(store: ReviewStore, manuscript_id: str, output_path: str,
                           review_ids: dict[str, str] | None = None) -> dict:
    destination = new_html_path(output_path)
    manuscript = store.load_manuscript(manuscript_id)
    report = DocumentAuditReport.model_validate(manuscript["report"])
    resolved = destination.resolve()
    inputs = [manuscript["document_path"], *manuscript["sources"]]
    if any(resolved == Path(path).resolve() for path in inputs):
        raise ValueError("Report output must not be a source path")
    selected = review_ids or {}
    if set(selected) - set(manuscript["packets"]):
        raise ValueError("A selected occurrence does not belong to this manuscript")
    manuscript_status = snapshot_bytes(manuscript["document_path"], manuscript["manuscript_sha256"])[1]
    source_states = {(path, source["sha256"]): source_status(LocalSource.model_validate(source))
                     for path, source in manuscript["sources"].items()}
    chains = load_review_chains(store, store.manuscript_review_ids(manuscript_id),
                                manuscript_id=manuscript_id, source_states=source_states)
    by_occurrence = _bind_chains(manuscript, report, chains)
    rows, sections = [], {}
    for key, original in manuscript["packets"].items():
        source = manuscript["sources"].get(original["source_path"], {})
        paper_status = source_states.get((original["source_path"], source.get("sha256")), "UNKNOWN")
        row = _resolve_row(original, by_occurrence[key], selected.get(key), paper_status, manuscript_status)
        row["followup"] = _followup_progress(store, row, by_occurrence[key], manuscript_status)
        rows.append(row)
        sections[key] = _occurrence_html(row, by_occurrence[key], source)

    counts = Counter(row["state"] for row in rows)
    followups = Counter(row["followup"]["status"] for row in rows if row["followup"])
    checked_at = datetime.now(timezone.utc).isoformat()
    summary = (f"<section class='scope'><h2>整稿客户端语义审查</h2><p>共 {len(rows)} 处正文引用 · "
               f"已记录 {counts['REVIEWED']} · 待判断 {counts['PENDING']} · 受阻 {counts['BLOCKED']} · "
               f"多条独立判断 {counts['MULTIPLE_REVIEWS']}</p>"
               f"<p>补查证据包待判断 {followups['PENDING_REVIEW']} · 已请求尚无结果 {followups['NO_SAVED_RESULT']} · 补查失败 {followups['FAILED']}</p><p>{BOUNDARY}</p>"
               f"<p>稿件快照 · <strong>{escape(manuscript_status)}</strong> · {escape(SOURCE_LABELS[manuscript_status])}"
               f"<br>{escape(manuscript['document_path'])}<br>SHA-256 · {escape(manuscript['manuscript_sha256'])}"
               f"<br>初始证据范围 · {escape(manuscript['initial_scope'])} · 文件状态检查时间（UTC） · {checked_at}</p></section>")
    document = ReportGenerator().generate_html(report, review_summary_html=summary, occurrence_html=sections)
    write_new_html(destination, document)
    return {"output_path": str(resolved), "manuscript_id": manuscript_id, "manuscript_sha256": manuscript["manuscript_sha256"],
            "manuscript_status": manuscript_status, "total_occurrences": len(rows), "reviewed_count": counts["REVIEWED"],
            "pending_count": counts["PENDING"], "blocked_count": counts["BLOCKED"], "multiple_review_count": counts["MULTIPLE_REVIEWS"],
            "pending_followup_count": followups["PENDING_REVIEW"],
            "occurrences": rows, "semantic_judgment_verified": False}
