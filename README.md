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
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Overview

Traditional study tools treat documents as static reading material.

ScholarOS transforms documents into **active learning experiences**.

By combining **local language models, document parsing, and a modular study mode system**, ScholarOS creates a study partner that:

- answers questions grounded in your actual notes
- generates flashcard pairs on any topic
- explains concepts with real-world analogies
- runs entirely inside a single Python process — no cloud, no daemon, no subscription

All processing occurs **locally on the user's device**. Your notes never leave your machine.

---

## Features

### Offline AI Learning

No internet connection required.  
All models and processing run locally via `llama-cpp-python` — no external runtime to install.

### PDF to Study Sessions

Convert any document into:

- Q&A sessions grounded in your material
- Flashcard pairs for active recall
- Concept explanations with analogies
- (v1.1+) MCQs, Socratic debate, subject packs

### Lightweight Architecture

Designed to run on:

- laptops with 4 GB RAM
- low-resource machines with no GPU
- shared devices in low-connectivity environments

### Modular Contribution System

Every study mode is a standalone plugin.  
Add a new mode by creating one file in `modes/` — implement `name`, `get_system_prompt()`, and `run()`. No core knowledge required.  
This is the 15-minute contribution entry point.

### Open Source

Fully open and contribution-friendly under Apache 2.0.

---

## Demo

> 📽️ **Demo GIF coming soon** — add `docs/demo.gif` before final submission.

Example workflow:

1. Run `make run` — the interface opens at `http://localhost:8080`
2. Upload a PDF (lecture notes, textbook chapter, research paper)
3. The system parses and indexes the document locally
4. Select a study mode and start your session

Example interactions:

```
# Q&A Mode
User:   What is the difference between mitosis and meiosis?
ScholarOS: Based on your notes (Lecture 3, page 12):
           Mitosis produces two identical diploid cells used for growth.
           Meiosis produces four haploid cells used for reproduction.

# Flashcard Mode
User:   Generate 5 flashcards on thermodynamics
ScholarOS: Q1: What does the first law of thermodynamics state?
           A1: Energy cannot be created or destroyed, only converted.
```

---

## Architecture

High-level system architecture:

```
PDF Input
   │
   ▼
Document Parser (PyMuPDF — 50-token overlap chunking)
   │
   ▼
Embedding Generator (sentence-transformers — all-MiniLM-L6-v2)
   │
   ▼
Vector Storage (ChromaDB — embedded, local SQLite)
   │
   ▼
Local Language Model (llama-cpp-python — Phi-3 Mini GGUF)
   │
   ▼
Study Mode Plugin (modes/ — Q&A, Flashcard, and community modes)
   │
   ▼
Web Interface (FastAPI + Vanilla HTML/CSS/JS)
```

Main components:

- `core/ingestion.py` — PDF parsing with 50-token overlap. Public API: `ingest_pdf()`, `extract_text_from_pdf()`, `chunk_text()`
- `core/vector_store.py` — ChromaDB embedded interface. Public class: `VectorStore`
- `core/llm_client.py` — llama-cpp-python wrapper. Exposes `build_rag_prompt()`, `generate()`, `generate_stream()`
- `core/__init__.py` — single import surface: `from core import ingest_pdf, VectorStore, LLMClient`
- `modes/base_mode.py` — abstract base. Implement `name`, `get_system_prompt()`, and `run()` to add a new mode
- `modes/` — contribution zone, one file per study mode
- `ui/server.py` — FastAPI router, no business logic
- `ui/web/` — decoupled frontend (index.html, style.css, app.js)

---

## Installation

Clone the repository:

```bash
git clone https://github.com/CricketFan18/ScholarOS.git
cd ScholarOS
```

Install dependencies:

```bash
# Linux / macOS
make install

# Windows
scripts\setup.bat
```

The Windows script handles pre-compiled `llama-cpp-python` wheel installation to bypass C++ compilation errors automatically.

Download the default model (Phi-3 Mini, ~2.2 GB):

```bash
make fetch-model
```

For constrained devices (2–3 GB RAM), set the fallback model first:

```bash
# In .env:
MODEL_NAME=qwen2.5-1.5b

make fetch-model
```

---

## Usage

Run the application:

```bash
make run
```

Open the interface in your browser:

