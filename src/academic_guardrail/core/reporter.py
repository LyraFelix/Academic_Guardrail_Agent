"""Self-contained reports. Imported data is escaped at the output boundary."""

import html
import ntpath
import re
from urllib.parse import quote

from academic_guardrail.core.models import DocumentAuditReport, RiskLevel
from academic_guardrail.core.result_formatter import format_counts, format_diagnostic, format_location

SCOPE = (
    "PASS 表示本次元数据核查或启发式检查未触发风险，不代表论文或断言的科学正确性。"
    "未发现撤稿记录不等于确认从未撤稿；请结合来源、检索范围与人工阅读判断。"
)
EMPTY = "未提取到引用；当前没有可核查条目，不代表文档已通过审查。"
RETRACTION_LABELS = {
    "CONFIRMED": "已确认撤稿", "SUSPECTED": "疑似撤稿，需复核",
    "NO_RECORD": "本次查询未发现撤稿记录", "NOT_CHECKED": "未完成撤稿检查",
}

# Inline assets keep saved reports independent of servers and build tools.
CSS = """
:root { color-scheme:light; --bg:#f3f5f8; --panel:#fff; --ink:#182536;
  --muted:#506074; --line:#d7dee7; --link:#1459a3; }
:root.dark { color-scheme:dark; --bg:#111923; --panel:#1c2836; --ink:#edf3fa;
  --muted:#b4c2d3; --line:#46576a; --link:#8ec5ff; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.65 system-ui,sans-serif; overflow-wrap:anywhere; }
main { max-width:1060px; margin:auto; padding:32px 20px; }
h1 { font-size:1.8rem; margin:0; } h2 { font-size:1.2rem; }
h3 { font-size:1.05rem; margin:.2em 0; }
p { margin:.5em 0; } a { color:var(--link); }
button,input,select { font:inherit; color:var(--ink); background:var(--panel);
  border:1px solid var(--line); border-radius:6px; padding:8px 12px; }
button { cursor:pointer; } :focus-visible { outline:3px solid var(--link); }
header,.controls { display:flex; gap:16px; flex-wrap:wrap; align-items:center; }
header { justify-content:space-between; } label { display:flex; gap:8px; align-items:center; }
input { width:min(330px,65vw); } .muted,footer { color:var(--muted); }
.scope,.empty { border:1px solid var(--line); border-radius:8px; padding:16px; }
.summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; margin:24px 0; }
.summary div,.citation-card { background:var(--panel); border:1px solid var(--line);
  border-radius:8px; padding:16px; }
.summary strong { display:block; font-size:1.6rem; }
.citation-card { margin:16px 0; border-left:5px solid #567da2; }
.citation-card[data-risk=pass] { border-left-color:#278255; }
.citation-card[data-risk=warning] { border-left-color:#ba790a; }
.citation-card[data-risk=danger] { border-left-color:#c34e53; }
.badge { font-size:.8rem; border:1px solid var(--line); border-radius:4px; padding:2px 6px; }
dl { display:grid; grid-template-columns:140px 1fr; gap:6px 16px; }
dt { color:var(--muted); } dd { margin:0; white-space:pre-wrap; }
blockquote { margin:8px 0; padding:10px 16px; border-left:3px solid var(--line);
  white-space:pre-wrap; background:var(--bg); }
li { margin:8px 0; } details { margin-top:12px; } summary { cursor:pointer; }
[hidden] { display:none !important; } footer { margin-top:32px; font-size:.85rem; }
@media(max-width:600px) { .summary { grid-template-columns:repeat(2,1fr); }
  dl { grid-template-columns:1fr; gap:2px; } dd { margin-bottom:10px; } }
@media print { .controls,#theme-toggle { display:none; } .citation-card { break-inside:avoid; }
  body { background:white; color:black; } }
"""

SCRIPT = """
const search = document.getElementById('search');
const riskFilter = document.getElementById('risk-filter');
const cards = Array.from(document.querySelectorAll('.citation-card'));
function applyFilters() {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const card of cards) {
    const matchesRisk = riskFilter.value === 'all' || card.dataset.risk === riskFilter.value;
    const matchesText = card.textContent.toLowerCase().includes(query);
    card.hidden = !(matchesRisk && matchesText);
    if (!card.hidden) visible += 1;
  }
  document.getElementById('visible-count').textContent = `显示 ${visible} / ${cards.length} 条`;
  document.getElementById('no-matches').hidden = visible > 0 || cards.length === 0;
}
search.addEventListener('input', applyFilters);
riskFilter.addEventListener('change', applyFilters);
document.getElementById('theme-toggle').addEventListener('click', function () {
  const dark = document.documentElement.classList.toggle('dark');
  this.setAttribute('aria-pressed', String(dark));
  this.textContent = dark ? '浅色模式' : '深色模式';
});
applyFilters();
"""


def _text(value):
    """Enums and missing values have stable display forms."""
    return str(getattr(value, "value", value)) if value is not None else "未提供"


def _escape(value):
    return html.escape(_text(value), quote=True)


