# ScholarOS

![License](https://img.shields.io/badge/license-Apache_2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

ScholarOS is a **local-first AI study assistant that transforms static documents into interactive learning sessions**.  
It runs entirely **offline**, enabling students to upload PDFs, ask questions, generate flashcards, and get concept explanations — without requiring an internet connection.

The goal of this project is to make **AI-powered learning accessible anywhere, on any hardware, for any student.**

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Demo](#demo)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Adding a New Study Mode](#adding-a-new-study-mode)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Overview

Traditional study tools treat documents as static reading material.

ScholarOS transforms documents into **active learning experiences**.

By combining **local language models, document parsing, and a modular study mode system**, ScholarOS creates a study partner that:

- answers questions grounded in your actual notes, with full multi-turn conversation support
- generates flashcard pairs on any topic
- produces structured summaries with headings and key findings
- runs entirely on-device — no cloud, no daemon, no subscription

All processing occurs **locally on the user's device**. Your notes never leave your machine.

---

## Features

### Offline AI Learning

No internet connection required after setup.  
All models and processing run locally via `llama-cpp-python` — no external runtime to install.

### PDF to Study Sessions

Convert any document into:

- **Q&A** — ask follow-up questions grounded in your material, streamed token-by-token with multi-turn history
- **Flashcards** — click-to-flip active recall cards generated on any topic
- **Summary** — structured executive summary rendered as formatted markdown
- (v1.1+) MCQs, Socratic debate, subject packs

### Lightweight Architecture

Designed to run on:

- laptops with 4 GB RAM
- low-resource machines with no GPU
- shared devices in low-connectivity environments

### Modular Contribution System

Every study mode is a standalone plugin.  
Add a new mode by creating one file in `backend/modes/` — implement `name`, `get_system_prompt()`, and `run()`. No core knowledge required.  
This is the 15-minute contribution entry point.

### Open Source

Fully open and contribution-friendly under Apache 2.0.

---

## Example workflow:

1. Run `python start.py` — the interface opens automatically in your browser
2. Upload a PDF (lecture notes, textbook chapter, research paper)
3. The system parses, chunks, and embeds the document locally
4. Switch between Q&A, Flashcards, and Summary tabs — conversation history persists across tab switches

Example interactions:

```
# Q&A Mode
User:      What is the difference between mitosis and meiosis?
ScholarOS: Based on your notes:
           Mitosis produces two identical diploid cells used for growth and repair.
           Meiosis produces four haploid cells used for sexual reproduction.

User:      Which one requires crossing over?
ScholarOS: Meiosis requires crossing over, which occurs during prophase I...

# Flashcard Mode
User:      Generate flashcards on thermodynamics
ScholarOS: Q: What does the first law of thermodynamics state?
           A: Energy cannot be created or destroyed, only converted between forms.
```

---

## Architecture

```
PDF Upload (browser)
      │
      ▼
FastAPI backend  (backend/api/main.py)
      │
      ├── Ingestion pipeline  (backend/core/ingestion.py)
      │       PyMuPDF text extraction → whitespace normalisation → overlapping chunks
      │
      ├── Vector store  (backend/core/vector_store.py)
      │       sentence-transformers (all-MiniLM-L6-v2) → ChromaDB (local SQLite)
      │
      ├── LLM client  (backend/core/llm_client.py)
      │       llama-cpp-python · eagerly loaded at startup · thread-safe · streaming
      │
      └── Study mode plugins  (backend/modes/)
              BaseMode → QAMode, FlashcardMode
              (add new modes here)

React + Vite frontend  (frontend/src/)
      │
      ├── Sidebar — PDF upload and document library
      ├── ChatMode — streaming Q&A with persistent multi-turn history
      ├── FlashcardMode — click-to-flip card grid
      └── SummaryMode — markdown-rendered executive summary
```

**Key design decisions:**

- Both the embedding model and LLM are loaded eagerly at startup so the first upload and first Q&A are fast. The terminal prints `LLM ready` when the app is fully warm.
- Q&A responses are streamed token-by-token via Server-Sent Events (SSE) so users see output immediately.
- Chat history is lifted to the root component so switching tabs never loses the conversation.
- Every internal path is anchored to `__file__` so the app works regardless of which directory uvicorn is invoked from.
- On WSL, `start.py` auto-detects the eth0 IP and writes `frontend/.env.local` so Windows browsers can reach the backend without manual configuration.

---

## Getting Started

### Prerequisites

| Tool | Minimum version | Required for |
|---|---|---|
| Python | 3.10 | Backend (always) |
| Node.js | 18 | Frontend |
| npm | 9 | Frontend (ships with Node.js) |

Node.js is only required if you want to run the frontend. The backend API works standalone.

### Quick start

```bash
# 1. Clone and enter the repo
git clone https://github.com/CricketFan18/ScholarOS && cd scholaros

# 2. Full setup — Python venv + npm dependencies, one command
python setup.py

# 3. Download a model
make fetch-model            # Phi-3 Mini (~2.3 GB), recommended
make fetch-model-fallback   # Qwen2.5 1.5B (~1 GB), for machines with < 6 GB RAM

# 4. Start everything
python start.py
```

`start.py` will:
- Verify the venv and Node.js are present
- Start the FastAPI backend on port 8000 and load both models into memory
- Start the Vite frontend on port 5173
- Open your browser automatically
- Shut both servers down cleanly on Ctrl-C

**Wait for this line before using the app:**
```
[Startup] ✓ LLM ready. ScholarOS is fully loaded and ready!
```

### WSL users (Windows Subsystem for Linux)

If you're running on WSL with a Windows browser, `start.py` handles this automatically — it detects the WSL network IP and writes it to `frontend/.env.local`. Open the URL printed in the terminal (e.g. `http://172.x.x.x:5173`) rather than `localhost:5173`.

### Make targets

```bash
make install-all          # Python venv + npm deps (same as python setup.py)
make fetch-model          # download Phi-3 Mini weights (~2.3 GB)
make fetch-model-fallback # download Qwen2.5 1.5B weights (~1 GB)
make run                  # backend + frontend + browser (wraps start.py)
make run-backend          # backend only
make run-frontend         # Vite dev server only (backend must be running)
make test                 # run the full backend test suite
make test-coverage        # tests + HTML coverage report (backend/htmlcov/)
make lint                 # format Python with black + isort
make clean                # remove venv, node_modules, ChromaDB data, caches
```

### Developer workflow (decoupled servers)

When you need hot-reload on both sides independently:

```bash
# Terminal 1
python start.py --backend-only

# Terminal 2
python start.py --frontend-only
```

### `start.py` reference

```
usage: start.py [-h] [--backend-only] [--frontend-only] [--no-browser] [--port PORT]

  --backend-only    Start only the FastAPI backend
  --frontend-only   Start only the Vite dev server
  --no-browser      Don't auto-open the browser on startup
  --port PORT       Backend port (default: 8000)
```

### Node.js not installed?

`python setup.py` will warn and continue — the Python environment is still set up correctly.  
You can run the backend alone and add Node.js later:

```bash
python start.py --backend-only
```

Install hints:

| Platform | Command |
|---|---|
| macOS | `brew install node` |
| Ubuntu/Debian | `sudo apt install nodejs npm` |
| Fedora | `sudo dnf install nodejs npm` |
| Windows | Download from [nodejs.org](https://nodejs.org/en/download) |
| Any (nvm) | [github.com/nvm-sh/nvm](https://github.com/nvm-sh/nvm) |

---

## Project Structure

```
scholaros/
├── start.py                        # unified launcher — starts backend + frontend
├── setup.py                        # full project setup (Python venv + npm)
├── Makefile                        # developer shortcuts
│
├── backend/
│   ├── api/
│   │   └── main.py                 # FastAPI app — endpoints only, no business logic
│   ├── core/
│   │   ├── __init__.py             # public surface: ingest_pdf, VectorStore, LLMClient
│   │   ├── ingestion.py            # PDF parsing → chunking pipeline
│   │   ├── vector_store.py         # ChromaDB wrapper — embed, store, query, delete
│   │   └── llm_client.py           # llama-cpp-python wrapper — generate, stream, prompt builder
│   ├── modes/
│   │   ├── __init__.py
│   │   ├── base_mode.py            # abstract base — implement 3 methods to add a mode
│   │   ├── qa_mode.py              # streaming Q&A with multi-turn history
│   │   └── flashcard_mode.py       # structured flashcard generation + parser
│   ├── tests/
│   │   ├── conftest.py             # shared fixtures
│   │   ├── test_api.py             # HTTP-level endpoint tests
│   │   ├── test_ingestion.py       # PDF parsing and chunking unit tests
│   │   └── test_modes.py           # study mode unit tests
│   ├── scripts/
│   │   ├── download_model.py       # downloads .gguf weights from HuggingFace
│   │   └── setup.bat               # Windows setup helper
│   ├── pyproject.toml              # Python package definition and dependencies
│   └── .env.example                # environment variable reference
│
└── frontend/
    ├── src/
    │   ├── App.jsx                 # root — owns activeDocId, activeTab, and messages state
    │   ├── api/
    │   │   └── client.js           # axios instance + endpoint registry
    │   ├── components/
    │   │   ├── Sidebar.jsx         # PDF upload + document library
    │   │   ├── common/
    │   │   │   └── MarkdownRenderer.jsx  # react-markdown with Tailwind Typography
    │   │   └── modes/
    │   │       ├── ChatMode.jsx        # streaming Q&A chat interface
    │   │       ├── FlashcardMode.jsx   # click-to-flip card grid
    │   │       └── SummaryMode.jsx     # markdown summary panel
    │   └── hooks/
    │       ├── useDocuments.js     # fetch, upload, delete document library
    │       ├── useStreamChat.js    # SSE streaming + multi-turn history
    │       ├── useFlashcards.js    # flashcard generation state
    │       └── useSummary.js       # summary generation state
    ├── package.json
    └── vite.config.js
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env` (done automatically by `python setup.py`):

```bash
cp backend/.env.example backend/.env
```

Available environment variables:

| Variable | Default | Description |
|---|---|---|
| `SCHOLAROS_MODELS_DIR` | `backend/models` | Directory containing `.gguf` model files |
| `SCHOLAROS_MODEL_FILE` | `Phi-3-mini-4k-instruct-q4.gguf` | Model filename to load |

To switch models, download an alternative `.gguf` file into `backend/models/` and update `SCHOLAROS_MODEL_FILE` in `backend/.env`.

---

## Adding a New Study Mode

Every mode lives in a single file in `backend/modes/`. To add one:

1. Create `backend/modes/your_mode.py`
2. Inherit from `BaseMode` and implement three methods:

```python
from modes.base_mode import BaseMode

class YourMode(BaseMode):

    @property
    def name(self) -> str:
        return "Your Mode"

    def get_system_prompt(self) -> str:
        return "You are ScholarOS. Your task is to..."

    def run(self, user_input, source_id=None, top_k=5) -> str:
        context_chunks, _ = self._retrieve(user_input, source_id=source_id, top_k=top_k)
        prompt = self.llm_client.build_rag_prompt(
            system_prompt=self.get_system_prompt(),
            context_chunks=context_chunks,
            user_question=user_input,
        )
        return self.llm_client.generate(prompt=prompt)
```

3. Register it in `backend/modes/__init__.py`
4. Add an endpoint in `backend/api/main.py`
5. Add a tab in `frontend/src/App.jsx`

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full walkthrough.

---

## Roadmap

| Version | Status | Key Features |
|---|---|---|
| v1.0.0 | ✅ Current | Q&A (streaming + multi-turn), Flashcards, Summary, React + Vite frontend, unified launcher, WSL support |
| v1.1.0 | 🔨 In Progress | MCQ generator, subject packs, advanced PDF parsing (tables + images) |
| v1.2.0 | 📋 Planned | Socratic debate mode, timeline builder, progress dashboard, multi-file sessions |
| v2.0.0 | 🌱 Vision | Mobile ports via llama.cpp Android bindings, voice I/O, multi-language support |

Track planned work on the [GitHub Issues board](https://github.com/CricketFan18/ScholarOS/issues).  
Issues labelled [`good first issue`](https://github.com/CricketFan18/ScholarOS/issues?q=label%3A%22good+first+issue%22) are ideal starting points for new contributors.

---

## Contributing

We welcome community contributions.

To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Make your changes and write tests
4. Ensure all tests pass: `make test`
5. Open a pull request targeting `main`

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide, branch naming conventions, commit format, and the step-by-step guide to adding a new study mode.

---

## License

This project is licensed under the Apache 2.0 License.  
It is enterprise-friendly, patent-safe, and free to use for any purpose.

See [LICENSE](LICENSE) for details.

```
Copyright (c) 2026 Samira Khan & Vivek Kesarwani
```

---

## Acknowledgements

### Built by

| Name | Role |
|---|---|
| Samira Khan | UI development, documentation, testing |
| Vivek Kesarwani | Core architecture, RAG pipeline, modes system |

KIIT University — Open Source Forge 2026

### Libraries and tools

| Library | Purpose |
|---|---|
| [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) | In-process LLM inference |
| [ChromaDB](https://trychroma.com) | Embedded local vector store |
| [sentence-transformers](https://sbert.net) | Local embedding model |
| [PyMuPDF](https://pymupdf.readthedocs.io) | PDF text extraction |
| [FastAPI](https://fastapi.tiangolo.com) | Async backend framework |
| [Vite](https://vitejs.dev) + [React](https://react.dev) | Frontend build tooling |
| [Tailwind CSS](https://tailwindcss.com) | Utility-first styling |
| [HuggingFace Hub](https://huggingface.co) | Model hosting |

We thank all contributors and the open-source community that made this possible.

---

*A team of 2 CS undergraduates with a lot of ideas to better the world in small ways.*