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
        import os
        doc_name = html.escape(os.path.basename(report.document_path))
        pass_pct = round((report.passed_count / max(report.total_citations, 1)) * 100, 1)

        # Build citation cards
        cards_html = []
        for r in report.results:
            risk_type = r.risk_level.name.lower()  # pass, notice, warning, danger
            badge_text = r.risk_level.value
            title = html.escape(r.verified_title or r.citation.title or r.citation.raw_text[:70])
            cit_id = html.escape(r.citation.id)

            doi_val = r.verified_doi or r.citation.doi
            if doi_val and not doi_val.startswith("cnki.local"):
                doi_link = f'<a href="https://doi.org/{html.escape(doi_val)}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-xs font-mono font-medium text-sky-500 hover:text-sky-400 hover:underline">DOI: {html.escape(doi_val)} <span class="text-[10px]">↗</span></a>'
            elif doi_val:
                doi_link = '<span class="inline-flex items-center gap-1 text-xs font-mono text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">📚 本地文献 / CSCD / CSSCI 索引</span>'
            else:
                doi_link = '<span class="text-xs text-slate-400">无 DOI 记录</span>'

            # 5-score breakdown badges
            score_badges = ""
            if r.resolution_metadata:
                rm = r.resolution_metadata
                score_badges = f'''
                <div class="flex flex-wrap gap-2 text-[11px] font-mono text-slate-500 dark:text-slate-400 pt-1">
                    <span class="bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">Title: <strong class="text-slate-700 dark:text-slate-200">{rm.get('title_score', 'N/A')}</strong></span>
                    <span class="bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">Author: <strong class="text-slate-700 dark:text-slate-200">{rm.get('author_score', 'N/A')}</strong></span>
                    <span class="bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">Year: <strong class="text-slate-700 dark:text-slate-200">{rm.get('year_score', 'N/A')}</strong></span>
                    <span class="bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">Margin: <strong class="text-slate-700 dark:text-slate-200">{rm.get('rank_margin', 'N/A')}</strong></span>
                </div>
                '''

            # Claim box
            claim_box = ""
            if r.claim:
                claim_box = f'''
                <div class="mt-3 p-3.5 bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-slate-200/80 dark:border-slate-800">
                    <div class="flex items-center gap-1.5 text-xs font-semibold text-sky-600 dark:text-sky-400 uppercase tracking-wider mb-1.5">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                        <span>正文断言原句 (Manuscript Claim)</span>
                    </div>
                    <blockquote class="text-sm italic text-slate-700 dark:text-slate-300 leading-relaxed font-serif pl-2 border-l-2 border-sky-400 dark:border-sky-500/50">
                        “{html.escape(r.claim.claim_sentence)}”
                    </blockquote>
                </div>
                '''

            # Evidence Text / Abstract box
            ev_box = ""
            ev_text = r.evidence_text or r.abstract_tldr
            granularity = r.evidence_granularity or "SENTENCE"
            if ev_text:
                ev_box = f'''
                <div class="mt-2.5 p-3.5 bg-emerald-50/50 dark:bg-emerald-950/20 rounded-xl border border-emerald-200/60 dark:border-emerald-800/40">
                    <div class="flex items-center justify-between text-xs font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider mb-1.5">
                        <span class="flex items-center gap-1.5">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            <span>被引文献精准证据原文 (Evidence Rationale)</span>
                        </span>
                        <span class="text-[10px] font-mono px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/60 rounded text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700/50">[{granularity}]</span>
                    </div>
                    <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed font-serif">
                        {html.escape(ev_text)}
                    </p>
                </div>
                '''

            # Ambiguous candidates box
            amb_box = ""
            if r.ambiguous_candidates:
                amb_rows = []
                for c in r.ambiguous_candidates:
                    c_title = html.escape(c.get("title", ""))
                    c_doi = f'<a href="https://doi.org/{html.escape(c["doi"])}" target="_blank" class="text-sky-500 underline font-mono">{html.escape(c["doi"])}</a>' if c.get("doi") else "无 DOI"
                    c_score = f'{c.get("score", 0.0):.2f}'
                    c_src = html.escape(c.get("source", ""))
                    amb_rows.append(f'<tr class="border-b border-slate-200 dark:border-slate-800"><td class="p-2">{c_title}</td><td class="p-2">{c_doi}</td><td class="p-2 font-mono font-semibold text-amber-500">{c_score}</td><td class="p-2">{c_src}</td></tr>')
                amb_table = "\n".join(amb_rows)
                amb_box = f'''
                <div class="mt-3 p-3.5 bg-amber-50 dark:bg-amber-950/20 rounded-xl border border-amber-200 dark:border-amber-800/40">
                    <div class="text-xs font-semibold text-amber-800 dark:text-amber-400 mb-2 flex items-center gap-1.5">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                        <span>⚠️ 候选消歧冲突 (Top-2 候选差值 &lt; 5%)</span>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left text-slate-600 dark:text-slate-300">
                            <thead class="bg-amber-100/50 dark:bg-amber-900/40 text-amber-900 dark:text-amber-200 font-semibold">
                                <tr>
                                    <th class="p-2">候选标题</th>
                                    <th class="p-2">DOI</th>
                                    <th class="p-2">匹配得分</th>
                                    <th class="p-2">数据来源</th>
                                </tr>
                            </thead>
                            <tbody>
                                {amb_table}
                            </tbody>
                        </table>
                    </div>
                </div>
                '''

            # Status pill styling
            if r.risk_level == RiskLevel.PASS:
                card_border = "border-l-4 border-l-emerald-500 hover:border-emerald-500/80"
                badge_style = "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800"
            elif r.risk_level == RiskLevel.NOTICE:
                card_border = "border-l-4 border-l-sky-500 hover:border-sky-500/80"
                badge_style = "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300 border-sky-300 dark:border-sky-800"
            elif r.risk_level == RiskLevel.WARNING:
                card_border = "border-l-4 border-l-amber-500 hover:border-amber-500/80"
                badge_style = "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-300 dark:border-amber-800"
            else:
                card_border = "border-l-4 border-l-rose-500 hover:border-rose-500/80 shadow-rose-500/10 shadow-lg"
                badge_style = "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 border-rose-300 dark:border-rose-800 font-bold animate-pulse"

            card = f'''
            <article class="citation-card {card_border} bg-white dark:bg-slate-800/80 p-5 rounded-2xl border border-slate-200 dark:border-slate-700/60 shadow-sm hover:shadow-md transition-all duration-200 mb-4" data-risk="{risk_type}" data-search="{html.escape((title + ' ' + (cit_id) + ' ' + (r.message)).lower())}">
                <div class="flex flex-wrap items-start justify-between gap-3 mb-2">
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-xs font-bold px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">[{cit_id}]</span>
                        <h3 class="text-base font-semibold text-slate-900 dark:text-white leading-snug">{title}</h3>
                    </div>
                    <span class="text-xs font-semibold px-2.5 py-1 rounded-full border {badge_style} uppercase tracking-wider">{badge_text}</span>
                </div>
                
                <div class="flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400 mb-2.5">
                    <span class="flex items-center gap-1">📍 {html.escape(r.citation.location_info or '文档正文')}</span>
                    <span class="flex items-center gap-1">🏷️ 状态: <code class="font-mono font-medium px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700/60 text-slate-700 dark:text-slate-300">{html.escape(r.status.value)}</code></span>
                    {doi_link}
                </div>

                <div class="text-xs md:text-sm text-slate-600 dark:text-slate-300 bg-slate-50/50 dark:bg-slate-900/30 p-2.5 rounded-lg border border-slate-100 dark:border-slate-800/60 font-sans leading-relaxed">
                    {html.escape(r.message)}
                </div>

                {score_badges}
                {amb_box}
                {claim_box}
                {ev_box}
            </article>
            '''
            cards_html.append(card)

        # Build detail table rows
        rows_html = []
        for r in report.results:
            risk_type = r.risk_level.name.lower()
            title = html.escape(r.verified_title or r.citation.title or r.citation.raw_text[:50])
            cit_id = html.escape(r.citation.id)

            if r.risk_level == RiskLevel.PASS:
                badge_style = "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
            elif r.risk_level == RiskLevel.NOTICE:
                badge_style = "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300 border-sky-200 dark:border-sky-800"
            elif r.risk_level == RiskLevel.WARNING:
                badge_style = "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-200 dark:border-amber-800"
            else:
                badge_style = "bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 border-rose-200 dark:border-rose-800 font-bold"

            row = f'''
            <tr class="border-b border-slate-200 dark:border-slate-800 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors" data-risk="{risk_type}" data-search="{html.escape((title + ' ' + cit_id).lower())}">
                <td class="p-3 font-mono text-xs font-semibold text-sky-600 dark:text-sky-400">{cit_id}</td>
                <td class="p-3 font-medium text-slate-900 dark:text-slate-100 max-w-xs truncate">{title}</td>
                <td class="p-3 font-mono text-xs text-slate-600 dark:text-slate-300">{html.escape(r.status.value)}</td>
                <td class="p-3"><span class="text-xs px-2 py-0.5 rounded-full border {badge_style} font-medium">{r.risk_level.value}</span></td>
                <td class="p-3 text-xs text-slate-500 dark:text-slate-400 max-w-sm truncate">{html.escape(r.message)}</td>
            </tr>
            '''
            rows_html.append(row)

        full_cards = "\n".join(cards_html)
        full_rows = "\n".join(rows_html)

        html_template = f"""<!DOCTYPE html>
<html lang="zh-CN" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🛡️ 学术论文引用与断言审查报告 - Academic Guardrail</title>
    <!-- Tailwind CSS with Typography -->
    <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
                        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
                        serif: ['Charter', 'Georgia', 'Cambria', 'Songti SC', 'SimSun', 'serif'],
                    }},
                    colors: {{
                        slate: {{
                            950: '#0b0f19',
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <!-- KaTeX CSS & JS for Academic Math Formula Rendering -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
    <style>
        /* Fallback styling for air-gapped / offline resilience */
        :root {{
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border-color: #e2e8f0;
        }}
        .dark {{
            --bg-color: #0b0f19;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: #334155;
        }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", sans-serif;
        }}
        /* Custom scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: rgba(148, 163, 184, 0.4); border-radius: 9999px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: rgba(148, 163, 184, 0.6); }}
    </style>
</head>
<body class="bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 min-h-screen transition-colors duration-200">
    
    <!-- Top Navigation Bar -->
    <header class="border-b border-slate-200 dark:border-slate-800/80 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-sky-500/20">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                </div>
                <div>
                    <h1 class="text-base font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
                        Academic Guardrail
                        <span class="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300 border border-sky-200 dark:border-sky-800">v0.1.0</span>
                    </h1>
                    <p class="text-xs text-slate-500 dark:text-slate-400">学术论文引用真实性与断言对齐审查报告</p>
                </div>
            </div>

            <div class="flex items-center gap-3">
                <button onclick="toggleTheme()" class="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-colors" title="切换暗黑/明亮模式">
                    <svg id="themeIconSun" class="w-4 h-4 hidden dark:block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                    <svg id="themeIconMoon" class="w-4 h-4 block dark:hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
                </button>
            </div>
        </div>
    </header>

    <!-- Main Container with Responsive TOC Layout -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            
            <!-- Sticky Table of Contents (TOC) Sidebar -->
            <aside class="hidden lg:block lg:col-span-3 sticky top-24 space-y-6">
                <div class="bg-white dark:bg-slate-900/90 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm">
                    <h2 class="text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3 flex items-center gap-1.5">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7"></path></svg>
                        报告导航 (Contents)
                    </h2>
                    <nav class="space-y-1 text-sm font-medium">
                        <a href="#sec-overview" class="toc-link block px-3 py-2 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                            1. 核心指标概览 (KPIs)
                        </a>
                        <a href="#sec-distribution" class="toc-link block px-3 py-2 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                            2. 风险与合规分布 (Matrix)
                        </a>
                        <a href="#sec-cards" class="toc-link block px-3 py-2 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                            3. 引用与证据对齐卡片 (Cards)
                        </a>
                        <a href="#sec-table" class="toc-link block px-3 py-2 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                            4. 全量核查明细表格 (Table)
                        </a>
                    </nav>

                    <div class="mt-6 pt-5 border-t border-slate-100 dark:border-slate-800">
                        <div class="text-xs text-slate-400 dark:text-slate-500 space-y-1.5">
                            <div>📄 审计对象: <span class="font-mono text-slate-700 dark:text-slate-300 font-semibold">{doc_name}</span></div>
                            <div>⚙️ 引擎: <span class="font-mono text-slate-700 dark:text-slate-300 font-semibold">Dual-Track CPU Core</span></div>
                        </div>
                    </div>
                </div>
            </aside>

            <!-- Main Content Body -->
            <div class="lg:col-span-9 space-y-8">
                
                <!-- Section 1: Overview & Hero KPI Cards -->
                <section id="sec-overview" class="scroll-mt-24 space-y-6">
                    <div class="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white rounded-3xl p-6 sm:p-8 shadow-xl relative overflow-hidden">
                        <div class="absolute -right-10 -bottom-10 w-64 h-64 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>
                        <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
                            <div>
                                <span class="text-xs font-mono font-semibold uppercase tracking-wider text-sky-400 bg-sky-950/60 border border-sky-800/80 px-2.5 py-1 rounded-full">Executive Summary</span>
                                <h2 class="text-2xl sm:text-3xl font-bold tracking-tight mt-2 text-white">手稿学术引用与断言审计概览</h2>
                            </div>
                            <div class="text-right">
                                <span class="text-xs text-slate-400">综合合规率 (Pass Rate)</span>
                                <div class="text-3xl font-bold font-mono text-emerald-400">{pass_pct}%</div>
                            </div>
                        </div>

                        <!-- Progress Bar -->
                        <div class="w-full bg-slate-800/90 rounded-full h-3 mb-6 p-0.5 overflow-hidden flex">
                            <div class="bg-emerald-500 h-full rounded-l-full" style="width: {(report.passed_count / max(report.total_citations, 1)) * 100}%" title="PASS"></div>
                            <div class="bg-sky-400 h-full" style="width: {(report.notice_count / max(report.total_citations, 1)) * 100}%" title="NOTICE"></div>
                            <div class="bg-amber-400 h-full" style="width: {(report.warning_count / max(report.total_citations, 1)) * 100}%" title="WARNING"></div>
                            <div class="bg-rose-500 h-full rounded-r-full" style="width: {(report.danger_count / max(report.total_citations, 1)) * 100}%" title="DANGER"></div>
                        </div>

                        <!-- Stat Grid Cards -->
                        <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
                            <div class="bg-slate-800/60 backdrop-blur rounded-2xl p-4 border border-slate-700/50">
                                <div class="text-xs font-medium text-slate-400">文献引用总数</div>
                                <div class="text-2xl font-mono font-bold text-white mt-1">{report.total_citations}</div>
                            </div>
                            <div class="bg-emerald-950/30 backdrop-blur rounded-2xl p-4 border border-emerald-800/40">
                                <div class="text-xs font-medium text-emerald-300">严格吻合 (PASS)</div>
                                <div class="text-2xl font-mono font-bold text-emerald-400 mt-1">{report.passed_count}</div>
                            </div>
                            <div class="bg-sky-950/30 backdrop-blur rounded-2xl p-4 border border-sky-800/40">
                                <div class="text-xs font-medium text-sky-300">补充提示 (NOTICE)</div>
                                <div class="text-2xl font-mono font-bold text-sky-400 mt-1">{report.notice_count}</div>
                            </div>
                            <div class="bg-amber-950/30 backdrop-blur rounded-2xl p-4 border border-amber-800/40">
                                <div class="text-xs font-medium text-amber-300">待查警告 (WARNING)</div>
                                <div class="text-2xl font-mono font-bold text-amber-400 mt-1">{report.warning_count}</div>
                            </div>
                            <div class="bg-rose-950/30 backdrop-blur rounded-2xl p-4 border border-rose-800/40 col-span-2 sm:col-span-1">
                                <div class="text-xs font-medium text-rose-300">撤稿/高危 (DANGER)</div>
                                <div class="text-2xl font-mono font-bold text-rose-400 mt-1">{report.danger_count}</div>
                            </div>
                        </div>
                    </div>
                </section>

                <!-- Section 2: Interactive Controls & Search Bar -->
                <section id="sec-distribution" class="scroll-mt-24 space-y-4">
                    <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200/80 dark:border-slate-800 shadow-sm flex flex-wrap items-center justify-between gap-4">
                        <!-- Risk Filter Pills -->
                        <div class="flex flex-wrap items-center gap-1.5" id="filterPills">
                            <button onclick="filterRisk('all', this)" class="filter-pill active px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-950 transition-all">全部 ({report.total_citations})</button>
                            <button onclick="filterRisk('pass', this)" class="filter-pill px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all">🟢 合格 ({report.passed_count})</button>
                            <button onclick="filterRisk('notice', this)" class="filter-pill px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all">🔵 提示 ({report.notice_count})</button>
                            <button onclick="filterRisk('warning', this)" class="filter-pill px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all">🟡 警告 ({report.warning_count})</button>
                            <button onclick="filterRisk('danger', this)" class="filter-pill px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all">🔴 高危 ({report.danger_count})</button>
                        </div>

                        <!-- Search Input -->
                        <div class="relative w-full sm:w-72">
                            <svg class="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                            <input type="text" id="searchInput" oninput="handleSearch()" placeholder="搜索文献标题、断言或 DOI..." class="w-full bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-4 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500/50">
                        </div>
                    </div>
                </section>

                <!-- Section 3: Citation Cards Grid / Stream -->
                <section id="sec-cards" class="scroll-mt-24 space-y-4">
                    <div class="flex items-center justify-between">
                        <h2 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <span>✨</span> 引用审计与证据对齐卡片
                        </h2>
                        <span class="text-xs text-slate-500 dark:text-slate-400 font-mono">共 {report.total_citations} 项</span>
                    </div>

                    <div id="cardsContainer">
                        {full_cards}
                    </div>
                </section>

                <!-- Section 4: Details Table Section -->
                <section id="sec-table" class="scroll-mt-24 space-y-4">
                    <div class="flex items-center justify-between">
                        <h2 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <span>📋</span> 全量文献核查明细表格
                        </h2>
                    </div>

                    <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-sm overflow-hidden">
                        <div class="overflow-x-auto">
                            <table class="w-full text-left text-xs">
                                <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-200 dark:border-slate-800">
                                    <tr>
                                        <th class="p-3">ID</th>
                                        <th class="p-3">文献标题 / 引用摘要</th>
                                        <th class="p-3">状态分类</th>
                                        <th class="p-3">风险等级</th>
                                        <th class="p-3">核查说明</th>
                                    </tr>
                                </thead>
                                <tbody id="tableBody" class="divide-y divide-slate-100 dark:divide-slate-800/60">
                                    {full_rows}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>

                <!-- Footer -->
                <footer class="pt-8 pb-12 text-center text-xs text-slate-400 dark:text-slate-500 border-t border-slate-200/60 dark:border-slate-800/60 space-y-1">
                    <p>Generated by <a href="https://github.com/LyraFelix/Academic_Guardrail_Agent" target="_blank" class="text-sky-500 font-semibold hover:underline">Academic Guardrail Agent</a> · Powered by Multilingual Claim Alignment & Retraction Watch 50K Index</p>
                    <p class="font-mono text-[11px]">Zero-LLM CPU-First Core Engine · Mathematical Formulations via KaTeX</p>
                </footer>
            </div>
        </div>
    </main>

    <!-- Client-Side Filter & Theme Scripts -->
    <script>
        // KaTeX Auto-Render Initializer
        document.addEventListener("DOMContentLoaded", function() {{
            if (typeof renderMathInElement === "function") {{
                renderMathInElement(document.body, {{
                    delimiters: [
                        {{left: "$$", right: "$$", display: true}},
                        {{left: "$", right: "$", display: false}},
                        {{left: "\\\\(", right: "\\\\)", display: false}},
                        {{left: "\\\\[", right: "\\\\]", display: true}}
                    ],
                    throwOnError: false
                }});
            }}
        }});

        // Dark/Light Theme Switcher
        function initTheme() {{
            const saved = localStorage.getItem('ag_theme');
            if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
                document.documentElement.classList.add('dark');
            }} else {{
                document.documentElement.classList.remove('dark');
            }}
        }}
        initTheme();

        function toggleTheme() {{
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('ag_theme', isDark ? 'dark' : 'light');
        }}

        // Filter & Search Logic
        let currentFilter = 'all';
        let searchQuery = '';

        function applyFilters() {{
            const cards = document.querySelectorAll('.citation-card');
            const rows = document.querySelectorAll('#tableBody tr');

            cards.forEach(card => {{
                const risk = card.getAttribute('data-risk');
                const text = card.getAttribute('data-search') || '';
                const matchRisk = (currentFilter === 'all' || risk === currentFilter);
                const matchSearch = (!searchQuery || text.includes(searchQuery));
                card.style.display = (matchRisk && matchSearch) ? 'block' : 'none';
            }});

            rows.forEach(row => {{
                const risk = row.getAttribute('data-risk');
                const text = row.getAttribute('data-search') || '';
                const matchRisk = (currentFilter === 'all' || risk === currentFilter);
                const matchSearch = (!searchQuery || text.includes(searchQuery));
                row.style.display = (matchRisk && matchSearch) ? 'table-row' : 'none';
            }});
        }}

        function filterRisk(risk, btn) {{
            currentFilter = risk;
            document.querySelectorAll('#filterPills button').forEach(b => {{
                b.className = "filter-pill px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all";
            }});
            btn.className = "filter-pill active px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-900 text-white dark:bg-white dark:text-slate-950 transition-all";
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
