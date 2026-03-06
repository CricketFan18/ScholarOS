.PHONY: help install install-frontend install-all fetch-model fetch-model-fallback \
        run run-backend run-frontend test test-coverage lint lint-check \
        clean clean-all

# ── Shell ──────────────────────────────────────────────────────────────────
# Use bash explicitly — /bin/sh (dash on Ubuntu) lacks pipefail and read -p.
SHELL       := bash
.SHELLFLAGS := -eu -o pipefail -c

# ── Variables ──────────────────────────────────────────────────────────────
# project-root venv (not inside backend/)
VENV         := venv
BACKEND_DIR  := backend
FRONTEND_DIR := frontend
PORT         := 8000

# Platform-aware paths to the venv interpreter and pip.
ifeq ($(OS),Windows_NT)
  PYTHON := $(VENV)/Scripts/python
  PIP    := $(VENV)/Scripts/pip
else
  PYTHON := $(VENV)/bin/python
  PIP    := $(VENV)/bin/pip
endif

# ── Help (default target) ──────────────────────────────────────────────────

help:               ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────────────

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

install: $(VENV)/bin/activate  ## Create venv and install backend Python dependencies
	@echo "→ Upgrading pip..."
	$(PIP) install --upgrade pip
	@echo "→ Installing ScholarOS backend + dev dependencies..."
	cd $(BACKEND_DIR) && ../$(PIP) install -e ".[dev]"
	@if [ ! -f $(BACKEND_DIR)/.env ]; then \
		cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env 2>/dev/null || \
		echo "SCHOLAROS_MODELS_DIR=models" > $(BACKEND_DIR)/.env; \
		echo "→ Created $(BACKEND_DIR)/.env"; \
	fi
	@echo "✓ Backend setup complete."

install-frontend:   ## Install frontend npm dependencies (requires Node.js 18+)
	@echo "→ Checking for Node.js..."
	@if ! command -v node &>/dev/null; then \
		echo "✗ Node.js not found. Install from https://nodejs.org/en/download"; \
		echo "  macOS:          brew install node"; \
		echo "  Ubuntu/Debian:  sudo apt install nodejs npm"; \
		exit 1; \
	fi
	@NODE_MAJOR=$$(node --version | sed 's/v//' | cut -d. -f1); \
	if [ "$$NODE_MAJOR" -lt 18 ]; then \
		echo "✗ Node.js v$$NODE_MAJOR is too old — Vite 5 requires v18+."; \
		exit 1; \
	fi
	@echo "→ Installing frontend dependencies..."
	cd $(FRONTEND_DIR) && npm install
	@echo "✓ Frontend dependencies installed."

install-all: install install-frontend  ## Full setup: Python venv + npm deps (recommended for first-time setup)
	@echo ""
	@echo "✓ Full setup complete! Next:"
	@echo "    make fetch-model"
	@echo "    make run"

# ── Model download ─────────────────────────────────────────────────────────

fetch-model:        ## Download the default model: Phi-3 Mini (~2.3 GB)
	@echo "→ Downloading Phi-3 Mini weights (~2.3 GB)..."
	cd $(BACKEND_DIR) && ../$(PYTHON) scripts/download_model.py --model default
	@echo "✓ Model ready in ./backend/models/"

fetch-model-fallback: ## Download the fallback model: Qwen2.5 1.5B (~1 GB, for 4 GB RAM machines)
	@echo "→ Downloading Qwen2.5 1.5B weights (~1.0 GB)..."
	cd $(BACKEND_DIR) && ../$(PYTHON) scripts/download_model.py --model fallback
	@echo "✓ Fallback model ready in ./backend/models/"

# ── Run ────────────────────────────────────────────────────────────────────

run: _check-model   ## Start backend + frontend together and open the browser (recommended)
	$(PYTHON) start.py --port $(PORT)

run-backend: _check-model  ## Start only the FastAPI backend (for decoupled development)
	@echo "→ Starting backend on http://localhost:$(PORT) ..."
	cd $(BACKEND_DIR) && ../$(PYTHON) -m uvicorn api.main:app \
		--host 0.0.0.0 --port $(PORT) --reload

run-frontend:       ## Start only the Vite dev server (backend must already be running)
	@if ! command -v npm &>/dev/null; then \
		echo "✗ npm not found. Run  make install-frontend  first."; \
		exit 1; \
	fi
	@echo "→ Starting frontend dev server..."
	cd $(FRONTEND_DIR) && npm run dev

_check-model:
	@if [ -z "$$(ls -A $(BACKEND_DIR)/models/*.gguf 2>/dev/null)" ]; then \
		echo ""; \
		echo "✗ No model weights found in ./backend/models/"; \
		echo "  Run: make fetch-model"; \
		echo ""; \
		exit 1; \
	fi

# ── Test ───────────────────────────────────────────────────────────────────

test:               ## Run the full backend test suite with verbose output
	@echo "→ Running ScholarOS test suite..."
	cd $(BACKEND_DIR) && ../$(PYTHON) -m pytest tests/ -v --tb=short

test-coverage:      ## Run tests and generate an HTML coverage report
	cd $(BACKEND_DIR) && ../$(PYTHON) -m pytest tests/ \
		--cov=core --cov=modes --cov=api --cov-report=html
	@echo "✓ Coverage report written to backend/htmlcov/index.html"

# ── Code quality ───────────────────────────────────────────────────────────

lint:               ## Format Python code with black and sort imports with isort
	$(PYTHON) -m black $(BACKEND_DIR)/core/ $(BACKEND_DIR)/modes/ \
	                   $(BACKEND_DIR)/api/  $(BACKEND_DIR)/tests/
	$(PYTHON) -m isort $(BACKEND_DIR)/core/ $(BACKEND_DIR)/modes/ \
	                   $(BACKEND_DIR)/api/  $(BACKEND_DIR)/tests/

lint-check:         ## Check Python formatting without making changes (CI use)
	$(PYTHON) -m black --check $(BACKEND_DIR)/core/ $(BACKEND_DIR)/modes/ \
	                            $(BACKEND_DIR)/api/  $(BACKEND_DIR)/tests/
	$(PYTHON) -m isort --check-only $(BACKEND_DIR)/core/ $(BACKEND_DIR)/modes/ \
	                                 $(BACKEND_DIR)/api/  $(BACKEND_DIR)/tests/

# ── Clean ──────────────────────────────────────────────────────────────────

clean:              ## Remove venv, node_modules, ChromaDB data, and Python caches
	rm -rf $(VENV)
	rm -rf $(FRONTEND_DIR)/node_modules
	rm -rf $(BACKEND_DIR)/data/chroma_db/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Environment and local database cleaned."

clean-all: clean    ## clean + remove model weights and backend/.env (asks for confirmation)
	@echo "→ This will permanently delete model weights and your backend/.env file."
	@read -p "   Are you sure? [y/N] " confirm && [ "$${confirm}" = "y" ]
	rm -rf $(BACKEND_DIR)/models/*.gguf
	rm -f $(BACKEND_DIR)/.env
	@echo "✓ Full clean complete."