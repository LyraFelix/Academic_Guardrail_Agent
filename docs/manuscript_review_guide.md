# 用一份初稿和参考目录生成整稿报告

准备一个带编号引用和参考文献表的 Markdown 或 Word 初稿，将能取得的参考论文放进一个目录。客户端逐处判断，Academic Guardrail 检查证据编号、逐字引文和来源位置。导出的 HTML 保留已判断、待判断和因来源问题受阻的各处引用。

## 先看完整例子

从源码安装后，在仓库根目录运行下列命令，输出目录选一个新的路径。

```bash
python -m scripts.validate_manuscript_review --output scratch/manuscript_demo
```

打开 `scratch/manuscript_demo/md/report.html` 或 `scratch/manuscript_demo/docx/report.html`。演示把同一份初稿分别作为 Markdown 和 Word 输入，走真实 MCP 通信。它使用两条预先写好的语义判断。脚本会读完证据分页，提交判断，并检查逐字引文是否等于原文件在相应坐标的文本。

Word 示例里，正文写有 `[1]`，参考文献表使用 Word 自带的单级十进制自动编号。服务端从列表定义读出显示的序号，保留原段落的字符位置。书目放在“参考文献”或“References”等标题后。遇到多级列表等无法确定编号的情况，打开报告中的解析提示，可把相应书目改成显式的 `[1]`、`[2]` 再检查。

| 初稿里的位置 | 报告中应看到的内容 |
| --- | --- |
| 第一处引用 [1]，默认批量是 256，训练 100 轮 | 反驳。默认批量是 4096，100 轮有依据。 |
| 第二处引用 [1]，默认训练 100 轮 | 支持。同一篇论文在这句话下有一条独立记录。 |
| 引用 [2]，2014 年的 Nature 论文 | 离线库给出已确认的撤稿记录。该行保留来源状态，语义取证受阻。 |
| 引用 [3]，演示用 pilot 文献 | 缺少能匹配的本地文件，报告列明原因。 |

