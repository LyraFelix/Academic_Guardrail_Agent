# 本地补查：从证据缺口到前后对照报告

这条流程让已有大模型客户端先说明缺少什么，再到同一篇本地论文里补查一次，并把两次判断放在一起。MCP 服务负责取文本、核对引用和保存来源关系；语义判断仍由客户端作出。

项目仍是 **一个 MCP 服务**。本轮增加本地准备、补查、报告三个工具，总计十个工具。服务端没有增加模型 API，也不需要新的依赖或模型密钥。

## 先运行一个完整例子

在已安装本项目依赖的仓库根目录运行：

```powershell
python -m scripts.validate_local_followup --output benchmarks/runs/local_followup_demo_01
```

输出目录必须是新的。脚本会通过实际 MCP stdio 执行准备、记录、补查、再次记录和报告导出，并保留请求/响应。

- `review.html`：摘要没有数字，正文出现 25% 后，两次脚本判断并排展示。
- `changed_source.html`：原文件被改动后，报告仍保留历史证据，并明确显示文件已变化。
- `validation.json`：非法指纹、重复补查、源文件变化等检查结果。
- `transcript.jsonl`：每个工具调用的参数和返回值。

这里使用 `docs/examples/local_followup_refs/study.txt` 的**虚构材料和脚本判断**。它验证程序流程，不是模型准确率实验。真实论文的验证单独记录在结果文档中。

## 在大模型客户端中使用

连接 `academic-guardrail-mcp` 后，可以这样给客户端任务：

支持 MCP 提示的客户端也可选择 `review_claim_workflow`，填写 `claim`、`citation`、`refs_dir` 和新的 HTML `output_path`。提供本地目录后，这个提示会引导完整补查流程；不提供目录时仍使用原有证据准备流程。

> 请检查这条论断是否由我提供的本地论文支持。先用 prepare_local_claim_review 读取该论文摘要；读完全部分页并保存判断。证据不足时，在 missing_evidence 中指出原论断的具体片段、缺失问题和检索词。再用 follow_up_local_claim 对同一篇论文补查一次，读取新证据包所有页面，结合原证据重新判断并保存。最后用 generate_claim_review_report 导出补查前后对照 HTML，说明剩余缺口，不把引文校验成功当作科学正确性认证。

操作顺序如下：

```mermaid
flowchart LR
    A[本地文献身份匹配与摘要] --> B[客户端初次判断]
    B --> C[保存判断和缺失信息]
    C --> D[同一论文定向补查一次]
    D --> E[旧证据加新增原文]
    E --> F[客户端重新判断并保存]
    F --> G[补查前后 HTML 报告]
```

### 1. 准备本地证据

```json
{
  "claim": "The treatment reduced mortality by 25% at six months.",
  "citation_str_or_doi": "Synthetic Local Follow-up Study",
  "refs_dir": "D:/papers/refs",
  "initial_scope": "abstract"
}
```

调用 `prepare_local_claim_review`。示例目录需要替换成实际文献目录；示例标题对应的是演示文件。

默认 `abstract` 使用真实抽出的摘要。没有摘要时返回空证据，允许客户端说明缺口后补查正文。`full_text` 明确提供当前解析器抽出的论文正文；不包含参考文献列表，也不保证覆盖 OCR、复杂表格、附录或所有 PDF 布局。

只有身份匹配、无阻断状态的本地论文能开始此流程。文献身份歧义或已确认撤稿时会拒绝开始。离线撤稿库的覆盖有限，未找到记录不能解释为论文从未撤稿。

返回值包括 `packet_id`、`packet_sha256`、证据句及坐标、分页和 `local_review` 来源信息。根据 `next_offset` 使用原有 `read_claim_evidence` 读完全部证据。

### 2. 保存判断和缺口

原有 `ClientJudgment` 增加可选字段：

```json
{
  "missing_evidence": [
    {
      "kind": "RESULT",
      "claim_part": "mortality by 25%",
      "question": "What mortality reduction was observed at six months?",
      "search_terms": ["mortality", "six months"]
    }
  ]
}
```

这是完整判断中的一个字段，其他结论、理由、引文、检查项等沿用[客户端导读](client_review_guide.md)。缺口类别包括实体对应、结果、人群、比较对象、时间和其他；类别仅用于解释，服务端不会据此推断事实。

