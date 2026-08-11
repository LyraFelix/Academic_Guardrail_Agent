"""Official SciFact Entailment Benchmark Evaluator.

Automatically downloads the official Allen AI SciFact dataset tarball
from S3 (https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz),
caches it in ~/.cache/academic_guardrail/scifact_data.tar.gz,
and evaluates ClaimEvaluator on official claims_dev.jsonl & corpus.jsonl.

Paper: Wadden et al., 2020 (EMNLP 2020) "Fact or Fiction: Verifying Scientific Claims"
"""

import os
import sys
import time
import json
import tarfile
import urllib.request
from typing import Tuple, List, Dict
from pathlib import Path
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

S3_SCIFACT_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
CACHE_DIR = Path.home() / ".cache" / "academic_guardrail"
TAR_PATH = CACHE_DIR / "scifact_data.tar.gz"


def ensure_scifact_data() -> Tuple[List[dict], Dict[int, dict]]:
    """Download and extract official SciFact dataset (claims_dev.jsonl and corpus.jsonl)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not TAR_PATH.exists() or TAR_PATH.stat().st_size == 0:
        console.print(f"[bold blue]📥 正在从 Allen AI 官方 S3 自动拉取 SciFact 数据集...[/bold blue]")
        try:
            with urllib.request.urlopen(S3_SCIFACT_URL) as resp:
                data = resp.read()
            with open(TAR_PATH, "wb") as f:
                f.write(data)
            console.print(f"[bold green]✓ 成功下载 SciFact 官方包 ({len(data) / 1024 / 1024:.2f} MB)[/bold green]\n")
        except Exception as e:
            console.print(f"[bold red]❌ 下载 SciFact 数据集失败: {e}[/bold red]")
            sys.exit(1)

    with tarfile.open(TAR_PATH, mode="r:gz") as tf:
        corpus_file = tf.extractfile("data/corpus.jsonl")
        corpus = {}
        for line in corpus_file.read().decode("utf-8").strip().split("\n"):
            if not line.strip():
                continue
            item = json.loads(line)
            corpus[item["doc_id"]] = item

        dev_file = tf.extractfile("data/claims_dev.jsonl")
        claims_dev = [json.loads(l) for l in dev_file.read().decode("utf-8").strip().split("\n") if l.strip()]

    return claims_dev, corpus


def run_official_scifact_benchmark():
    console.print("[bold cyan]======================================================[/bold cyan]")
    console.print("[bold cyan] 🧪 Allen AI SciFact 官方标准基准测试 (Official Dev Set)[/bold cyan]")
    console.print("[bold cyan]======================================================[/bold cyan]\n")

    claims_dev, corpus = ensure_scifact_data()
    evaluator = ClaimEvaluator()

    # Build evaluation instances: (claim_text, abstract_text, gold_label)
    eval_samples = []
    for c in claims_dev:
        claim_text = c["claim"]
        evidence_dict = c.get("evidence", {})
        
        if not evidence_dict:
            # No evidence in corpus => NEUTRAL / NOT_ENOUGH_INFO
            # Pair with first cited_doc if available, else skip
            for doc_id in c.get("cited_doc_ids", []):
                if doc_id in corpus:
                    abstract_text = " ".join(corpus[doc_id].get("abstract", []))
                    eval_samples.append((claim_text, abstract_text, "NEUTRAL"))
            continue

        for doc_id_str, ev_list in evidence_dict.items():
            doc_id = int(doc_id_str)
            if doc_id not in corpus:
                continue
            abstract_sentences = corpus[doc_id].get("abstract", [])
            abstract_text = " ".join(abstract_sentences)

            # Determine gold label for this doc
            # ev_list item: {"sentences": [...], "label": "SUPPORT" | "CONTRADICT"}
            labels = {ev.get("label") for ev in ev_list}
            if "SUPPORT" in labels:
                gold_label = "SUPPORTS"
            elif "CONTRADICT" in labels:
                gold_label = "CONTRADICTS"
            else:
                gold_label = "NEUTRAL"

            eval_samples.append((claim_text, abstract_text, gold_label))

    console.print(f"📊 评测总样本数 (Total Claim-Abstract Pairs): [bold yellow]{len(eval_samples)}[/bold yellow]\n")

    tp_sup, fp_sup, fn_sup = 0, 0, 0
    tp_con, fp_con, fn_con = 0, 0, 0
    correct = 0

    start_time = time.time()
    for claim, abstract, gold_label in eval_samples:
        score, reason, _ = evaluator.evaluate_alignment(claim, abstract)

        if "Polarity mismatch" in reason or "contradiction" in reason.lower():
            pred_label = "CONTRADICTS"
        elif score >= 0.25:
            pred_label = "SUPPORTS"
        else:
            pred_label = "NEUTRAL"

        if pred_label == gold_label:
            correct += 1

        if pred_label == "SUPPORTS" and gold_label == "SUPPORTS":
            tp_sup += 1
        elif pred_label == "SUPPORTS" and gold_label != "SUPPORTS":
            fp_sup += 1
        elif pred_label != "SUPPORTS" and gold_label == "SUPPORTS":
            fn_sup += 1

        if pred_label == "CONTRADICTS" and gold_label == "CONTRADICTS":
            tp_con += 1
        elif pred_label == "CONTRADICTS" and gold_label != "CONTRADICTS":
            fp_con += 1
        elif pred_label != "CONTRADICTS" and gold_label == "CONTRADICTS":
            fn_con += 1

    elapsed = time.time() - start_time
    total = len(eval_samples)
    acc = correct / max(total, 1)

    p_sup = tp_sup / max(tp_sup + fp_sup, 1)
    r_sup = tp_sup / max(tp_sup + fn_sup, 1)
    f1_sup = 2 * (p_sup * r_sup) / max(p_sup + r_sup, 1e-6)

    p_con = tp_con / max(tp_con + fp_con, 1)
    r_con = tp_con / max(tp_con + fn_con, 1)
    f1_con = 2 * (p_con * r_con) / max(p_con + r_con, 1e-6)

    table = Table(title="SciFact 官方评测标准结果 (Official Dev Set)")
    table.add_column("指标 (Metric)", style="cyan")
    table.add_column("SUPPORTS (支持)", style="green")
    table.add_column("CONTRADICTS (反驳)", style="magenta")
    table.add_column("Overall (总体)", style="bold yellow")

    table.add_row("Precision (准确率)", f"{p_sup:.2f}", f"{p_con:.2f}", "-")
    table.add_row("Recall (召回率)", f"{r_sup:.2f}", f"{r_con:.2f}", "-")
    table.add_row("F1-Score (F1 值)", f"{f1_sup:.2f}", f"{f1_con:.2f}", f"{(f1_sup + f1_con)/2:.2f}")
    table.add_row("Accuracy (准确度)", "-", "-", f"{acc:.1%}")

    console.print(table)
    console.print(f"\n⏱️ 评测耗时: [bold]{elapsed:.2f} 秒[/bold] (平均单条 {elapsed/total*1000:.2f} ms)\n")


if __name__ == "__main__":
    from typing import Tuple, List, Dict
    run_official_scifact_benchmark()
