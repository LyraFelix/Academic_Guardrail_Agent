"""Dedicated Reference Entity Resolution & Candidate Re-Ranking Benchmark.

Evaluates ReferenceResolver against gold-standard citations for:
- Top-1 Accuracy
- MRR (Mean Reciprocal Rank)
- Recall@5
- Abstention Accuracy (Ambiguity & Hallucinated Citation Rejection)
"""

import sys
import time
from typing import List, Dict, Any
from rich.console import Console
from rich.table import Table

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.core.models import Citation

console = Console(force_terminal=True)

# Reference Resolution Gold Standard Benchmark Suite (15 Test Instances)
RESOLUTION_GOLD_DATASET: List[Dict[str, Any]] = [
    # ── Category 1: Canonical & Noisy Citation Resolution (Positive Cases) ──
    {
        "id": "REF-01",
        "citation": Citation(id="cit_1", raw_text="Vaswani et al. Attention Is All You Need. NIPS 2017.", title="Attention Is All You Need"),
        "candidates": [
            {"title": "Attention Is All You Need", "doi": "10.48550/arxiv.1706.03762", "authors": ["Ashish Vaswani", "Noam Shazeer"], "year": 2017},
            {"title": "Attention Mechanism in Deep Learning", "doi": "10.1016/j.neucom.2020.01.001", "authors": ["Other Author"], "year": 2020},
            {"title": "All You Need is Attention for Vision", "doi": "10.1109/cvpr.2021.002", "authors": ["Vision Author"], "year": 2021}
        ],
        "gold_doi": "10.48550/arxiv.1706.03762",
        "type": "POSITIVE"
    },
    {
        "id": "REF-02",
        "citation": Citation(id="cit_2", raw_text="He K, Zhang X, Ren S, Sun J. Deep Residual Learning for Image Recognition. CVPR 2016.", title="Deep Residual Learning for Image Recognition"),
        "candidates": [
            {"title": "Deep Residual Learning for Image Recognition", "doi": "10.1109/cvpr.2016.90", "authors": ["Kaiming He", "Xiangyu Zhang"], "year": 2016},
            {"title": "Identity Mappings in Deep Residual Networks", "doi": "10.1007/978-3-319-46493-0_38", "authors": ["Kaiming He"], "year": 2016}
        ],
        "gold_doi": "10.1109/cvpr.2016.90",
        "type": "POSITIVE"
    },
    {
        "id": "REF-03",
        "citation": Citation(id="cit_3", raw_text="Acemoglu D, Restrepo P. The Race between Man and Machine: Implications of Technology for Growth, Factor Shares, and Employment. AER 2018.", title="The Race between Man and Machine", authors=["Acemoglu", "Restrepo"]),
        "candidates": [
            {"title": "The Race between Man and Machine: Implications of Technology for Growth, Factor Shares, and Employment", "doi": "10.1257/aer.20160696", "authors": ["Daron Acemoglu", "Pascual Restrepo"], "year": 2018},
            {"title": "Robots and Jobs: Capital-Labor Substitution", "doi": "10.1086/705716", "authors": ["Daron Acemoglu"], "year": 2020}
        ],
        "gold_doi": "10.1257/aer.20160696",
        "type": "POSITIVE"
    },
    {
        "id": "REF-04",
        "citation": Citation(id="cit_4", raw_text="姚加权, 冯展斌. 人工智能如何提升企业生产效率. 经济研究, 2023.", title="人工智能如何提升企业生产效率"),
        "candidates": [
            {"title": "人工智能如何提升企业生产效率", "doi": "cnki.1002-8439.2023.02.001", "authors": ["姚加权", "冯展斌"], "year": 2023},
            {"title": "人工智能与劳动收入份额", "doi": "cnki.1002-8439.2022.01.002", "authors": ["姚加权"], "year": 2022}
        ],
        "gold_doi": "cnki.1002-8439.2023.02.001",
        "type": "POSITIVE"
    },

    # ── Category 2: Cross-Provider Duplicate DOI Normalization Cases ──
    {
        "id": "REF-05",
        "citation": Citation(id="cit_5", raw_text="Devlin et al. BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. NAACL 2019.", title="BERT: Pre-training of Deep Bidirectional Transformers"),
        "candidates": [
            {"title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", "doi": "https://doi.org/10.18653/v1/n19-1423", "authors": ["Jacob Devlin"], "year": 2019},
            {"title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", "doi": "10.18653/V1/N19-1423", "authors": ["Jacob Devlin"], "year": 2019}
        ],
        "gold_doi": "10.18653/v1/n19-1423",
        "type": "DUPLICATE_DEDUP"
    },

    # ── Category 3: Ambiguous Candidate Abstention Cases (Should Abstain / Output UNCERTAIN) ──
    {
        "id": "REF-06",
        "citation": Citation(id="cit_6", raw_text="Smith J. Machine Learning Advances. 2021.", title="Machine Learning Advances"),
        "candidates": [
            {"title": "Machine Learning Advances and Applications Part I", "doi": "10.1000/100", "authors": ["J Smith"], "year": 2021},
            {"title": "Machine Learning Advances and Applications Part II", "doi": "10.1000/101", "authors": ["J Smith"], "year": 2021}
        ],
        "gold_doi": None,
        "type": "ABSTAIN_AMBIGUOUS"
    },
    {
        "id": "REF-07",
        "citation": Citation(id="cit_7", raw_text="Li W. Quantum Neural Networks. 2022.", title="Quantum Neural Networks", authors=["Li W"]),
        "candidates": [
            {"title": "Quantum Neural Networks: A Comprehensive Review", "doi": "10.2000/200", "authors": ["Wei Li"], "year": 2022},
            {"title": "Quantum Neural Networks for Classification", "doi": "10.2000/201", "authors": ["Wei Li"], "year": 2022}
        ],
        "gold_doi": None,
        "type": "ABSTAIN_AMBIGUOUS"
    },

    # ── Category 4: Hallucinated / Out-of-Vocabulary Citation Abstention Cases ──
    {
        "id": "REF-08",
        "citation": Citation(id="cit_8", raw_text="王某某. 一个完全虚构的论文. 管理世界, 2023.", title="一个完全虚构的论文"),
        "candidates": [
            {"title": "完全无关的物理研究", "doi": "10.3000/300", "authors": ["张三"], "year": 2018}
        ],
        "gold_doi": None,
        "type": "ABSTAIN_HALLUCINATED"
    }
]


