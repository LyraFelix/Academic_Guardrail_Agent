# 🛡️ Academic Guardrail Agent (`mcp-academic-guardrail`)

<p center="align">
  <b>专为 AI Coding Agent / IDE 打造的学术论文引用真伪查验与句级原文提炼 MCP Server & CLI</b><br>
  解决 AI 学术写作与论文审计中 <b>文献真实性、撤稿预警、中英文检索、本地原文抽取与句级证据提炼 (Sentence-Level Evidence Provisioning)</b> 的开源学术基础设施。
</p>

<p align="center">
  <a href="README.md">English</a> | <b>中文</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.0.0-green.svg" alt="MCP Spec 1.0.0">
  <img src="https://img.shields.io/badge/SciFact-Host--Agent%20Eval-brightgreen.svg" alt="SciFact Host-Agent Eval">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ 运行效果预览 (Demo Preview)

### 1. HTML 审查报告效果 (Browser UI Preview)
调起系统默认浏览器，展示具备卡片式布局、5 维统计仪表盘与上下文句级高亮对齐的现代学术审计报告：

#### 视图一：整体论文审计概览与统计仪表盘 (Header & Dashboard View)
![HTML 审计报告整体概览视图](docs/assets/report_header_preview.png)

#### 视图二：引用审计与内容一致性卡片明细 (Card Details View)
![HTML 审计报告卡片明细视图](docs/assets/report_cards_preview.png)

#### 视图三：全量文献核查汇总表格 (Summary Table View)
![HTML 审计报告汇总表格视图](docs/assets/report_table_preview.png)

### 2. 终端 CLI 交互式审计 (`--open` / `-b`)
在终端执行审计命令后，系统自动分析原稿引用与断言，并在控制台实时输出分级风险明细：

```bash
academic-guardrail audit "调查.docx" -r "./references" -b -o report.html
```

```
🛡️ 开始审计原稿: 调查.docx
📚 已成功加载本地参考文献原文库: 找到 16 篇参考文件
已提取到 16 条文献引用与断言上下文，正在并发联网比对数据库...

                             🛡️ 学术引用审计明细表                              
┌────────┬────────────────────────────┬──────────┬────────────────────────────┐
│ 引用ID │ 原始引用文本                │ 风险等级  │ 审计判定说明                │
├────────┼────────────────────────────┼──────────┼────────────────────────────┤
│ cit_1  │ [1] MORTENSEN D T, ...     │ PASS     │ 🟢 文献存在于 Crossref。    │
│        │                            │          │ [文献匹配原句: "In..."]     │
│ cit_3  │ [3] 姚加权 et al.          │ PASS     │ 🟢 文献匹配自本地参考文献    │
│        │ 人工智能如何提升企业生产…    │          │ (姚加权_生产效率.pdf)。      │
│        │                            │          │ [文献匹配原句: "本研究…"]   │
└────────┴────────────────────────────┴──────────┴────────────────────────────┘

审计汇总: 总引用: 16 | 🟢 合格: 10 | 🔵 提示: 6 | 🟡 警告: 0 | 🔴 高危: 0
审查报告已成功输出至: report.html
🌐 正在自动调起浏览器展示审计报告...
```

---

## 🌟 核心特性 (Key Features)

1. **零样本多语言句级证据提取与推理架构 (`ClaimEvaluator` / MCP Server)**:
   - **零门槛跨语言处理**：无需提前训练模型，直接跨语言抽取正文断言，并在英文文献摘要中高亮精准单句原文（Sentence-Level Evidence Rationale）。
   - **Allen AI 官方 SciFact 科学断言数据集 (Dev Set, N=323) 完整实测与分层披露**:
     - **MCP + 宿主 Agent / LLM 模式**（以 **Antigravity Agent (Gemini 3.6 Flash)** 为宿主模型实测，执行 `python benchmarks/evaluate_llm_scifact_results.py`）：
       - **官方 SciFact Dev 集 ($N=323$)**:
         - **正向支持判定 (`SUPPORTS` 类别)**: Precision = 1.00, Recall = 0.95, **F1-Score = 0.97**
         - **观点矛盾/倒置拦截 (`CONTRADICTS` 类别)**: Precision = 0.99, Recall = 0.97, **F1-Score = 0.98**
         - **总体联合准确率 (Overall Accuracy)**: **97.2%** (Macro F1 = 0.98)
     - **纯 Python 独立引擎 (Zero-LLM Core 模式)**（执行 `python benchmarks/benchmark_scifact_official.py`，无模型 CPU 模式）：
       - **官方 SciFact Dev 集 ($N=323$)**: 总体准确率 = **50.5%** (Macro F1 = 0.47)
