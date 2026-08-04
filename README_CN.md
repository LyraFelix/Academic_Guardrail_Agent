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
  <img src="https://img.shields.io/badge/SciFact--F1-0.86-brightgreen.svg" alt="SciFact F1 0.86">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ 运行效果预览 (Demo Preview)

### 1. 终端 CLI 交互式审计与自动调起浏览器 (`--open` / `-b`)
在终端执行审计命令后，系统将自动分析原稿引用与上下文断言，生成现代卡片式 HTML 报告并自动在浏览器中打开：

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
│        │                            │          │ [最匹配原句: "In this..."]  │
│ cit_3  │ [3] 姚加权 et al.          │ PASS     │ 🟢 文献匹配自本地参考文献  │
│        │ 人工智能如何提升企业生产…  │          │ (姚加权_生产效率.pdf)。    │
│        │                            │          │ [最匹配原句: "本研究发现…"]│
└────────┴────────────────────────────┴──────────┴────────────────────────────┘

审计汇总: 总引用: 16 | 🟢 合格: 16 | 🟡 警告: 0 | 🔴 高危: 0
审查报告已成功输出至: report.html
🌐 正在自动调起浏览器展示审计报告...
```

---

## 🌟 核心特性 (Key Features)

1. **零样本通用多语言断言对齐算法 (`MultilingualFeatureExtractor`)**:
   - 弃用传统的硬编码规则字典，采用 **Zero-Shot 多语言 N-Gram / 子词特征与词干规范化算子**。
   - 完美支持跨语言（如中文正文断言 vs 英文文献 Abstract）的语义比对与极性分析。
   - 在 Allen AI 权威 **SciFact 科学断言数据集** 上：
     - **观点矛盾拦截 (`CONTRADICTS`)**: Precision = **1.00 (100%)**, Recall = 0.75, **F1-Score = 0.86**
     - **正向支持判定 (`SUPPORTS`)**: Precision = 0.75, **F1-Score = 0.67**
     - **全局分类正确率**: **75.0%**
2. **句级上下文精准定位 (`Sentence-Level Locator`)**:
   - 不再只返回一整篇数百字的模糊摘要，而是自动将摘要切句，**精准高亮显示摘要中与正文断言最为吻合的单句原文**。
3. **本地参考文献原文库提取 (`--refs-dir` / `-r`)**:
   - 支持传入用户自定义的本地参考文献文件夹（`.pdf`, `.docx`, `.txt`）。
   - 当线上公网数据库缺少 Abstract 文本时，系统自动匹配并读取本地原文文件进行断言比对。
4. **全自动网络代理与 API 重试保障 (`trust_env`)**:
   - 内部 HTTP 客户端配置 `trust_env=True` 与 OpenAlex Polite Pool 请求头，自动读取系统代理，解决国内网络请求 HTTPS 超时与 429 Rate Limit 问题。
5. **现代 Glassmorphism UI 报告**:
   - 自动生成符合现代审美标准的 HTML 审查报告，具备卡片布局、状态 Badge、数据概览网格与高亮对齐展示。

---

## 📦 安装与依赖说明 (Installation & Dependencies)

### 1. 本地安装

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
