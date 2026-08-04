# 🛡️ Academic Guardrail Agent (`mcp-academic-guardrail`)

<p center="align">
  <b>全流程学术论文引用与断言一致性校验 Agent (MCP Server & CLI)</b><br>
  解决 AI 学术写作中 <b>文献真伪、撤稿警示、中英文支持与断言一致性 (Claim vs Content Match)</b> 的开源学术护栏。
</p>

<p align="center">
  <a href="README.md">English</a> | <b>中文</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.0.0-green.svg" alt="MCP Spec 1.0.0">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ 运行效果预览 (Demo Preview)

### 1. Agent 响应预览 (Antigravity / Cursor / Claude Desktop)
当 AI Agent 接收到论文审计指令时，系统会自动调起 MCP 工具进行全量比对并返回多维风险报告：

```
🛡️ **文档审计完成**: 总引用 10 项 | 🟢 通过 7 | 🟡 警告 2 | 🔴 高危 1

- [🔴 DANGER]  Hwang et al. (2006) -> 🔴 论文存在撤稿记录 (DOI: 10.1016/j.cell.2006.02.001)，存在严重学术合规风险！
- [🟡 WARNING] 张三 et al. (2099) -> 🟡 数据库未查证到该文献，可能系 AI 虚构或 DOI 错误。
- [🔵 NOTICE]  Vitamin D Study    -> 🔵 断言一致性较弱 (0.25)。检测出极性矛盾：用户断言“降低风险”，但文献摘要结论为“did not lower risk”。
- [🟢 PASS]    ResNet (CVPR 2016) -> 🟢 匹配成功，文献真实，撤稿状态正常。
```

### 2. 终端 CLI 交互式报表 (Terminal HTML & Rich Console)

```
                 📊 学术 Guardrail 大样本评测明细 (Total: 23)                  
┌────────┬──────────────┬────────────────────────────────┬────────────┬────────────┬─────────┐
│ 编号   │ 分类         │ 测试用例描述                   │ 预测状态   │ 预期状态   │ 判定    │
├────────┼──────────────┼────────────────────────────────┼────────────┼────────────┼─────────┤
│ RET-01 │ Retraction   │ Hwang et al. 干细胞 Cell 撤稿  │ RETRACTED  │ RETRACTED  │ PASS ✅ │
│ RET-02 │ Retraction   │ STAP 干细胞 Nature 撤稿        │ RETRACTED  │ RETRACTED  │ PASS ✅ │
│ DOI-01 │ Valid DOI    │ ResNet 论文 (He et al. 2016)   │ VALID      │ VALID      │ PASS ✅ │
│ SCF-02 │ SciFact      │ AMPK 与癌细胞增殖 (Contradict) │ Score: 0.25│ NOTICE     │ PASS ✅ │
│ FK-01  │ Fake Citation│ 虚构数字 DOI                   │ UNVERIFIED │ UNVERIFIED │ PASS ✅ │
└────────┴──────────────┴────────────────────────────────┴────────────┴─────────┘
```

---

## 🌟 核心特性 (Key Features)

1. **三维一体校验**:
   - 🟢 **真实性校验**: 自动提取原稿中的引用与 DOI，对接 OpenAlex (2.5 亿条)、Crossref (1.4 亿条) 及 Semantic Scholar 全球学术数据库。
   - 🔴 **撤稿审查**: 实时比对 Retraction Watch 与 Crossref 撤稿（Retraction Notice / Expression of Concern）数据。
   - 🔵 **语义断言校验**: 自动提取原稿引用的上下文断言句 (Context Claim)，与文献 Abstract/TLDR 进行语义比对，警示断言偏差与断章取义风险。
2. **断言一致性比对算法**:
   - 结合 Token 重叠率与 Jaccard/Sequence 相似度计算一致性得分 $S_{\text{score}}$。
   - 引入学术领域**对向极性词树树图 (Polarity Antonym Graph)**（如 `increase` vs `inhibit`, `reduce` vs `did not lower`），精准拦截极性反转与观点曲解错误。
3. **中英文双语支持**:
   - 针对 GB/T 7714 国标格式（如 `[1] 张三, 李四. 某算法[J]. 计算机学报, 2022.`）自动正则拆解与模糊比对。
4. **多原稿格式支持**:
   - 支持 `.pdf`（仅限含文字层的可选择 PDF）、`.docx` (Word)、`.md` (Markdown)、`.tex` / `.bib` (LaTeX)。
5. **全 Agent 兼容**:
   - 基于标准 MCP (Model Context Protocol) 协议开发，原生兼容 **Codex、Trea、Cursor、Windsurf、Claude Desktop、Antigravity**。

---

## 📦 安装与依赖说明 (Installation & Dependencies)

### 1. 软件依赖与网络要求

> **注**：OpenAlex / Crossref / Semantic Scholar 为开放免费数据库，**无需注册 API Key**即可直接使用。但由于请求全球学术 REST API 接口，运行设备需要具备**稳定的公网/外网访问环境**。

### 2. 本地安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/mcp-academic-guardrail.git
cd mcp-academic-guardrail

# 2. 可编辑模式安装
pip install -e .
```

---

## 🚀 使用指南 (Usage)

### 1. 命令行 (CLI) 快速审计

审计论文原稿并输出 HTML 报告：
```bash
academic-guardrail audit sample_manuscript.md -o report.html
```

校验单条文献或 DOI：
```bash
academic-guardrail verify "10.1109/CVPR.2016.90"
```

运行本地基准测试集：
```bash
python benchmark_runner.py
```

### 2. 配置为 MCP Server (Cursor / Antigravity / Claude Desktop)

在你的 Agent 配置文件 (如 `claude_desktop_config.json` 或 Agent MCP 设置) 中添加：

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

## ⚠️ 已知限制 (Known Limitations)

1. **PDF 格式限制**：系统使用 `pdfplumber` 提取文本，**仅支持包含文字层的矢量/电子版 PDF**。如果是扫描件（纯图片组成的 PDF），需要提前进行 OCR 识别，暂不支持直接解析纯图片扫描件。
2. **公网 API 限流与网络延迟**：免费开放 API（OpenAlex/Crossref）存在约 10 次/秒的速率限制（Rate Limit）。大规模文献审计建议使用内置的离线评估引擎（`OfflineRetractionDB`）。
3. **中文文献覆盖范围**：对于有 DOI 注册的中文核心期刊（如《计算机学报》、《软件学报》），系统能够通过 Crossref / OpenAlex 精准匹配；对于少量未注册 DOI 的早期非核心地方期刊，可能触发 `UNVERIFIED` 提醒。

---

## 📄 开源协议 (License)

[MIT License](LICENSE)
