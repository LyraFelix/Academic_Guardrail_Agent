# Academic Guardrail Agent

[English](README.md) | 中文

一个用于检查论文引用的 Python 项目，提供命令行和 MCP 接口。它查询文献元数据、保留撤稿来源，并把正文与可用参考文本做启发式比对，帮助使用者定位需要人工复核的引用。

本项目目前是学习与工程实践项目。文本相似度不是事实证明，文献存在也不表示正文说法成立。

## 安装与运行

要求 Python 3.10 或以上。建议在独立环境中从本仓库安装：

```powershell
python -m pip install -e ".[dev]"
academic-guardrail verify "10.1038/nature12968" --offline
academic-guardrail audit docs/examples/sample_manuscript.md --offline -o report.html
```

项目的发行包名是 `mcp-academic-guardrail`，CLI 命令名是 `academic-guardrail`。上面的源码安装不依赖同名 PyPI 项目是否已发布。

## 在线与离线

默认模式会查询 OpenAlex、Crossref 和/或 Semantic Scholar。`--refs-dir` 仅提供本地参考文件，并不会自动关闭在线查询。

```powershell
# 在线查询，并可用本地参考文件补充文本
academic-guardrail audit manuscript.docx --refs-dir references -o report.html

# 严格离线：只用本地撤稿数据库和参考文件
academic-guardrail audit manuscript.docx --refs-dir references --offline -o report.html

# 单条文献元数据查询；不做正文断言核验
academic-guardrail verify "Attention Is All You Need" --detail detailed
```

离线模式不创建在线数据源客户端，不加载或下载嵌入模型。HTML 报告的 CSS 和 JavaScript 全部内联，可离线打开、搜索和筛选；点击 DOI 链接仍会打开外部网站。

内置撤稿库只有 **3 条历史示例**，不代表完整 Retraction Watch 数据库。`RETRACTION_DB_PATH` 可以指向同结构的本地 SQLite 数据库；项目当前没有完整数据库的自动下载与同步功能。离线查不到 DOI 时返回 `UNVERIFIED`，不能据此判定论文未撤稿。

可选 `python -m pip install -e ".[full]"` 启用 sentence-transformers。在非离线模式下，首次使用可能下载模型；无此依赖时使用词面规则。两种方式都只提供比对线索。

## 读懂结果

| 字段 | 含义 |
| --- | --- |
| `status` | 当前结果：匹配、未核实、撤稿或文本不匹配 |
| `risk_level` | 本次检查的提示等级，不是科学正确率 |
| `evidence_status` | 匹配到在线文章、本地文件、歧义、查询失败等原因 |
| `retraction_status` | `CONFIRMED` / `SUSPECTED` / `NO_RECORD` / `NOT_CHECKED` |
| `sources` | 数据源、证据类型、标识符、说明及来源自身的撤稿标记 |
| `verification_scope` | `REFERENCE_METADATA` 或 `HEURISTIC_ALIGNMENT` |

先确认文献身份，再归属撤稿证据。歧义候选即使带撤稿标记，也不能直接说用户引用的是撤稿论文。标题中出现 “retraction” 只作为疑似线索；同 DOI 的明确撤稿证据不会被另一来源的否定标记覆盖。

`PASS` 仅表示本次核验范围内未触发风险。`NO_RECORD` 仅表示查询过的来源没有记录，不能解释成“状态正常”。查询超时、限流与无结果分开保留。本地文件通过标题等元数据匹配；另一论文参考文献列表中出现标题，不构成匹配依据。

## MCP 使用

MCP 客户端可以启动源码安装后生成的命令：

```json
{
  "mcpServers": {
    "academic-guardrail": {
      "command": "academic-guardrail-mcp"
    }
  }
}
```

可用工具：`verify_single_citation`、`check_paper_retraction`、`audit_document_claims`、`generate_audit_html_report`。四个工具均支持 `offline: true`。文献核验和审计支持 `detail` 为 `compact`、`detailed`、`debug`。宿主 Agent 是否调用其他在线工具，由宿主配置控制。

## 学习与验证

推荐先读 [第一阶段代码导读](docs/learning_guide.md)，按“数据模型 → 纯判定函数 → 服务层 → 接口”顺序阅读，再运行相应回归测试。

```powershell
python -m pytest tests -q
```

测试默认隔离缓存、阻止真实 HTTP、关闭嵌入模型，验证的是工程行为，不是线上 API 可用性或 LLM 的学术推理准确率。

历史 `benchmarks/` 脚本和数据保留供后续整理。目前不再把历史准确率、延迟或小样例匹配率作为本版本的已验证能力：评测入口、样本选择与原始模型调用记录仍需独立重建和核验。

## 当前局限

- 解析器只覆盖部分引用格式；PDF 排版、BibTeX/LaTeX 关联和同一文献多次引用仍可能丢失信息。
- 本地标题、作者、年份来自简易抽取；匹配分数不是校准后的概率，歧义时需要补全信息。
- 词面规则和嵌入相似度不能可靠判断数值、因果、限定条件或真实蕴含。
- 在线来源可能缺摘要、延迟索引或不可用；撤稿数据库也可能不完整或过期。

这些限制应在演示和简历介绍时明确。可以描述已实现的多源查询、来源保留、统一判定、离线模式和回归测试，不宜宣称“自动保证论文正确”或未经复现的准确率。
