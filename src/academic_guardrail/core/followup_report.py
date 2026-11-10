"""Traceable local-review reports; client reasoning is never server-certified."""

from datetime import datetime, timezone
import html
import json
from pathlib import Path

from academic_guardrail.core.followup_models import LocalReviewContext
from academic_guardrail.core.models import SourceLocation
from academic_guardrail.core.reporter import CSS, RETRACTION_LABELS
from academic_guardrail.core.result_formatter import format_location
from academic_guardrail.core.review_store import ReviewStore, content_digest


BOUNDARY = (
    "结论来自客户端模型；服务端只核对保存的记录、证据链接和逐字引文，未认证语义判断。"
    "标签变化、检索命中或引文有效都不代表缺口已经解决，也不代表结论正确。"
    "审阅范围按客户端声明保存，不等于观察到模型实际阅读了全部证据。"
)
SOURCE_LABELS = {
    "CURRENT": "当前文件字节与记录时快照一致；仅表示文件一致性。",
    "CHANGED": "警告：当前源文件已变化。下方保留历史快照，不能当作当前文件的审查结果。",
    "MISSING": "警告：当前源文件已缺失。下方仅能追溯保存的历史快照。",
    "UNREADABLE": "警告：当前源文件不可读取，无法确认它是否仍与历史快照一致。",
    "UNKNOWN": "没有本地源文件快照，无法判断当前文件状态。",
}
CONCLUSION_LABELS = {
    "SUPPORTED": "支持", "CONTRADICTED": "矛盾",
    "NOT_ENOUGH_EVIDENCE": "证据不足", "UNCERTAIN": "不确定",
}
RETRIEVAL_LABELS = {
    "ADDED": "已追加候选证据；仍需客户端判断它是否回答了缺口。",
    "NO_MATCH": "本次有限字面检索未命中；不能据此证明论文中没有相关证据。",
    "NO_NEW_EVIDENCE": "命中的证据已在原证据包中；未追加新的证据单元。",
    "NOT_REQUESTED": "尚未请求追补检索。",
}
EXTRA_CSS = """
.chain { margin:28px 0; background:var(--panel); border:1px solid var(--line);
  border-radius:10px; padding:24px; }
.stages { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));
  gap:18px; margin-top:20px; }
.stage { min-width:0; border:1px solid var(--line); border-radius:8px; padding:18px; }
.stage h3 { margin-bottom:12px; } h4 { margin:20px 0 6px; }
.stage > .badge { display:block; font-size:1.05rem; font-weight:600; padding:8px 10px;
  background:var(--bg); }
.status { padding:12px 16px; border-left:4px solid #567da2; background:var(--bg); }
.status.warning { border-left-color:#b27000; }
.boundary { border:2px solid #567da2; padding:16px; border-radius:8px; }
.stage dl { grid-template-columns:115px 1fr; font-size:.92rem; }
.quoted { margin:12px 0; } .quoted p { font-size:.9rem; }
.source-meta { font-size:.93rem; } pre { white-space:pre-wrap; overflow-wrap:anywhere;
  font-size:.8rem; padding:12px; background:var(--bg); }
code { overflow-wrap:anywhere; } .findings { padding-left:22px; }
@media(max-width:600px) { .chain { padding:16px; } .stage dl { grid-template-columns:1fr; } }
@media print { .stages { display:block; } .stage { margin:12px 0; }
  .chain { break-inside:auto; } details[open] { break-inside:auto; } }
"""


def _selected_ids(review_ids: list[str]) -> list[str]:
    if not isinstance(review_ids, list) or not review_ids:
        raise ValueError("Supply at least one explicit review ID")
    selected = []
    for identifier in review_ids:
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("Review IDs must be nonempty strings")
        identifier = identifier.strip()
        if identifier not in selected:
            selected.append(identifier)
        if len(selected) > 50:
            raise ValueError("Select at most 50 distinct review IDs")
    return selected


def _validate_initial(context: LocalReviewContext) -> None:
    if context.round != 0 or context.parent_review_id or context.parent_review_sha256:
        raise ValueError("A follow-up must link to an initial round-0 review without a parent")


