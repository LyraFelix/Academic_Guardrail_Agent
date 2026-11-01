# 反驳分析与同证据对照导读

这个 MCP 不内置大模型。客户端负责理解论断与文献，服务端负责保留来源、核对引用和检查客户端声明的一致性。本轮新增的 `findings` 让你能看到：客户端到底认为哪一部分被支持、反驳，或者没有证据。

## 从一个例子理解

原论断：`Treatment increases mortality and the effect lasts ten years.`
证据：`Treatment reduced mortality compared with placebo. Follow-up lasted six months.`

“增加死亡率”与给定结果方向相反。即使十年结果缺失，明确的方向矛盾仍可反驳这个合取论断。反过来，如果论断询问出血，而文献只测量死亡率，不能把死亡率的方向当作出血的反证。

客户端可以提交：

```json
{
  "claim_part": "Treatment increases mortality",
  "relation": "CONTRADICTS",
  "evidence_ids": ["e1"],
  "reason": "The provided sentence reports reduced mortality versus placebo."
}
```

`claim_part` 必须逐字来自原论断，证据 ID 必须有对应的逐字引用。同一分项只保留一个 finding；相互冲突且无法解决的观察记为 `UNCLEAR`。如果客户端已经提交 `CONTRADICTS`，总判断却是 `NOT_ENOUGH_EVIDENCE`，服务端会拒绝这个不一致的提交，要求客户端回到原文检查。

服务端并不验证“降低”是否真的反驳“增加”，也不证明分项覆盖了原论断的全部含义。因此返回 `findings_semantically_verified=false`。旧客户端不传 `findings` 仍可使用；这个兼容模式也没有新增的分项一致性保障。

## 三组对照各回答什么

| 组 | 给模型的内容 | 用途 |
| --- | --- | --- |
| `direct` | 完整论断、编号原文、简短任务说明、共同 JSON 格式 | 直接使用同一客户端的基线 |
| `guided_direct` | 相同原文和格式，加项目语义判断提示 | 观察提示本身的作用 |
| `mcp` | 与上一组相同，再加实际 MCP 的检索/规则提示；通过 MCP 保存 | 观察额外提示和可验证记录流程的作用 |

三组都得到相同的完整证据、编号、顺序和输出格式。直接组也是结构化输出基线，已经受到字段结构的引导。规则状态不是语义答案；MCP 协议或传输方式本身也不会提升模型智力。

先比较原始模型标签，再分别报告相同离线检查器的接受率、接受后的标签一致率和逐字引用有效率。一次引用检查失败不会删除它原本的语义错误。只有 MCP 组另外执行实际 `record_claim_review`；没有自动修复重试或额外推理轮次。

## 阅读代码的顺序

1. `core/review_models.py`：`ClaimFinding` 和原有 `ClientJudgment` 的字段。
2. `core/review_instructions.py`：反驳、缺失、范围和比较对象的判断提示，与工具调用指令分开。
3. `core/claim_review.py`：核对原论断片段、引用和已声明关系的一致性，不生成语义标签。
4. `benchmarks/client_comparison.py`：三组提示的唯一差异、原始标签提取、指标和逐条配对胜负。
5. `scripts/prepare_paired_review.py`：抽样、排除旧样本、实际 MCP 证据包、冻结全部提示。
6. `scripts/codex_review_client.py` 与 `run_paired_review.py`：独立上下文调用、原始记录、超时/异常保留和相同检查器。
7. `scripts/score_paired_review.py`：最后才打开 gold，检查哈希和完整分母，再计分。

## 复现入口

已完成的 30 条三组试跑使用 `paired_source_review_v1`，代码固定为 `adeaa9a`。要重放该轮模型输入，先检出该提交；计分可直接重放保留的 v1 记录。本轮报告不会因后续提示修改而重算模型答案。

当前新计划标记为 **v2**：已把完整的跨字段存储规则放入三组共同说明和 schema 描述。v1 中直接组没有同等明确地得到“每个 finding 引用 ID 都须有逐字引用”的说明，因此其记录接受率差距不能当作 MCP 检出了更多事实错误。**v2 尚未运行新的模型效果实验**；未来验证需追加排除本轮 30 条输入，不能把已看过结果的同一批样本称为未见验证集。

在仓库根目录和已安装项目依赖的 Python 环境运行。运行器另外需要已安装、已登录的 Codex CLI；它使用现有客户端，不读取或打印认证文件，不是服务端依赖。

如需从头重建本轮排除清单，先按前两轮协议生成 12 和 60 条输入，再准备新对照。各输出目录必须是新的，脚本不会覆盖旧结果。

```powershell
python -m benchmarks download-scifact --output benchmarks/data/scifact.tar.gz
python -m scripts.prepare_client_pilot --archive benchmarks/data/scifact.tar.gz --output benchmarks/data/prior_12 --size 12
python -m scripts.prepare_client_evaluation --archive benchmarks/data/scifact.tar.gz --prior-inputs benchmarks/data/prior_12/inputs.jsonl --output benchmarks/data/prior_60
python -m scripts.prepare_paired_review --archive benchmarks/data/scifact.tar.gz --exclude-inputs benchmarks/data/prior_12/inputs.jsonl benchmarks/data/prior_60/discovery/inputs.jsonl benchmarks/data/prior_60/validation/inputs.jsonl --output benchmarks/runs/paired_data_01
python -m scripts.run_paired_review --plan benchmarks/runs/paired_data_01/plan/plan.json --batch benchmarks/runs/paired_data_01/batch --output benchmarks/runs/paired_model_01
python -m scripts.score_paired_review --run benchmarks/runs/paired_model_01 --gold benchmarks/runs/paired_data_01/dataset/gold.jsonl --output benchmarks/runs/paired_metrics_01.json
```

模型固定配置在 `codex_review_client.py`，当前请求 `gpt-6.1-sol`、推理 `high`。改变配置须重新准备计划，不能沿用旧运行目录。CLI 版本、每次命令、提示、输出格式、原始事件、最终答案及 token 均保留；缺失用量为未知，不补成零。

每个样本每组启动一个新的临时上下文，没有恢复旧会话。运行器请求关闭记忆、技能、外部工具和联网，采用空临时工作目录；本机版本的诊断仍显示工具定义及技能元数据可能存在。已观察到的零工具调用不能证明工具完全不可用，故一旦实际调用工具或事件无法解析就停止后续批次。这个对照是受控 Codex 客户端流程，不是去掉所有系统提示的裸模型 API。配置和运行方式参见 [OpenAI 非交互模式文档](https://learn.chatgpt.com/docs/non-interactive-mode)与[配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)。

每次只调用一次 CLI，运行器不重试；CLI 内部传输可能重试，不能把调用次数直接当作 HTTP 请求次数。三组同一案例至多并行三个调用，启动顺序按案例轮换。时间含客户端启动和模型处理；缓存及网络会影响它，不能由 token 换算未测量的费用或人工节省。

30 条均衡公开 train 样本只适合探索性配对观察。必须保留反驳召回/精确率的分母、误报、拒绝和失败；不能把以前 3/8 与新数据上的分数相减称为增益。冻结记录和计分可以复现，再次调用模型不保证相同答案。
