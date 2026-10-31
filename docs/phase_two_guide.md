# 第二阶段代码导读：从一条引用追到原文

这轮处理“引用是否漏掉、是否用对文献、证据能否找回”。可以先运行下面的离线例子，再按调用链阅读。样例里的论文、论断和 DOI 均为软件测试用的合成数据，不是学术事实或效果评测。

```powershell
python -m academic_guardrail.cli audit docs/examples/phase_two_manuscript.md --refs-dir docs/examples/phase_two_refs --offline -o phase_two_report.html
```

样例应得到 **1 个文献条目、3 次正文引用、3 条核查结果**。前两处引用指向同一篇文献，第三处 `[2]` 缺少条目，会显示 `UNRESOLVED_CITATION`。第一处和第二处都保留，元数据只查一次。

## 先理解三个对象

| 对象 | 样例 | 责任 |
| --- | --- | --- |
| `Citation` | 参考文献列表的 `[1]` | 保存标题、作者、DOI 和条目原文；`id` 是文档内引用键，不是全球论文 ID |
| `ContextClaim` | 正文第一次和第二次 `[1]` | 各有 `occurrence_id`、原始标记、所在句子和位置，指向同一个 `citation_id` |
| `EvidencePassage` | 本地参考文件中的一个段落 | 保存可检索原文、来源类型和坐标；先确认文件身份，再允许使用其文字 |

只有参考文献条目、没有正文引用的文献，仍检查元数据，但 `claim=None`。直接输入 `.bib` 文件也不会生成虚构的正文句子。

`DocumentParser.parse()` 返回 `ParsedDocument(citations, occurrences, diagnostics)`。旧的 `parse_document()` 保留元组列表适配器；其中未被正文引用的条目对应 `(citation, None)`，调用方不能再假设每条都有论断。

## 代码怎么连起来

```text
read_document → ExtractedText（原文、页边界、提取提示）
                    ↓
DocumentParser.parse → Citation 列表 + ContextClaim 列表
                    ↓
AuditService._prepare_reference（每个引用键一次）
    ├─ 在线元数据 / 本地撤稿库
    ├─ LocalRefStore.select_candidate（先检查 DOI 和元数据冲突）
    └─ PreparedReference（共享的元数据结果、可检索段落）
                    ↓
_evaluate_occurrence（每处引用复制一份独立结果）
    ├─ 在各页段落中找相关文本
    ├─ 调用既有启发式比对
    └─ locate_excerpt（把摘录定位回原文）
                    ↓
统一 formatter → CLI / MCP / HTML / Markdown
```

推荐依次阅读 `models.py`、`tests/test_parser_occurrences.py`、`parser.py`、`tests/test_local_evidence_chain.py`、`ref_store.py`、`passages.py`、`service.py`。这些路径都相对于 `src/academic_guardrail/core/`，测试相对于仓库根目录。`bibliography.py` 只负责 BibTeX 的字面量字段；`text_extraction.py` 只负责按顺序读取文件。没有新增运行时依赖。

## 为什么要保留三个计数

- `total_references`：识别出的文献条目数；缺失引用的占位对象不计入。
- `total_occurrences`：正文与文献之间的引用关联数。`[1, 2]` 是两次关联；同一个 `[1]` 出现两处也是两次。
- `total_citations`：兼容旧接口的结果行数，等于正文关联结果加上未被引用条目的元数据结果。风险等级计数以这些结果行为分母。

缺失或重复的引用键会显示解析提示，并停止对该条目的数据源查询。解析为零、出现扫描空页、读取失败，都不能解释成文档已经通过。

## 文本位置的含义

`SourceLocation` 的 `char_start` / `char_end` 是提取文本的零起点、左闭右开区间。可以用 `text[start:end]` 恢复原文。

- PDF 页码从 1 开始，空页仍占一个页码；合并文本用两个换行分隔各页，不插入“Page 1”等字符串。
- 正文引用坐标指向原始标记；证据坐标指向实际显示的摘录。它们属于两个不同文件。
- Word 位置对应正文段落和表格的提取顺序；不虚构排版页码。所有 `line` 都是提取文本行号，不是屏幕或 PDF 的视觉行号。
- `.tex` 的正文位置来自 `.tex`，外部参考条目的位置来自实际读取的 `.bib`。