def _validate_parent(before: dict, after: dict) -> None:
    parent = before["context"]
    child = after["context"]
    if parent is None:
        raise ValueError("A local follow-up cannot link to a review without a local source snapshot")
    _validate_initial(parent)
    if child.parent_review_sha256 != before["record"]["review_sha256"]:
        raise ValueError("Follow-up parent review checksum mismatch")
    if before["packet"].packet_id == after["packet"].packet_id:
        raise ValueError("A follow-up needs its own immutable packet")
    if before["packet"].claim != after["packet"].claim:
        raise ValueError("Follow-up and parent claims differ")
    if parent.source != child.source:
        raise ValueError("Follow-up and parent local sources differ")
    if Path(parent.refs_root).resolve() != Path(child.refs_root).resolve():
        raise ValueError("Follow-up and parent reference roots differ")
    if parent.citation != child.citation or parent.initial_scope != child.initial_scope:
        raise ValueError("Follow-up and parent citation or initial scope differ")
    judgment = before["record"]["judgment"]
    if judgment["conclusion"] not in {"NOT_ENOUGH_EVIDENCE", "UNCERTAIN"}:
        raise ValueError("A follow-up parent must have an unresolved client judgment")
    if child.gap is None or child.gap.model_dump(mode="json") not in judgment.get("missing_evidence", []):
        raise ValueError("Follow-up gap does not belong to the parent judgment")
    old_evidence, new_evidence = before["packet"].evidence, after["packet"].evidence
    if new_evidence[:len(old_evidence)] != old_evidence:
        raise ValueError("Follow-up must preserve the original evidence unchanged")
    if len({item.id for item in new_evidence}) != len(new_evidence):
        raise ValueError("Follow-up evidence IDs must be distinct")
    if child.added_evidence_ids != [item.id for item in new_evidence[len(old_evidence):]]:
        raise ValueError("Follow-up added evidence IDs differ from its appended evidence")
    if child.retrieval_status == "NOT_REQUESTED":
        raise ValueError("A follow-up must record its retrieval outcome")
    if (child.retrieval_status == "ADDED") != bool(child.added_evidence_ids):
        raise ValueError("Follow-up retrieval status differs from its added evidence")
    if child.retrieval_status == "NO_MATCH" and child.matched_passages != 0:
        raise ValueError("A no-match follow-up cannot contain matched passages")
    if not 0 <= child.matched_passages <= child.total_passages:
        raise ValueError("Follow-up passage counts are inconsistent")


def build_review_chains(store: ReviewStore, review_ids: list[str]) -> list[dict]:
    """Load explicit immutable records; include a child's exact parent, never latest."""
    selected = _selected_ids(review_ids)
    snapshots = {}

    def load(identifier):
        if identifier not in snapshots:
            record = store.load_review(identifier)
            packet = store.load_packet(record["packet_id"])
            if record["packet_sha256"] != content_digest(packet.model_dump(mode="json")):
                raise ValueError("Review record differs from its packet snapshot")
            context = store.load_context(packet.packet_id)
            snapshots[identifier] = {"record": record, "packet": packet, "context": context}
        return snapshots[identifier]

    chains, included_parents = [], set()
    for identifier in selected:
        after = load(identifier)
        context = after["context"]
        if context is not None and context.round == 1:
            if not context.parent_review_id or not context.parent_review_sha256:
                raise ValueError("Follow-up parent review link is incomplete")
            if context.parent_review_id == identifier:
                raise ValueError("Cycle in follow-up parent review links")
            before = load(context.parent_review_id)
            _validate_parent(before, after)
            included_parents.add(context.parent_review_id)
            chains.append({"before": before, "after": after})
        else:
            if context is not None:
                _validate_initial(context)
            chains.append({"before": after, "after": None})

    # A selected parent already appears in every selected child that cites it.
    chains = [chain for chain in chains if chain["after"] is not None
              or chain["before"]["record"]["review_id"] not in included_parents]
    from academic_guardrail.core.local_evidence import source_status
    checked_at = datetime.now(timezone.utc).isoformat()
    for chain in chains:
        context = chain["before"]["context"]
        chain["source_status"] = source_status(context.source) if context else "UNKNOWN"
        chain["source_status_checked_utc"] = checked_at
    return chains


