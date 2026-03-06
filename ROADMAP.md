# Roadmap

This document outlines the planned direction of ScholarOS.  
It helps contributors understand current priorities, upcoming features, and long-term goals.

The roadmap may evolve as the project grows and community needs change.

---

## Table of Contents

- [Vision](#vision)
- [Current Status](#current-status)
- [Short-Term Goals](#short-term-goals)
- [Mid-Term Goals](#mid-term-goals)
- [Long-Term Goals](#long-term-goals)
- [Future Research Directions](#future-research-directions)
- [Contribution Opportunities](#contribution-opportunities)
- [Community Feedback](#community-feedback)
- [Versioning Strategy](#versioning-strategy)
- [Disclaimer](#disclaimer)

---

## Vision

ScholarOS aims to build a **local-first AI study assistant** that enables students to transform static documents into interactive learning sessions — with no internet connection, no subscription, and no GPU required.

The long-term vision is to make **AI-powered education accessible offline, on any hardware, for any learner anywhere in the world.**

Key principles guiding development:

- Offline-first architecture — the app must work with zero network access
- Accessibility on low-resource devices — 4 GB RAM is the target ceiling, not the floor
- Modular contribution system — any developer should be able to extend the app in under 15 minutes
- Community-driven improvements — subject packs, new modes, and translations owned by the community
- Transparent development — all planned work is tracked publicly on GitHub Issues

---

## Current Status

Current development stage: **v1.0 — Hackathon MVP**

Implemented and shipped:

- Local RAG pipeline using `llama-cpp-python` and ChromaDB (fully in-process, no external servers)
- PDF ingestion with PyMuPDF — 50-token overlap chunking for academic multi-column layouts
- Q&A Mode — questions answered and grounded in uploaded document context
- Flashcard Mode — auto-generated Q&A pairs from any topic or page range
- Web interface — decoupled FastAPI backend + Vanilla HTML/CSS/JS frontend
- Three-command setup: `make install` → `make fetch-model` → `make run`
- Windows support via `scripts/setup.bat` with pre-compiled wheel handling
- Full documentation suite: README, CONTRIBUTING, CODE_OF_CONDUCT, ROADMAP, LICENSE

Known limitations at v1.0:

- Single PDF per session — multi-file sessions not yet supported
- Tables and images in PDFs are not parsed — text-only extraction
- No session history or progress tracking
- No voice input or output

---

## Short-Term Goals

### v1.1 — Subject Pack Ecosystem

Goal: enable community-driven domain expertise without requiring code contributions.

Planned features:

- Subject Pack format — community-contributed JSON files containing domain-specific system prompts
- Example packs: JEE Physics, UPSC History, Law, Computer Science fundamentals
- Pack registry — a `packs.json` index installable via `make install-pack PACK=jee-physics`
- Advanced PDF parsing — improved handling of tables and images in complex academic papers
- MCQ generator mode — multiple-choice questions with a full answer key
- Model auto-detection — ScholarOS detects available models and recommends the best one for available RAM

---

### v1.2 — Deeper Learning Modes

Goal: move beyond information retrieval into active pedagogy.

Planned features:

- Socratic debate mode — guided questioning instead of direct answers
- Timeline builder — chronological event mapping for history and social science notes
- Progress dashboard — topics covered, weak areas flagged, session history stored locally
- Multi-file sessions — ingest an entire folder of PDFs as a single knowledge base
- Spaced repetition scheduler — SM-2 algorithm for flashcard review intervals

---

## Mid-Term Goals

### v1.3 — Accessibility and Reach

Focus on expanding who can use ScholarOS.

Planned improvements:

- Handwritten notes support via local OCR (Tesseract integration)
- ARM device optimisation — tested and documented setup for Raspberry Pi 4/5
- Institutional deployment guide — shared server setup for schools and NGOs over LAN
- Offline installer — single-file executable that bundles Python, dependencies, and a base model

Performance improvements:

- Faster embedding pipeline with batch processing
- Reduced RAM footprint for the 2 GB device segment
- Startup time under 5 seconds on mid-range hardware

---

## Long-Term Goals

### v2.0 — Fully Offline AI Tutor

Major milestone for the project.

Key capabilities:

- Voice input and output — local Whisper (speech-to-text) + Piper TTS (text-to-speech)
- Exam pattern mode — past-paper-style questions for named exams (JEE, UPSC, SAT, IELTS, WAEC)
- Multi-language support — prompt templates translated by community contributors, prioritising Hindi, Bengali, Swahili, Arabic, and Portuguese
- Conversational tutoring — multi-turn dialogue that maintains session context
- LLM-agnostic backend — swap `llama-cpp-python` for any local backend via a single config line

Target outcomes:

- Runs on a shared Raspberry Pi 5 serving multiple students over LAN
- Deployable by an NGO or school without contacting the original maintainers
- Stable plugin API that allows third-party mode development outside the core repository

---

## Future Research Directions

Possible areas for exploration beyond v2.0:

- Personalised learning paths — adaptive study sessions based on tracked performance
- Concept graph visualisation — map relationships between topics across documents
- On-device fine-tuning — lightweight LoRA adaptation on student-specific material
- Mobile ports — llama.cpp Android bindings to bring ScholarOS to offline mobile devices
- Automatic syllabus alignment — map document content to known curriculum frameworks

These ideas are exploratory and may change depending on community contributions and feasibility.

---

## Contribution Opportunities

Contributors can help in several areas right now.

### Study Modes

- Add new modes by inheriting from `BaseMode` in `modes/`
- Improve prompt templates in existing modes
- Build the Socratic debate mode or timeline builder

### Subject Packs

- Contribute domain-specific JSON prompt packs for any subject or exam
- Translate existing packs into other languages

### Backend Development

- Improve table and image extraction in `core/ingestion.py`
- Optimise chunking strategy for different document types
- Reduce memory footprint for low-RAM devices

### Frontend Development

- Improve the web UI accessibility (WCAG compliance)
- Build a progress dashboard view
- Improve mobile browser responsiveness

### Documentation

- Write tutorials for first-time contributors
- Translate the README into other languages
- Write architecture explanation guides for the `docs/` folder

Browse [open issues](https://github.com/CricketFan18/ScholarOS/issues) and look for the `good first issue` label to find a starting point.

---

## Community Feedback

The roadmap is influenced by feedback from contributors and users.

Suggestions can be made through:

- [GitHub Issues](https://github.com/CricketFan18/ScholarOS/issues) — bug reports and feature requests
- [GitHub Discussions](https://github.com/CricketFan18/ScholarOS/discussions) — open-ended ideas and questions
- Pull Requests — propose and build changes directly

Community participation helps guide the future direction of the project.

---

## Versioning Strategy

ScholarOS follows semantic versioning:

```
MAJOR.MINOR.PATCH
```

- **MAJOR** — incompatible architecture changes
- **MINOR** — new features or study modes added in a backward-compatible way
- **PATCH** — bug fixes and minor improvements

All version changes are recorded in [CHANGELOG.md](CHANGELOG.md).

---

## Disclaimer

Roadmap items represent **intentions rather than guarantees**.  
Priorities may shift as development progresses, new contributors join, or community needs change.

We welcome involvement from anyone who wants to help shape the future of this project.

---

*ScholarOS — Samira Khan & Vivek Kesarwani — KIIT University — Open Source Forge 2026*