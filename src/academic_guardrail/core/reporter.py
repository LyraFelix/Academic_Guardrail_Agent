"""Report generator module for terminal, Markdown, and HTML reports."""

import json
from typing import List
from academic_guardrail.core.models import DocumentAuditReport, VerificationResult, RiskLevel


class ReportGenerator:
    """Generates Markdown, HTML, and terminal audit reports."""

    def generate_markdown(self, report: DocumentAuditReport) -> str:
        md = []
        md.append(f"# 🛡️ 学术论文引用与断言审查报告 (Academic Guardrail Report)")
        md.append(f"**审计文件**: `{report.document_path}`")
        md.append(f"**引用总数**: {report.total_citations} | 🟢 合格: {report.passed_count} | 🟡 警告: {report.warning_count} | 🔴 高危: {report.danger_count}\n")
        
        md.append("---")
        md.append("## 🚨 高风险与未查证引用警示 (High-Risk & Unverified Citations)")
        
        risk_results = [r for r in report.results if r.risk_level in [RiskLevel.DANGER, RiskLevel.WARNING, RiskLevel.NOTICE]]
        if not risk_results:
            md.append("> 🟢 **优秀**：未发现撤稿、虚构引用或断言偏差项！\n")
        else:
            for r in risk_results:
                badge = "🔴 [DANGER]" if r.risk_level == RiskLevel.DANGER else ("🟡 [WARNING]" if r.risk_level == RiskLevel.WARNING else "🔵 [NOTICE]")
                md.append(f"### {badge} {r.citation.title or r.citation.raw_text[:50]}")
                md.append(f"- **引用位置**: {r.citation.location_info or '未知'}")
                md.append(f"- **状态分类**: `{r.status.value}`")
                if r.verified_doi or r.citation.doi:
                    md.append(f"- **DOI**: [{r.verified_doi or r.citation.doi}](https://doi.org/{r.verified_doi or r.citation.doi})")
                md.append(f"- **核查处置说明**: {r.message}")
                if r.claim:
                    md.append(f"- **正文断言句**: *\"{r.claim.claim_sentence}\"*")
                if r.abstract_tldr:
                    md.append(f"- **摘要概述**: {r.abstract_tldr[:200]}...")
                md.append("")

        md.append("---")
        md.append("## 📋 全量引用核查明细 (Full Verification Details)")
        md.append("| ID | 论文标题 / 原始引用 | 状态 | 风险等级 | 说明 |")
        md.append("|---|---|---|---|---|")
        for r in report.results:
            title = r.verified_title or r.citation.title or r.citation.raw_text[:30]
            md.append(f"| {r.citation.id} | {title} | `{r.status.value}` | `{r.risk_level.value}` | {r.message[:50]} |")

        return "\n".join(md)

    def generate_html(self, report: DocumentAuditReport) -> str:
        # Build cards for risk items
        cards_html = []
        for r in report.results:
            badge_class = "badge-danger" if r.risk_level == RiskLevel.DANGER else ("badge-warning" if r.risk_level == RiskLevel.WARNING else ("badge-notice" if r.risk_level == RiskLevel.NOTICE else "badge-pass"))
            badge_text = r.risk_level.value
            title = r.verified_title or r.citation.title or r.citation.raw_text[:60]
            
            doi_link = ""
            doi_val = r.verified_doi or r.citation.doi
            if doi_val and not doi_val.startswith("cnki.local"):
                doi_link = f'<a href="https://doi.org/{doi_val}" target="_blank" class="doi-link">DOI: {doi_val} ↗</a>'
            elif doi_val:
                doi_link = f'<span class="doi-tag">来源: CSCD/CSSCI 数据库</span>'

            claim_box = ""
            if r.claim:
                claim_box = f'''
                <div class="claim-box">
                    <span class="claim-label">📄 正文断言引用句：</span>
                    <blockquote class="claim-quote">“{r.claim.claim_sentence}”</blockquote>
                </div>
                '''

            tldr_box = ""
            if r.abstract_tldr:
                tldr_box = f'''
                <div class="abstract-box">
                    <span class="abstract-label">💡 论文摘要概述：</span>
                    <p class="abstract-text">{r.abstract_tldr[:220]}...</p>
                </div>
                '''

            card = f'''
            <div class="citation-card {badge_class}-border">
                <div class="card-header">
                    <h3 class="paper-title">{title}</h3>
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div class="card-meta">
                    <span class="meta-item">📍 位置：{r.citation.location_info or '文档正文'}</span>
                    <span class="meta-item">🏷️ 状态：<code>{r.status.value}</code></span>
                    {doi_link}
                </div>
                <div class="card-msg">{r.message}</div>
                {claim_box}
                {tldr_box}
            </div>
            '''
            cards_html.append(card)

        # Build detail table rows
        rows_html = []
        for r in report.results:
            badge_class = "badge-danger" if r.risk_level == RiskLevel.DANGER else ("badge-warning" if r.risk_level == RiskLevel.WARNING else ("badge-notice" if r.risk_level == RiskLevel.NOTICE else "badge-pass"))
            title = r.verified_title or r.citation.title or r.citation.raw_text[:40]
            row = f'''
            <tr>
                <td><code>{r.citation.id}</code></td>
                <td><strong>{title}</strong></td>
                <td><code>{r.status.value}</code></td>
                <td><span class="badge {badge_class}">{r.risk_level.value}</span></td>
                <td>{r.message[:60]}</td>
            </tr>
            '''
            rows_html.append(row)

        full_cards = "\n".join(cards_html)
        full_rows = "\n".join(rows_html)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🛡️ 学术引用与断言审查报告 - Academic Guardrail</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border-color: #e2e8f0;
            --pass-color: #10b981;
            --notice-color: #3b82f6;
            --warning-color: #f59e0b;
            --danger-color: #ef4444;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 30px 20px;
        }}

        .container {{ max-width: 1000px; margin: 0 auto; }}

        .header {{
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--border-color);
        }}
        .header h1 {{ font-size: 26px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 10px; }}
        .header .subtitle {{ color: var(--text-secondary); font-size: 14px; margin-top: 5px; }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 18px 20px;
            border: 1px solid var(--border-color);
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            text-align: center;
        }}
        .stat-num {{ font-size: 32px; font-weight: 700; line-height: 1.1; margin-bottom: 4px; }}
        .stat-label {{ font-size: 13px; color: var(--text-secondary); font-weight: 500; }}

        .c-pass {{ color: var(--pass-color); }}
        .c-notice {{ color: var(--notice-color); }}
        .c-warning {{ color: var(--warning-color); }}
        .c-danger {{ color: var(--danger-color); }}

        .section-title {{
            font-size: 18px;
            font-weight: 600;
            margin: 25px 0 15px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .citation-card {{
            background: var(--card-bg);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid var(--border-color);
            border-left-width: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
            transition: transform 0.15s ease;
        }}
        .citation-card:hover {{ transform: translateY(-2px); }}

        .badge-pass-border {{ border-left-color: var(--pass-color); }}
        .badge-notice-border {{ border-left-color: var(--notice-color); }}
        .badge-warning-border {{ border-left-color: var(--warning-color); }}
        .badge-danger-border {{ border-left-color: var(--danger-color); }}

        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 15px; margin-bottom: 8px; }}
        .paper-title {{ font-size: 16px; font-weight: 600; color: var(--text-primary); }}

        .badge {{
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
        }}
        .badge-pass {{ background: #d1fae5; color: #065f46; }}
        .badge-notice {{ background: #dbeafe; color: #1e40af; }}
        .badge-warning {{ background: #fef3c7; color: #92400e; }}
        .badge-danger {{ background: #fee2e2; color: #991b1b; }}

        .card-meta {{ display: flex; flex-wrap: wrap; gap: 15px; font-size: 13px; color: var(--text-secondary); margin-bottom: 10px; }}
        .doi-link {{ color: var(--notice-color); text-decoration: none; font-weight: 500; }}
        .doi-link:hover {{ text-decoration: underline; }}
        .doi-tag {{ background: #f1f5f9; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}

        .card-msg {{ font-size: 14px; font-weight: 500; margin-bottom: 12px; color: #334155; }}

        .claim-box {{
            background: #f8fafc;
            border-radius: 6px;
            padding: 12px 15px;
            border: 1px dashed #cbd5e1;
            margin-top: 10px;
        }}
        .claim-label {{ font-size: 12px; font-weight: 600; color: #64748b; display: block; margin-bottom: 4px; }}
        .claim-quote {{ font-size: 13px; color: #1e293b; font-style: italic; margin: 0; }}

        .abstract-box {{
            background: #f1f5f9;
            border-radius: 6px;
            padding: 10px 14px;
            margin-top: 8px;
        }}
        .abstract-label {{ font-size: 12px; font-weight: 600; color: #475569; }}
        .abstract-text {{ font-size: 13px; color: #334155; margin-top: 4px; }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            margin-top: 15px;
        }}
        th, td {{ padding: 12px 16px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--border-color); }}
        th {{ background: #f1f5f9; font-weight: 600; color: var(--text-secondary); }}
        tr:last-child td {{ border-bottom: none; }}
        code {{ background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ 学术引用与断言审查报告</h1>
            <div class="subtitle">审计文件：<code>{report.document_path}</code> | 生成时间：系统实时动态校验</div>
        </div>

        <div class="summary-grid">
            <div class="stat-card">
                <div class="stat-num">{report.total_citations}</div>
                <div class="stat-label">文献引用总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-num c-pass">{report.passed_count}</div>
                <div class="stat-label">合格 (PASS)</div>
            </div>
            <div class="stat-card">
                <div class="stat-num c-warning">{report.warning_count}</div>
                <div class="stat-label">警告 (WARNING)</div>
            </div>
            <div class="stat-card">
                <div class="stat-num c-danger">{report.danger_count}</div>
                <div class="stat-label">高危 (DANGER)</div>
            </div>
        </div>

        <div class="section-title">🚨 引用审计与内容一致性卡片明细</div>
        {full_cards}

        <div class="section-title">📋 全量文献核查汇总表格</div>
        <table>
            <thead>
                <tr>
                    <th>引用ID</th>
                    <th>文献标题 / 引用摘要</th>
                    <th>状态</th>
                    <th>风险等级</th>
                    <th>处置建议说明</th>
                </tr>
            </thead>
            <tbody>
                {full_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        return html

