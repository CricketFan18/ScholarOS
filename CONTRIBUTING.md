# Contributing to ScholarOS

First off, thank you for considering contributing to ScholarOS.  
This project exists because of community support, and we welcome contributions of all kinds — new study modes, bug fixes, documentation, subject packs, and ideas.

Please read this guide before submitting contributions.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Understanding the Architecture](#understanding-the-architecture)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Branching Strategy](#branching-strategy)
- [Submitting Issues](#submitting-issues)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Coding Standards](#coding-standards)
- [Commit Message Format](#commit-message-format)
- [Testing](#testing)
- [Documentation](#documentation)
- [Review Process](#review-process)
- [Your First Contribution](#your-first-contribution)

---

## Code of Conduct

This project follows a Code of Conduct to ensure a welcoming and respectful environment.

Please read the full policy here: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

By participating in this project you agree to follow its guidelines.

---

## Ways to Contribute

You can contribute in several ways:

- Reporting bugs
- Suggesting new study modes
- Building new study modes
- Fixing bugs
- Improving documentation
- Writing or improving tests
- Contributing subject packs (domain-specific prompt templates)
- Improving the frontend UI
- Reviewing pull requests

Even small improvements help.

---

## Understanding the Architecture

ScholarOS is divided into three strictly isolated layers.

```
core/      Handles llama-cpp-python inference, PDF chunking, ChromaDB.
           Locked down. Do not modify unless fixing a specific bug.

ui/        FastAPI server (router only) + decoupled index.html, style.css, app.js.
           Great for frontend contributors. No core knowledge needed.

modes/     THE CONTRIBUTION ZONE.
           Every study mode is a standalone Python class inheriting from BaseMode.
           Add a new mode by creating one file here. Nothing else needs to change.
```

**The golden rule:** if you are adding a new study mode, you should only ever need to create one new file inside `modes/`. If you find yourself editing `core/`, stop and ask in the issue thread first.

---

## Getting Started

1. Fork the repository

2. Clone your fork

```bash
git clone https://github.com/YOUR_USERNAME/ScholarOS.git
```

3. Navigate to the project

```bash
cd ScholarOS
```

4. Add the upstream repository

```bash
git remote add upstream https://github.com/CricketFan18/ScholarOS.git
```

5. Install dependencies

```bash
# Linux / macOS
make install

# Windows
scripts\setup.bat
```

The Windows script handles pre-compiled `llama-cpp-python` wheel installation to bypass C++ compilation errors on machines without build tools.

---

## Development Setup

Recommended environment: Python 3.10+, 4 GB RAM minimum.

Download the default model (Phi-3 Mini, ~2.2 GB):

```bash
make fetch-model
```

For constrained devices (2–3 GB RAM), set the fallback model in `.env` first:

```bash
MODEL_NAME=qwen2.5-1.5b
```

Then run:

```bash
make fetch-model
```

Activate the virtual environment:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Run the project locally:

```bash
make run
```

The web interface opens at `http://localhost:8080`.

---

## Branching Strategy

We follow a simple branching model.

**main**  
Stable production code. All PRs target this branch.

**Feature branches**

```
feature/<feature-name>
```

Examples:

```
feature/socratic-debate-mode
feature/subject-pack-registry
```

**Bugfix branches**

```
bugfix/<issue-name>
```

Examples:

```
bugfix/pdf-unicode-crash
bugfix/flashcard-empty-output
```

**Other branch types**

```
docs/<description>
subject-pack/<pack-name>
refactor/<description>
chore/<description>
```

Use lowercase and hyphens only. No spaces, no uppercase.

---

## Submitting Issues

Before opening a new issue:

1. Check [existing issues](https://github.com/CricketFan18/ScholarOS/issues) to avoid duplicates.
2. Make sure you are on the latest version by pulling from `main`.

**Bug reports** — use the [Bug Report template](https://github.com/CricketFan18/ScholarOS/issues/new?template=bug_report.md).

Include the following details:

- Clear title
- Description of the problem
- Steps to reproduce
- Expected behaviour
- Actual behaviour (full error message if available)
- Environment details

Example environment block:

```
OS: Ubuntu 22.04
Python: 3.11
Model: phi3-mini
Available RAM: 8 GB
```

**Feature / mode proposals** — use the [New Mode Proposal template](https://github.com/CricketFan18/ScholarOS/issues/new?template=new_mode.md).

Include:

- What the mode does (one sentence)
- Who benefits from it
- A rough prompt template using `{context}` and `{query}`
- An example of what the output should look like

---

## Pull Request Guidelines

Before submitting a pull request:

1. Fork the repository
2. Create a correctly named feature or bugfix branch
3. Make your changes
4. Write tests if adding new functionality
5. Ensure all tests pass: `pytest tests/ -v`
6. Run the linter: `ruff check .`
7. Run the formatter: `black .`
8. Update `CHANGELOG.md` under `[Unreleased]`
9. Open a pull request targeting `main`

PR titles should be descriptive.

Examples:

```
Add Socratic debate study mode
Fix PDF chunking crash on multi-column academic papers
Improve flashcard output formatting
```

Each pull request should focus on **one change only**.

Link the related issue in your PR description using `Closes #<issue-number>`.

---

## Coding Standards

**Python style**

We follow PEP 8. Use the formatter before committing:

```bash
black .
```

**Linting**

```bash
ruff check .
```

ruff replaces flake8, isort, and pyupgrade in a single fast tool.

**pre-commit hooks**

Both tools run automatically on `git commit` after `make install`. If your code fails, the commit is blocked. Fix the issue and commit again.

```bash
# Run manually on all files:
pre-commit run --all-files
```

**Typing**

Use type hints on all function signatures.

Example:

```python
def extract_text(pdf_path: str) -> list[str]:
    ...
```

**Docstrings**

Every class and public method needs at least a one-sentence docstring.

**No `print()` statements**

Use Python's `logging` module instead. `print()` in production code will be flagged in review.

---

## Commit Message Format

Use the [Conventional Commits](https://www.conventionalcommits.org) specification.

Format:

```
type(scope): short description
```

Examples:

```
feat(modes): add socratic debate mode
fix(core): handle unicode characters in PDF chunk extraction
docs(contributing): add Windows setup troubleshooting steps
test(modes): add unit tests for flashcard output validation
chore(deps): update llama-cpp-python to 0.2.90
```

Commit types:

```
feat      New feature or study mode
fix       Bug fix
docs      Documentation changes only
refactor  Code restructuring, no behaviour change
test      Adding or fixing tests
chore     Build process, dependency updates
style     Formatting only, no logic change
```

Scopes match the directory name: `core`, `modes`, `ui`, `tests`, `scripts`, `docs`.

Rules:

- Subject line 72 characters or fewer
- Use the imperative mood: "add feature" not "added feature"
- No period at the end of the subject line
- Add `Closes #123` in the footer if the commit resolves an issue

---

## Testing

Run the full test suite before submitting any PR:

```bash
pytest tests/ -v
```

If you add a new study mode, include a corresponding test file:

```
tests/
    test_ingestion.py
    test_modes.py
    test_your_mode_name.py    ← required for new modes
```

At minimum, test that:

- The mode initialises without errors
- `get_prompt_template()` returns a string containing `{context}` and `{query}`
- `format_output()` returns a string given a string input

See `tests/test_modes.py` for the established pattern.

---

## Documentation

Documentation is extremely valuable.

If your PR introduces a new study mode, new behaviour, or configuration changes, please update:

- `README.md` — add the mode to the Features section
- `ROADMAP.md` — mark the item as completed if it was planned
- `CHANGELOG.md` — add an entry under `[Unreleased]`
- `docs/` — add architecture notes if you changed data flow

---

## Review Process

After submitting a PR:

1. CI runs automatically — your PR must be green before review begins
2. A maintainer will give first feedback within **72 hours**
3. Changes may be requested — address them in new commits, do not force-push
4. Once approved and all checks pass, the PR will be merged

If you have not heard back within 5 days, leave a comment on the PR. Do not open a duplicate.

Please be patient during review. We are a small team.

---

## Your First Contribution

The fastest path to a merged contribution is adding a new study mode.

1. Browse [issues labelled `good first issue`](https://github.com/CricketFan18/ScholarOS/issues?q=label%3A%22good+first+issue%22)
2. Leave a comment to claim the issue — a maintainer will assign it within 24 hours
3. Set up your dev environment using the steps above
4. Read `modes/qa_mode.py` — it shows exactly what a mode looks like in practice
5. Create `modes/your_mode_name.py` and inherit from `BaseMode`:

```python
from modes.base_mode import BaseMode

class YourModeName(BaseMode):
    """One sentence describing what this mode does."""

    def get_prompt_template(self) -> str:
        return """You are a study assistant. Use only the context below.

Context:
{context}

Student: {query}

Your response:"""

    def format_output(self, response: str) -> str:
        return response
```

6. Create `tests/test_your_mode_name.py`
7. Run `pytest tests/ -v`, `ruff check .`, `black .`
8. Commit using the Conventional Commits format
9. Open a PR targeting `main` and link the issue

You do not need to understand `core/` or `ui/` to make a meaningful contribution.

---

*ScholarOS is built by Samira Khan & Vivek Kesarwani — KIIT University.*  
*A team of 2 CS undergraduates with a lot of ideas to better the world in small ways.*