仓库内的 `simclr.txt` 只收录节选。报告里 TXT 的行号和字符区间定位到这份节选。使用原始 PDF 可得到 PDF 页码。先把固定版本保存到本机，再运行下面的命令。两个版本的报告都会核验默认设置与训练数字的原句来自 PDF 第 3 页。[SimCLR v3 原文](https://arxiv.org/pdf/2002.05709v3#page=3) · [演示初稿](examples/manuscript_review.md)

```bash
python -m scripts.validate_manuscript_review --simclr-pdf path/to/simclr.pdf --output scratch/manuscript_pdf_demo
```

## 换上自己的初稿

按 README 的 MCP 配置，在能访问稿件目录的客户端启动 `academic-guardrail-mcp`。选择 `review_manuscript_workflow`，传入 `file_path`、`refs_dir` 和新的 `output_path`。支持工具但没有提示菜单的客户端可直接使用这段请求：

> 请用 Academic Guardrail 审查我这份 draft.docx，参考文献在 references。用 prepare_manuscript_review 建立整稿审查。按每处引用分别读完证据，提交带逐字引文的判断，保留缺文献、歧义及撤稿条目。最后用 generate_manuscript_review_report 输出 draft_review.html，告诉我哪些句子要改、哪些引用还缺原文。

也可将已有 `audit_document_claims` 的 `client_review`、`offline` 均设为 `true`。返回的是同一种审查队列。普通 CLI 的 `audit` 命令仍可生成规则和元数据报告。模型由 MCP 客户端提供，离线参数控制服务端的检索。

这里的“全文”指解析器提取到的论文正文。文后的参考文献、需要 OCR 的扫描页、复杂表格或附录可能缺失。若断言依赖的实验只见于附录，先查看证据包是否真的有相应段落，再给出判断。

1. **固定稿件和来源。** `prepare_manuscript_review` 读取稿件字节，解析编号引用，记录每处引用的 `occurrence_id`、句子和稿件位置。举例来说，两处 [1] 共用同一篇参考文献，却各有独立的 `packet_id`。默认读取本地论文的可解析全文。缺失原文、来源歧义或撤稿的行都有原因。先看 `parse_diagnostics`，作者年份制等未识别格式可能导致漏掉引用。
2. **阅读、判断和保存。** 初稿的引用清单一次返回，每处引用的证据单独分页。对每一行 `PENDING`，把该行的 `packet_id` 传给 `read_claim_evidence`，从第 0 项开始读到 `next_offset` 为空。用 `record_claim_review` 提交结论、理由和引文，`expected_packet_sha256` 必须与阅读时相同。确实读完的连续编号可写成 `"reviewed_evidence_ids": ["e1-e91"]`。引文和逐项判断仍使用一个具体编号，例如 `e45`。服务端会拒绝越界、重复或重叠。支持、反驳和证据不足都要求声明全包。只读了一部分时可以记录 `UNCERTAIN`，列出实际读过的编号。
3. **按需要补查。** 对放不下或希望先读摘要的论文，可显式选择 `initial_scope="abstract"`。记录缺失的数字、条件或其他必要事实，调用 `follow_up_local_claim` 定向查同一篇论文，再读取新包并保存判断。两次判断都留在同一处引用下。[补查工作流](local_followup_guide.md)
4. **导出一份报告。** `generate_manuscript_review_report` 根据 `manuscript_id` 找到本稿的保存记录。单一补查链展示初判和终判。有多条独立判断时均保留，并标明尚未选择，可用 `review_ids` 对指定引用选择一条。报告保留未完成条目。稿件或原文变更后，历史判断仍有快照可查，修改后的版本需要重新准备。

打开报告后可以按客户端的“矛盾”“证据不足”或“来源受阻”筛选。每张卡片先列稿件中的句子、客户端的理由和逐字引文。核对 PDF 的数字时，一起看引文下面的页码和字符区间。同一张卡片可展开前后判断、来源快照和服务端规则提示。

## 连续编号的离线复验

在上轮 90 条补查流程最终回答中，客户端逐个列出了 4,907 个证据编号。把每条回答实际列出的编号改写成连续范围后，90 条回答共用 90 个范围。两种写法的逐字引文位置一致，都有 89 条通过。SimCLR 的一条回答只声明了 `e1-e90`，包内还有 `e91`，两种写法都被拒绝。这里统计的是声明条目数，客户端的 token 消耗需要单独测量。

有历史归档时可从仓库根目录重算。输出选一个新的文件名。[校验脚本](../scripts/replay_review_coverage.py)

```powershell
python -m scripts.replay_review_coverage --runs ../audit_guardrail_20261118_terra_max_evaluation/runs_02 --output scratch/range_replay.json
```

## 按代码走一次

| 想弄清的问题 | 从这里开始 |
| --- | --- |
| 同一篇文献被引两次，为什么有两个结果？ | [parser.py](../src/academic_guardrail/core/parser.py) 的 `_add_occurrence` 记录每处正文引用，[manuscript_review.py](../src/academic_guardrail/core/manuscript_review.py) 为每处可审查引用建立独立证据包。 |
| 怎样避免把别处的引文挂到这句话上？ | [review_store.py](../src/academic_guardrail/core/review_store.py) 在保存时检查稿件、原文和证据快照。[manuscript_report.py](../src/academic_guardrail/core/manuscript_report.py) 按稿件、引用位置和原始证据包重新校验关联。 |
| 搜索能识别断行，为什么还能回到原字？ | [search_view.py](../src/academic_guardrail/core/search_view.py) 保留从搜索文本到原文的坐标对应关系。[passage_ranking.py](../src/academic_guardrail/core/passage_ranking.py) 挑选候选原段，[passage_structure.py](../src/academic_guardrail/core/passage_structure.py) 查找关联小标题和表头。 |
| 连续编号是否会放过错误引文？ | [claim_review.py](../src/academic_guardrail/core/claim_review.py) 先在当前包里展开声明，再用具体编号和原文子串核对每条引文。结果通过表示引用位置可核对，语义判断仍来自客户端。 |
| 怎么复现这两份报告和离线评测？ | [示例 MCP 客户端](../scripts/validate_manuscript_review.py) 执行两种稿件格式。[90 条样本的检索回归](manuscript_retrieval_results.md) 记录历史输入、消融步骤和结果。 |
