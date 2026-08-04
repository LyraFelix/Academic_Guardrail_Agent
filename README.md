# 🛡️ Academic Guardrail Agent (`mcp-academic-guardrail`)

<p center="align">
  <b>End-to-End Academic Citation & Claim Consistency Verification Agent (MCP Server & CLI)</b><br>
  An open-source academic guardrail addressing <b>citation validity, retraction alerts, multilingual support, local reference extraction, and zero-shot claim alignment (Claim vs Content Match)</b>.
</p>

<p align="center">
  <b>English</b> | <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.0.0-green.svg" alt="MCP Spec 1.0.0">
  <img src="https://img.shields.io/badge/SciFact--F1-0.86-brightgreen.svg" alt="SciFact F1 0.86">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ Demo Preview

### Interactive CLI Audit & Auto-Browser Launch (`--open` / `-b`)
Run the audit command in your terminal to inspect claims and citations across databases and local reference files. A modern glassmorphism HTML report is generated and auto-launched in your default browser:

```bash
academic-guardrail audit "paper.docx" -r "./references" -b -o report.html
```

```
🛡️ Starting Audit: paper.docx
📚 Loaded Local Reference Store: Found 16 reference files
Extracted 16 citations & claims. Querying databases asynchronously...

                             🛡️ Academic Audit Summary                              
┌────────┬────────────────────────────┬──────────┬────────────────────────────┐
│ ID     │ Citation Text              │ Risk     │ Verification Summary       │
├────────┼────────────────────────────┼──────────┼────────────────────────────┤
│ cit_1  │ [1] MORTENSEN D T, ...     │ PASS     │ 🟢 Valid in Crossref.      │
│        │                            │          │ [Matched Sentence: "In..."]│
│ cit_3  │ [3] Yao et al.             │ PASS     │ 🟢 Matched Local File      │
│        │ AI & Firm Productivity...  │          │ (Yao_Productivity.pdf).    │
│        │                            │          │ [Matched Sentence: "AI..."]│
└────────┴────────────────────────────┴──────────┴────────────────────────────┘

Summary: Total: 16 | 🟢 PASS: 16 | 🟡 WARNING: 0 | 🔴 DANGER: 0
Report output to: report.html
🌐 Auto-launching default system browser...
```

---

## 🌟 Key Features

1. **Zero-Shot Universal Multilingual Claim Alignment (`MultilingualFeatureExtractor`)**:
   - Replaces hardcoded dictionaries with a **Zero-Shot Subword N-Gram, Stemming & Synonym Normalization Operator**.
   - Supports cross-lingual claim comparison (e.g., Chinese manuscript claim vs English abstract).
   - SciFact Gold Standard Benchmark Performance:
     - **Contradiction Interception (`CONTRADICTS`)**: Precision = **1.00 (100%)**, Recall = 0.75, **F1-Score = 0.86**
     - **Support Verification (`SUPPORTS`)**: Precision = 0.75, **F1-Score = 0.67**
     - **Overall Classification Accuracy**: **75.0%**
2. **Sentence-Level Context Locator (`find_best_matching_sentence`)**:
   - Automatically splits abstracts and extracts the single best-matching sentence corresponding to the user's claim.
3. **Local Reference Paper Extractor (`--refs-dir` / `-r`)**:
   - Accepts user-supplied directories of reference PDFs, DOCX, or TXT files.
   - When online APIs lack abstract text, the system extracts abstracts directly from local reference papers.
4. **Proxy & Rate Limit Resilience (`trust_env`)**:
   - Includes `trust_env=True` and OpenAlex Polite Pool headers to eliminate SSL timeouts and HTTP 429 rate limit issues.
5. **Modern Glassmorphism UI Reports**:
   - Renders styled HTML reports with summary grids, badges, and highlighted context alignment.

---

## 📦 Installation & Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/mcp-academic-guardrail.git
cd mcp-academic-guardrail

# 2. Editable install
pip install -e .
```

---

## 🚀 Quick Start

### 1. CLI Usage

Audit a paper manuscript and open the HTML report:
```bash
academic-guardrail audit manuscript.docx -b -o report.html
```

Audit with a local directory of reference papers (PDF/DOCX/TXT):
```bash
academic-guardrail audit manuscript.docx -r ./references -b -o report.html
```

Verify a single DOI or citation:
```bash
academic-guardrail verify "10.1109/CVPR.2016.90"
```

Run the SciFact NLI Claim Alignment Benchmark:
```bash
python benchmark_claims.py
```

### 2. MCP Server Setup (Antigravity / Cursor / Claude Desktop)

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

## 📄 License

[MIT License](LICENSE)
