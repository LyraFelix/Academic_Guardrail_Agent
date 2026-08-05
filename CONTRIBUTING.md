# Contributing to Academic Guardrail Agent

Thank you for your interest in contributing to **Academic Guardrail Agent**! We welcome contributions from developers, researchers, and open-source enthusiasts.

---

## 🛠️ Getting Started

### 1. Fork & Clone
```bash
git clone https://github.com/your-username/Academic_Guardrail_Agent.git
cd Academic_Guardrail_Agent
```

### 2. Set Up Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

### 3. Run Test Suite
```bash
pytest -v
```

---

## 📝 Pull Request Guidelines

1. **Create a Feature Branch**: `git checkout -b feat/your-feature-name`
2. **Write Unit Tests**: Ensure new features are covered under `tests/`.
3. **Check Code Quality**: Ensure `pytest` passes cleanly.
4. **Submit PR**: Open a Pull Request against the `master` branch with a clear title and description.

---

## 🐞 Reporting Issues

If you encounter bugs, false positives in claim alignment, or API rate limit issues, please open an Issue on GitHub with:
- System OS and Python version
- Steps to reproduce
- Sample citation / DOI or manuscript snippet (anonymized)
