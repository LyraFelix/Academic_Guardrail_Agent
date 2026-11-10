# 本地补查的真实材料验证：怎样运行，怎样看结果

这份导读解释评测流程。功能使用和代码阅读顺序见[本地补查导读](local_followup_guide.md)；具体测量结果另见[结果记录](local_followup_results.md)。评测脚本是可选工具，不会被 MCP 服务导入，也没有给服务端增加模型 API。

## 三个结果各代表什么

每条论断先让现有客户端只读摘要，得到一次共同的初始判断。随后运行两条路径：

| 结果 | 模型拿到什么 | 每例最多几次调用 |
| --- | --- | ---: |
| `abstract_only` | 论断和摘要 | 1，是两条路径共享的起点 |
| `fulltext_direct` | 初始判断，加同一篇论文的完整可解析正文 | 2，包含共同起点 |
| `local_followup` | 初始判断，加根据一个已记录缺口取得的有限原文 | 2，包含共同起点 |

直接读全文的路径每条都会执行第二次判断。本地补查路径仅对已成功记录、带具体缺口的证据不足或不确定判断补查一次；已得出明确结论的样本沿用初始结果。缺口缺失、记录被拒或检索失败也保留在分母里。

因此 N 条样本最多实际执行 3N 次调用，而不是 4N：共同起点只运行一次。计算每条路径的有效成本时都加上起点；计算本轮实际总成本时只加一次。摘要结果仅用于观察初始信息不足，不能当作与完整补查流程预算相同的竞争方法。

两条后续路径使用同一客户端、输出格式、语义说明、原论断和初始判断；都在新的独立上下文中回答。它们的主要区别是提供全文还是提供检索选出的文本。全文对照也使用项目解析和编号后的原文，是受控结构化客户端对照，不代表完全去掉系统提示的裸 API。模型提示不包含 MCP 规则分数或推荐标签。

## 输入和参考标签分开

准备阶段的 JSONL 每行必须只有这七个字符串字段：

```json
{"id":"case_01","partition":"dev","paper_id":"paper_01","claim":"The claim to check.","citation_str_or_doi":"10.1234/example","paper_title":"Example title","source_path":"D:/papers/refs/paper_01.txt"}
```

`source_path` 必须在指定文献目录内，身份匹配结果必须指向这份文件。一个输入文件只包含一个分区。不要把原始 PDF 与同一篇论文的整理文本同时放进索引目录，否则可能形成重复身份。

参考标签文件每行至少包含 `id`、`abstract_only_label` 和 `fulltext_label`。允许的标签是 `SUPPORTED`、`CONTRADICTED`、`NOT_ENOUGH_EVIDENCE`。摘要标签与全文标签分开，是因为摘要可能没有给出正文实际报告的结果。标签文件还应保留出处、逐字证据和歧义说明，供结果完成后的人工核对。

准备和运行脚本没有 gold 路径参数。准备只接收事先记录的标签文件 SHA-256；运行保存完全部答案后，计分脚本才读取对应分区的标签。这里的 gold 指预先制定的参考判断，不意味着天然无误或经过独立专家认证。

## 可复现的执行顺序

在仓库根目录、已安装项目依赖的环境中执行。运行模型还需要已安装并登录的 Codex CLI；复用现有客户端，不读取或打印认证文件。

```powershell
python -m scripts.prepare_local_followup_evaluation --inputs benchmarks/data/local_followup/dev_inputs.jsonl --refs-dir benchmarks/data/local_followup/refs --expected-gold-sha256 <事先记录的dev标签SHA256> --output benchmarks/runs/local_dev_plan_01
python -m scripts.run_local_followup_evaluation --plan benchmarks/runs/local_dev_plan_01/plan.json --output benchmarks/runs/local_dev_run_01 --timeout 180
python -m scripts.score_local_followup_evaluation --run benchmarks/runs/local_dev_run_01 --gold benchmarks/data/local_followup/dev_gold.jsonl --output benchmarks/runs/local_dev_scores_01.json
```

将输入、标签及输出目录换成验证分区，再执行同样三步。验证样本来自另外的论文，不能看过其参考答案后再修改检索或提示，并继续称其为未使用的验证集。

所有输出目录和结果文件必须使用新路径。准备阶段冻结输入、来源指纹、实际 MCP 证据包、提示模板、输出格式、模型配置及运行代码。执行阶段复制证据存储，保留原始准备目录，并记录每次请求、CLI 命令、事件、答案、耗时、用量和 MCP 收据。计分会重新核对文件清单及哈希，拒绝缺例、重复或改动过的结果。

模型配置在 `scripts/codex_review_client.py`。改变模型、提示、检索或运行代码后必须建立新计划，不能沿用旧冻结目录。运行器不修复答案，也不重试失败判断；CLI 内部是否重试网络请求不能由调用次数推断。请求关闭其他工具、记忆和技能，一旦实际观察到工具调用、无法解析的事件或重复会话 ID 就停止后续运行。独立上下文和未观察到工具使用不等于掌握完整后台提示。

原始 PDF、整理文本、标签和模型运行记录保存在本地。真实材料记录必须包含版本明确的原始链接、文件哈希、提取和整理方式，以及从整理文本回到原文的坐标映射。已有的冻结输出可以重新计分；再次调用模型不保证答案相同。

## 先看正确性，再看节省

主要比较全文参考标签下的最终结果，保留全部样本和失败：

- 总标签一致数，以及支持、反驳、证据不足各自的分母。
- 正确的明确判断数、错误的明确判断数，以及仍未解决的样本数。
- 逐条比较补查相对直接全文的胜、负、同对、同错，而不是只比较两个百分比。
- 引文是否逐字存在、记录是否通过检查，单独统计；这些不是语义正确率。
- 共享起点加后续判断的输入/输出 token 和耗时；未报告的用量保持未知。

补查后从证据不足改成支持，只有参考证据确实支持它时才算解决。输出更少文本、记录接受率更高或报告更完整，也不能单独证明判断能力提高。不能把未测量的美元费用或人工阅读时间写成节省。

## 阅读评测代码

1. `benchmarks/local_followup_evaluation.py`：共同规则、提示构造和冻结检查。
2. `scripts/prepare_local_followup_evaluation.py`：只接触公开输入，调用实际 MCP 准备摘要和全文包。
3. `scripts/run_local_followup_evaluation.py`：共享初判、两条后续路径和原始结果保存。
4. `scripts/score_local_followup_evaluation.py`：最后打开参考标签，分别计算语义结果、引用检查和成本。
5. `tests/test_local_followup_evaluation.py`：通过离线替身检验协议和计分边界；这些测试不是模型效果数据。
