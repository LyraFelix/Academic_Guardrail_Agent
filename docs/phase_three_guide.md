# 第三阶段：把语义检查拆成可以读懂的规则

这一阶段修复数字、否定、因果和适用范围差异。项目仍是一个 MCP Server，四个工具与 CLI 共用 `AuditService`，没有增加第二套判定服务，也没有引入新模型或依赖。

## 1. 先理解结果

旧流程曾把“死亡率降低 90%”与“降低 10%”判为 `SUPPORTED`，因为其余文字几乎相同。新流程用相似度找原文，找到后再逐项检查。

| `alignment_state` | 含义 | 应用中的等级 |
| --- | --- | --- |
| `TEXT_ALIGNED` | 已检查的文字和限定相符，仍需阅读全文 | NOTICE |
| `POTENTIAL_CONFLICT` | 可比对象和指标出现具体数量或肯否差异 | WARNING |
| `REVIEW_REQUIRED` | 因果、范围、语法、单位或不同证据需要解释 | NOTICE |
| `INSUFFICIENT_EVIDENCE` | 没有可用文本，或找不到对象和指标对应的片段 | NOTICE |

四种状态都不代表“说法为真/为假”。`claim_alignment_score` 保留旧字段名，含义是**检索相似度**；高分与数字冲突可以同时发生。旧 `SUPPORTED` / `CONTRADICTED` 标签不再由新判定产生。

`status=VALID` 可以表示元数据已匹配，同时正文得到 NOTICE；它不表示正文已通过科学验证。`PASS` 留给元数据检查。已确认撤稿仍优先返回 DANGER。

## 2. 阅读顺序和调用链

```text
AuditService._evaluate_occurrence
    └─ ClaimEvaluator.assess_passages
         ├─ text.clause_units：分句，保留原文子串和限定
         ├─ 相似度排序：找到可能相关的片段
         ├─ text.target_mismatch：检查是否在说同一对象和指标
         ├─ _check_pair
         │    ├─ scope.check_scope：因果、可能性、人群、条件和时间
         │    ├─ polarity.check_polarity：局部谓词的否定与方向
         │    └─ numbers.check_numbers：显式单位和数值
         ├─ 检查相关片段是否给出不同表述
         └─ ClaimAssessment：状态、提示、原句、来源、位置
    └─ format_result / ReportGenerator：展示已有结果
```

先读 `tests/fixtures/semantic_cases.json` 的输入/预期，再读 `core/models.py` 的字段。接着依次看 `core/claim_checks/` 内的 `numbers.py`、`polarity.py`、`scope.py`、`text.py`，最后读 `providers/claim_eval.py` 的编排。

`core/text_similarity.py` 保留原来的词面检索方法；可选嵌入模型也只用于排序。即使向量相似度为 1，仍要走同样的规则检查。

## 3. 四类规则实际检查什么

**数字：** 使用 `Decimal` 解析小数和前导小数（如 `.5`），保留百分比与百分点的区别。显式单位表允许 `5 mg = 0.005 g`、`50 ms = 0.05 s` 等换算。上界、下界、开闭边界和“大约”分别保留；`10%` 与 `up to 10%` 需要复核。

数值比较前要确认主体、指标和条件。不同时间、人群、未知单位、复合单位（如 mg/kg）、区间、科学计数、多个数值与指标绑定不清时，返回复核。`not 20%` 不能反驳 `10%`，因为两句可能同时成立。引用标记 `[1]` 不作为测量值。

**否定：** 展开 `doesn't` 等缩写，把 `cause/causes` 归为同一谓词，检查当前分句的否定位置；系动词后的 `was not` 也保留。`not only` / “不仅”不当作否定。相反方向只在对象和指标可比时提示冲突。

“没有发现证据”“统计不显著”“不能排除”和双重否定都要求复核。“没有增加”也不能直接解释成“减少”。不相关句子的否定不会用于反转当前论断。

**因果：** 把原文的 `associated with` / “相关”写成 `causes` / “导致”，或直接写成确定效果时，给出 `CAUSAL_OVERSTATEMENT`。它提示措辞变强，不会推断研究已经证明因果关系。

**范围：** 检查部分到所有、可能到确定、人群/实验对象变化、时间变化及显式条件短语。逗号前后的 `In mice`、`After 12 weeks`、`only when ...` 不会直接丢掉。对象标签也保留，`Drug A` 和 `Drug B` 不会因为共同含有 drug 就被认为是同一药物。

## 4. 为什么每条提示都带原文

`SemanticFinding` 保存提示代码、类别、级别、说明、触发断言、证据原文、来源及位置。NUMBER_MISMATCH 需要让你直接看到“90%”与“10%”，再打开对应文件核对。

本地坐标沿用第二阶段约定：页码从 1 开始，字符是提取文本中的零基半开区间 `[start, end)`。在线摘要没有本地坐标时保持为空，不能借用另一个片段的位置。

多个相关片段可能给出不同数字或肯否表述。程序保留两边原句并返回 `EVIDENCE_DISAGREEMENT`，不靠最高相似度选择一个答案。不同研究条件可能解释差异，因此仍需阅读全文。

## 5. 自己运行并观察

在仓库已安装开发依赖的环境里：

```powershell
academic-guardrail audit docs/examples/phase_three_manuscript.md --refs-dir docs/examples/phase_three_refs --offline -o phase_three_report.html
python -m pytest tests/test_semantic_checks.py tests/test_semantic_edge_cases.py tests/test_semantic_data_flow.py -q
python scripts/validate_phase_three.py --output-dir phase_three_validation
```

验收脚本要求新输出目录，避免覆盖旧记录。它保存 50 个合成样例的逐条结果、JSON/HTML/Markdown 报告、真实 CLI 输出、MCP stdio 四工具调用记录及禁止 HTTP/模型访问的计数。演示文稿有 1 个条目、4 次正文引用，分别触发四类提示；这些是软件测试材料，没有实验结论。

`test_semantic_edge_cases.py` 保存独立审查与实际运行发现的追加反例；`test_semantic_data_flow.py` 检查来源位置、等级、跨片段差异和展示一致性。完整回归与构建记录见 [验证记录](phase_three_validation.md)。

## 6. 如何修改规则

1. 先写原句与断言，说明为什么应该提示；再写一个只差一个词的正常对照。
2. 运行测试确认当前失败；检查状态、提示代码、实际原句，不要只检查分数。
3. 在对应的小模块里修改，不往 CLI、MCP 或报告里加判定分支。
4. 先跑该组测试，再跑完整回归。无法可靠解析时增加复核提示，不用人为压低分数来模拟矛盾。

`evaluate_alignment()` 仍返回五元素元组，但状态词和分数解释已改变。新代码优先用有字段名的 `assess()` / `assess_passages()`。依赖旧标签或“低分等于矛盾”的历史 benchmark 脚本需要单独迁移，不能直接计算本版准确率。

## 7. 保留的边界

这是可解释的表面规则，**不是完整的自然语言推理系统**。复杂长句、代词指代、否定作用域、被动语态、未登记单位、跨句条件、同义改写及中英文翻译仍可能遗漏或过度提示。部分正确句会进入人工复核，这是当前保守比较策略的代价。

文本可能来自摘要或不完整全文；程序没有审查实验设计、偏倚、统计方法或原始数据。本阶段没有跑真实模型、在线覆盖或独立留出的准确率评测。简历可以描述“实现带原文定位的数值、否定、因果及范围检查，并通过离线回归与 MCP 入口验证”，不应写成“保证论文正确”或未经独立评测的准确率。
