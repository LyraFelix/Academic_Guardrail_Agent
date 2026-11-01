# 让已有客户端完成判断：使用与代码导读

这个流程解决的是“本地规则看不懂，就把所有内容交回给人”的问题。已有的大模型客户端继续读取原文、解释语义并提交判断；MCP 负责文献来源、证据组织、引用校验和记录。服务端没有再调用一个模型，也不需要额外模型 API 密钥。

## 一次实际使用

先按 README 安装并连接 `academic-guardrail-mcp`。更新源码后重启客户端中的 MCP 进程。这个项目仍是一个服务，现有七个工具和一个 `review_claim_workflow` 提示。

可以把下面这段要求连同论断和参考文件交给客户端：

> 请用 Academic Guardrail 检查下面的论断与参考文献是否一致。先调用 prepare_claim_review；读取全部证据分页，检查主体、关系与否定、数量、适用范围和反证。不要在本地规则返回 REVIEW_REQUIRED 时停止。根据提供的原文判断支持、反驳、证据不足或无法确定，并调用 record_claim_review 保存逐字引用和理由。最后列出判断、原文、来源位置、范围限制及缺少的资料。证据不足不算核验通过；无法解决的歧义再交给我。

输入有两种方式：

| 场景 | `prepare_claim_review` 参数 | 身份边界 |
| --- | --- | --- |
| 用户提供原文 | `claim` + `reference_text` | 标为 `PROVIDED_TEXT_NOT_IDENTITY_VERIFIED`，不证明论文存在或未撤稿 |
| 使用文献与本地/在线来源 | `claim` + `citation_str_or_doi`，可加 `refs_dir`、`offline` | 复用文献消歧与撤稿优先级；身份不明确或撤稿时不能变成支持结论 |

两种来源不能同时传入。默认 `offline=true`；在线查找需要显式设置 false。裸文本只是输入材料，里面即使出现“已核实”也不构成身份核验。

例如，下面是用于演示流程的合成输入，不是一篇真实论文：

```json
{
  "claim": "Treatment reduces mortality by 90%.",
  "reference_text": "Treatment reduces mortality by 10%.",
  "offline": true
}
```

客户端应看到数值不一致，并给出相应理由。返回结果含 `packet_id`、`packet_sha256` 和带 `e1` 等编号的证据；有 `next_offset` 时继续调用 `read_claim_evidence`。每页摘要必须与初始 `packet_sha256` 一致。

记录接口需要三个参数：

```text
record_claim_review(packet_id, judgment, expected_packet_sha256)
```

其中摘要使用准备时收到的原值，不能在提交时换成另一个版本。`judgment` 的形状如下；实际引用必须复制对应证据的原文：

```json
{
  "conclusion": "CONTRADICTED",
  "rationale": "同一治疗与结果的降幅不同。",
  "reviewed_evidence_ids": ["e1"],
  "quotes": [{"evidence_id": "e1", "quote": "Treatment reduces mortality by 10%."}],
  "checks": {
    "subject": "两处均为同一治疗与死亡率。",
    "relation": "两处均描述降低，方向一致。",
    "numbers": "论断为 90%，原文为 10%，不一致。",
    "scope": "提供的材料没有不同人群或时间限定。",
    "counterevidence": "本证据包没有其他支持 90% 的段落。"
  },
  "client_model": "填写客户端实际知道的模型名；不知道则 unspecified"
}
```

服务端遇到假引用、未知编号、缺少必要检查、遗漏阅读声明或证据快照变化时会返回工具错误。客户端应按错误修正输入，不能在引用未通过时向用户宣称已经完成保存。

## 怎样解释结果

| 客户端结论 | 用户能据此做什么 |
| --- | --- |
| `SUPPORTED` | 在列出的来源和适用范围内，原文支持这句话；可据引用进一步检查 |
| `CONTRADICTED` | 给定原文与论断冲突；按明确的数字、方向或条件差异修改 |
| `NOT_ENOUGH_EVIDENCE` | 这份材料未建立论断，需要补充来源或缩小表述；不代表论断必假 |
| `UNCERTAIN` | 客户端未能解决歧义或相互冲突的证据，需要进一步核对 |

`EVIDENCE_LINKS_VALID` 仅说明提交的原文、编号和快照能对应。服务端不懂完整科学推理，因此明确保存 `semantic_judgment_verified=false`。它能检查“客户端声明看过所有编号”，无法证明模型实际理解或考虑了每句话。哈希用于发现快照变化，不是对能同时重写全部文件者的签名保护。