`tests/test_extracted_locations.py` 用真实 PDF/Word 文件验证顺序和坐标。`test_late_pdf_evidence_has_exact_file_page_and_offsets` 验证第三页文字能被检索，并检查 `fulltext[start:end] == evidence_text`。

## 如何避免拿错论文背书

1. 本地论文 DOI 只从简易首页元数据区域抽取。参考文献列表中的 DOI 不属于包含它的论文。
2. 已知目标 DOI 时要求本地 DOI 与之对应；本地缺 DOI 时也不降级成标题猜测。没有目标 DOI 时才使用标题、作者、年份匹配。首页有多个 DOI、多个文件身份难分时保留歧义，不任选一个。
3. 在线查询发现了 DOI，就用这个已解析身份继续匹配本地文件，不能退回宽泛的原始标题。
4. 通过本地标题发现新的 DOI 后，在在线和离线模式下都补查本地撤稿库。原先的在线超时信息仍保留。
5. 本地全文按段落和页码切分；参考文献列表不作为本文证据。没有摘要就保留空值，不把开头 500 字称为摘要。

`evidence_status` 回答身份和数据获取问题；`retrieval_status` 回答有没有可用的论断文本：`NOT_REQUESTED`、`AVAILABLE`、`NO_TEXT`、`NO_RELEVANT_PASSAGE`、`AMBIGUOUS`。例如元数据已匹配但没有文本时，这处正文引用仍为未核实。上游 `TIMEOUT` 可以与本地命中同时存在。

`text_source` 区分 `ONLINE_ABSTRACT`、`LOCAL_ABSTRACT`、`LOCAL_FULLTEXT`。低于 0.15 的段落相关性只触发“未找到足够相关片段”；该阈值不是校准概率，也不是判定论断为假的阈值。语义比对本身仍沿用旧启发式，需要第三阶段处理数字、否定、范围等反例。

## 本轮支持范围

| 格式 | 已覆盖 | 仍有限制 |
| --- | --- | --- |
| TXT / Markdown | 编号条目、跨行条目、重复/分组/区间标记、直接 DOI；屏蔽常见代码和数学块 | 作者年份制、任意标点风格、复杂列表仍需人工核对 |
| BibTeX | 常见条目、嵌套花括号、引号和数字字面量；保留组织作者分组 | 不执行 `@string`、`#` 拼接、任意 TeX 宏；会输出提示 |
| LaTeX | `cite/citep/citet/parencite/textcite/autocite/footcite`、`bibitem`、文稿目录内的 `.bib` | 不编译 TeX、不展开宏或子文件；检测到时提示 |
| DOCX | 正文段落、表格和嵌套表格的文档顺序 | 脚注、尾注、文本框不读取；检测到时提示；页眉页脚不属于当前提取范围 |
| PDF | 有文本层的页面、物理页码、后页段落检索 | 不做 OCR；多栏顺序、跨页断句、图表、公式仍依赖 pypdf 提取质量 |
| arXiv 目标 | 现代 ID 与明确的 arxiv.org abs/pdf URL | 只做标识符元数据检查，不下载或审计远程正文 |

这些支持点有离线回归测试，不能据此声称任意论文均能完整解析、文献身份绝对正确或论断准确率提升。

## 自己做一个小练习

复制样例，在正文再加一句 `[1]`，观察引用次数增加而文献条目数不变。然后把本地文件的 DOI 改成另一个值，观察系统停止使用该文件的正文。最后把证据句移到 PDF 后页，查看报告的页码和摘录位置。

运行 `python -m pytest tests -q` 检查整体行为。另可运行 `python scripts/validate_phase_two.py --output-dir <新的输出目录>` 保存真实 MCP stdio 握手和离线文档审计记录；该脚本使用合成样例并阻止 HTTP 客户端、外部 HTTP 发送及嵌入模型初始化。这些是工程验证，不是新的模型实验。
