# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | ✅ Active support  |

## Reporting a Vulnerability

We take security issues seriously. If you discover a vulnerability in **Academic Guardrail Agent**, please **do not open a public GitHub issue**.

Instead, follow responsible disclosure:

### How to Report

1. **Email**: Send a detailed report to the repository maintainer via the email listed on the [GitHub profile](https://github.com/LyraFelix).
2. **Include in your report**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested mitigations (optional)

### What to Expect

- **Acknowledgement**: Within **5 business days** of receiving your report.
- **Assessment**: We will evaluate the severity and scope.
- **Fix & Disclosure**: We aim to release a patch within **30 days** for confirmed vulnerabilities. We will coordinate with you on the public disclosure timeline.

### Scope

Issues in scope include:
- Remote code execution via malformed document inputs (PDF/DOCX parsing)
- Path traversal in `--refs-dir` or `file_path` arguments
- Credential or email leakage via API request headers
- Supply chain vulnerabilities in dependencies

Issues **out of scope**:
- Rate-limiting or availability of third-party APIs (Crossref, OpenAlex, Semantic Scholar)
- Academic misjudgments or false-positive citation results (these are feature limitations, not security vulnerabilities)

---

Thank you for helping keep Academic Guardrail Agent secure.
