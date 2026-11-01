# 可复现评测入口

从仓库根目录运行，使用已经安装项目开发依赖的 Python 环境。没有新增模型或依赖。`python -m benchmarks --help` 列出命令；下载、预测和评分是三个独立步骤。

## 一次完整运行

```powershell
# 仅此步骤联网，下载经过 SHA-256 固定的官方公开数据。
python -m benchmarks download-scifact --output benchmarks/data/scifact.tar.gz

# 之后的步骤均离线，输出目录必须不存在。
python -m benchmarks prepare-scifact --archive benchmarks/data/scifact.tar.gz --output benchmarks/data/scifact_dev_v1
python -m benchmarks run --dataset benchmarks/data/scifact_dev_v1 --method guardrail --output benchmarks/runs/scifact_run_01

# 不重新预测，只核对文件并从原始预测重算指标。
python -m benchmarks score --dataset benchmarks/data/scifact_dev_v1 --run benchmarks/runs/scifact_run_01

# 独立重跑，再比较数据、代码、配置、环境和逐条语义输出。
python -m benchmarks run --dataset benchmarks/data/scifact_dev_v1 --method guardrail --output benchmarks/runs/scifact_run_02
python -m benchmarks compare benchmarks/runs/scifact_run_01 benchmarks/runs/scifact_run_02
```

已有正确版本的本地 archive 时跳过下载，直接传 `--archive`。数据哈希不符会报错，不会静默换版本。缺少数据不会在 `run` 中自动下载。重复目录也会报错；请换新名称保留每次结果。

对照方法：把 `--method` 改为 `overlap`（词面相似度，固定阈值 0.50）或 `always_review`（始终要求复核），并指定新的输出目录。它们接收相同完整摘要，不读取答案；都是简单诊断对照，不能当作发表论文中的 NLI 基线。

合成回归单独运行：

```powershell
python -m benchmarks prepare-regression --output benchmarks/data/regression_v1
python -m benchmarks run --dataset benchmarks/data/regression_v1 --output benchmarks/runs/regression_run_01
```

这些 50 个样例参与了第三阶段规则开发，属于开发回归，不是独立留出集。数据和运行目录默认被 Git 忽略，发布的是流程与测试，而不是下载的数据和临时产物。

## 输入与输出

准备目录含 `inputs.jsonl`、`gold.jsonl`、`manifest.json`，SciFact 还保留 `source.tar.gz`。输入只有 ID、论断和摘要句子；答案标签、预期提示、标注证据句在独立 gold 文件。每个原始 cited document 都保留，不能只取有标签的文献。

运行目录包含：

| 文件 | 用途 |
| --- | --- |
| `predictions.jsonl` | 每条原始状态、分数、原文、提示、耗时和错误；逐条刷新到磁盘 |
| `manifest.json` | 数据哈希、代码哈希与 Git 状态、配置、环境、时间、完成状态、离线访问计数 |
| `metrics.json` | 带明确分子分母的结构化指标 |
| `summary.md` | 状态分布、指标和提示代码频数 |
| `cases.tsv` | 所有样本的输入、标签与输出，便于筛选 |
| `failures.json` | 所有漏掉的矛盾告警、非矛盾标签告警、不受支持的文字对齐及运行错误，含全文和原因 |

单条异常记为 ERROR 并继续，仍占分母；命令最终退出码非零。中断保留已写出的行，manifest 为 `incomplete`，不能评分或冒充完整运行。修改预测或输入后校验会失败。哈希用于识别文件变化，不是对人为重写整个 manifest 的防伪签名。

## 如何解释 SciFact 结果

固定数据为 300 条 dev 论断与全部 340 个所引文献配对：SUPPORT 138、CONTRADICT 71、NEI 131。每对提供完整摘要，不提供标注证据句。粒度是**配对**，同一论断引用多篇文献时会出现多行。

这测试“给定所引文献时，当前规则发出什么提示”。它不测试从 5,183 篇文献中检索，不核验真实 DOI、解析稿件或撤稿覆盖，也不是 [官方 SciFact leaderboard 指标](https://github.com/allenai/scifact/blob/master/doc/evaluation.md)。dev 曾用于项目历史评测，不能称为从未接触过的留出集。

| 指标 | 定义与边界 |
| --- | --- |
| `contradiction_alert_precision` | 标为 POTENTIAL_CONFLICT 且 gold=CONTRADICT / 所有 POTENTIAL_CONFLICT；没发告警时为 null |
| `contradiction_alert_recall` | 上述命中 / 所有 CONTRADICT；ERROR 和复核均不能计为命中 |
| `support_alert_rate` / `nei_alert_rate` | 在 SUPPORT / NEI 上发出具体冲突告警的比例；NEI 不表示论断为假 |
| `aligned_support_fraction` | TEXT_ALIGNED 中 gold=SUPPORT 的比例；只是诊断，生产系统仍要求人工阅读 |
| `review_required_rate` | REVIEW_REQUIRED 状态比例；没有测量人的工作量 |
| `rationale_any_hit` | 主摘录与任一标注证据句有字符重叠 / 所有有证据配对 |
| `rationale_complete_hit` | 主摘录完整包含至少一组标注证据句 / 所有有证据配对；不是官方证据评分 |

不要将四个复核状态硬映射成三类真值，再计算“综合准确率”。SUPPORT 标签与某些措辞复核提示也可能并存；需要结合失败案例解释。

## 源码与历史文件

按 `schema.py → datasets.py → predictors.py → metrics.py → runner.py → reporting.py → __main__.py` 阅读。数据、预测、计分和展示各有单独职责。[中文学习导读](../docs/phase_four_guide.md) 解释为何这样划分。

旧脚本原文保存在 [legacy](legacy/README.md)，哈希可核验；旧入口会给迁移提示。八条参考文献消歧样例仅保留为已有单元测试的输入，不代表外部检索准确率。

SciFact 来源：[官方项目](https://github.com/allenai/scifact)、[数据格式](https://github.com/allenai/scifact/blob/master/doc/data.md)、[许可](https://github.com/allenai/scifact/blob/master/LICENSE.md)。Wadden et al. (2020), *Fact or Fiction: Verifying Scientific Claims*。上游许可文件将 claims/annotations 标为 CC BY 4.0，摘要标为 ODC-By 1.0；版本与来源存于 `scifact_source.json` 及准备目录 manifest。
