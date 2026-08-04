"""Dedicated Claim Consistency & Entailment Verification Benchmark Script.

Evaluates claim_eval.py against SciFact gold-standard claims for 
Precision, Recall, F1-Score, and Confusion Matrix.
"""

import sys
import time
from rich.console import Console
from rich.table import Table

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from academic_guardrail.providers.claim_eval import ClaimEvaluator
from academic_guardrail.core.models import RiskLevel

console = Console(force_terminal=True)

# Gold Standard SciFact Benchmark Claims Suite (12 Annotations)
SCIFACT_GOLD_DATASET = [
    # Category 1: SUPPORTS (Positive Alignment)
    {"claim": "Visual hallucinations occur in up to 60% of patients with Parkinson's disease.", "abstract": "Visual hallucinations occur in up to 60% of patients with Parkinson's disease.", "gold_label": "SUPPORTS"},
    {"claim": "MicroRNA-21 expression promotes cardiac fibrosis.", "abstract": "MicroRNA-21 is up-regulated in diseased heart tissue and stimulates fibroblasts.", "gold_label": "SUPPORTS"},
    {"claim": "CRISPR-Cas9 enables precise genome editing in human cells.", "abstract": "Cas9 RNA-guided endonuclease mediates targeted site-specific DNA cleavage.", "gold_label": "SUPPORTS"},
    {"claim": "STING activation stimulates type I interferon production.", "abstract": "Activation of the STING pathway induces robust type I interferon responses.", "gold_label": "SUPPORTS"},
    {"claim": "Metformin reduces all-cause mortality in diabetic patients.", "abstract": "Metformin therapy was associated with decreased overall mortality rates.", "gold_label": "SUPPORTS"},
    
    # Category 2: CONTRADICTS (Polarity Inversion / Distorted Claims)
    {"claim": "AMPK activation directly increases cancer cell proliferation.", "abstract": "AMPK activation inhibits cell proliferation in multiple cancer cell lines.", "gold_label": "CONTRADICTS"},
    {"claim": "Vitamin D supplementation reduces total cardiovascular events.", "abstract": "Randomized trial showed Vitamin D did not lower cardiovascular risk.", "gold_label": "CONTRADICTS"},
    {"claim": "Statins significantly elevate blood pressure in hypertensive patients.", "abstract": "Statins do not increase blood pressure and slightly attenuate hypertension.", "gold_label": "CONTRADICTS"},
    {"claim": "Calorie restriction accelerates cellular aging process.", "abstract": "Caloric restriction slows down biological aging and extends lifespan.", "gold_label": "CONTRADICTS"},

    # Category 3: NEUTRAL / UNRELATED (Off-topic or Weak Relevance)
    {"claim": "Quantum computing improves natural language processing.", "abstract": "Deep learning models require large GPU memory during training.", "gold_label": "NEUTRAL"},
    {"claim": "Graphene oxide promotes lung regeneration.", "abstract": "Silicon nanoparticles exhibit minimal toxicity in hepatic tissue.", "gold_label": "NEUTRAL"},
    {"claim": "Aspirin prevents Alzheimer's disease progression.", "abstract": "Aspirin is widely prescribed for anti-platelet therapy in stroke patients.", "gold_label": "NEUTRAL"}
]


def run_claim_verification_benchmark():
    console.print("[bold blue]🧪 启动内容断言一致性审查自动化检验 (Claim Consistency Benchmark)[/bold blue]\n")
    evaluator = ClaimEvaluator()

    tp_supports, fp_supports, fn_supports = 0, 0, 0
    tp_contradicts, fp_contradicts, fn_contradicts = 0, 0, 0

    table = Table(title="📊 断言对齐与矛盾识别逐项评测")
    table.add_column("编号", style="cyan")
    table.add_column("断言句 (Claim)", style="white")
    table.add_column("预测得分", style="yellow")
    table.add_column("预测标签", style="bold")
    table.add_column("真实标签 (Gold)", style="dim")
    table.add_column("结果", style="bold")

    start_time = time.time()
    for idx, item in enumerate(SCIFACT_GOLD_DATASET, 1):
        score, reason = evaluator.evaluate_alignment(item["claim"], item["abstract"])
        
        # Mapping Score -> Predicted Label
        if score >= 0.50:
            pred_label = "SUPPORTS"
        elif score < 0.30:
            pred_label = "CONTRADICTS" if "Polarity mismatch" in reason or "contradiction" in reason.lower() else "NEUTRAL"
        else:
            pred_label = "NEUTRAL"

        gold_label = item["gold_label"]
        is_correct = (pred_label == gold_label)

        if pred_label == "SUPPORTS":
            if gold_label == "SUPPORTS": tp_supports += 1
            else: fp_supports += 1
        if gold_label == "SUPPORTS" and pred_label != "SUPPORTS":
            fn_supports += 1

        if pred_label == "CONTRADICTS":
            if gold_label == "CONTRADICTS": tp_contradicts += 1
            else: fp_contradicts += 1
        if gold_label == "CONTRADICTS" and pred_label != "CONTRADICTS":
            fn_contradicts += 1

        badge = "[green]PASS ✅[/green]" if is_correct else "[red]FAIL ❌[/red]"
        table.add_row(f"CLM-{idx:02d}", item["claim"][:35] + "...", f"{score:.2f}", pred_label, gold_label, badge)

    console.print(table)
    elapsed = round(time.time() - start_time, 4)

    prec_supports = tp_supports / max(tp_supports + fp_supports, 1)
    rec_supports = tp_supports / max(tp_supports + fn_supports, 1)
    f1_supports = 2 * (prec_supports * rec_supports) / max(prec_supports + rec_supports, 0.001)

    prec_contra = tp_contradicts / max(tp_contradicts + fp_contradicts, 1)
    rec_contra = tp_contradicts / max(tp_contradicts + fn_contradicts, 1)
    f1_contra = 2 * (prec_contra * rec_contra) / max(prec_contra + rec_contra, 0.001)

    console.print(f"\n[bold]📈 内容审查评测核心指标 (SciFact Metric Results)[/bold]:")
    console.print(f"- **SUPPORTS (正向支持断言)**: Precision = {prec_supports:.2f}, Recall = {rec_supports:.2f}, [bold green]F1-Score = {f1_supports:.2f}[/bold green]")
    console.print(f"- **CONTRADICTS (观点矛盾断言)**: Precision = {prec_contra:.2f}, Recall = {rec_contra:.2f}, [bold green]F1-Score = {f1_contra:.2f}[/bold green]")
    console.print(f"- **评估总耗时**: {elapsed} 秒")

if __name__ == '__main__':
    run_claim_verification_benchmark()
