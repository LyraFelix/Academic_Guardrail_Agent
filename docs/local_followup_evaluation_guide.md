# 本地补查的真实材料验证：怎样运行，怎样看结果

这份导读解释评测流程。功能使用和代码阅读顺序见[本地补查导读](local_followup_guide.md)；具体测量结果另见[结果记录](local_followup_results.md)。评测脚本是可选工具，不会被 MCP 服务导入，也没有给服务端增加模型 API。

## 四个结果各代表什么

当前协议为 `local_evidence_followup_v2`，统一使用 `gpt-6.1-terra` 和 `max` 推理设置。每条论断先只读摘要，得到一次共同初判；随后独立执行全文主对照、两阶段全文次对照，以及符合条件的本地补查终判。

| 结果 | 模型拿到什么 | 每例最多几次调用 |
| --- | --- | ---: |
| `abstract_only` | 论断和摘要 | 1，是两条路径共享的起点 |
| `fulltext_single` | 论断和同一篇论文的完整可解析正文，**没有初始判断** | 1，只计这一次全文调用；主对照 |
| `fulltext_direct` | 初始判断，加同一篇论文的完整可解析正文 | 2，包含共同起点 |
| `local_followup` | 初始判断，加根据一个已记录缺口取得的有限原文 | 2，包含共同起点 |

两个全文对照每条都会执行。主对照不接收摘要初判，也不接收任何其他臂的答案；次对照只接收原始摘要初判。本地补查仅对已成功记录、带具体缺口的证据不足或不确定判断补查一次；已得出明确结论的样本沿用初始结果。缺口缺失、记录被拒或检索失败也沿用初始原始结果，保留在分母里。

N 条样本最多实际执行 **4N** 次调用；全部无需补查时是 3N 次。90 条样本的冻结上限是 360 次。实际总成本为摘要初判、独立全文、两阶段全文终判、补查终判四类调用之和，摘要初判只计一次。比较两阶段流程成本时，各自包含摘要初判；独立全文主对照只计自己的一次调用。摘要臂只是共同起点的诊断结果。

主比较回答“摘要加局部补查，相对于一次独立全文判断，结果和 token 有何变化”；次比较保持共同初判，进一步比较全文与检索选文的差异。四臂使用同一模型、输出格式、语义说明和原论断。初判之后最多三个终判并发，每次调用都有新且唯一的 CLI 会话。全文对照使用项目解析和编号后的原文，是受控结构化客户端对照；提示不包含 MCP 规则分数或推荐标签。

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

90 例安排为 `development`、`validation_a`、`validation_b` 三个各 30 例的分区，论文互不重叠。上面的三条命令只说明单批接口。正式研究必须先完成三批的 prepare，核对全部计划共 90 例、360 次调用上限、相同协议/模型/代码和互不重叠的论文，再执行三批 run，最后才 score 和汇总；不能把 prepare/run/score 三步逐批循环，也不能根据第一批答案调整后两批。保留首个调用之前生成的全批次冻结清单及每个 plan 的哈希。

每批最多生成 30 条报告记录，适用现有每次 50 条的报告上限。验证样本来自另外的论文，不能看过其参考答案后再修改检索或提示，并继续称其为未使用的验证集。单批运行器校验本批计划；全批次冻结和总预算必须由研究执行清单检查，汇总器事后拒绝混合配置或跨分区论文重叠。

研究执行器应创建一个 `seen_threads = set()`，并在每次调用 `run_async(plan, output, timeout=600, seen_threads=seen_threads)` 时传入同一个集合；同步 `run` 也支持此参数。这样第二批若复用第一批的 CLI 会话 ID，会在观察到重复后立即停止后续调用。单批 CLI 命令不变，默认使用本批自己的集合。汇总器还会从严格校验的原始收据独立检查跨批次会话 ID，且在所有检查通过前不打开任何 gold。

全部完成后汇总实际运行目录和各自的标签文件：

```powershell
python -m scripts.summarize_local_followup_evaluation --batch benchmarks/runs/local_dev_run_01 benchmarks/data/local_followup/dev_gold.jsonl --batch benchmarks/runs/local_validation_a_run_01 benchmarks/data/local_followup/validation_a_gold.jsonl --batch benchmarks/runs/local_validation_b_run_01 benchmarks/data/local_followup/validation_b_gold.jsonl --output benchmarks/runs/local_combined_scores_01.json --cases-csv benchmarks/runs/local_combined_cases_01.csv
```

这里的路径是示例，须换成实际冻结材料路径。汇总器支持任意非空、互不重叠的批次列表；本次研究仍按事先批准的三批 90 例和总计 360 次调用上限执行。汇总器先调用严格运行校验，再打开标签，重新计算结果，不读取可修改的历史 score JSON。它拒绝模型、推理或协议混用、重复 case ID、跨批次会话 ID 复用，以及同一论文或同源字节跨分区。可以另传两个验证分区，得到单独的合并验证结果；不要把开发集混入验证分母。