def _escape(value) -> str:
    if value is None:
        value = "未提供 / 未知"
    elif isinstance(value, bool):
        value = "true" if value else "false"
    return html.escape(str(value), quote=True)


def _fields(items) -> str:
    return "<dl>" + "".join(f"<dt>{_escape(label)}</dt><dd>{_escape(value)}</dd>"
                             for label, value in items) + "</dl>"


def _json_details(title: str, value) -> str:
    return (f"<details><summary>{_escape(title)}</summary><pre>"
            f"{_escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre></details>")


def _gap_html(gaps: list[dict]) -> str:
    if not gaps:
        return "<p>客户端未列出缺失证据；这不证明不存在证据缺口。</p>"
    return "<ol>" + "".join("<li>" + _fields([
        ("缺口类型", gap.get("kind")), ("原断言部分", gap.get("claim_part")),
        ("需要回答的问题", gap.get("question")),
        ("客户端建议检索词", " · ".join(gap.get("search_terms", []))),
    ]) + "</li>" for gap in gaps) + "</ol>"


def _source_status_html(snapshot: dict, source_state: str) -> str:
    context = snapshot["context"]
    if context is None:
        return ("<p class='status warning'>UNKNOWN · 旧记录没有本地源文件快照："
                "无法检查当前文件一致性或确认所读文本覆盖全文。"
                "记录中的引用元数据核验状态单独保留。</p>")
    warning = "" if source_state == "CURRENT" else " warning"
    return (f"<p class='status{warning}'><strong>{_escape(source_state)}</strong> · "
            f"{_escape(SOURCE_LABELS.get(source_state, SOURCE_LABELS['UNKNOWN']))}</p>"
            f"<p class='muted'>本地源文件：{_escape(context.source.path)}</p>")


def _metadata_html(snapshot: dict, checked_at: str) -> str:
    packet, context = snapshot["packet"], snapshot["context"]
    reference = packet.reference or {}
    citation = context.citation.model_dump(mode="json") if context else reference.get("citation", {})
    title = reference.get("verified_title") or citation.get("title")
    doi = reference.get("verified_doi") or citation.get("doi")
    retraction = reference.get("retraction_status", "NOT_CHECKED")
    parts = ["<section class='source-meta'><h3>引用元数据与本地来源</h3>", _fields([
        ("标题", title), ("DOI / 标识符", doi),
        ("记录时引用状态", packet.reference_status),
        ("记录时撤稿检查", f"{retraction} · {RETRACTION_LABELS.get(retraction, '未知状态')}"),
    ])]
    parts.append("<p class='muted'>以上是记录时的引用与来源信息，与客户端的语义结论分开。"
                 "本地匹配不等于出版社身份认证；本报告未联网重新核验身份或撤稿情况。"
                 "未发现撤稿记录不等于确认从未撤稿。</p>")
    parts.append("<details><summary>引用信息、来源快照与核验范围详情</summary>" + _fields([
        ("引用原文", citation.get("raw_text")), ("作者", "、".join(citation.get("authors", [])) or None),
        ("年份 / 期刊会议", f"{citation.get('year') or '未知'} / {citation.get('venue') or '未知'}"),
        ("记录时核验范围", reference.get("verification_scope")), ("撤稿说明", reference.get("retraction_info")),
    ]))
    if context is not None:
        source = context.source
        parts.append(_fields([
            ("源文件", source.path), ("本地引用目录", context.refs_root),
            ("本地快照标题", source.title), ("本地快照 DOI", source.doi),
            ("原文件 SHA-256", source.sha256), ("提取文本 SHA-256", source.text_sha256),
            ("文件状态检查时间", checked_at),
            ("初始证据范围", "摘要（abstract）" if context.initial_scope == "abstract" else "全文（full_text，受已保存证据包范围限制）"),
        ]))
    parts.append("</details>")
    if reference.get("sources"):
        parts.append(_json_details("记录时的元数据 / 撤稿信息来源", reference["sources"]))
    parts.append("</section>")
    return "\n".join(parts)