```
http://localhost:8080
```

Upload a PDF and select a study mode to begin.

**Available study modes:**

```
qa          Ask questions grounded in your uploaded documents
flashcard   Generate Q&A flashcard pairs from any topic or page range
```

**Switching modes:**

```
mode qa
mode flashcard
```

**Uploading documents:**

```bash
upload path/to/your/notes.pdf
upload path/to/slides/*.pdf
```

---

## Project Structure

```
scholaros/
    core/
        ingestion.py        PDF parser — ingest_pdf(), extract_text_from_pdf(), chunk_text()
        vector_store.py     ChromaDB embedded interface — VectorStore
        llm_client.py       llama-cpp-python wrapper — build_rag_prompt(), generate(), generate_stream()
        __init__.py         Public API surface — from core import ingest_pdf, VectorStore, LLMClient
    modes/
        base_mode.py        Abstract base class all modes inherit
        qa_mode.py          Q&A study mode
        flashcard_mode.py   Flashcard generation mode
    ui/
        server.py           FastAPI application (router only)
        web/
            index.html      Decoupled UI structure
            style.css       Decoupled styles
            app.js          Decoupled client logic
    scripts/
        download_model.py   Pulls .gguf weights from HuggingFace
        setup.bat           Windows setup with pre-compiled wheels
    models/                 Git-ignored — holds .gguf weight files
    tests/
        test_ingestion.py
        test_modes.py
    README.md
    CONTRIBUTING.md
    CODE_OF_CONDUCT.md
    ROADMAP.md
    LICENSE
    Makefile
    pyproject.toml
    .env.example
```

---

## Configuration

Copy the example config and edit as needed:

```bash
cp .env.example .env
```

Available settings in `.env`:

```
MODEL_NAME=phi3-mini
CHUNK_SIZE=512
TOP_K=5
UI_PORT=8080
```

To switch to the fallback model on a low-RAM device:

```
MODEL_NAME=qwen2.5-1.5b
```

---

## Roadmap

| Version | Status | Key Features |
|---|---|---|
| v1.0.0 | ✅ Current | Q&A Mode, Flashcard Mode, local RAG via llama-cpp-python + ChromaDB, full docs |
| v1.1.0 | 🔨 In Progress | Subject Pack ecosystem, advanced PDF parsing (tables + images), MCQ generator |
| v1.2.0 | 📋 Planned | Socratic debate mode, timeline builder, progress dashboard, multi-file sessions |
| v2.0.0 | 🌱 Vision | Mobile ports via llama.cpp Android bindings, voice I/O, multi-language packs |

Track all planned work on the [GitHub Issues board](https://github.com/CricketFan18/ScholarOS/issues).  
Issues labelled [`good first issue`](https://github.com/CricketFan18/ScholarOS/issues?q=label%3A%22good+first+issue%22) are ideal starting points for new contributors.

---

## Contributing

We welcome community contributions.

To contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes and write tests
4. Ensure all tests pass: `pytest tests/ -v`
5. Open a pull request targeting `main`

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide, branch naming conventions, commit format, and the step-by-step guide to adding a new study mode.

---

## License

This project is licensed under the Apache 2.0 License.  
It is enterprise-friendly, patent-safe, and free to use for any purpose.

See [LICENSE](LICENSE) for details.

```
Copyright (c) 2025 Samira Khan & Vivek Kesarwani
```

---

## Acknowledgements

### Built by

| Name | Role |
|---|---|
| Samira Khan | Core architecture, RAG pipeline, modes system |
| Vivek Kesarwani | UI development, documentation, testing |

KIIT University — Open Source Forge 2025

### Libraries and tools

This project builds upon the following open-source work:

- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — in-process LLM inference via llama.cpp bindings
- [ChromaDB](https://trychroma.com) — embedded vector store
- [sentence-transformers](https://sbert.net) — local embedding models
- [PyMuPDF](https://pymupdf.readthedocs.io) — PDF text extraction
- [FastAPI](https://fastapi.tiangolo.com) — lightweight async web framework
- [HuggingFace Hub](https://huggingface.co) — model hosting for reproducible GGUF downloads

We thank all contributors and the open-source community that made this possible.

---

*A team of 2 CS undergraduates with a lot of ideas to better the world in small ways.*