`claim_part` 必须逐字来自原论断；每个缺口给 1–6 个不重复的字面检索词，每词最多 100 字符。服务端不会自动发明同义词或实体别名。给论断添加它没有表达的“仅限”“全部”等要求，同样可能造成错误的证据不足判断。

调用原有 `record_claim_review` 后，会得到 `review_id` 和 `review_sha256`。这些值把后续操作绑定到你刚保存的那次判断。

### 3. 补查一次并重新判断

```json
{
  "review_id": "使用初次记录返回的值",
  "expected_review_sha256": "使用同次记录返回的值",
  "gap_index": 0
}
```

调用 `follow_up_local_claim`。它接受初次 `NOT_ENOUGH_EVIDENCE` 或 `UNCERTAIN` 判断，从已保存缺口中选择一个。每个初始证据包只允许一次补查尝试；重复提交不会自动增加检索预算。执行失败也会留下记录，需要重新准备审查才能开始新的一次尝试。

检索限定为同一个原文件，排除参考文献列表。按检索词命中排序，最多选择三段及其前后相邻段落，并按原文顺序返回。英文字词及数值保留边界检查；中文词语支持无空格文本中的字面匹配。它没有向量检索、语义同义词扩展或别名数据库。

| 返回状态 | 含义 |
| --- | --- |
| `ADDED` | 新包增加了原包没有覆盖的候选文本；尚未判断是否回答缺口 |
| `NO_MATCH` | 当前字面检索没有命中；不等于论文中绝无相关信息 |
| `NO_NEW_EVIDENCE` | 找到的文本已在原证据中；重新切块不算新增覆盖 |

新证据包保留原论断、原证据编号和原文位置。客户端重新读完所有页后，再次调用 `record_claim_review`，使用**新包**的 ID 和摘要。服务端不会自动把 NEI 改成支持或反驳，也不会自动修复引用或改写模型答案。

### 4. 导出报告

```json
{
  "review_ids": ["再次判断保存后返回的 review_id"],
  "output_path": "D:/papers/review_result.html"
}
```

调用 `generate_claim_review_report`，会自动找到这条记录绑定的初次判断。也可提供多条记录，将多个论断的结果汇总在同一个报告里。必须使用新的 `.html` 或 `.htm` 路径，不能覆盖来源文件或已有报告。

报告显示原论断、补查前后判断、客户端名称、理由、逐字引文和位置、所缺信息、检索范围及当前文件状态。指纹和原始 JSON 放在折叠详情中，方便定位问题。报告不会自动把独立论断合并回旧版稿件规则报告；本工具输出的是选定论断的客户端审查报告。

## 为什么要保存两个版本

假设初次记录基于某份论文，随后本地文件被替换。如果直接覆盖旧证据，就无法知道旧判断究竟看了什么。因此：

- 原证据包与判断记录保持不变；新判断有独立 ID。
- 补查记录绑定初次记录的摘要，保留所选缺口与原文件指纹。
- 提交新判断时检查文件是否仍然一致；变化或缺失会拒绝保存。
- 生成报告时仍能读取历史证据，同时显示 `CHANGED`、`MISSING` 或 `UNREADABLE`。静态 HTML 的状态是生成时的检查，不会自动更新。

这些哈希用于发现内容变化和错配，不是面对能重写整个存储目录者的数字签名。原文件字节一致，也不能证明解析完整或科学结论正确。

## 建议按这个顺序阅读代码

1. `review_models.py` 的 `MissingEvidence`：先看客户端需要描述什么。
2. `local_evidence.py`：读 `snapshot_for_record` 和 `search_local_evidence`，理解文件指纹、命中排序及上下文。
3. `local_review.py`：读 `prepare_local_review` 和 `follow_up_review`，从初始包追踪到新包。
4. `followup_models.py`、`review_store.py`：理解来源上下文为什么与旧版证据包分开保存，以及怎样绑定父记录。
5. `followup_report.py`：读取指定记录、检查前后关系，再渲染 HTML。
6. `mcp_server.py`：三个新工具只连接上述模块；语义结论来自客户端。
7. `tests/test_local_followup.py` 和 `scripts/validate_local_followup.py`：分别看单元级边界与实际 MCP 传输流程。

代码兼容旧版证据包，不给旧 packet 增加默认字段而破坏历史摘要。旧判断没有本地来源上下文时可以展示，但不能据此声称完成本地补查或当前文件核验。