def _lookup_html(context: LocalReviewContext | None) -> str:
    if context is None:
        return "<p>无本地追补上下文；检索范围、命中数与新增证据数未知。</p>"
    if context.round == 0:
        return "<p>初始审查；尚未请求本地追补检索（NOT_REQUESTED）。</p>"
    parts = [_gap_html([context.gap.model_dump(mode="json")]) if context.gap else "",
             _fields([
                 ("检索状态", f"{context.retrieval_status} · {RETRIEVAL_LABELS.get(context.retrieval_status, '未知')}"),
                 ("实际查询词", " · ".join(context.query_terms) or "无"),
                 ("检索范围", context.search_scope),
                 ("返回命中段落 / 已检索段落", f"{context.matched_passages} / {context.total_passages}"),
                 ("新增证据单元数", len(context.added_evidence_ids)),
                 ("新增证据 ID", " · ".join(context.added_evidence_ids) or "无"),
             ]),
             "<p class='muted'>检索限于同一本地论文的正文（排除参考文献部分）。"
             "返回命中段落数不包含随同保留的相邻上下文；新增证据单元按追加的句子计数。"
             "检索命中仅表示候选文本，不代表问题已经得到回答。</p>"]
    return "\n".join(parts)


def _stage_html(snapshot: dict, heading: str) -> str:
    record, packet, context = snapshot["record"], snapshot["packet"], snapshot["context"]
    judgment = record["judgment"]
    conclusion = judgment["conclusion"]
    evidence_scope = "未知；未记录本地范围"
    if context is not None:
        evidence_scope = "摘要" if context.initial_scope == "abstract" else "全文（以保存包为限）"
        if context.round == 1:
            evidence_scope += " + 一次本地追补"
    parts = [f"<section class='stage'><h3>{_escape(heading)}</h3>",
             f"<p class='badge'>客户端判断：{_escape(CONCLUSION_LABELS.get(conclusion, '未知'))}</p>",
             _fields([
                 ("客户端模型", judgment.get("client_model")), ("记录时间（UTC）", record.get("recorded_utc")),
                 ("证据范围", evidence_scope),
                 ("声明审阅 / 包内证据", f"{len(judgment.get('reviewed_evidence_ids', []))} / {len(packet.evidence)}"),
             ]), "<h4>客户端判断理由</h4>", f"<p>{_escape(judgment.get('rationale'))}</p>",
             "<h4>逐字引文与坐标</h4>"]
    for quote in record.get("quotes", []):
        location = SourceLocation.model_validate(quote["location"]) if quote.get("location") else None
        parts.append(f"<div class='quoted'><p>{_escape(quote.get('evidence_id'))} · "
                     f"{_escape(quote.get('source_kind'))}</p><blockquote>{_escape(quote.get('quote'))}</blockquote>"
                     f"<p>{_escape(format_location(location))}</p></div>")
    if not record.get("quotes"):
        parts.append("<p>没有提交逐字引文。</p>")
    parts.append("<p class='muted'>引文的字面链接已由记录读取过程核对；它是否支持该判断仍需人工阅读。</p>")
    parts.append("<h4>客户端列出的缺失证据</h4>" + _gap_html(judgment.get("missing_evidence", [])))
    parts.append("<h4>本地检索与证据增量</h4>" + _lookup_html(context))
    parts.append("<details><summary>客户端逐项检查与断言分解</summary>")
    labels = {"subject": "对象", "relation": "关系", "numbers": "数值", "scope": "适用范围", "counterevidence": "相反证据"}
    parts.append(_fields([(labels.get(key, key), value) for key, value in judgment.get("checks", {}).items()]))
    for finding in judgment.get("findings", []):
        parts.append(_fields([
            ("原断言部分", finding.get("claim_part")), ("客户端判断关系", finding.get("relation")),
            ("引用的证据 ID", " · ".join(finding.get("evidence_ids", []))), ("理由", finding.get("reason")),
        ]))
    if judgment.get("suggested_revision"):
        parts.append("<h4>客户端改写建议（语义未认证）</h4>" + _fields([
            ("建议文本", judgment["suggested_revision"].get("text")),
            ("理由", judgment["suggested_revision"].get("reason")),
            ("证据 ID", " · ".join(judgment["suggested_revision"].get("evidence_ids", []))),
        ]))
    parts.append("</details>")
    parts.append(_json_details("完整记录、证据包与本地上下文快照", {
        "record": record, "packet": packet.model_dump(mode="json"),
        "local_context": context.model_dump(mode="json") if context else None,
    }))
    parts.append("</section>")
    return "\n".join(parts)