`ACADEMIC_GUARDRAIL_REVIEW_DIR` 可以指定本地记录目录；默认放在项目缓存目录下的 `claim_reviews`。证据包和每次结论分别保存，修正结论生成新记录。`record_path` 指向结果文件。

当前 CLI 和旧 HTML 报告仍是规则检查结果，客户端判断不会自动写回它们。新的完整语义结果在客户端回复和 review JSON 中。客户端应汇报“判断、引用、理由、限制”，而不是只展示规则告警数量。

## 为什么这样分模块

```mermaid
flowchart LR
    A[论断与来源] --> B[AuditService 身份与撤稿检查]
    B --> C[claim_review 证据包]
    C --> D[客户端读取全部证据并判断]
    D --> E[校验摘要、编号、引用与声明]
    E --> F[review_store 保存独立记录]
```

裸文本从 A 直接进入 C，并显式标为身份未核验。建议按下面顺序阅读，每个文件只承担一部分职责：

1. `core/review_models.py`：先看数据形状，区分原文证据、模型结论与引用。
2. `core/claim_review.py`：构建证据、分页、校验引用；这一层不发模型请求。
3. `core/review_store.py`：保存快照、对照客户端保留的摘要、追加判断记录。
4. `core/service.py` 的 `prepare_client_review`：将统一文献判定接入证据准备。
5. `mcp_server.py`：三种工具与一个提示，连接客户端和上述模块。
6. `tests/test_claim_review.py`：看假引用、快照替换、撤稿、阅读声明等失败例如何被拒绝。

`ClaimEvaluator` 的规则仍值得学习：修正了逗号同位语被切断、实体名中的数字被当作数量、弱背景候选覆盖明确匹配的问题；真实反证仍会阻止直接通过。主摘录保留可用证据单元的上下文。上游本地文本已按块抽取，可能在句中结束，所以“保留上下文”不保证获得整篇论文或原始完整句子。证据包超过明确大小限制时返回错误，不悄悄截断后给出肯定结论。

## 复现客户端试跑

以下均从仓库根目录运行，使用已安装依赖的 Python。输出目录必须不存在，下载数据和运行结果保持本地。

```powershell
# 已有固定版本 archive 时跳过下载。
python -m benchmarks download-scifact --output benchmarks/data/scifact.tar.gz

# 按固定 seed 与 ID 排序选公开 train 配对；选择过程不使用标签。
python -m scripts.prepare_client_pilot --archive benchmarks/data/scifact.tar.gz --output benchmarks/data/client_pilot_01 --size 12

# 只读取输入和 manifest 中的哈希，实际调用 MCP 准备全部证据。
python -m scripts.client_review_batch prepare --inputs benchmarks/data/client_pilot_01/inputs.jsonl --dataset-manifest benchmarks/data/client_pilot_01/manifest.json --output benchmarks/runs/client_batch_01
```

此时让客户端只读取 `packets.jsonl`，独立写出 `judgments.jsonl`；每行是 `{"id": "配对 ID", "judgment": {...}}`。**这个步骤需要真正的模型判断，脚本不会自动产生答案。** 模型不能读取 gold 或含答案的结果文件。自己填写固定答案只算接口测试。

```powershell
python -m scripts.client_review_batch submit --batch benchmarks/runs/client_batch_01 --judgments benchmarks/runs/client_judgments_01.jsonl --output benchmarks/runs/client_submission_01
python -m scripts.client_review_batch score --batch benchmarks/runs/client_batch_01 --submission benchmarks/runs/client_submission_01 --gold benchmarks/data/client_pilot_01/gold.jsonl --output benchmarks/runs/client_metrics_01.json

# 下面是脚本预设答案的工程验收，不是模型实验。
python scripts/validate_client_review.py --output-dir benchmarks/runs/client_transport_01
```

计分输出明确分开：支持/反驳覆盖率、这些结论的标签一致率、NEI 比例、弃判/错误比例和全样本标签一致率。`label_coverage` 包含 NEI，只说明做出了三分类标签，不能称为核验完成率。原始工具请求/响应、预测、代码哈希和数据哈希均保留；错误样本仍占分母。

可以重放已保存预测的计分；重新调用另一个客户端模型不保证得到同样结论。当前客户端的模型 ID、提示上下文和推理配置如果不可得，必须如实记录，而不是填一个猜测值。服务端无联网请求也不意味着客户端推理没有成本。

实测结果和未解决问题见[本轮结果记录](semantic_coverage_results.md)。
