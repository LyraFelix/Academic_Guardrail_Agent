# 🛡️ Academic Guardrail Agent (`mcp-academic-guardrail`)

<p align="center">
  <b>Unified Academic Research Integrity, Citation Verification & Claim Alignment Guardrail</b><br>
  An open-source Model Context Protocol (MCP) Server and CLI tool to eliminate <b>AI hallucinations, retracted paper references, and claim distortion</b> in academic writing.
</p>

<p align="center">
  <b>English</b> | <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.0.0-green.svg" alt="MCP Spec 1.0.0">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ Execution Preview & Demo

### 1. AI Agent Response Preview (Antigravity / Cursor / Claude Desktop)
When triggered by an AI Agent, `mcp-academic-guardrail` audits all citations in the manuscript and returns structured risk indicators:

```
🛡️ **Document Audit Completed**: Total Citations: 10 | 🟢 Passed: 7 | 🟡 Warning: 2 | 🔴 Danger: 1

- [🔴 DANGER]  Hwang et al. (2006) -> 🔴 PAPER RETRACTED! (DOI: 10.1016/j.cell.2006.02.001). Severe academic integrity compliance risk!
- [🟡 WARNING] Zhang et al. (2099) -> 🟡 Unverified citation. Possible AI hallucination or invalid DOI.
- [🔵 NOTICE]  Vitamin D Study    -> 🔵 Weak claim alignment (0.25). Polarity contradiction detected: Claim states "reduces risk", but abstract concludes "did not lower risk".
- [🟢 PASS]    ResNet (CVPR 2016) -> 🟢 Citation verified & authentic. Paper active.
```

### 2. Interactive Terminal Benchmark Output

```
                 📊 Academic Guardrail Benchmark Matrix (Total: 23)             
┌────────┬──────────────┬────────────────────────────────┬────────────┬────────────┬─────────┐
│ ID     │ Category     │ Case Description               │ Predicted  │ Expected   │ Result  │
├────────┼──────────────┼────────────────────────────────┼────────────┼────────────┼─────────┤
│ RET-01 │ Retraction   │ Hwang et al. Cell Retraction   │ RETRACTED  │ RETRACTED  │ PASS ✅ │
│ RET-02 │ Retraction   │ STAP Stem Cell Nature          │ RETRACTED  │ RETRACTED  │ PASS ✅ │
│ DOI-01 │ Valid DOI    │ ResNet (He et al. 2016)        │ VALID      │ VALID      │ PASS ✅ │
│ SCF-02 │ SciFact      │ AMPK & Cancer (Contradiction) │ Score: 0.25│ NOTICE     │ PASS ✅ │
│ FK-01  │ Fake Citation│ Non-existent Digital DOI       │ UNVERIFIED │ UNVERIFIED │ PASS ✅ │
└────────┴──────────────┴────────────────────────────────┴────────────┴─────────┘
```

---

## 🌟 Key Features

1. **3-D Verification Pipeline**:
   - 🟢 **Citation Verification**: Automatically extracts DOIs and paper titles, cross-referencing against 250M+ OpenAlex works, 140M+ Crossref entries, and Semantic Scholar.
   - 🔴 **Retraction Interception**: Real-time matching against Retraction Watch datasets and Crossref retraction notices.
   - 🔵 **Claim-Content Consistency**: Parses context claim sentences around citation markers (`[1]`) and evaluates semantic alignment against paper abstracts.
2. **Polarity Antonym Graph Alignment**:
   - Computes token overlap and sequence similarity ($S_{\text{score}}$).
   - Incorporates a specialized **Polarity Antonym Graph** (e.g. `increase` vs `inhibit`, `reduce` vs `did not lower`) to catch claim distortions and polarity inversions.
3. **Bilingual Chinese & English Support**:
   - Built-in regex and fuzzy matcher for Chinese GB/T 7714 citation formats (`[1] 张三. 某算法[J]. 计算机学报, 2022.`).
4. **Multi-Format Manuscript Parser**:
   - Supports `.pdf` (text-selectable), `.docx` (Word), `.md` (Markdown), and `.tex` / `.bib` (LaTeX).
5. **Universal Agent Compatibility**:
   - Built on standard MCP JSON-RPC protocol. Natively compatible with **Codex, Trea, Cursor, Windsurf, Claude Desktop, and Antigravity**.

---

## 📦 Prerequisites & Dependencies

> **Note**: OpenAlex, Crossref, and Semantic Scholar APIs are open-access and **DO NOT require any API Key**. However, a **stable internet connection** is required for live REST API queries.

---

## 🚀 Installation & Getting Started

### 1. Install via pip

```bash
git clone https://github.com/your-org/mcp-academic-guardrail.git
cd mcp-academic-guardrail
pip install -e .
```

### 2. CLI Audit Command

Audit a manuscript and output an HTML report:
```bash
academic-guardrail audit sample_manuscript.md -o report.html
```

Verify a single DOI or citation:
```bash
academic-guardrail verify "10.1109/CVPR.2016.90"
```

### 3. Configure as MCP Server

Add to your AI Client's configuration file (e.g., `claude_desktop_config.json` or Agent MCP Settings):

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

## ⚠️ Known Limitations

1. **PDF Text Layer Dependency**: PDF parsing relies on `pdfplumber` and **only supports text-selectable PDFs**. Scanned PDFs (pure images without OCR text layers) are not supported directly and require prior OCR preprocessing.
2. **Public REST API Rate Limits**: Free public APIs (OpenAlex/Crossref) enforce rate limits (~10 requests/sec). For high-volume offline evaluations, use the bundled offline SQLite engine (`OfflineRetractionDB`).
3. **Chinese Core Coverage**: Chinese papers with registered DOIs (e.g., in *Journal of Computer Research and Development*, *Journal of Software*) are fully matched. Non-core local journals lacking registered DOIs may trigger `UNVERIFIED` alerts.

---

## 📄 License

Distributed under the [MIT License](LICENSE).