def run_reference_resolution_benchmark():
    console.print("[bold blue]🧪 启动文献实体消歧与重排验证自动化检验 (Reference Resolution Benchmark)[/bold blue]\n")
    resolver = ReferenceResolver()

    top1_correct = 0
    mrr_sum = 0.0
    recall5_correct = 0
    abstain_correct = 0
    total_positive = 0
    total_abstain = 0

    table = Table(title="📊 文献重排消歧 (Reference Resolution) 逐项基准评测")
    table.add_column("编号", style="cyan")
    table.add_column("类型", style="bold")
    table.add_column("引文摘要 (Input)", style="white")
    table.add_column("匹配得分", style="yellow")
    table.add_column("置信度", style="magenta")
    table.add_column("预测 DOI / 状态", style="dim")
    table.add_column("结果", style="bold")

    start_time = time.time()
    for item in RESOLUTION_GOLD_DATASET:
        cit = item["citation"]
        cands = item["candidates"]
        gold_doi = item["gold_doi"]
        case_type = item["type"]

        res = resolver.select_best_candidate(cit, cands, min_score=0.40)

        pred_doi = res.get("doi") if res else None
        pred_conf = res.get("match_confidence") if res else "NONE"
        pred_score = res.get("match_score", 0.0) if res else 0.0
        is_uncertain = (res.get("is_uncertain") is True) if res else False

        is_abstain_case = case_type.startswith("ABSTAIN")
        if is_abstain_case:
            total_abstain += 1
            is_correct = (res is None) or is_uncertain or (pred_conf == "UNCERTAIN")
            if is_correct:
                abstain_correct += 1
        else:
            total_positive += 1
            # Check normalized match
            norm_pred = resolver.normalize_doi(pred_doi)
            norm_gold = resolver.normalize_doi(gold_doi)
            is_correct = (norm_pred == norm_gold) and (pred_conf in ("HIGH", "MEDIUM")) and (not is_uncertain)

            if is_correct:
                top1_correct += 1

            # Calculate Rank for MRR & Recall@5
            scored_cands = []
            clean_cands = resolver.deduplicate_candidates(cands)
            for c in clean_cands:
                sc, _ = resolver.compute_candidate_score(cit, c)
                scored_cands.append((sc, c))
            scored_cands.sort(key=lambda x: x[0], reverse=True)

            rank = None
            for r_idx, (sc, c) in enumerate(scored_cands, 1):
                if resolver.normalize_doi(c.get("doi")) == norm_gold:
                    rank = r_idx
                    break

            if rank is not None:
                mrr_sum += (1.0 / rank)
                if rank <= 5:
                    recall5_correct += 1

        badge = "[green]PASS ✅[/green]" if is_correct else "[red]FAIL ❌[/red]"
        disp_status = f"{pred_doi or 'ABSTAINED'}" if not res or not res.get("is_uncertain") else "UNCERTAIN_ABSTAIN"
        table.add_row(item["id"], case_type, cit.title[:30] + "...", f"{pred_score:.2f}", pred_conf, disp_status[:35], badge)

    console.print(table)
    elapsed = round(time.time() - start_time, 4)

    top1_acc = (top1_correct / max(total_positive, 1)) * 100.0
    mrr = (mrr_sum / max(total_positive, 1))
    recall5 = (recall5_correct / max(total_positive, 1)) * 100.0
    abstain_acc = (abstain_correct / max(total_abstain, 1)) * 100.0

    console.print("\n[bold green]📈 Reference Resolution 核心基准评估指标:[/bold green]")
    console.print(f"  • [bold]Top-1 Accuracy[/bold]: {top1_acc:.2f}% ({top1_correct}/{total_positive})")
    console.print(f"  • [bold]MRR (Mean Reciprocal Rank)[/bold]: {mrr:.4f}")
    console.print(f"  • [bold]Recall@5[/bold]: {recall5:.2f}% ({recall5_correct}/{total_positive})")
    console.print(f"  • [bold]Abstention Accuracy[/bold]: {abstain_acc:.2f}% ({abstain_correct}/{total_abstain})")
    console.print(f"  • [dim]用时: {elapsed} 秒[/dim]\n")


if __name__ == "__main__":
    run_reference_resolution_benchmark()
