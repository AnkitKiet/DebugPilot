# DebugPilot 🚀 (git-bisect-fix)

DebugPilot is an automated self-healing framework designed to pinpoint, diagnose, and repair git regressions. It leverages a zero-LLM-cost programmatic `git bisect` combined with a multi-agent **LangGraph** orchestration system to analyze and repair bugs on auto-generated git branches.

---

## 📂 Project Structure

```
Bisect/
├── git-bisect-fix/         # Automated RCA & Fix Agent CLI
│   ├── agent/              # LangGraph Agents (RCA & Fix)
│   ├── bisect/             # Git Bisection Runner & HTTP Oracle
│   └── tests/              # Test suite (61 unit tests)
└── bisect-test-api/        # FastAPI Test Harness API
    ├── main.py             # Active server file with middleware regression
    └── seed_commits.sh     # Seeding script for git regression history
```

---

## ✨ Features

- **Automated Git Bisection:** Zero-LLM-cost search utilizing python's git bindings to narrow down the regression commit.
- **Dynamic Response Oracle:** A client oracle capable of evaluating response status code, body substrings, and case-insensitive HTTP headers (e.g., verifying compliance/trace headers like `X-Trace-Id`).
- **Phase 2 Root Cause Analysis (RCA):** LangGraph agent fetching transitive imports and git diffs to generate formatted Markdown reports.
- **Human Gate Prompt:** Terminal prompt requiring human approval before initiating fixing actions.
- **Phase 3 Self-Healing Fix Agent:** Plans, applies, verifies (against target oracle), and commits the correction on a new `fix/` branch.

---

## 🛠️ Getting Started

### 1. Setup Environment
Navigate to the `git-bisect-fix` folder, copy `.env.example`, and fill in your Gemini API key:
```bash
cd git-bisect-fix
cp .env.example .env
# Edit .env and supply your GOOGLE_API_KEY
```

### 2. Configure the Test Harness API
Initialize the FastAPI repository with its seeded git history and dependencies:
```bash
cd ../bisect-test-api
pip install -r requirements.txt
rm -rf .git && rm -f README.md  # Ensure a clean slate
bash seed_commits.sh
```
*Take note of the printed `GOOD_COMMIT` and `BAD_COMMIT` hashes from the command output.*

### 3. Start the API Server
Start the Uvicorn development server:
```bash
../git-bisect-fix/.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🚀 Usage Guide

Open another terminal window, navigate to `git-bisect-fix`, and execute `cli.sh` using the good/bad hashes:

```bash
cd git-bisect-fix
bash cli.sh \
  --good <GOOD_COMMIT_HASH> \
  --bad <BAD_COMMIT_HASH> \
  --curl 'curl -s -X POST http://localhost:8000/api/order -H "Content-Type: application/json" -d "{\"product_id\":\"SKU-001\",\"quantity\":2,\"user_id\":\"user-123\"}"' \
  --repo ../bisect-test-api
```

### Flow Execution:
1. **Phase 1 (Bisect):** Binary searches commits and stops on the first commit returning `500` status (due to a missing `X-Trace-Id` header).
2. **Phase 2 (RCA):** The agent identifies that `response.headers["X-Trace-Id"]` was commented out in `main.py` middleware.
3. **Human Gate:** Prompts you to apply the fix: `Proceed to automated fix on new branch? [y/N]:`
4. **Phase 3 (Fix Agent):** Restores the commented-out statement, verifies that headers are present (returning HTTP `200`), and commits the fix to branch `fix/bisect-<commit_hash>`.

---

## 🧪 Running Tests

A complete suite of 61 unit tests verifies schemas, tools, graphs, bisection, and oracle behavior:
```bash
cd git-bisect-fix
.venv/bin/pytest
```
