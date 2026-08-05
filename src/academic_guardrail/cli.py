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

from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.models import (
    VerificationResult, VerificationStatus, RiskLevel, DocumentAuditReport
)
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator


from academic_guardrail.core.ref_store import LocalRefStore
from typing import Optional


@click.group()
def main():
    """🛡️ Academic Guardrail Agent CLI Tool"""
    pass


@main.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output report file path (.html or .md)')
@click.option('--refs-dir', '-r', type=click.Path(exists=True), help='包含参考文献 PDF/DOCX/TXT 原文的本地文件夹')
@click.option('--open', '-b', 'open_browser', is_flag=True, help='审计完成后自动在系统浏览器中打开 HTML 报告')
def audit(file_path: str, output: str, refs_dir: Optional[str], open_browser: bool):
    """审计指定原稿 (.pdf, .docx, .md, .tex) 中的文献引用与断言."""
    console.print(f"[bold blue]🛡️ 开始审计原稿:[/bold blue] {file_path}")
    
    ref_store = LocalRefStore(refs_dir) if refs_dir else None
    if ref_store and ref_store.papers:
        console.print(f"[bold green]📚 已成功加载本地参考文献原文库:[/bold green] 找到 {len(ref_store.papers)} 篇参考文件")

    async def _verify_single(cit, claim, provider, evaluator):
        verify_res = await provider.verify_citation(title=cit.title or cit.raw_text, doi=cit.doi)
        
        if verify_res.get("is_retracted"):
            status = VerificationStatus.RETRACTED
            risk = RiskLevel.DANGER
            msg = "🔴 论文存在撤稿记录，强烈建议删除该引用！"
        elif verify_res.get("matched"):
            abstract = verify_res.get("abstract", "")
            source_name = verify_res.get("source", "权威数据库")
            
            # Fallback to local reference file if online abstract is missing
            local_abstract = None
            if not abstract and ref_store:
                match_res = ref_store.find_abstract_for_citation(cit.title or "", cit.raw_text)
                if match_res:
                    local_abstract, ref_filename = match_res
                    source_name = f"本地参考文献 ({ref_filename})"

            target_abstract = abstract or local_abstract

            if not target_abstract:
                status = VerificationStatus.VALID
                risk = RiskLevel.PASS
                msg = f"🟢 文献存在于{source_name}。因数据库及本地库未收录摘要原文，已完成元数据校验并跳过断言比对。"
            else:
                score, reason, best_sent = evaluator.evaluate_alignment(claim.claim_sentence, target_abstract)
                context_str = f" [最匹配的原句: \"{best_sent[:120]}...\"]" if best_sent else ""
                if score < 0.20:
                    status = VerificationStatus.CLAIM_MISMATCH
                    risk = RiskLevel.NOTICE
                    msg = f"🔵 正文断言与{source_name}摘要语义匹配度较弱 ({score:.2f})。{reason}{context_str}"
                else:
                    status = VerificationStatus.VALID
                    risk = RiskLevel.PASS
                    msg = f"🟢 正文断言与{source_name}摘要核心观点高度吻合 ({score:.2f})。{reason}{context_str}"
        else:
            status = VerificationStatus.UNVERIFIED
            risk = RiskLevel.WARNING
            msg = "🟡 数据库未核实该文献，请检查拼写或手工确认。"

        return VerificationResult(
            citation=cit,
            claim=claim,
            status=status,
            risk_level=risk,
            verified_title=verify_res.get("title"),
            verified_doi=verify_res.get("doi"),
            abstract_tldr=verify_res.get("abstract"),
            message=msg
        )

    async def _run_audit():
        parser = DocumentParser()
        provider = ChineseAcademicProvider()
        evaluator = ClaimEvaluator()

        pairs = parser.parse_document(file_path)
        if not pairs:
            console.print("[yellow]ℹ️ 未能在文件中找到文献引用标记或 GB/T 7714 格式。[/yellow]")
            return

        sem = asyncio.Semaphore(10)

        async def _bounded_verify(cit, claim):
            async with sem:
                try:
                    return await asyncio.wait_for(
                        _verify_single(cit, claim, provider, evaluator),
                        timeout=15.0
                    )
                except asyncio.TimeoutError:
                    return VerificationResult(
                        citation=cit,
                        claim=claim,
                        status=VerificationStatus.UNVERIFIED,
                        risk_level=RiskLevel.WARNING,
                        message="🟡 请求超时：数据库查证已超过 15 秒限制"
                    )

        tasks = [_bounded_verify(cit, claim) for cit, claim in pairs]
        results = await asyncio.gather(*tasks)

        passed = sum(1 for r in results if r.risk_level in [RiskLevel.PASS, RiskLevel.NOTICE])
        warning = sum(1 for r in results if r.risk_level == RiskLevel.WARNING)
        danger = sum(1 for r in results if r.risk_level == RiskLevel.DANGER)

        report = DocumentAuditReport(
            document_path=file_path,
            total_citations=len(pairs),
            passed_count=passed,
            warning_count=warning,
            danger_count=danger,
            results=results
        )

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

            if open_browser or output.endswith('.html'):
                abs_path = os.path.abspath(output)
                console.print(f"[bold cyan]🌐 正在自动调起浏览器展示审计报告...[/bold cyan]")
                webbrowser.open(f"file:///{abs_path}")

    asyncio.run(_run_audit())


if __name__ == '__main__':
    main()
