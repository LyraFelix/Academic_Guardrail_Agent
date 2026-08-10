"""Report generator module for terminal, Markdown, and HTML reports.

Features a high-star open-source aesthetic with Glassmorphism, Dark Mode,
Interactive Filter Tabs, Live Search, Neon Status Glows, and Responsive Layouts.
"""

import json
import html
from typing import List
from academic_guardrail.core.models import DocumentAuditReport, VerificationResult, RiskLevel


class ReportGenerator:
    """Generates Markdown, HTML, and terminal audit reports."""

    def generate_markdown(self, report: DocumentAuditReport) -> str:
        import os
        md = []
        md.append(f"# 🛡️ 学术论文引用与断言审查报告 (Academic Guardrail Report)")
        md.append(f"**审计文件**: `{os.path.basename(report.document_path)}`")
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
            risk_type = r.risk_level.name.lower()  # pass, notice, warning, danger
            badge_class = f"badge-{risk_type}"
            badge_text = r.risk_level.value
            title = html.escape(r.verified_title or r.citation.title or r.citation.raw_text[:70])
            
            doi_link = ""
            doi_val = r.verified_doi or r.citation.doi
            if doi_val and not doi_val.startswith("cnki.local"):
                doi_link = f'<a href="https://doi.org/{doi_val}" target="_blank" class="doi-link">DOI: {html.escape(doi_val)} ↗</a>'
            elif doi_val:
                doi_link = f'<span class="doi-tag">📚 本地文献 / CSCD / CSSCI 索引</span>'

            claim_box = ""
            if r.claim:
                claim_box = f'''
                <div class="claim-box">
                    <div class="box-header">
                        <span class="box-icon">📌</span>
                        <span class="box-title">正文断言引用句：</span>
                    </div>
                    <blockquote class="claim-quote">“{html.escape(r.claim.claim_sentence)}”</blockquote>
                </div>
                '''

            tldr_box = ""
            if r.abstract_tldr:
                tldr_box = f'''
                <div class="abstract-box">
                    <div class="box-header">
                        <span class="box-icon">🔍</span>
                        <span class="box-title">被引文献匹配核心摘要/最匹配单句：</span>
                    </div>
                    <p class="abstract-text">{html.escape(r.abstract_tldr)}</p>
                </div>
                '''

            card = f'''
            <div class="citation-card card-{risk_type}" data-risk="{risk_type}" data-search="{html.escape(title.lower())}">
                <div class="card-header">
                    <h3 class="paper-title">{title}</h3>
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div class="card-meta">
                    <span class="meta-item">📍 位置：{html.escape(r.citation.location_info or '文档正文')}</span>
                    <span class="meta-item">🏷️ 状态：<code>{html.escape(r.status.value)}</code></span>
                    {doi_link}
                </div>
                <div class="card-msg">{html.escape(r.message)}</div>
                {claim_box}
                {tldr_box}
            </div>
            '''
            cards_html.append(card)

        # Build detail table rows
        rows_html = []
        for r in report.results:
            risk_type = r.risk_level.name.lower()
            badge_class = f"badge-{risk_type}"
            title = html.escape(r.verified_title or r.citation.title or r.citation.raw_text[:50])
            row = f'''
            <tr data-risk="{risk_type}" data-search="{html.escape(title.lower())}">
                <td><code class="code-id">{html.escape(r.citation.id)}</code></td>
                <td><strong class="tbl-title">{title}</strong></td>
                <td><code class="status-tag">{html.escape(r.status.value)}</code></td>
                <td><span class="badge {badge_class}">{r.risk_level.value}</span></td>
                <td class="tbl-msg">{html.escape(r.message)}</td>
            </tr>
            '''
            rows_html.append(row)

        full_cards = "\n".join(cards_html)
        full_rows = "\n".join(rows_html)
        import os
        doc_name = html.escape(os.path.basename(report.document_path))

        html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🛡️ 学术引用与断言审查报告 - Academic Guardrail</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(20, 27, 45, 0.75);
            --card-hover: rgba(30, 41, 69, 0.85);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(255, 255, 255, 0.15);
            
            --pass-glow: rgba(16, 185, 129, 0.25);
            --pass-color: #10b981;
            --pass-bg: rgba(16, 185, 129, 0.12);
            --pass-border: #10b981;

            --notice-glow: rgba(56, 189, 248, 0.25);
            --notice-color: #38bdf8;
            --notice-bg: rgba(56, 189, 248, 0.12);
            --notice-border: #38bdf8;

            --warning-glow: rgba(251, 191, 36, 0.25);
            --warning-color: #fbbf24;
            --warning-bg: rgba(251, 191, 36, 0.12);
            --warning-border: #fbbf24;

            --danger-glow: rgba(244, 63, 94, 0.3);
            --danger-color: #f43f5e;
            --danger-bg: rgba(244, 63, 94, 0.15);
            --danger-border: #f43f5e;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(16, 185, 129, 0.08) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(244, 63, 94, 0.05) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            line-height: 1.6;
            padding: 40px 24px;
            min-height: 100vh;
        }}

        .container {{ max-width: 1100px; margin: 0 auto; }}

        /* Top Header */
        .header {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 28px 32px;
            margin-bottom: 28px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
        }}
        .header-main {{ flex: 1; min-width: 280px; }}
        .header-title {{ 
            font-size: 28px; 
            font-weight: 800; 
            color: #ffffff; 
            display: flex; 
            align-items: center; 
            gap: 12px;
            letter-spacing: -0.5px;
        }}
        .header-badge {{
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{ 
            color: var(--text-secondary); 
            font-size: 14px; 
            margin-top: 8px; 
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .doc-path {{
            font-family: 'JetBrains Mono', monospace;
            background: rgba(255, 255, 255, 0.06);
            padding: 3px 8px;
            border-radius: 6px;
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.2);
            font-size: 13px;
        }}

        /* Summary Dashboard Cards */
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 28px;
        }}
        .stat-card {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-radius: 16px;
            padding: 20px 24px;
            border: 1px solid var(--border-color);
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }}
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: var(--border-color);
        }}
        .stat-card:hover {{
            transform: translateY(-3px);
            border-color: var(--border-highlight);
        }}
        
        .stat-card.sc-total::before {{ background: linear-gradient(90deg, #38bdf8, #818cf8); }}
        .stat-card.sc-pass::before {{ background: var(--pass-color); box-shadow: 0 0 10px var(--pass-color); }}
        .stat-card.sc-warning::before {{ background: var(--warning-color); box-shadow: 0 0 10px var(--warning-color); }}
        .stat-card.sc-danger::before {{ background: var(--danger-color); box-shadow: 0 0 10px var(--danger-color); }}

        .stat-num {{ 
            font-size: 36px; 
            font-weight: 800; 
            line-height: 1; 
            margin-bottom: 6px; 
            letter-spacing: -1px;
        }}
        .stat-label {{ font-size: 13px; color: var(--text-secondary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}

        .c-total {{ color: #ffffff; }}
        .c-pass {{ color: var(--pass-color); text-shadow: 0 0 12px var(--pass-glow); }}
        .c-notice {{ color: var(--notice-color); text-shadow: 0 0 12px var(--notice-glow); }}
        .c-warning {{ color: var(--warning-color); text-shadow: 0 0 12px var(--warning-glow); }}
        .c-danger {{ color: var(--danger-color); text-shadow: 0 0 12px var(--danger-glow); }}

        /* Filter Controls */
        .controls-bar {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 14px 20px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .filter-tabs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .filter-btn {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 8px 16px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .filter-btn:hover {{ background: rgba(255, 255, 255, 0.08); color: #fff; }}
        .filter-btn.active {{
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(129, 140, 248, 0.2));
            border-color: #38bdf8;
            color: #ffffff;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
        }}

        .search-box {{
            position: relative;
            flex: 1;
            max-width: 320px;
            min-width: 200px;
        }}
        .search-input {{
            width: 100%;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 8px 14px 8px 36px;
            color: #fff;
            font-size: 13px;
            outline: none;
            transition: all 0.2s ease;
        }}
        .search-input:focus {{
            border-color: #38bdf8;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.25);
        }}
        .search-icon {{
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 13px;
        }}

        .section-title {{
            font-size: 20px;
            font-weight: 700;
            margin: 32px 0 16px 0;
            display: flex;
            align-items: center;
            gap: 10px;
            color: #ffffff;
            letter-spacing: -0.3px;
        }}

        /* Citation Cards */
        .citation-card {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 18px;
            border: 1px solid var(--border-color);
            border-left-width: 6px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .citation-card:hover {{
            transform: translateY(-2px);
            background: var(--card-hover);
            border-color: var(--border-highlight);
        }}

        .card-pass {{ border-left-color: var(--pass-border); }}
        .card-notice {{ border-left-color: var(--notice-border); }}
        .card-warning {{ border-left-color: var(--warning-border); }}
        .card-danger {{ border-left-color: var(--danger-border); box-shadow: 0 0 20px var(--danger-glow); }}

        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px; }}
        .paper-title {{ font-size: 17px; font-weight: 700; color: #ffffff; line-height: 1.4; }}

        .badge {{
            padding: 5px 12px;
            border-radius: 30px;
            font-size: 12px;
            font-weight: 700;
            white-space: nowrap;
            letter-spacing: 0.3px;
            text-transform: uppercase;
        }}
        .badge-pass {{ background: var(--pass-bg); color: var(--pass-color); border: 1px solid var(--pass-border); box-shadow: 0 0 10px var(--pass-glow); }}
        .badge-notice {{ background: var(--notice-bg); color: var(--notice-color); border: 1px solid var(--notice-border); box-shadow: 0 0 10px var(--notice-glow); }}
        .badge-warning {{ background: var(--warning-bg); color: var(--warning-color); border: 1px solid var(--warning-border); box-shadow: 0 0 10px var(--warning-glow); }}
        .badge-danger {{ background: var(--danger-bg); color: var(--danger-color); border: 1px solid var(--danger-border); box-shadow: 0 0 10px var(--danger-glow); }}

        .card-meta {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--text-secondary); margin-bottom: 14px; align-items: center; }}
        .card-meta code {{ font-family: 'JetBrains Mono', monospace; background: rgba(255, 255, 255, 0.06); padding: 2px 8px; border-radius: 4px; color: #e2e8f0; }}
        .doi-link {{ color: #38bdf8; text-decoration: none; font-weight: 600; transition: color 0.2s ease; }}
        .doi-link:hover {{ color: #7dd3fc; text-decoration: underline; }}
        .doi-tag {{ background: rgba(255, 255, 255, 0.05); padding: 3px 10px; border-radius: 6px; font-size: 12px; color: var(--text-secondary); border: 1px solid var(--border-color); }}

        .card-msg {{ font-size: 14px; font-weight: 500; margin-bottom: 14px; color: #cbd5e1; line-height: 1.6; }}

        .claim-box {{
            background: rgba(15, 23, 42, 0.6);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px dashed rgba(56, 189, 248, 0.3);
            margin-top: 12px;
        }}
        .box-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }}
        .box-icon {{ font-size: 14px; }}
        .box-title {{ font-size: 12px; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.5px; }}
        .claim-quote {{ font-size: 13.5px; color: #e2e8f0; font-style: italic; line-height: 1.6; margin: 0; }}

        .abstract-box {{
            background: rgba(16, 185, 129, 0.06);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 12px;
            padding: 14px 18px;
            margin-top: 10px;
        }}
        .abstract-box .box-title {{ color: #34d399; }}
        .abstract-text {{ font-size: 13.5px; color: #cbd5e1; margin-top: 4px; line-height: 1.6; }}

        /* Details Table */
        .table-wrap {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border-radius: 16px;
            border: 1px solid var(--border-color);
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 14px;
        }}
        th {{
            background: rgba(255, 255, 255, 0.03);
            padding: 16px 20px;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
        }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
        .code-id {{ font-family: 'JetBrains Mono', monospace; color: #38bdf8; font-weight: 600; }}
        .tbl-title {{ color: #ffffff; font-weight: 600; }}
        .status-tag {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; background: rgba(255, 255, 255, 0.06); padding: 3px 8px; border-radius: 4px; color: #cbd5e1; }}
        .tbl-msg {{ font-size: 13px; max-width: 300px; color: var(--text-secondary); }}

        .footer {{
            text-align: center;
            margin-top: 40px;
            color: var(--text-muted);
            font-size: 13px;
        }}
        .footer a {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
        .footer a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="header-main">
                <h1 class="header-title">
                    <span>🛡️</span>
                    <span>学术论文引用与断言审查报告</span>
                    <span class="header-badge">v0.1.0</span>
                </h1>
                <div class="subtitle">
                    <span>📄 审计文档：</span>
                    <span class="doc-path">{doc_name}</span>
                </div>
            </div>
        </header>

        <!-- Summary Metric Cards -->
        <section class="summary-grid">
            <div class="stat-card sc-total">
                <div class="stat-num c-total">{report.total_citations}</div>
                <div class="stat-label">文献引用总数</div>
            </div>
            <div class="stat-card sc-pass">
                <div class="stat-num c-pass">{report.passed_count}</div>
                <div class="stat-label">合格 (PASS)</div>
            </div>
            <div class="stat-card sc-warning">
                <div class="stat-num c-warning">{report.warning_count}</div>
                <div class="stat-label">警告 (WARNING)</div>
            </div>
            <div class="stat-card sc-danger">
                <div class="stat-num c-danger">{report.danger_count}</div>
                <div class="stat-label">高危 (DANGER)</div>
            </div>
        </section>

        <!-- Dynamic Controls Bar -->
        <div class="controls-bar">
            <div class="filter-tabs">
                <button class="filter-btn active" onclick="filterRisk('all', this)">全部 ({report.total_citations})</button>
                <button class="filter-btn" onclick="filterRisk('pass', this)">🟢 合格 ({report.passed_count})</button>
                <button class="filter-btn" onclick="filterRisk('notice', this)">🔵 提示</button>
                <button class="filter-btn" onclick="filterRisk('warning', this)">🟡 警告 ({report.warning_count})</button>
                <button class="filter-btn" onclick="filterRisk('danger', this)">🔴 高危 ({report.danger_count})</button>
            </div>
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" class="search-input" id="searchInput" placeholder="搜索文献标题或关键词..." oninput="handleSearch()">
            </div>
        </div>

        <!-- Citation Cards Section -->
        <h2 class="section-title">✨ 引用审计与内容一致性卡片明细</h2>
        <section id="cardsContainer">
            {full_cards}
        </section>

        <!-- Details Table Section -->
        <h2 class="section-title">📋 全量文献核查汇总表格</h2>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>引用ID</th>
                        <th>文献标题 / 引用摘要</th>
                        <th>状态</th>
                        <th>风险等级</th>
                        <th>核查处置说明</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                    {full_rows}
                </tbody>
            </table>
        </div>

        <footer class="footer">
            <p>Generated by <a href="https://github.com/LyraFelix/Academic_Guardrail_Agent" target="_blank">Academic Guardrail Agent</a> · Powered by Multilingual Claim Alignment & Retraction Watch 50K Index</p>
        </footer>
    </div>

    <script>
        let currentFilter = 'all';
        let searchQuery = '';

        function applyFilters() {{
            const cards = document.querySelectorAll('.citation-card');
            const rows = document.querySelectorAll('#tableBody tr');

            cards.forEach(card => {{
                const risk = card.getAttribute('data-risk');
                const title = card.getAttribute('data-search') || '';
                const matchRisk = (currentFilter === 'all' || risk === currentFilter);
                const matchSearch = (!searchQuery || title.includes(searchQuery));
                card.style.display = (matchRisk && matchSearch) ? 'block' : 'none';
            }});

            rows.forEach(row => {{
                const risk = row.getAttribute('data-risk');
                const title = row.getAttribute('data-search') || '';
                const matchRisk = (currentFilter === 'all' || risk === currentFilter);
                const matchSearch = (!searchQuery || title.includes(searchQuery));
                row.style.display = (matchRisk && matchSearch) ? 'table-row' : 'none';
            }});
        }}

        function filterRisk(risk, btn) {{
            currentFilter = risk;
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }}

        function handleSearch() {{
            searchQuery = document.getElementById('searchInput').value.toLowerCase().trim();
            applyFilters();
        }}
    </script>
</body>
</html>"""
        return html_template
