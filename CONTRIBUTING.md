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
backend/core/      Handles llama-cpp-python inference, PDF chunking, ChromaDB.
                   Locked down. Do not modify unless fixing a specific bug.

backend/api/       FastAPI server — routing only, no business logic.
frontend/          React + Vite single-page app — all UI code lives here.
                   Great for frontend contributors. No core knowledge needed.

backend/modes/     THE CONTRIBUTION ZONE.
                   Every study mode is a standalone Python class inheriting from BaseMode.
                   Implement name, get_system_prompt(), and run(). One file. Nothing else needs to change.
```

**The golden rule:** if you are adding a new study mode, you should only ever need to create one new file inside `backend/modes/`. If you find yourself editing `backend/core/`, stop and ask in the issue thread first.

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
# Linux / macOS / WSL
python setup.py

# Windows
backend\scripts\setup.bat
```

The Windows script handles pre-compiled `llama-cpp-python` wheel installation to bypass C++ compilation errors on machines without build tools.

---

## Development Setup

Recommended environment: Python 3.10+, Node.js 18+, 4 GB RAM minimum.

Download the default model (Phi-3 Mini, ~2.3 GB):

```bash
make fetch-model
```

For constrained devices (2–3 GB RAM), use the fallback model instead:

```bash
make fetch-model-fallback
```

Activate the virtual environment:

```bash
# Linux / macOS / WSL
source venv/bin/activate

# Windows
venv\Scripts\activate
```

Run the project locally:

```bash
python start.py
```

The backend starts on `http://localhost:8000` and the frontend on `http://localhost:5173`.  
On WSL, `start.py` auto-detects the correct network IP — open the URL it prints rather than `localhost`.

**Wait for this line before using the app:**
```
[Startup] ✓ LLM ready. ScholarOS is fully loaded and ready!
```

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
Model: Phi-3-mini-4k-instruct-q4.gguf
Available RAM: 8 GB
WSL: yes / no
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
5. Ensure all tests pass: `make test`
6. Run the formatter: `make lint`
7. Update `CHANGELOG.md` under `[Unreleased]`
8. Open a pull request targeting `main`

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

We follow PEP 8. Run the formatter and import sorter before committing:

```bash
make lint
```

This runs `black .` and `isort .` across the backend.

**Type hints**

Use type hints on all function signatures.

Example:

```python
def extract_text(pdf_path: str) -> list[str]:
    ...
```

**Docstrings**

Every class and public method needs at least a one-sentence docstring.

**Print statements**

ScholarOS uses `print()` for startup and ingest progress messages — this is intentional so users running from a terminal can see exactly what the server is doing. New code should follow the same pattern: print clearly-labelled progress messages for operations that take more than a second, and stay silent for fast operations.

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
docs(contributing): add WSL setup troubleshooting steps
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

Scopes match the directory name: `core`, `modes`, `api`, `frontend`, `tests`, `scripts`, `docs`.

Rules:

- Subject line 72 characters or fewer
- Use the imperative mood: "add feature" not "added feature"
- No period at the end of the subject line
- Add `Closes #123` in the footer if the commit resolves an issue

---

## Testing

Run the full test suite before submitting any PR:

```bash
make test
```

If you add a new study mode, include a corresponding test file:

```
backend/tests/
    test_ingestion.py
    test_modes.py
    test_your_mode_name.py    ← required for new modes
```

At minimum, test that:

- The mode initialises without errors
- `name` property returns a non-empty string
- `get_system_prompt()` returns a non-empty string
- `run()` returns a string given a valid user input

See `backend/tests/test_modes.py` for the established pattern.

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
4. Read `backend/modes/qa_mode.py` — it shows exactly what a mode looks like in practice
5. Create `backend/modes/your_mode_name.py` and inherit from `BaseMode`:

```python
from __future__ import annotations

from typing import Iterator, Optional

from modes.base_mode import BaseMode


class YourModeName(BaseMode):
    """One sentence describing what this mode does."""

    @property
    def name(self) -> str:
        return "Your Mode Name"

    def get_system_prompt(self) -> str:
        """
        System-level instruction sent to the LLM before every query.
        Tell it how to behave, what role it plays, and what constraints to follow.
        """
        return (
            "You are ScholarOS, an expert academic tutor. "
            "Answer using only the provided document context. "
            # Add your mode-specific instructions here.
        )

    def run(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """
        Blocking entry point. Retrieves context and returns a complete response string.
        BaseMode._retrieve() handles the vector store query — call it here.
        Return a plain string on error so the UI can display it gracefully.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            return str(exc)

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
        )
        return self.llm_client.generate(prompt=prompt)

    def run_stream(
        self,
        user_input: str,
        source_id: Optional[str] = None,
        top_k: int = 5,
    ) -> Iterator[str]:
        """
        Optional but recommended. Streams the response token-by-token for the UI.
        If omitted, the UI falls back to the blocking run() method.
        """
        try:
            context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        except ValueError as exc:
            yield str(exc)
            return

        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
        )
        yield from self.llm_client.generate_stream(prompt=prompt)
```

6. Create `backend/tests/test_your_mode_name.py`
7. Run `make test` and `make lint`
8. Commit using the Conventional Commits format — e.g. `feat(modes): add your mode name`
9. Open a PR targeting `main` and link the issue

**BaseMode contract at a glance:**

| Method / Property | Required | Purpose |
|---|---|---|
| `name` | ✅ | Display name shown in the UI |
| `get_system_prompt()` | ✅ | Role and constraints sent to the LLM |
| `run()` | ✅ | Blocking — calls `_retrieve()` → `build_rag_prompt()` → `generate()` |
| `run_stream()` | ⭕ Recommended | Streaming — same flow, yields tokens via `generate_stream()` |
| `_retrieve()` | Provided | Do not override — inherited from BaseMode |

You do not need to understand `backend/core/` or `frontend/` to make a meaningful contribution.

---

*ScholarOS is built by Samira Khan & Vivek Kesarwani — KIIT University.*  
*A team of 2 CS undergraduates with a lot of ideas to better the world in small ways.*