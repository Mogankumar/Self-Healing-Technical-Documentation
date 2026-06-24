#  Self-Healing Technical Documentation

A GitHub Action that monitors your codebase, detects when code changes make documentation inaccurate, and automatically opens a fix PR with corrected docs  or flags the discrepancy for human review.

> **Built as a portfolio project demonstrating production-grade AI engineering:** embeddings, retrieval, LLM generation, and CI/CD deployment in a system other engineers would actually want to install.

---

## The Problem

Every engineering team has this problem. Code evolves continuously through PRs and commits. Documentation is updated manually and infrequently. Over time, a gap forms between what the code *does* and what the docs *say it does*. Function signatures change, default values shift, new parameters appear  and the docs quietly become lies.

This project automates the detection and repair of that gap.

---

## Demo

**What happens when you open a PR that changes a function:**

1. The Action triggers automatically
2. It detects which functions changed
3. It finds the documentation sections linked to those functions
4. It asks an LLM: *"Is this doc still accurate given the code change?"*
5. If stale: it rewrites only the inaccurate parts, validates the fix, and opens a PR
6. If uncertain: it posts a review comment flagging the section for human review

---

## Example

**Code change (PR #1):**
```python
# Before
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour

# After
TOKEN_EXPIRY_SECONDS = 7200  # 2 hours
```

**Auto-generated fix PR (PR #2), opened by the Action:**

> **docs: fix stale section — Authentication > Token Generation**
>
> `TOKEN_EXPIRY_SECONDS` in `src/auth.py` was modified in PR #1.
>
> **Why the docs were stale:** The documentation states tokens are valid for 1 hour (3600 seconds), but the code now sets TOKEN_EXPIRY_SECONDS to 7200 seconds.
>
> **Confidence:** high · **Validation:** passed

---

## How It Works

The system runs in five phases:

### Phase 1 — Code-to-Docs Index
Parses every Python file into semantic chunks (functions, classes) using the AST. Parses every Markdown file into sections by heading. Links them two ways:
- **Lexical pass** — if a doc section mentions a function name, link them
- **Semantic pass** — compute embeddings for both, link pairs with cosine similarity > 0.75

Persists the graph as `docs-index.json` in your repo.

### Phase 2 — Change Detection
On every PR, parses the git diff to identify which functions, classes, and constants changed. Filters out noise (comment-only changes, test files, whitespace). Queries the index to find which doc sections are linked to changed code — these are the *suspects*.

### Phase 3 — LLM Verification
For each suspect section, sends the LLM the old code, the new code, and the doc section content. Asks: *"Is this documentation still accurate?"* Returns a structured verdict (`accurate` / `stale` / `uncertain`) with a specific diagnosis. This filters out false positives.

### Phase 4 — Repair Engine
For confirmed stale sections, runs two LLM passes:
- **Pass 1 (Repair):** Rewrites only the inaccurate parts, preserving style and structure
- **Pass 2 (Validation):** A second LLM call validates the correction before trusting it

Assigns a confidence level. High confidence → auto-fix PR. Low confidence → human review comment.

### Phase 5 — GitHub Integration
- **High confidence:** Creates a branch, commits the corrected doc, opens a PR with full traceability
- **Low confidence:** Posts a comment on the original PR with the diagnosis and a link to the affected section
- **Every run:** Posts a summary comment listing all sections checked, fixed, and flagged

---

## Tech Stack

| Component | Tool | Why |
|---|---|---|
| Language | Python 3.11+ | |
| Code parsing | `ast` (stdlib) | Accurate, handles edge cases regex can't |
| Doc parsing | Custom heading splitter | Preserves breadcrumb paths |
| Embeddings | `sentence-transformers` | Free, local, no API calls |
| Vector similarity | `scikit-learn` cosine similarity | Simple, no server needed |
| Index storage | JSON file in repo | Version-controlled, zero infrastructure |
| LLM | Groq — Llama 3.3 70B | Free tier, fast, strong reasoning |
| GitHub API | `PyGithub` | PR creation and comment posting |
| CI/CD | GitHub Actions | Native integration |

---

## Installation

### 1. Add the Action to your workflow

Create `.github/workflows/doc-check.yml`:

```yaml
name: Self-Healing Docs

on:
  pull_request:
    paths:
      - '**.py'

jobs:
  doc-check:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install -r requirements.txt

      - name: Build docs index
        run: python -m doc_checker.indexer .

      - name: Run doc check
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          BASE_BRANCH: ${{ github.event.pull_request.base.sha }}
          REPO_ROOT: .
          INDEX_PATH: docs-index.json
        run: python -m doc_checker.main
```

### 2. Add secrets to your repository

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Where to get it |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — free |
| `GH_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens (needs `repo` scope) |

### 3. That's it

Open a PR that changes a Python file. The Action will run automatically.

---

## Local Development

```bash
# Clone and set up
git clone https://github.com/yourusername/self-heal-technical-doc
cd self-heal-technical-doc
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add your GROQ_API_KEY to .env

# Build the index
python -m doc_checker.indexer .

# Run the pipeline locally
REPO_ROOT=. INDEX_PATH=docs-index.json BASE_BRANCH=HEAD~1 python -m doc_checker.main
```

---

## Project Structure

```
self-heal-technical-doc/
├── .github/
│   └── workflows/
│       └── doc-check.yml       # GitHub Actions workflow
├── doc_checker/
│   ├── parser.py               # AST-based code parser + markdown parser
│   ├── indexer.py              # Embedding + graph builder
│   ├── detector.py             # Git diff parser + change detection
│   ├── verifier.py             # LLM staleness verification
│   ├── repairer.py             # LLM doc repair + validation
│   ├── github_integration.py   # PR creation + comment posting
│   └── main.py                 # Pipeline orchestration
├── docs-index.json             # Persisted code-to-docs graph
└── requirements.txt
```

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | required | Groq API key for LLM calls |
| `GH_TOKEN` | required in CI | GitHub token for PR creation |
| `REPO_ROOT` | `.` | Root directory to scan |
| `INDEX_PATH` | `docs-index.json` | Path to the index file |
| `BASE_BRANCH` | `HEAD~1` | Git ref to diff against |
| `PR_NUMBER` | — | PR number (set automatically in CI) |

---

## Accuracy

Tested against a suite of deliberate breaking changes:

| Change type | Detected | Correctly diagnosed | Fix quality |
|---|---|---|---|
| Changed constant value | ✅ | ✅ | ✅ |
| New function parameter | ✅ | ✅ | ✅ |
| Changed default value | ✅ | ✅ | ✅ |
| Renamed role/enum value | ✅ | ✅ | ✅ |
| Comment-only change | ➖ skipped | — | — |
| Test file change | ➖ skipped | — | — |

---

## Design Decisions

**Why a JSON graph instead of a vector database?**
The index is version-controlled alongside the code. Diffs are visible in PRs. No server to run or manage. For a single-repo tool this is always the right call.

**Why two LLM passes instead of one?**
Separating verification (judgment) from repair (generation) produces dramatically more trustworthy output. A single pass that does both oscillates between the two tasks and performs worse at each.

**Why Groq + Llama instead of GPT-4?**
The free tier on Groq (14,400 requests/day) is sufficient for this use case. The pipeline makes 2-3 LLM calls per suspect section, so a typical PR uses under 20 calls. Swapping in GPT-4 or Claude requires changing one line.

**Why local embeddings instead of an embeddings API?**
`sentence-transformers` runs entirely locally — no API calls, no cost, no rate limits. The `all-MiniLM-L6-v2` model is fast and produces high-quality embeddings for this use case.

---

## License

MIT
