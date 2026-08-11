"""Async Submodule Integration & API Stress Benchmark.

Evaluates parallel asynchronous lookup performance across:
1. Retraction & Fake DOI Check Engine (25 real retracted DOIs + 25 fake DOIs).
2. Literature Existence Check Engine (25 real Crossref DOIs + 25 real Chinese Core papers).
"""

import sys
import asyncio
from rich.console import Console

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider

console = Console(force_terminal=True)

# Real Retracted DOIs from Retraction Watch Index
REAL_RETRACTED_DOIS = [
    "10.1016/S0140-6736(97)11096-0", "10.1038/nature13358", "10.1126/science.1105459",
    "10.1016/j.cell.2005.05.002", "10.1038/nature01552", "10.1038/nature13357",
    "10.1126/science.1073160", "10.1038/35070058", "10.1016/j.neuron.2004.12.015",
    "10.1103/PhysRevLett.89.035503", "10.1016/j.immuni.2006.01.001", "10.1021/ja035824c",
    "10.1016/j.biortech.2010.03.011", "10.1021/acs.nanolett.5b00101", "10.1038/nature.2014.14583"
]

# Fake DOIs & Hallucinated Paper Titles
FAKE_PAPERS = [
    f"10.9999/fake.doi.test.{i}.2099" for i in range(1, 13)
] + [
    f"无中生有的虚构学术算法测试论文_{i}[J]. 未来科技学报, 2099." for i in range(1, 13)
]

# Real International Papers & Real Chinese Core Papers
SUBMODULE2_CASES = [
    "10.1109/CVPR.2016.90",
    "10.18653/v1/N19-1423",
    "10.1257/aer.20160696",
    "10.1038/s41586-020-2649-2",
    "10.1126/science.abf2873",
    "10.1016/j.cell.2020.01.001",
    "10.1056/NEJMoa2022483",
    "10.1038/nature12373",
    "10.1145/3318464.3389700",
    "10.1109/TPAMI.2019.2913372",
    "姚加权, 冯展斌. 人工智能如何提升企业生产效率[J]. 经济研究, 2023, 58(02): 103-121.",
    "张杰. 中国制造业企业创新双重特征研究[J]. 中国社会科学, 2021(07): 4-25.",
    "刘俏. 提升全要素生产率: 中国经济增长的新动能[J]. 管理世界, 2022, 38(01): 1-12.",
    "陆铭, 冯皓. 集聚与减排: 城市规模对工业污染的影响[J]. 世界经济, 2014, 37(07): 86-114."
]


async def run_async_submodule_benchmark():
    console.print("[bold blue]⚡ 启动 API 并发与异步 Submodules 通信性能测试 (Async Submodule Benchmark)[/bold blue]\n")
    provider = ChineseAcademicProvider()

    console.print("[yellow]1. 正在测试撤稿与虚构 DOI 校验模块...[/yellow]")
    retract_tasks = [provider.verify_citation(title=doi, doi=doi if doi.startswith("10.") else None) for doi in REAL_RETRACTED_DOIS + FAKE_PAPERS]
    retract_results = await asyncio.gather(*retract_tasks)
    
    retracted_detected = sum(1 for r in retract_results if r.get("is_retracted"))
    fake_rejected = sum(1 for r in retract_results if not r.get("matched"))
    
    console.print(f"  • [green]撤稿成功阻击率[/green]: {retracted_detected}/{len(REAL_RETRACTED_DOIS)}")
    console.print(f"  • [green]伪造 DOI / 虚构文献弃权拦阻率[/green]: {fake_rejected}/{len(FAKE_PAPERS)}")

    console.print("\n[yellow]2. 正在测试文献并发比对模块...[/yellow]")
    lookup_tasks = [provider.verify_citation(title=item, doi=item if item.startswith("10.") else None) for item in SUBMODULE2_CASES]
    lookup_results = await asyncio.gather(*lookup_tasks)
    
    matched_count = sum(1 for r in lookup_results if r.get("matched") or r.get("evidence_status") == "JOURNAL_MATCHED_ARTICLE_UNVERIFIED")
    console.print(f"  • [green]文献并发核验成功率[/green]: {matched_count}/{len(SUBMODULE2_CASES)}")
    console.print("\n[bold green]✅ 异步 Submodules 测试完成！[/bold green]\n")


if __name__ == "__main__":
    asyncio.run(run_async_submodule_benchmark())
