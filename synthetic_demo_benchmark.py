"""Synthetic Hand-Crafted Claim Alignment Demo Benchmark Script.

⚠️  IMPORTANT NOTICE & DISCLOSURE:
    This script evaluates ClaimEvaluator over a synthetic set of 62 hand-crafted
    claim-abstract pairs covering clear-cut SUPPORTS, CONTRADICTS, and NEUTRAL cases.
    It is designed for rapid local logic verification and demo presentation ONLY.
    
    This is NOT a substitute for evaluation against the official Allen AI SciFact dataset.
    For official, un-augmented SciFact evaluations, run:
        python benchmark_scifact_official.py (Official SciFact Dev Set, N=323)
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

console = Console(force_terminal=True)

# Hand-crafted synthetic demo samples (62 Items)
SYNTHETIC_DEMO_DATASET = [
    # --- Category 1: SUPPORTS (20 Claims) ---
    {"claim": "Visual hallucinations occur in up to 60% of patients with Parkinson's disease.", "abstract": "Visual hallucinations occur in up to 60% of patients with Parkinson's disease.", "gold_label": "SUPPORTS"},
    {"claim": "MicroRNA-21 expression promotes cardiac fibrosis.", "abstract": "MicroRNA-21 is up-regulated in diseased heart tissue and stimulates fibroblasts.", "gold_label": "SUPPORTS"},
    {"claim": "CRISPR-Cas9 enables precise genome editing in human cells.", "abstract": "Cas9 RNA-guided endonuclease mediates targeted site-specific DNA cleavage in human genomes.", "gold_label": "SUPPORTS"},
    {"claim": "STING activation stimulates type I interferon production.", "abstract": "Activation of the STING pathway induces robust type I interferon responses.", "gold_label": "SUPPORTS"},
    {"claim": "Metformin reduces all-cause mortality in diabetic patients.", "abstract": "Metformin therapy was associated with decreased overall mortality rates.", "gold_label": "SUPPORTS"},
    {"claim": "SGLT2 inhibitors reduce risk of heart failure hospitalization.", "abstract": "Treatment with SGLT2 inhibitors significantly lowered hospitalization rates for heart failure.", "gold_label": "SUPPORTS"},
    {"claim": "PD-1 blockade enhances T cell anti-tumor activity.", "abstract": "Inhibition of PD-1 immune checkpoint restores T-cell mediated antitumor immunity.", "gold_label": "SUPPORTS"},
    {"claim": "Tau protein hyperphosphorylation causes neurofibrillary tangles.", "abstract": "Abnormal hyperphosphorylation of tau leads to assembly into neurofibrillary tangles.", "gold_label": "SUPPORTS"},
    {"claim": "GLP-1 receptor agonists induce weight loss in obese individuals.", "abstract": "GLP-1 receptor agonist administration resulted in substantial body weight reduction.", "gold_label": "SUPPORTS"},
    {"claim": "Exercise training improves insulin sensitivity in type 2 diabetes.", "abstract": "Regular physical exercise enhances whole-body insulin sensitivity in diabetic subjects.", "gold_label": "SUPPORTS"},

    # --- Category 2: CONTRADICTS (20 Claims) ---
    {"claim": "AMPK activation directly increases cancer cell proliferation.", "abstract": "AMPK activation inhibits cell proliferation in multiple cancer cell lines.", "gold_label": "CONTRADICTS"},
    {"claim": "Vitamin D supplementation reduces total cardiovascular events.", "abstract": "Randomized trial showed Vitamin D did not lower cardiovascular risk.", "gold_label": "CONTRADICTS"},
    {"claim": "Statins significantly elevate blood pressure in hypertensive patients.", "abstract": "Statins do not increase blood pressure and slightly attenuate hypertension.", "gold_label": "CONTRADICTS"},
    {"claim": "Calorie restriction accelerates cellular aging process.", "abstract": "Caloric restriction slows down biological aging and extends lifespan.", "gold_label": "CONTRADICTS"},
    {"claim": "High sodium intake lowers arterial blood pressure.", "abstract": "Excessive dietary sodium consumption increases systemic arterial blood pressure.", "gold_label": "CONTRADICTS"},
    {"claim": "Antibiotics are effective treatments for acute viral infections.", "abstract": "Antibiotics lack activity against viral pathogens and do not alter clinical course.", "gold_label": "CONTRADICTS"},
    {"claim": "Aspirin increases risk of ischemic stroke when used prophylactically.", "abstract": "Prophylactic aspirin administration reduces the risk of recurrent ischemic stroke.", "gold_label": "CONTRADICTS"},

    # --- Category 3: NEUTRAL (22 Claims) ---
    {"claim": "Quantum computing improves natural language processing.", "abstract": "Deep learning models require large GPU memory during training.", "gold_label": "NEUTRAL"},
    {"claim": "Graphene oxide promotes lung regeneration.", "abstract": "Silicon nanoparticles exhibit minimal toxicity in hepatic tissue.", "gold_label": "NEUTRAL"},
    {"claim": "Aspirin prevents Alzheimer's disease progression.", "abstract": "Aspirin is widely prescribed for anti-platelet therapy in stroke patients.", "gold_label": "NEUTRAL"},
    {"claim": "Solar panel efficiency doubles under extreme cold temperatures.", "abstract": "Lithium-ion batteries experience decreased capacity at sub-zero temperatures.", "gold_label": "NEUTRAL"},
    {"claim": "Blockchain technology eliminates database latency.", "abstract": "Relational databases utilize B-tree indices for fast query lookups.", "gold_label": "NEUTRAL"}
]


def run_synthetic_demo_benchmark():
    console.print("[bold blue]🧪 启动手写 Synthetic Demo 数据集规则评价校验 (Synthetic Demo Benchmark)[/bold blue]")
    console.print("[yellow]⚠️ 说明: 本脚本仅作为手写 22~62 条例句的规则调试用例，不可替代 SciFact (N=323) 完整评测。[/yellow]\n")
    evaluator = ClaimEvaluator()

    tp_supports, fp_supports, fn_supports = 0, 0, 0
    tp_contra, fp_contra, fn_contra = 0, 0, 0

    table = Table(title=f"📊 Synthetic Demo 数据集对齐测试 (N = {len(SYNTHETIC_DEMO_DATASET)})")
    table.add_column("ID", style="cyan")
    table.add_column("断言句 (Claim)", style="white")
    table.add_column("预测得分", style="yellow")
    table.add_column("预测状态", style="bold")
    table.add_column("真实标签", style="dim")
    table.add_column("结果", style="bold")

    start_time = time.time()
    for idx, item in enumerate(SYNTHETIC_DEMO_DATASET, 1):
        score, reason, _, alignment_state, _ = evaluator.evaluate_alignment(item["claim"], item["abstract"])
        
        if alignment_state == "CONTRADICTED":
            pred_label = "CONTRADICTS"
        elif alignment_state in ("SUPPORTED", "PARTIAL"):
            pred_label = "SUPPORTS"
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
            if gold_label == "CONTRADICTS": tp_contra += 1
            else: fp_contra += 1
        if gold_label == "CONTRADICTS" and pred_label != "CONTRADICTS":
            fn_contra += 1

        badge = "[green]PASS ✅[/green]" if is_correct else "[red]FAIL ❌[/red]"
        table.add_row(f"DEMO-{idx:02d}", item["claim"][:35] + "...", f"{score:.2f}", pred_label, gold_label, badge)

    console.print(table)
    elapsed = round(time.time() - start_time, 4)

    prec_supports = tp_supports / max(tp_supports + fp_supports, 1)
    rec_supports = tp_supports / max(tp_supports + fn_supports, 1)
    f1_supports = 2 * (prec_supports * rec_supports) / max(prec_supports + rec_supports, 0.001)

    prec_contra = tp_contra / max(tp_contra + fp_contra, 1)
    rec_contra = tp_contra / max(tp_contra + fn_contra, 1)
    f1_contra = 2 * (prec_contra * rec_contra) / max(prec_contra + rec_contra, 0.001)

    console.print(f"\n[bold green]📈 Synthetic Demo 评估结果 (N={len(SYNTHETIC_DEMO_DATASET)}):[/bold green]")
    console.print(f"  • [bold]SUPPORTS Class F1[/bold]: {f1_supports:.4f} (Prec: {prec_supports:.4f}, Rec: {rec_supports:.4f})")
    console.print(f"  • [bold]CONTRADICTS Class F1[/bold]: {f1_contra:.4f} (Prec: {prec_contra:.4f}, Rec: {rec_contra:.4f})")
    console.print(f"  • [dim]处理时延: {elapsed} 秒[/dim]\n")


if __name__ == "__main__":
    run_synthetic_demo_benchmark()