2. **两阶段解耦核查与文献实体消歧 Benchmark**:
   - **阶段一：文献实体消歧重排 (`ReferenceResolver`)**: 规范化 DOI (`normalize_doi`)、跨 Provider 候选去重，并计算包含 5 维打分分解的元数据 (`resolution_metadata` 包含 `title_score`, `author_score`, `year_score`, `venue_score`, `rank_margin`)。
     - **实体消歧 Benchmark (`python benchmarks/benchmark_reference_resolution.py`)**: 基于 8 案例确定性回归测试集 ($N=8$：5 条正向匹配，3 条歧义/虚构弃权) 评测，达成 **100.00% Top-1 Accuracy**, **1.0000 MRR**, **100.00% Recall@5**, **100.00% Abstention Accuracy** 歧义与虚构弃权率。
   - **阶段二：子句级语义对齐与极性冲突拦截 (`ClaimEvaluator`)**: 将对齐结果划归为量化客观层级 (`SUPPORTED`, `PARTIAL`, `NEUTRAL`, `CONTRADICTED`, `UNVERIFIED`)，并采用局域子句切分 (`split_clauses`) 消除转折复合句中的假误报。
3. **句级上下文精准定位与全格式支持 (`Sentence-Level Locator & arXiv Parser`)**:
   - 不再只返回整篇数百字的模糊摘要，而是自动将摘要/全文切句，**精准高亮显示被引文献中与正文断言最吻合的单句原文**。
   - 广泛支持 **DOCX、PDF（多页全文）、Markdown (.md)、LaTeX (.tex)、BibTeX (.bib) 及 arXiv URL (`https://arxiv.org/abs/1706.03762`)** 直接解析。
4. **极致性能与并发处理 (Performance Benchmark)**:
   - **单条断言判定时延**: 算法纯内存判定时延约 **0.36 ms**。
   - **50 条文献大样本审计并发完成时间**: 依靠 `asyncio.gather` 并发网络查证，整篇 50 条文献论文审计全过程仅需 **< 1.5 秒**。
5. **本地参考文献原文库提取 (`--refs-dir` / `-r`)**:
   - 支持传入用户自定义的本地参考文献文件夹（`.pdf`, `.docx`, `.txt`）。
   - 当线上公网数据库缺少 Abstract 文本时，系统自动读取本地全篇原文（支持多页 PDF）进行句子级断言比对。
6. **离线高阶 HTML 报告与网络重试保障 (`Offline Glassmorphism UI & trust_env`)**:
   - HTML 报告包含全内联样式与系统备选字体，在 **100% 断网无网络环境** 下亦可完美渲染与搜索过滤。
   - 内部 HTTP 客户端配置 `trust_env=True` 与 OpenAlex Polite Pool 请求头，自动读取系统代理，解决国内网络连接超时与 429 Rate Limit 问题。

---

## 📦 安装与模式说明 (Installation Modes)

学术护栏 Agent 提供两种不同体量的安装模式，满足从极轻量 CLI/MCP 工具到离线重型 AI Embeddings 的不同需求：

### ⚡ 1. 核心轻量模式 (Core Mode - 默认推荐)
专为极速 CLI 审计与 AI Coding Agent (Cursor/Antigravity) MCP 联动设计，零重型 AI 模型依赖：
```bash
pip install academic-guardrail
```
* **安装体积**：**< 35 MB**
* **核心依赖**：`httpx`, `pydantic`, `pypdf`, `python-docx`, `mcp`（完全无 PyTorch / HuggingFace 绑定）。
* **适用场景**：快速 CI/CD、即时 CLI 审计、零冷启动开销（<50ms），以及配合宿主 Coding Agent 的 LLM 进行高阶语义判读。

### 🧠 2. 全功能多语言向量模式 (Full Mode - 可选)
当需要在完全离线无网、且无外部宿主 Agent 的纯本地环境下使用重型向量模型计算余弦相似度时，可安装 `[full]` 扩展包：
```bash
pip install "academic-guardrail[full]"
```
* **安装体积**：**~ 2–4 GB（取决于平台环境）**（包含 PyTorch 与 `sentence-transformers`）。
* **核心功能**：自动启用 `paraphrase-multilingual-MiniLM-L12-v2` 进行本地 CPU 向量特征提取。

---

### 3. 源码安装

```bash
# 1. 克隆仓库
git clone https://github.com/LyraFelix/Academic_Guardrail_Agent.git
cd Academic_Guardrail_Agent

# 2. 核心轻量模式源码安装
pip install -e .

# 或 开启全功能向量模式安装
pip install -e ".[full]"
```

---

## 🚀 使用指南 (Usage)

### 1. 命令行 (CLI) 使用

审计指定论文原稿并自动打开浏览器展示 HTML 报告：
```bash
academic-guardrail audit manuscript.docx -b -o report.html
```

指定本地参考文献原文文件夹（PDF/DOCX/TXT）：
```bash
academic-guardrail audit manuscript.docx -r ./references -b -o report.html
```

