# Changelog

All notable changes to the **Academic Guardrail Agent** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added arXiv URL (`https://arxiv.org/abs/...`) direct manuscript & citation parser in `ManuscriptParser`.
- Added GitHub Actions CI/CD workflow (`.github/workflows/ci.yml`) for multi-Python version testing.
- Added `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
- Added offline-capable system font fallback in HTML report generator (`reporter.py`).

## [0.1.0] - 2026-08-05

### Added
- Hybrid Multilingual Claim Alignment Engine (`claim_eval.py`) with 3D weighted feature matching & polarity antonym graph.
- Local Reference Paper Extractor (`ref_store.py`) supporting full-text PDF, DOCX, and TXT scanning.
- Glassmorphism Dark Mode HTML Report Generator with interactive risk filter tabs and live search bar.
- MCP Server interface (`mcp_server.py`) and CLI commands (`academic-guardrail audit` / `verify`).
- SciFact benchmark suites (`benchmark_claims.py`, `benchmark_large_scifact.py`, `benchmark_large_submodules.py`).
