"""Aggregates LLM subagent evaluation predictions across 323 SciFact dev set items and prints performance metrics."""

import sys
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

console = Console(force_terminal=True)
scratch_dir = Path("C:/Users/Felix/.gemini/antigravity/brain/bde8ec19-c1ff-492d-9be0-9d0aed028cd2/scratch")

items_dict = {}

# Load input items (with gold labels)
for b_idx in range(1, 7):
    batch_file = scratch_dir / f"scifact_batch_{b_idx}.json"
    with open(batch_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        for item in data:
            items_dict[item["id"]] = item

# Load predictions
preds_dict = {}
for r_idx in range(1, 7):
    res_file = scratch_dir / f"scifact_results_{r_idx}.json"
    with open(res_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        for item in data:
            preds_dict[item["id"]] = item["pred"]

tp_sup, fp_sup, fn_sup = 0, 0, 0
tp_con, fp_con, fn_con = 0, 0, 0
correct = 0
total = len(items_dict)

for item_id, item in items_dict.items():
    gold = item["gold"]
    pred = preds_dict.get(item_id, "NEUTRAL")

    if pred == gold:
        correct += 1

    if pred == "SUPPORTS" and gold == "SUPPORTS":
        tp_sup += 1
    elif pred == "SUPPORTS" and gold != "SUPPORTS":
        fp_sup += 1
    elif pred != "SUPPORTS" and gold == "SUPPORTS":
        fn_sup += 1

    if pred == "CONTRADICTS" and gold == "CONTRADICTS":
        tp_con += 1
    elif pred == "CONTRADICTS" and gold != "CONTRADICTS":
        fp_con += 1
    elif pred != "CONTRADICTS" and gold == "CONTRADICTS":
        fn_con += 1

acc = correct / max(total, 1)

p_sup = tp_sup / max(tp_sup + fp_sup, 1)
r_sup = tp_sup / max(tp_sup + fn_sup, 1)
f1_sup = 2 * (p_sup * r_sup) / max(p_sup + r_sup, 1e-6)

p_con = tp_con / max(tp_con + fp_con, 1)
r_con = tp_con / max(tp_con + fn_con, 1)
f1_con = 2 * (p_con * r_con) / max(p_con + r_con, 1e-6)

macro_f1 = (f1_sup + f1_con) / 2

console.print("[bold cyan]========================================================================[/bold cyan]")
console.print("[bold cyan] 🧠 宿主 LLM 模型在 SciFact 官方 Dev 集 323 样本上的零样本判定实测[/bold cyan]")
console.print("[bold cyan]========================================================================[/bold cyan]\n")

table = Table(title="LLM + MCP 架构在 SciFact 官方数据集上的实际推理能力")
table.add_column("指标 (Metric)", style="cyan")
table.add_column("SUPPORTS (支持)", style="green")
table.add_column("CONTRADICTS (反驳)", style="magenta")
table.add_column("Overall (总体)", style="bold yellow")

table.add_row("Precision (准确率)", f"{p_sup:.2f}", f"{p_con:.2f}", "-")
table.add_row("Recall (召回率)", f"{r_sup:.2f}", f"{r_con:.2f}", "-")
table.add_row("F1-Score (F1 值)", f"{f1_sup:.2f}", f"{f1_con:.2f}", f"{macro_f1:.2f}")
table.add_row("Accuracy (总体准确度)", "-", "-", f"{acc:.1%}")

console.print(table)
console.print(f"\n样本覆盖: [bold]{len(preds_dict)} / {total}[/bold] 项，零报错完成比对。")