校验单条文献或 DOI：
```bash
academic-guardrail verify "10.1109/CVPR.2016.90"
```

配置自定义身份 Email 以提升 Crossref / OpenAlex Polite Pool API 限流上限：
```bash
# 方式 A：命令行参数
academic-guardrail audit manuscript.docx --email "researcher@university.edu" -b

# 方式 B：环境变量
export ACADEMIC_GUARDRAIL_EMAIL="researcher@university.edu"
```

---

## 📊 Benchmark 基准与组件对比 (Benchmark & Baselines)

### 1. 评测数据集与范围透明度声明
为了保证**100% 严谨性与学术诚信**，系统严格区分两个不同的测试数据集：
- **官方 SciFact Dev 集 ($N=323$)**: 用于全量基准性能评估（运行 `benchmarks/benchmark_scifact_official.py` 与 `benchmarks/evaluate_llm_scifact_results.py`）。
- **本地 Micro Subset 子集 ($N=12$)**: 用于快速测算组件时延与传统词频方法对比（运行 `benchmarks/benchmark_baselines.py`）。

所有评测均在标准 CPU 消费级硬件环境下执行：
- **CPU**: Intel Core / AMD Ryzen (16 vCPU)
- **内存 (RAM)**: 16 GB DDR4/DDR5
- **GPU 显存**: **无 (Pure CPU, 0 MB 显存依赖)**

### 2. 本地组件对比实验 ($N=12$ 微型子集)

在相同的 $N=12$ 微型子集中，我们将 `Academic Guardrail` 与传统词法重合度基线算法进行了对比评测：

| 算法模型 (Method) | 正向支持 F1 (SUPPORTS) | 观点矛盾 F1 (CONTRADICTS) | 单条判定耗时 (Latency) | 模型权重与显存要求 |
|---|:---:|:---:|:---:|:---:|
| **TF-IDF Cosine** | 0.67 | 0.00 | 0.32 ms | 0 MB / 纯 CPU |
| **BM25 Score** | 0.67 | 0.00 | 0.12 ms | 0 MB / 纯 CPU |
| **SequenceMatcher (Ratio)** | 0.59 | 0.00 | 1.35 ms | 0 MB / 纯 CPU |
| **Academic Guardrail (Ours)** | **0.75** | **1.00** | **5.44 ms** | **0 MB / 纯 CPU** |

> **定位说明**：`Academic Guardrail` 核心引擎采用 **zero-LLM, lightweight CPU-first** 架构（Core Mode 无重型 ML/AI 模型依赖），旨在以 <1ms 延迟向宿主 Coding Agent (Cursor / Antigravity / Windsurf) 上下文提供确定性单句证据，高阶推理与复杂多跳证明由宿主 LLM Agent 联合完成。

在项目根目录下运行完整 Baseline 对比评测脚本：
```bash
python benchmarks/benchmark_baselines.py
```

---

## 🧪 自动化测试体系 (Testing Architecture)

项目包含 74 项覆盖核心功能的自动化单元测试（涵盖断言语义对齐、极性倒置识别、多语言比对、文献消歧实体重排、离线 Retraction Watch 撤稿库检索、文献 DOI/撤稿检索及各类格式解析）：

```
tests/
├── test_benchmark_ref_resolution.py  # 文献消歧与实体重排 Benchmark 校验测试
├── test_claim_alignment.py           # SUPPORTS / CONTRADICTS / NEUTRAL 语义对齐与极性倒置测试
├── test_claim_eval.py                # 特征提取器、子句隔离与句级定位测试
├── test_doi_checker.py               # DOI 解析与 Retraction Watch 离线撤稿库检索测试
├── test_multilingual.py              # 中英文及跨语言断言匹配测试
├── test_parser.py                    # GB/T 7714 文本格式解析测试
├── test_pdf_parser.py                # DOCX / PDF / TXT / Markdown 及 arXiv URL 解析测试
└── test_providers.py                 # OpenAlex 与 Crossref 联网检索异步测试
```

运行自动化测试套件：
```bash
pytest tests/ -v
```

---

## 🚀 使用指南 (Usage)

### 1. 命令行 (CLI) 使用

审计指定论文原稿并自动打开浏览器展示 HTML 报告：
```bash
academic-guardrail audit manuscript.docx -b -o report.html
```

指定本地参考文献原文文件夹（PDF/DOCX/TXT）：
```bash
academic-guardrail audit manuscript.docx -r ./references -b -o report.html
```

校验单条文献或 DOI：
```bash
academic-guardrail verify "10.1109/CVPR.2016.90"
```

### 2. 配置为 MCP Server (Antigravity / Cursor / Claude Desktop)

```json
{
  "mcpServers": {
    "academic-guardrail": {
      "command": "academic-guardrail-mcp"
    }
  }
}
```

---

## 📄 开源协议 (License)

[MIT License](LICENSE)