所有输出目录和结果文件必须使用新路径。准备阶段冻结输入、来源指纹、实际 MCP 证据包、摘要提示、无先前答案的全文提示、两阶段提示模板、输出格式、模型配置、预先记录的 gold 哈希及运行代码。执行阶段复制证据存储，保留原始准备目录，并记录每次请求、CLI 命令、事件、答案、耗时、用量和 MCP 收据。计分会重新核对文件清单及哈希、每臂调用归属和原始提示，拒绝缺例、重复或改动过的结果。

冻结和运行还会验证实际导入的 `academic_guardrail` 包：其全部 `.py` 文件清单及内容必须与当前 `src/academic_guardrail` 相同。比较时只把 CRLF 换行规范化为 LF，其他字节、缺失文件或额外文件均不放过。可以使用匹配的已安装 wheel，也可以通过 `PYTHONPATH` 指向当前源码；不能只哈希 checkout，却实际运行旧 wheel。计划和运行清单的 `imported_core` 保存实际导入位置、校验说明及规范化哈希。MCP 子进程会把已验证包的父目录放在继承的 `PYTHONPATH` 之前，以使用同一份核心实现。

模型与推理配置只在 `scripts/codex_review_client.py` 定义，输出提示中的 `client_model` 也从这个常量生成。改变模型、提示、检索或运行代码后必须建立新计划，不能沿用旧冻结目录。运行器不修复答案，也不重试失败判断；CLI 内部是否重试网络请求不能由调用次数推断。请求关闭其他工具、两种 multi-agent 功能、记忆和技能，一旦实际观察到工具调用、无法解析的事件或重复会话 ID 就停止后续运行。一组调用全部失败也停止，留下不可完整计分的 incomplete 记录。独立上下文和未观察到工具使用不等于掌握完整后台提示。

原始 PDF、整理文本、标签和模型运行记录保存在本地。真实材料记录必须包含版本明确的原始链接、文件哈希、提取和整理方式，以及从整理文本回到原文的坐标映射。**旧版冻结输出必须在匹配其源代码和环境的历史 checkout 中重计分**，当前 v2 代码会拒绝旧协议或旧代码指纹。不要修改旧运行来让新代码接受。再次调用模型不保证答案相同。

## 先看正确性，再看节省

主要比较全文参考标签下的最终结果，保留全部样本和失败：

- 反驳召回率：正确反驳数 / 全部参考标签为反驳的样本数；反驳精确率：正确反驳数 / 全部预测反驳数。两者都报告计数、分母与描述性 Wilson 95% 区间。
- NEI、UNCERTAIN、ERROR 各自占全部样本的比例；可避免 NEI 另以参考标签为支持或反驳的样本为分母。错误不能从分母删除。
- 正确和错误的明确判断数。`false_concrete` 包含把参考 NEI 判成支持或反驳的情况。
- 逐条报告主比较和次比较的胜、负、同对、同错；同时看逐论文结果，防止一篇论文的多条论断主导整体趋势。
- 引文是否逐字存在、记录是否通过检查，单独统计；这些不是语义正确率。
- 分开看总输入、缓存输入、非缓存输入、输出和推理 token。只有每次调用的输入和缓存输入都已知时，才计算完整的非缓存输入合计；推理 token 是输出的一部分，不能再加到输出上。任何未完整报告的字段保持 `null`；partial subtotals 只是已观察小计。

补查后从证据不足改成支持，只有参考证据确实支持它时才算解决。输出更少文本、记录接受率更高或报告更完整，也不能单独证明判断能力提高。不能把未测量的美元费用或人工阅读时间写成节省。材料是依据真实来源编写的论断与参考判断，并非独立专家 gold 或自然分布基准；同论文样本相关，区间与配对检验只作描述性分析，不能据此声称一般准确率。

## 阅读评测代码

1. `benchmarks/local_followup_evaluation.py`：共同规则、提示构造和冻结检查。
2. `scripts/prepare_local_followup_evaluation.py`：只接触公开输入，调用实际 MCP 准备摘要和全文包。
3. `scripts/run_local_followup_evaluation.py`：共享初判、三个独立终判和原始结果保存。
4. `scripts/score_local_followup_evaluation.py`：最后打开参考标签，分别计算语义结果、引用检查和成本。
5. `scripts/summarize_local_followup_evaluation.py`：重验多批运行、汇总主次比较与逐论文结果、导出逐例 CSV。
6. `tests/test_local_followup_evaluation.py` 和 `tests/test_local_followup_summary.py`：通过离线替身检验协议和计分边界；这些测试不是模型效果数据。