def _markdown(value):
    """Neutralize raw HTML and Markdown syntax in imported data."""
    text = re.sub(r"([\\`*{}\[\]()#+!|>~-])", r"\\\1", _escape(value)).replace("\n", " ")
    # Intraword underscores (citation IDs) and periods need no escaping.
    return re.sub(r"(?<!\w)_|_(?!\w)", r"\\_", text)


def _source_text(source):
    # Also accept dictionaries from earlier serialized source records.
    get = source.get if isinstance(source, dict) else lambda key: getattr(source, key, None)
    retracted = get("is_retracted")
    finding = "未提供" if retracted is None else ("是" if retracted else "否")
    return " | ".join(_text(get(key)) for key in ("source", "kind", "identifier", "detail")) + f" | 撤稿标记: {finding}"


def _retraction(result):
    status = _text(getattr(result, "retraction_status", "NOT_CHECKED"))
    return f"{status} · {RETRACTION_LABELS.get(status, '未知状态')}"


def _doi_html(doi):
    if not doi:
        return "无 DOI 记录"
    if str(doi).startswith("cnki.local"):
        return f"本地文献标识：{_escape(doi)}"
    # Fixed origin and encoded path: imported identifiers never become markup.
    target = "https://doi.org/" + quote(str(doi), safe="/")
    return f'<a href="{_escape(target)}" target="_blank" rel="noopener noreferrer">{_escape(doi)}</a>'


