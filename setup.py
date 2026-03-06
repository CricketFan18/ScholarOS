#!/usr/bin/env python3
"""
setup.py
--------
Full-project setup script for ScholarOS.

Handles everything a new contributor or end user needs to run the app:
  1. Check Python version (3.10+)
  2. Check Node.js and npm (18+), with platform-specific install hints
  3. Create and populate the Python virtual environment (venv/ at project root)
  4. Install frontend npm dependencies
  5. Copy backend/.env.example → backend/.env (if not already present)
  6. Print a clear next-steps summary

This script has zero third-party dependencies so it can be run on a bare
machine before anything is installed:

    python setup.py

On Windows, run in PowerShell or Git Bash. No admin privileges required —
all installs are user-local (venv + node_modules).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR     = Path(__file__).parent.resolve()
BACKEND_DIR  = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR     = ROOT_DIR / "venv"       # venv lives at project root, not inside backend/

if platform.system() == "Windows":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_PIP    = VENV_DIR / "Scripts" / "pip.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_PIP    = VENV_DIR / "bin" / "pip"

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_USE_COLOUR = sys.stdout.isatty() and platform.system() != "Windows"

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def step(n: int, total: int, msg: str) -> None:
    print(_c("1;36", f"\n[{n}/{total}] {msg}"))

def ok(msg: str)   -> None: print(_c("32",   f"  ✓  {msg}"))
def info(msg: str) -> None: print(_c("0",    f"       {msg}"))
def warn(msg: str) -> None: print(_c("33",   f"  ⚠  {msg}"))

def abort(msg: str) -> None:
    print(_c("1;31", f"  ✗  {msg}"), file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

TOTAL_STEPS = 5


def check_python() -> None:
    step(1, TOTAL_STEPS, "Checking Python version …")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        abort(
            f"Python 3.10+ is required. You have {major}.{minor}.\n"
            "  Download from: https://www.python.org/downloads/"
        )
    ok(f"Python {major}.{minor} — OK")


def check_node() -> None:
    """
    Verify Node.js >=18 and npm are available.

    If either is missing or outdated, prints platform-specific install
    instructions and continues — backend-only mode will still work without
    Node.js, so we don't abort here.
    """
    step(2, TOTAL_STEPS, "Checking Node.js and npm …")

    node_path = shutil.which("node")
    npm_path  = shutil.which("npm")

    if not node_path or not npm_path:
        missing = "Node.js" if not node_path else "npm"
        warn(f"{missing} not found on PATH.")
        _print_node_install_hint()
        warn("Continuing — backend-only mode will still work.")
        warn("To use the frontend later, install Node.js then re-run this script.")
        return

    try:
        raw   = subprocess.check_output(["node", "--version"], text=True).strip()
        major = int(raw.lstrip("v").split(".")[0])
        if major < 18:
            warn(f"Node.js {raw} is too old — Vite 5 requires v18+.")
            _print_node_install_hint()
            warn("Continuing — upgrade Node.js before running the frontend.")
            return
        ok(f"Node.js {raw} — OK")
    except (subprocess.CalledProcessError, ValueError, IndexError):
        warn("Could not determine Node.js version. Proceeding anyway.")
        return

    npm_ver = subprocess.check_output(["npm", "--version"], text=True).strip()
    ok(f"npm {npm_ver} — OK")


def _print_node_install_hint() -> None:
    system = platform.system()
    info("Install Node.js (v18 or newer):")
    if system == "Darwin":
        info("  Homebrew:   brew install node")
        info("  Download:   https://nodejs.org/en/download")
    elif system == "Linux":
        info("  Ubuntu/Debian:  sudo apt install nodejs npm")
        info("  Fedora:         sudo dnf install nodejs npm")
        info("  Arch:           sudo pacman -S nodejs npm")
        info("  nvm (any distro): https://github.com/nvm-sh/nvm")
    else:
        info("  Download:   https://nodejs.org/en/download")


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------

def setup_python_env() -> None:
    step(3, TOTAL_STEPS, "Setting up Python virtual environment …")

    if not VENV_DIR.exists():
        info(f"Creating venv at {VENV_DIR} …")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        ok("venv created.")
    else:
        ok("venv already exists — skipping creation.")

    info("Upgrading pip …")
    subprocess.run([str(VENV_PIP), "install", "--upgrade", "pip", "-q"], check=True)

    # Install the backend package in editable mode from backend/pyproject.toml
    info("Installing ScholarOS backend + dev dependencies …")
    subprocess.run(
        [str(VENV_PIP), "install", "-e", ".[dev]", "-q"],
        cwd=BACKEND_DIR,    # pip resolves pyproject.toml relative to cwd
        check=True,
    )
    ok("Python dependencies installed.")


def setup_frontend_deps() -> None:
    step(4, TOTAL_STEPS, "Installing frontend npm dependencies …")

    if not shutil.which("npm"):
        warn("npm not available — skipping frontend dependency install.")
        warn("Install Node.js 18+ then run:  cd frontend && npm install")
        return

    if not FRONTEND_DIR.exists():
        warn(f"frontend/ directory not found at {FRONTEND_DIR}. Skipping.")
        return

    if (FRONTEND_DIR / "node_modules").exists():
        ok("node_modules already exists — skipping npm install.")
        return

    info("Running npm install in frontend/ …")
    try:
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
        ok("npm dependencies installed.")
    except subprocess.CalledProcessError as exc:
        abort(f"npm install failed: {exc}")


def setup_env_file() -> None:
    step(5, TOTAL_STEPS, "Configuring environment …")

    env_file    = BACKEND_DIR / ".env"
    env_example = BACKEND_DIR / ".env.example"

    if env_file.exists():
        ok("backend/.env already exists — skipping.")
        return

    if env_example.exists():
        shutil.copy(env_example, env_file)
        ok("backend/.env created from backend/.env.example")
        info("Edit backend/.env to customise ports, model paths, etc.")
    else:
        warn("backend/.env.example not found — creating a minimal backend/.env")
        env_file.write_text(
            "# ScholarOS environment configuration\n"
            "SCHOLAROS_MODELS_DIR=models\n"
            "SCHOLAROS_MODEL_FILE=Phi-3-mini-4k-instruct-q4.gguf\n"
        )
        ok("backend/.env created with defaults.")


def print_summary() -> None:
    print()
    print(_c("1;32", "  ┌─ Setup complete! ────────────────────────────────────┐"))
    print(_c("1;32", "  │                                                       │"))
    print(_c("1;32", "  │  Next steps:                                          │"))
    print(_c("1;32", "  │                                                       │"))
    print(_c("1;32", "  │  1. Download a model (skip if already done):          │"))
    print(_c("1;32", "  │       make fetch-model                                │"))
    print(_c("1;32", "  │                                                       │"))
    print(_c("1;32", "  │  2. Start the full app (backend + frontend):           │"))
    print(_c("1;32", "  │       python start.py                                 │"))
    print(_c("1;32", "  │                                                       │"))
    print(_c("1;32", "  │  Developer (decoupled) workflow:                      │"))
    print(_c("1;32", "  │       python start.py --backend-only                  │"))
    print(_c("1;32", "  │       python start.py --frontend-only                 │"))
    print(_c("1;32", "  │                                                       │"))
    print(_c("1;32", "  └───────────────────────────────────────────────────────┘"))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print()
    print(_c("1;36", "  ScholarOS — Full Project Setup"))
    print(_c("36",   "  ────────────────────────────────"))
    print()

    check_python()
    check_node()
    setup_python_env()
    setup_frontend_deps()
    setup_env_file()
    print_summary()


if __name__ == "__main__":
    main()