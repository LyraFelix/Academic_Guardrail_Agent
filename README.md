# 🛡️ Academic Guardrail Agent (`mcp-academic-guardrail`)

<p center="align">
  <b>Citation Verification & Evidence Context Provisioning MCP Server & CLI for AI Coding Agents</b><br>
  An open-source academic infrastructure providing <b>citation metadata validation, retraction alerts, multilingual database lookups, local reference extraction, and sentence-level evidence context provisioning</b>.
</p>

<p align="center">
  <b>English</b> | <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.0.0-green.svg" alt="MCP Spec 1.0.0">
  <img src="https://img.shields.io/badge/SciFact-Host--Agent%20Eval-brightgreen.svg" alt="SciFact Host-Agent Eval">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License MIT">
</p>

---

## 🖼️ Demo Preview

### 1. Browser UI Report Preview
Auto-launches your system browser to render a modern glassmorphism HTML report with 5-metric summary cards, badges, and sentence-level context alignment:

#### View 1: Header & 5-Metric Dashboard Summary View
![HTML Report Header & Dashboard View](docs/assets/report_header_preview.png)

#### View 2: Citation Audit & Claim Consistency Cards View
![HTML Report Cards View](docs/assets/report_cards_preview.png)

#### View 3: Full Citation Audit Table View
![HTML Report Table View](docs/assets/report_table_preview.png)

### 2. Interactive CLI Audit (`--open` / `-b`)
Run the audit command in your terminal to inspect claims and citations across public APIs and local reference files:

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
│        │                            │          │ [Ref Sentence: "In..."]    │
│ cit_3  │ [3] Yao et al.             │ PASS     │ 🟢 Matched Local File      │
│        │ AI & Firm Productivity...  │          │ (Yao_Productivity.pdf).    │
│        │                            │          │ [Ref Sentence: "AI..."]    │
└────────┴────────────────────────────┴──────────┴────────────────────────────┘

Summary: Total: 16 | 🟢 PASS: 10 | 🔵 NOTICE: 6 | 🟡 WARNING: 0 | 🔴 DANGER: 0
Report output to: report.html
🌐 Auto-launching default system browser...
```

---

## 🌟 Key Features

1. **Multilingual Sentence-Level Evidence Provisioning Architecture (`ClaimEvaluator` / MCP Server)**:
   - **Zero-Setup Cross-Lingual Evidence Extraction**: Directly extracts manuscript claims and pinpoints the exact matching sentence from English reference abstracts.
   - **Disclosed Evaluation Protocol on Official SciFact Dataset**:
     - **Host-Agent Evaluation (MCP + Host LLM Mode)** (evaluated with **Antigravity Agent (Gemini 3.6 Flash)** as host model, run `python evaluate_llm_scifact_results.py`):
       - **Official SciFact Dev Set ($N=323$)**:
         - **Support Verification (`SUPPORTS` Class)**: Precision = 1.00, Recall = 0.95, **F1-Score = 0.97**
         - **Contradiction Interception (`CONTRADICTS` Class)**: Precision = 0.99, Recall = 0.97, **F1-Score = 0.98**
         - **Overall Joint Accuracy**: **97.2%** (Macro F1 = 0.98)
     - **Standalone Python Engine (Zero-LLM Core Mode)** (run `python benchmark_scifact_official.py`, deterministic no-model CPU mode):
       - **Official SciFact Dev Set ($N=323$)**: Overall Accuracy = **50.5%** (Macro F1 = 0.47)
2. **Two-Stage Decoupled Verification & Entity Resolution Benchmark**:
   - **Stage 1: Reference Entity Resolution (`ReferenceResolver`)**: Normalizes DOIs (`normalize_doi`), performs cross-provider candidate deduplication, and calculates 5-score breakdown metadata (`resolution_metadata` containing `title_score`, `author_score`, `year_score`, `venue_score`, `rank_margin`).
     - **Resolution Benchmark (`python benchmark_reference_resolution.py`)**: Achieves **100.00% Top-1 Accuracy**, **1.0000 MRR**, **100.00% Recall@5**, and **100.00% Abstention Accuracy** on ambiguous/hallucinated citations.
   - **Stage 2: Clause-Level Alignment & Polarity Conflict Detection (`ClaimEvaluator`)**: Evaluates claims into calibrated objective tiers (`SUPPORTED`, `PARTIAL`, `NEUTRAL`, `CONTRADICTED`, `UNVERIFIED`) using localized sub-clause segmentation (`split_clauses`) to eliminate false contradiction alerts on complex compound sentences.
3. **Sentence-Level Context Locator & Multi-Format Parsing (`Sentence-Level Locator & arXiv Parser`)**:
   - Automatically splits abstracts/full-text into sentences and highlights the exact single sentence in the reference paper that best corresponds to the manuscript claim.
   - Out-of-the-box support for **DOCX, PDF (multi-page full-text), Markdown (.md), LaTeX (.tex), BibTeX (.bib), and direct arXiv URLs (`https://arxiv.org/abs/1706.03762`)**.
4. **Performance Benchmarks**:
   - **Per-Claim Decision Latency**: Memory-based hybrid claim matching takes **~0.36 ms** per claim.
   - **50-Citation Audit Execution Time**: Concurrent batch querying via `asyncio.gather` completes a full 50-citation manuscript audit in **< 1.5 seconds**.
5. **Local Reference Paper Extractor (`--refs-dir` / `-r`)**:
   - Accepts user-supplied directories of reference PDFs, DOCX, or TXT files.
   - Scans multi-page PDF full text to perform sentence-level claim alignment when online APIs lack abstracts.
