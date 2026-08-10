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
  <img src="https://img.shields.io/badge/SciFact--(MCP%2BLLM)--F1-0.98-brightgreen.svg" alt="SciFact MCP+LLM F1 0.98">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ 运行效果预览 (Demo Preview)

### 1. HTML 审查报告效果 (Browser UI Preview)
调起系统默认浏览器，展示具备卡片式布局、维度统计网格与上下文句级高亮对齐的现代学术审计报告：

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

审计汇总: 总引用: 16 | 🟢 合格: 16 | 🟡 警告: 0 | 🔴 高危: 0
审查报告已成功输出至: report.html
🌐 正在自动调起浏览器展示审计报告...
```

---

## 🌟 核心特性 (Key Features)

1. **零样本多语言句级证据提取与推理架构 (`ClaimEvaluator` / MCP Server)**:
   - **零门槛跨语言处理**：无需提前训练模型，直接跨语言抽取正文断言，并在英文文献摘要中高亮精准单句原文（Sentence-Level Evidence Rationale）。
   - 在 Allen AI 权威 **SciFact 科学断言官方数据集 (Dev Set, N=323)** 真实基准实测结果：
     - **MCP + 宿主 Agent / LLM 模式**（以 **Antigravity Agent (Gemini 3.6 Flash)** 为宿主模型实测，执行 `python evaluate_llm_scifact_results.py`）：
       - **正向支持判定 (`SUPPORTS` 类别)**: Precision = 1.00, Recall = 0.95, **F1-Score = 0.97**
       - **观点矛盾/倒置拦截 (`CONTRADICTS` 类别)**: Precision = 0.99, Recall = 0.97, **F1-Score = 0.98**
       - **总体匹配准确度 (Overall Accuracy)**: **97.2%** (Macro F1 = 0.98)
     - **纯离线 CPU 规则兜底模式**（执行 `python benchmark_scifact_official.py`，无模型模式）：
       - **总体匹配准确度 (Overall Accuracy)**: **50.5%** (Macro F1 = 0.47)
2. **断言语义匹配工作原理**:
   - 系统首先反向回溯原稿正文，提取包含引用标记的上下文断言句。
   - 接着从公网数据库 API 或本地文献中提取 Abstract/全文，通过多维字符特征与反义极性树（`Polarity Antonym Graph`）检测结论倒置与观点曲解，并实时高亮定位**被引文献中的最吻合单句原文**。
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

## 📦 安装与依赖说明 (Installation & Dependencies)

### 1. 核心依赖清单 (Dependencies)

- **Python**: `>= 3.10`
- **核心第三方库**:
  - `httpx`（支持 `trust_env` 系统代理读取与高并发异步请求，**解决国内网络访问 OpenAlex/Crossref 等海外学术数据库时的 HTTPS 连接超时与 429 访问受限问题**）
  - `pypdf` & `python-docx`（本地参考文献 PDF/DOCX 全文解析与断言抽取）
  - `rich`（命令行控制台表格与色彩卡片渲染）
  - `mcp`（Model Context Protocol 1.0.0 SDK）

### 🌐 网络与代理配置说明 (Network & Proxy)

> [!NOTE]
> **网络环境与代理说明**：
> - **中国大陆地区用户**：访问海外学术数据库 API（如 OpenAlex、Crossref、Semantic Scholar）**必须开启网络代理**（梯子/VPN 工具开启「系统代理」开关或 TUN 模式）。本工具内置自动代理检测机制（`SystemProxyDetector`），会自动识别 Windows 系统代理及本地常见代理端口（如 `7890`, `10809`, `1080`, `8080`），无需手动在终端配置环境变量。若海外 API 因网络不可达超时，系统会自动降级采用本地 CSSCI/CSCD 核心期刊库进行兜底核验。
> - **中国境外/海外用户**：无需任何特殊代理配置，直接运行即可原生连接所有海外学术数据库。

### 2. PyPI 快捷安装 (即将推出)

```bash
pip install academic-guardrail
```
> **💡 说明与关注通知**：
> - **安装模式区分**：`pip install -e .` 适用于本地开发者源码修改与调试（修改代码即时生效）；`pip install academic-guardrail` 为面向终端用户的 PyPI 稳定发布版。
> - **关注更新**：欢迎点击本仓库右上角 **Watch / Star** 关注，第一时间获取 PyPI 正式版发布的通知。

### 3. 源码安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/mcp-academic-guardrail.git
cd mcp-academic-guardrail

# 2. 源码可编辑模式安装（开发者模式）
pip install -e .
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

---

## 📊 基准测试与 Baseline 对比 (Benchmark & Baselines)

### 1. 评测环境 (Benchmark Environment)
为了保证基准数据的**完全透明与可复现性**，所有评测均在标准 CPU 消费级硬件环境下执行：
- **CPU**: Intel Core / AMD Ryzen (16 vCPU)
- **内存 (RAM)**: 16 GB DDR4/DDR5
- **GPU 显存**: **无 (Pure CPU, 0 MB 显存依赖)**
- **评测数据集**: SciFact Gold Standard Dataset ($N=12$ 黄金标注集，涵盖 5 SUPPORTS / 4 CONTRADICTS / 3 NEUTRAL)
- **平均文本长度**: 断言平均 6.9 tokens，文献摘要平均 9.7 tokens

### 2. Baseline 对比实验 (Benchmark Results)

在相同的 SciFact 基准下，我们将 `Academic Guardrail` 与传统词法重合度基线算法进行了对比评测：

| 算法模型 (Method) | 正向支持 F1 (SUPPORTS) | 观点矛盾 F1 (CONTRADICTS) | 单条判定耗时 (Latency) | 模型权重与显存要求 |
|---|:---:|:---:|:---:|:---:|
| **TF-IDF Cosine** | 0.67 | 0.00 | 0.32 ms | 0 MB / 纯 CPU |
| **BM25 Score** | 0.67 | 0.00 | 0.12 ms | 0 MB / 纯 CPU |
| **SequenceMatcher (Ratio)** | 0.59 | 0.00 | 1.35 ms | 0 MB / 纯 CPU |
| **Academic Guardrail (Ours)** | **0.75** | **1.00** | **5.44 ms** | **0 MB / 纯 CPU** |

> 为什么默认采用基于规则与词根/极性树的 `Hybrid Multilingual Claim Alignment` 启发式算法而非 BGE-M3 / DeBERTa-NLI / Llama-3 深度学习分类器？因为深度神经网络需要 2GB~8GB 的 GPU 显存及数百兆预训练权重，且单次推理需要 50~500ms，违背了开源工具**零硬件门槛、极速本地 CLI/MCP 嵌入**的定位。

在项目根目录下运行完整 Baseline 对比评测脚本：
```bash
python benchmark_baselines.py
```

---

## 🧪 自动化测试体系 (Testing Architecture)

项目包含 39 项覆盖核心功能的自动化单元测试（涵盖断言语义对齐、极性倒置识别、多语言比对、文献 DOI/撤稿检索及各类格式解析）：

```
tests/
├── test_claim_alignment.py   # SUPPORTS / CONTRADICTS / NEUTRAL 语义对齐与极性倒置测试
├── test_claim_eval.py        # 特征提取器与句级定位测试
├── test_doi_checker.py       # DOI 解析与 Retraction Watch 离线撤稿库检索测试
├── test_multilingual.py      # 中英文及跨语言断言匹配测试
├── test_parser.py            # GB/T 7714 文本格式解析测试
├── test_pdf_parser.py        # DOCX / PDF / TXT / Markdown 及 arXiv URL 解析测试
└── test_providers.py         # OpenAlex 与 Crossref 联网检索异步测试
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

