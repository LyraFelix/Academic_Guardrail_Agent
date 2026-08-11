"""CLI interface for academic-guardrail tool."""

import os
import sys
import asyncio
import webbrowser
import click
from rich.console import Console
from rich.table import Table

# Reconfigure stdout/stderr encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

console = Console(force_terminal=True)

from typing import Optional
from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.models import RiskLevel
from academic_guardrail.core.service import AuditService


@click.group()
def main():
    """🛡️ Academic Guardrail Agent CLI Tool"""
    pass


@main.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output report file path (.html or .md)')
@click.option('--refs-dir', '-r', type=click.Path(exists=True), help='包含参考文献 PDF/DOCX/TXT 原文的本地文件夹')
@click.option('--email', '-e', type=str, help='Crossref/OpenAlex Polite Pool 用户身份邮箱')
@click.option('--open', '-b', 'open_browser', is_flag=True, help='审计完成后自动在系统浏览器中打开 HTML 报告')
def audit(file_path: str, output: str, refs_dir: Optional[str], email: Optional[str], open_browser: bool):
    """审计指定原稿 (.pdf, .docx, .md, .tex) 中的文献引用与断言."""
    if email:
        os.environ["ACADEMIC_GUARDRAIL_EMAIL"] = email
    console.print(f"[bold blue]🛡️ 开始审计原稿:[/bold blue] {file_path}")

    # Default output path if browser open option is selected without explicit output file
    if open_browser and not output:
        output = f"{os.path.splitext(file_path)[0]}_report.html"

    async def _run_audit():
        service = AuditService()
        try:
            report = await service.audit_document(file_path, refs_dir=refs_dir)
            
            if report.total_citations == 0:
                console.print("[yellow]ℹ️ 未能在文件中找到文献引用标记或 GB/T 7714 格式。[/yellow]")
                return

            console.print(f"[green]已提取到 {report.total_citations} 条文献引用与断言上下文，已完成联网与语义审计。[/green]\n")
            results = report.results

            # Display rich terminal table
            table = Table(title="🛡️ 学术引用审计明细表")
            table.add_column("引用ID", style="cyan")
            table.add_column("原始引用文本", style="white")
            table.add_column("风险等级", style="bold")
            table.add_column("审计判定说明", style="dim")

            for r in results:
                risk_color = "green" if r.risk_level == RiskLevel.PASS else ("blue" if r.risk_level == RiskLevel.NOTICE else ("yellow" if r.risk_level == RiskLevel.WARNING else "red"))
                table.add_row(
                    r.citation.id,
                    r.citation.raw_text[:40] + "...",
                    f"[{risk_color}]{r.risk_level.value}[/{risk_color}]",
                    r.message
                )

            console.print(table)
            console.print(f"\n[bold]审计汇总[/bold]: 总引用: {report.total_citations} | [green]🟢 合格: {report.passed_count}[/green] | [yellow]🟡 警告: {report.warning_count}[/yellow] | [red]🔴 高危: {report.danger_count}[/red]")

            if output:
                generator = ReportGenerator()
                if output.endswith('.html'):
                    content = generator.generate_html(report)
                else:
                    content = generator.generate_markdown(report)
                with open(output, 'w', encoding='utf-8') as f:
                    f.write(content)
                console.print(f"[bold green]审查报告已成功输出至:[/bold green] {output}")

                if open_browser and output.endswith('.html'):
                    abs_path = os.path.abspath(output)
                    console.print(f"[bold cyan]🌐 正在自动调起浏览器展示审计报告...[/bold cyan]")
                    webbrowser.open(f"file:///{abs_path}")
        finally:
            await service.close()

    asyncio.run(_run_audit())


@main.command()
@click.argument('citation_or_doi', type=str)
@click.option('--email', '-e', type=str, help='Crossref/OpenAlex Polite Pool 用户身份邮箱')
def verify(citation_or_doi: str, email: Optional[str]):
    """校验单条文献或 DOI (例如: "10.1109/CVPR.2016.90")."""
    if email:
        os.environ["ACADEMIC_GUARDRAIL_EMAIL"] = email
    console.print(f"[bold blue]🔍 正在联网比对数据库校验文献:[/bold blue] {citation_or_doi}")

    async def _run_verify():
        from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
        provider = ChineseAcademicProvider(email=email)
        try:
            is_doi = citation_or_doi.strip().startswith("10.") or "10." in citation_or_doi
            res = await provider.verify_citation(
                title=citation_or_doi if not is_doi else "",
                doi=citation_or_doi if is_doi else None
            )

            if res.get("is_retracted"):
                console.print(f"[bold red]🔴 [DANGER/撤稿警示] 论文已被撤稿或发出学术预警！[/bold red]")
                console.print(f"标题: 《{res.get('title')}》")
                console.print(f"DOI: {res.get('doi')}")
            elif res.get("matched"):
                console.print(f"[bold green]🟢 [PASS/验证通过] 数据库成功查实匹配论文。[/bold green]")
                console.print(f"标题: 《{res.get('title')}》")
                console.print(f"DOI: {res.get('doi')}")
                conf = res.get("confidence", 1.0)
                console.print(f"置信度: {conf:.2f}")
                meta = res.get("resolution_metadata")
                if meta:
                    console.print(f"消歧拆解: Title={meta.get('title_score')}, Author={meta.get('author_score')}, Margin={meta.get('rank_margin')}")
                if res.get("abstract"):
                    console.print(f"摘要片段: \"{res.get('abstract')[:200]}...\"")
            elif res.get("evidence_status") == "JOURNAL_MATCHED_ARTICLE_UNVERIFIED":
                console.print(f"[bold blue]🔵 [NOTICE/期刊在录待查] {res.get('message')}[/bold blue]")
            else:
                console.print(f"[bold yellow]🟡 [WARNING/未查证] 无法在数据库中核实该文献，请检查拼写或格式。[/bold yellow]")
        finally:
            await provider.close()

    asyncio.run(_run_verify())


if __name__ == '__main__':
    main()
