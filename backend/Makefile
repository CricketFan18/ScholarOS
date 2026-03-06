.PHONY: help install fetch-model fetch-model-fallback run test lint clean clean-all

# ── Variables ──────────────────────────────────────────────────────────────

VENV        := venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
PORT        := 8000

# Detect Windows (nmake / git-bash)
ifeq ($(OS),Windows_NT)
  PYTHON  := $(VENV)/Scripts/python
  PIP     := $(VENV)/Scripts/pip
endif

# ── Help (default target) ──────────────────────────────────────────────────

help:          ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────────────

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

install: $(VENV)/bin/activate  ## Create venv and install all dependencies
	@echo "→ Upgrading pip..."
	$(PIP) install --upgrade pip
	@echo "→ Installing ScholarOS + dev dependencies..."
	$(PIP) install -e ".[dev]"
	@if [ ! -f .env ]; then cp .env.example .env && echo "→ Created .env from .env.example"; fi
	@echo ""
	@echo "✓ Setup complete!"
	@echo "  Next steps:"
	@echo "    1. source venv/bin/activate"
	@echo "    2. make fetch-model"
	@echo "    3. make run"

# ── Model download ─────────────────────────────────────────────────────────

fetch-model:   ## Download default model: Phi-3 Mini (~2.3 GB)
	@echo "→ Downloading Phi-3 Mini weights (~2.3 GB)..."
	$(PYTHON) scripts/download_model.py --model default
	@echo "✓ Model ready in ./models/"

fetch-model-fallback:  ## Download fallback model: Qwen2.5 1.5B (~1.0 GB, for 4 GB RAM machines)
	@echo "→ Downloading Qwen2.5 1.5B fallback weights (~1.0 GB)..."
	$(PYTHON) scripts/download_model.py --model fallback
	@echo "✓ Fallback model ready in ./models/"

# ── Run ────────────────────────────────────────────────────────────────────

run: _check-model ## Start the ScholarOS FastAPI server (auto-reloads on code changes)
	@echo "→ Starting ScholarOS on http://localhost:$(PORT) ..."
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port $(PORT) --reload

_check-model:
	@if [ -z "$$(ls -A models/*.gguf 2>/dev/null)" ]; then \
		echo ""; \
		echo "✗ No model weights found in ./models/"; \
		echo "  Run: make fetch-model"; \
		echo ""; \
		exit 1; \
	fi

# ── Test ───────────────────────────────────────────────────────────────────

test:          ## Run the full test suite with verbose output
	@echo "→ Running ScholarOS test suite..."
	$(PYTHON) -m pytest tests/ -v --tb=short

test-coverage: ## Run tests and generate an HTML coverage report
	$(PYTHON) -m pytest tests/ --cov=core --cov=modes --cov-report=html
	@echo "✓ Coverage report written to htmlcov/index.html"

# ── Code quality ───────────────────────────────────────────────────────────

lint:          ## Format code with black and sort imports with isort
	$(PYTHON) -m black core/ modes/ api/ tests/
	$(PYTHON) -m isort core/ modes/ api/ tests/

lint-check:    ## Check formatting without making changes (useful in CI)
	$(PYTHON) -m black --check core/ modes/ api/ tests/
	$(PYTHON) -m isort --check-only core/ modes/ api/ tests/

# ── Clean ──────────────────────────────────────────────────────────────────

clean:         ## Remove venv, ChromaDB data, and Python caches
	rm -rf $(VENV)
	rm -rf data/chroma_db/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Environment and local database cleaned."

clean-all: clean  ## clean + remove downloaded model weights and .env
	@echo "→ This will delete model weights and your .env file."
	@read -p "   Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	rm -rf models/*.gguf
	rm -f .env
	@echo "✓ Full clean complete."