6. **Air-Gapped HTML Report & Tri-State Verification Safety**:
   - Disables false-positive core journal endorsements by returning a neutral **Tri-State (`matched = None`, `JOURNAL_MATCHED_ARTICLE_UNVERIFIED`)** when only journal names match without an verified article record.
   - The generated HTML report contains zero external CDN dependencies, using system font fallbacks to render and filter perfectly in 100% air-gapped offline environments.
   - Includes `trust_env=True` and OpenAlex Polite Pool headers to eliminate SSL timeouts and HTTP 429 rate limit issues across international API calls.

---

## 📦 Installation & Setup

### 1. Installation Modes (Core vs Full)

Academic Guardrail offers two distinct installation footprints based on your environment requirements:

#### ⚡ Core Mode (Default - Recommended)
Designed for lightweight CLI usage and AI Coding Agent MCP integrations with zero heavy ML dependencies:
```bash
pip install academic-guardrail
```
* **Footprint**: **< 35 MB**
* **Dependencies**: `httpx`, `pydantic`, `pypdf`, `python-docx`, `mcp` (Zero PyTorch / HuggingFace lock-in).
* **Best For**: Fast CI/CD, instant CLI auditing, zero cold-start delay (<50ms), and Host Agent (Cursor/Antigravity) LLM context-provisioning.

#### 🧠 Full Mode (Optional Multilingual Vector Embeddings)
Installs heavy pretrained vector Transformer models for offline, standalone vector similarity scoring without an external Host LLM:
```bash
pip install "academic-guardrail[full]"
```
* **Footprint**: **~ 3.0 GB** (Includes PyTorch & `sentence-transformers`).
* **Feature**: Automatically loads `paraphrase-multilingual-MiniLM-L12-v2` for offline CPU vector embeddings.

---

### 2. Install from Source

```bash
# 1. Clone the repository
git clone https://github.com/LyraFelix/Academic_Guardrail_Agent.git
cd Academic_Guardrail_Agent

# 2. Editable install (Core Mode)
pip install -e .

# Or Editable install with Full Vector Support
pip install -e ".[full]"
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

Configure your email for Crossref / OpenAlex Polite Pool rate-limit boosts:
```bash
# Option A: Command-line flag
academic-guardrail audit manuscript.docx --email "researcher@university.edu" -b

# Option B: Environment variable
export ACADEMIC_GUARDRAIL_EMAIL="researcher@university.edu"
```

---

## 📊 Benchmark & Baseline Comparison

### 1. Benchmark Datasets & Scope Disclosures
For **100% transparency and academic rigor**, we distinguish between benchmark datasets:
- **Official SciFact Dev Set ($N=323$)**: Used for official full-scale dataset evaluation (`benchmark_scifact_official.py` & `evaluate_llm_scifact_results.py`).
- **Local Micro Baseline Subset ($N=12$)**: Used for quick local component execution latency and baseline comparisons (`benchmark_baselines.py`).

All benchmarks are executed under a standard consumer CPU environment:
- **CPU**: Intel Core / AMD Ryzen (16 vCPU)
- **RAM**: 16 GB DDR4/DDR5
- **GPU VRAM**: **None (Pure CPU, 0 MB VRAM)**

### 2. Local Component Baseline Comparison ($N=12$ Subset)

We evaluated `Academic Guardrail` against standard lexical baseline methods on the local micro subset:

| Method | SUPPORTS F1 | CONTRADICTS F1 | Latency | GPU VRAM / Weights |
|---|:---:|:---:|:---:|:---:|
| **TF-IDF Cosine** | 0.67 | 0.00 | 0.32 ms | 0 MB / Pure CPU |
| **BM25 Score** | 0.67 | 0.00 | 0.12 ms | 0 MB / Pure CPU |
| **SequenceMatcher (Ratio)** | 0.59 | 0.00 | 1.35 ms | 0 MB / Pure CPU |
| **Academic Guardrail (Ours)** | **0.75** | **1.00** | **5.44 ms** | **0 MB / Pure CPU** |

> Note: `Academic Guardrail` operates as a lightweight, CPU-first Core Mode engine for instant MCP context provisioning. High-level semantic reasoning is jointly performed with host AI agents (Cursor / Antigravity / Windsurf).

> Why use a lightweight `Hybrid Multilingual Claim Alignment` heuristic algorithm over heavy pretrained NLI models (BGE-M3, DeBERTa-v3-NLI, Llama-3)? Neural NLI models require 2GB–8GB GPU VRAM and 50–500ms latency, which violates our core goal of a **zero-dependency, instant, CPU-only local CLI & MCP tool**.

Run the full baseline comparison script from the project root:
```bash
python benchmark_baselines.py
```

---

## 🧪 Testing & Verification Suite

The repository contains 74 automated unit tests covering semantic alignment, polarity contradiction detection, multilingual matching, reference resolution, offline Retraction Watch database, DOI/retraction verification, and file parsers:

```
tests/
├── test_benchmark_ref_resolution.py  # Reference resolution & entity disambiguation tests
├── test_claim_alignment.py           # SUPPORTS / CONTRADICTS / NEUTRAL semantic alignment tests
├── test_claim_eval.py                # Feature extractor, clause isolator & sentence locator tests
├── test_doi_checker.py               # DOI resolution & Retraction Watch offline index tests
├── test_multilingual.py              # Chinese, English, & cross-lingual claim matching tests
├── test_parser.py                    # GB/T 7714 citation parsing tests
├── test_pdf_parser.py                # DOCX / PDF / TXT / Markdown & arXiv URL parser tests
└── test_providers.py                 # OpenAlex & Crossref async lookup tests
```

Run the complete test suite:
```bash
pytest tests/ -v
```

---

## 🚀 Usage Guide

### 1. Command Line Interface (CLI)

Audit a manuscript and launch the interactive HTML report in your browser:
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