class ReportGenerator:
    """Render service results without adding new verification conclusions."""

    def generate_markdown(self, report: DocumentAuditReport) -> str:
        lines = ["# 🛡️ 学术论文引用与断言审查报告 (Academic Guardrail Report)",
                 f"**审计文件**: {_markdown(ntpath.basename(report.document_path))}",
                 f"**核查模式**: {'离线' if getattr(report, 'offline', False) else '在线（以实际来源为准）'}",
                 f"**核查计数**: {_markdown(format_counts(report))}",
                 f"**结果等级**: PASS: {report.passed_count} | "
                 f"NOTICE: {report.notice_count} | WARNING: {report.warning_count} | DANGER: {report.danger_count}",
                 "", SCOPE, ""]
        if not report.results:
            lines.append(EMPTY)
        for diagnostic in report.parse_diagnostics:
            lines.append(f"- **解析 / 文件提示**: {_markdown(format_diagnostic(diagnostic))}")
        for result in report.results:
            title = result.verified_title or result.citation.title or result.citation.raw_text
            lines.extend([f"## {_markdown(result.citation.id)} · {_markdown(title)}",
                          f"- **状态 / 风险**: {_markdown(result.status)} / {_markdown(result.risk_level)}",
                          f"- **原始引用**: {_markdown(result.citation.raw_text)}",
                          f"- **位置**: {_markdown(result.citation.location_info)}",
                          f"- **DOI / 标识符**: {_markdown(result.verified_doi or result.citation.doi)}",
                          f"- **撤稿检查**: {_markdown(_retraction(result))}",
                          f"- **说明**: {_markdown(result.message)}"])
            if result.claim:
                lines.append(f"- **引用位置**: {_markdown(result.claim.occurrence_id)} · {_markdown(format_location(result.claim.location))}")
                lines.append(f"- **正文断言**: {_markdown(result.claim.claim_sentence)}")
            if result.retraction_info:
                lines.append(f"- **撤稿说明**: {_markdown(result.retraction_info)}")
            lines.append(f"- **核查范围**: {_markdown(result.verification_scope)}")
            lines.append(f"- **证据状态**: {_markdown(result.evidence_status)}")
            lines.append(f"- **文本检索**: {_markdown(result.retrieval_status)}")
            if result.failure_reason:
                lines.append(f"- **查询异常**: {_markdown(result.failure_reason)}")
            if result.evidence_text:
                lines.append(f"- **证据片段**: {_markdown(result.evidence_text)}")
                lines.append(f"- **文本来源**: {_markdown(result.text_source)} · {_markdown(format_location(result.evidence_location))}")
            if result.abstract_tldr and result.abstract_tldr != result.evidence_text:
                lines.append(f"- **文献摘要（背景信息）**: {_markdown(result.abstract_tldr)}")
            for source in getattr(result, "sources", []) or []:
                lines.append(f"- **来源**: {_markdown(_source_text(source))}")
            lines.append("")
        return "\n".join(lines)

    def _card(self, result):
        title = result.verified_title or result.citation.title or result.citation.raw_text
        risk = result.risk_level.name.lower()
        fields = [("原始引用", result.citation.raw_text), ("条目位置", result.citation.location_info),
                  ("核查状态", result.status), ("撤稿检查", _retraction(result)), ("说明", result.message)]
        for label, attribute in (("证据状态", "evidence_status"), ("失败原因", "failure_reason"),
                                 ("撤稿说明", "retraction_info"), ("核查范围", "verification_scope"),
                                 ("元数据匹配分数", "reference_confidence"), ("断言对齐分数", "claim_alignment_score"),
                                 ("对齐状态", "alignment_state"), ("对齐引擎", "alignment_engine"), ("语义模式", "semantic_mode"),
                                 ("文本检索", "retrieval_status"), ("文本来源", "text_source")):
            value = getattr(result, attribute, None)
            if value is not None:
                fields.append((label, value))
        details = "".join(f"<dt>{label}</dt><dd>{_escape(value)}</dd>" for label, value in fields)
        parts = [f'<article class="citation-card" data-risk="{_escape(risk)}">',
                 f'<span class="badge">{_escape(result.risk_level)}</span>',
                 f"<h3>[{_escape(result.citation.id)}] {_escape(title)}</h3>",
                 f"<dl>{details}<dt>DOI / 标识符</dt><dd>{_doi_html(result.verified_doi or result.citation.doi)}</dd></dl>"]
        if result.claim:
            parts.append(f"<p>引用位置：{_escape(result.claim.occurrence_id)} · {_escape(format_location(result.claim.location))}</p>")
            parts.append(f"<h4>正文断言</h4><blockquote>{_escape(result.claim.claim_sentence)}</blockquote>")
        evidence = result.evidence_text
        if evidence:
            parts.append(f"<h4>证据片段 · {_escape(result.evidence_granularity)}</h4><blockquote>{_escape(evidence)}</blockquote>")
            parts.append(f"<p>证据位置：{_escape(format_location(result.evidence_location))}</p>")
        if result.abstract_tldr and result.abstract_tldr != evidence:
            parts.append(f"<details><summary>文献摘要（背景信息）</summary><blockquote>{_escape(result.abstract_tldr)}</blockquote></details>")
        sources = getattr(result, "sources", []) or []
        parts.append("<h4>核查来源</h4><ul>" + ("".join(f"<li>{_escape(_source_text(source))}</li>" for source in sources)
                     or "<li>没有记录来源；不能据此补充核查结论。</li>") + "</ul>")
        if result.resolution_metadata:
            rows = "".join(f"<dt>{_escape(key)}</dt><dd>{_escape(value)}</dd>" for key, value in result.resolution_metadata.items())
            parts.append(f"<details><summary>匹配评分明细（用于辅助匹配）</summary><dl>{rows}</dl></details>")
        if result.ambiguous_candidates:
            rows = "".join("<li>" + " · ".join(_escape(candidate.get(key)) for key in ("title", "doi", "score", "source")) + "</li>"
                           for candidate in result.ambiguous_candidates)
            parts.append(f"<details><summary>待人工消歧的候选文献</summary><ul>{rows}</ul></details>")
        return "\n".join(parts) + "</article>"

    def generate_html(self, report: DocumentAuditReport) -> str:
        name = _escape(ntpath.basename(report.document_path))
        mode = "离线：仅使用本地数据，未执行在线检索或语义模型加载。" if getattr(report, "offline", False) else "在线核查：实际查询结果与可用性请查看每条引用的来源和状态。"
        counts = [("文献条目", report.total_references), ("正文引用次数", report.total_occurrences),
                  ("核查结果", report.total_citations), ("PASS", report.passed_count),
                  ("NOTICE", report.notice_count), ("WARNING", report.warning_count), ("DANGER", report.danger_count)]
        summary = "".join(f"<div>{label}<strong>{_escape(count)}</strong></div>" for label, count in counts)
        options = '<option value="all">全部风险</option>' + "".join(f'<option value="{risk.name.lower()}">{risk.value}</option>' for risk in RiskLevel)
        cards = "\n".join(self._card(result) for result in report.results)
        empty = f'<p class="empty">{EMPTY}</p>' if not report.results else ""
        diagnostics = ""
        if report.parse_diagnostics:
            diagnostics = "<section class='scope'><h2>解析 / 文件提示</h2><ul>" + "".join(
                f"<li>{_escape(format_diagnostic(item))}</li>" for item in report.parse_diagnostics) + "</ul></section>"
        return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>引用核查报告 · {name}</title><style>{CSS}</style></head>
<body><main><header><div><h1>学术论文引用与断言审查报告</h1><p>{name}</p></div>
<button type="button" id="theme-toggle" aria-pressed="false">深色模式</button></header>
<p class="muted">{mode}</p><p class="scope">{SCOPE}</p>
<section class="summary" aria-label="核查计数">{summary}</section>
<p class="muted">{_escape(format_counts(report))}</p>{diagnostics}
<h2>引用核查明细</h2><div class="controls">
<label for="risk-filter">风险筛选 <select id="risk-filter">{options}</select></label>
<label for="search">搜索 <input id="search" type="search" placeholder="标题、DOI、断言或来源"></label>
<span id="visible-count" role="status" aria-live="polite"></span></div>
<noscript><p>JavaScript 未启用：下方完整报告仍可阅读，筛选和主题切换不可用。</p></noscript>
{empty}<p id="no-matches" class="empty" hidden>没有符合筛选条件的引用。</p>{cards}
<footer>Academic Guardrail · 报告的样式与筛选脚本均内嵌，无需联网。点击 DOI 链接会打开外部网站。</footer>
</main><script>{SCRIPT}</script></body></html>'''
