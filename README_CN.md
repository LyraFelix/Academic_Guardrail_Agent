# 🛡️ Academic Guardrail Agent (`mcp-academic-guardrail`)

<p center="align">
  <b>全流程学术论文引用与断言一致性校验 Agent (MCP Server & CLI)</b><br>
  解决 AI 学术写作中 <b>文献真伪、撤稿警示、中英文支持、本地原文库提取与零样本断言一致性 (Claim vs Content Match)</b> 的开源学术护栏。
</p>

<p align="center">
  <a href="README.md">English</a> | <b>中文</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.0.0-green.svg" alt="MCP Spec 1.0.0">
  <img src="https://img.shields.io/badge/SciFact--Contradicts--F1-0.86-brightgreen.svg" alt="SciFact Contradicts F1 0.86">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ 运行效果预览 (Demo Preview)

### 1. HTML 审查报告效果 (Browser UI Preview)
调起系统默认浏览器，展示具备卡片式布局、维度统计网格与上下文句级高亮对齐的现代学术审计报告（呈现在报告中的高亮文本为**从被引文献摘要或全篇 PDF 原文中切分提取出的吻合单句**）：

![HTML 审计报告效果预览](docs/assets/report_preview.png)

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
│ 引用ID │ 原始引用文本               │ 风险等级 │ 审计判定说明               │
├────────┼────────────────────────────┼──────────┼────────────────────────────┤
│ cit_1  │ [1] MORTENSEN D T, ...     │ PASS     │ 🟢 文献存在于 Crossref。   │
│        │                            │          │ [文献匹配原句: "In..."]    │
│ cit_3  │ [3] 姚加权 et al.          │ PASS     │ 🟢 文献匹配自本地参考文献  │
│        │ 人工智能如何提升企业生产…  │          │ (姚加权_生产效率.pdf)。    │
│        │                            │          │ [文献匹配原句: "本研究…"]  │
└────────┴────────────────────────────┴──────────┴────────────────────────────┘

审计汇总: 总引用: 16 | 🟢 合格: 16 | 🟡 警告: 0 | 🔴 高危: 0
审查报告已成功输出至: report.html
🌐 正在自动调起浏览器展示审计报告...
```

---

## 🌟 核心特性 (Key Features)

1. **零样本多语言断言对齐算法 (`MultilingualFeatureExtractor`)**:
   - **零门槛跨语言处理**：本算法无需提前训练模型，也无需预置专业领域字典，能够直接跨语言比对中文正文断言与英文文献摘要的核心观点。
   - **算法细节**：底层结合 Token 词干提取（Stemming）、学术近义词规范化与多语言 N-Gram 字符特征匹配。
   - 在 Allen AI 权威 **SciFact 科学断言数据集** 上：
     - **观点矛盾/倒置拦截 (`CONTRADICTS` 类别)**: Precision = **1.00 (100%)**, Recall = 0.75, **F1-Score = 0.86**
     - **正向支持判定 (`SUPPORTS` 类别)**: Precision = 0.75, Recall = 0.61, **F1-Score = 0.67**
     - *(全量集加权平均 Weighted Average F1 = 0.77)*
2. **断言语义匹配工作原理**:
   - 系统首先反向回溯原稿正文，提取包含引用标记的上下文断言句。
   - 接着从公网数据库 API 或本地文献中提取 Abstract/全文，通过多维字符特征与反义极性树（`Polarity Antonym Graph`）检测结论倒置与观点曲解，并实时高亮定位**被引文献中的最吻合单句原文**。
3. **句级上下文精准定位 (`Sentence-Level Locator`)**:
   - 不再只返回整篇数百字的模糊摘要，而是自动将摘要/全文切句，**精准高亮显示被引文献中与正文断言最吻合的单句原文**。
4. **本地参考文献原文库提取 (`--refs-dir` / `-r`)**:
   - 支持传入用户自定义的本地参考文献文件夹（`.pdf`, `.docx`, `.txt`）。
   - 当线上公网数据库缺少 Abstract 文本时，系统自动读取本地全篇原文（支持多页 PDF）进行句子级断言比对。
5. **全自动网络代理与 API 重试保障 (`trust_env`)**:
   - 内部 HTTP 客户端配置 `trust_env=True` 与 OpenAlex Polite Pool 请求头，自动读取系统代理，解决 HTTPS 超时与 429 Rate Limit 问题。

---

## 📦 安装与依赖说明 (Installation & Dependencies)

### 1. 核心依赖清单 (Dependencies)

- **Python**: `>= 3.10`
- **核心第三方库**:
  - `httpx` (支持 `trust_env` 系统代理读取与高并发异步请求)
  - `pypdf` & `python-docx` (本地参考文献 PDF/DOCX 全文解析)
  - `rich` (命令行控制台表格与色彩卡片渲染)
  - `mcp` (Model Context Protocol 1.0.0 SDK)

### 2. PyPI 快捷安装 (即将推出)

```bash
pip install academic-guardrail
```
> **注**：目前项目处于快速迭代期，暂需从源码安装，我们将尽快发布至 PyPI 官方索引。

### 3. 源码安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/mcp-academic-guardrail.git
cd mcp-academic-guardrail

# 2. 可编辑模式安装
pip install -e .
```

---

## 🚀 使用指南 (Usage)

### 1. 命令行 (CLI) 使用

审计指定论文原稿并自动打开浏览器：
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

运行 SciFact 权威断言断言评测基准：
```bash
python benchmark_claims.py
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