def generate_review_html(chains: list[dict]) -> str:
    """Render only loaded chains; never reread mutable sources or call a model."""
    if not chains:
        raise ValueError("A report requires at least one loaded review chain")
    cards = []
    for index, chain in enumerate(chains, 1):
        before, after = chain["before"], chain["after"]
        cards.append(f"<article class='chain'><h2>审查链 {index}</h2><h3>原始断言</h3>"
                     f"<blockquote>{_escape(before['packet'].claim)}</blockquote>")
        cards.append(_source_status_html(before, chain["source_status"]))
        if after:
            cards.append("<p>下方展示同一原始断言的初次审查与一次本地追补后的判断。"
                         "结论变化不自动记为改进；请对照新增证据与理由阅读。</p>")
        else:
            cards.append("<p>本链仅包含所选记录；没有选择已记录的追补后判断。</p>")
        cards.append("<div class='stages'>" + _stage_html(before, "初次审查" if before["context"] else "独立历史审查"))
        if after:
            cards.append(_stage_html(after, "追补后审查"))
        cards.append("</div>" + _metadata_html(before, chain["source_status_checked_utc"]) + "</article>")
    records = sum(2 if chain["after"] else 1 for chain in chains)
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>本地证据追补与断言审查报告</title><style>{CSS}{EXTRA_CSS}</style></head>
<body><main><header><div><h1>本地证据追补与断言审查报告</h1>
<p>{len(chains)} 条审查链 · {records} 个记录快照</p></div></header>
<p class="boundary">{BOUNDARY}</p>
<p class="muted">报告根据所选审查记录生成，并保留对应的初次判断。
源文件状态反映报告生成时的一次检查；保存的报告不会随文件更新。</p>
{''.join(cards)}
<footer>Academic Guardrail · 样式全部内嵌，无远程资源或脚本。展开详情可读取完整保存快照。</footer>
</main></body></html>'''


def save_review_report(store: ReviewStore, review_ids: list[str], output_path: str | Path) -> dict:
    """Create a new HTML file exclusively; never overwrite a source or report."""
    destination = Path(output_path).expanduser()
    if destination.is_dir():
        raise ValueError("Report output must be a new HTML file, not a directory")
    if destination.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Report output must have an .html or .htm suffix")
    if ":" in destination.name:
        raise ValueError("Report output cannot use an alternate data stream")
    chains = build_review_chains(store, review_ids)
    resolved = destination.resolve()
    for chain in chains:
        for snapshot in (chain["before"], chain["after"]):
            if snapshot is None:
                continue
            context = snapshot["context"]
            source_paths = [context.source.path] if context else []
            source_paths += [item.location.file_path for item in snapshot["packet"].evidence if item.location]
            if any(resolved == Path(path).resolve() for path in source_paths):
                raise ValueError("Report output must not be a source path")
    document = generate_review_html(chains)
    # 'x' is the final check, including races, symlinks and existing reports.
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
        handle.write("\n")
    return {"output_path": str(resolved), "chain_count": len(chains),
            "review_ids": [snapshot["record"]["review_id"] for chain in chains
                           for snapshot in (chain["before"], chain["after"]) if snapshot],
            "semantic_judgment_verified": False}
