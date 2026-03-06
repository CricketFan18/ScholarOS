#!/usr/bin/env python3
"""
start.py
--------
Unified launcher for ScholarOS — starts the FastAPI backend and the Vite
frontend in a single command and opens the app in the default browser.

Usage:
    python start.py                  # start everything (default)
    python start.py --backend-only   # API server only (no frontend)
    python start.py --frontend-only  # Vite dev server only
    python start.py --no-browser     # don't auto-open the browser
    python start.py --port 9000      # custom backend port (default: 8000)

Developer workflow (decoupled):
    Terminal 1: python start.py --backend-only
    Terminal 2: python start.py --frontend-only

Both processes are managed as subprocesses of this script. Ctrl-C (or closing
the terminal) sends SIGINT to this process, which propagates to both children
so nothing is left dangling in the background.

Prerequisites:
    • Python 3.10+
    • Node.js 18+ and npm (only needed if running the frontend)
    • A model in ./backend/models/ (run `make fetch-model` first)
    • Python venv with dependencies installed (`python setup.py` or `make install`)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — all resolved relative to this file so the script works regardless
# of which directory the user invokes it from.
# ---------------------------------------------------------------------------

ROOT_DIR     = Path(__file__).parent.resolve()
BACKEND_DIR  = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR     = ROOT_DIR / "venv"

# Platform-aware path to the Python interpreter inside the project venv.
# Using the venv's interpreter directly means the script works even when the
# user hasn't run `source venv/bin/activate` in their shell.
if platform.system() == "Windows":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"

# ---------------------------------------------------------------------------
# ANSI colour helpers (no-op on Windows unless the terminal declares TERM)
# ---------------------------------------------------------------------------

_USE_COLOUR = platform.system() != "Windows" or os.environ.get("TERM")

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def info(msg: str)    -> None: print(_c("36",   f"[ScholarOS] {msg}"))
def success(msg: str) -> None: print(_c("32",   f"[ScholarOS] ✓ {msg}"))
def warn(msg: str)    -> None: print(_c("33",   f"[ScholarOS] ⚠ {msg}"))
def error(msg: str)   -> None: print(_c("31",   f"[ScholarOS] ✗ {msg}"), file=sys.stderr)


# ---------------------------------------------------------------------------
# WSL detection
# ---------------------------------------------------------------------------

def _get_host_ip() -> str:
    """
    Detect the correct IP address to use for the backend API URL.

    On WSL (Windows Subsystem for Linux), 'localhost' in the Windows browser
    does not route to the WSL network interface. We detect WSL by checking
    /proc/version and return the eth0 IP so Vite's proxy and the frontend
    client both point at the reachable address.

    On native Linux and macOS, 'localhost' works fine.

    Returns:
        IP string — either the WSL eth0 address or '127.0.0.1'.
    """
    try:
        version = Path("/proc/version").read_text().lower()
        if "microsoft" in version or "wsl" in version:
            # WSL detected — get eth0 IP
            result = subprocess.check_output(
                ["ip", "addr", "show", "eth0"], text=True
            )
            for line in result.splitlines():
                line = line.strip()
                if line.startswith("inet ") and "/" in line:
                    ip = line.split()[1].split("/")[0]
                    warn(f"WSL detected — using host IP {ip} instead of localhost")
                    warn("Open the app at  http://{ip}:5173  in your Windows browser")
                    return ip
    except Exception:
        pass
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def check_venv() -> None:
    """Abort with a clear message if the virtual environment doesn't exist yet."""
    if not VENV_PYTHON.exists():
        error("Virtual environment not found.")
        error("Run:  python setup.py   (or: make install)")
        sys.exit(1)


def check_node() -> tuple[str, str]:
    """
    Verify that Node.js (>=18) and npm are available on PATH.

    Returns:
        Tuple of (node_version, npm_version) strings.

    Raises:
        SystemExit: If node/npm are missing or the Node version is too old.
    """
    node_path = shutil.which("node")
    npm_path  = shutil.which("npm")

    if not node_path:
        error("Node.js not found on PATH.")
        _print_node_install_hint()
        sys.exit(1)

    if not npm_path:
        error("npm not found on PATH. It normally ships bundled with Node.js.")
        _print_node_install_hint()
        sys.exit(1)

    try:
        raw   = subprocess.check_output(["node", "--version"], text=True).strip()
        major = int(raw.lstrip("v").split(".")[0])
        if major < 18:
            error(f"Node.js {raw} is too old — ScholarOS requires v18 or newer.")
            _print_node_install_hint()
            sys.exit(1)
        node_ver = raw
    except (subprocess.CalledProcessError, ValueError):
        error("Could not determine Node.js version.")
        sys.exit(1)

    npm_ver = subprocess.check_output(["npm", "--version"], text=True).strip()
    return node_ver, npm_ver


def _print_node_install_hint() -> None:
    system = platform.system()
    if system == "Darwin":
        warn("Install Node.js via Homebrew:  brew install node")
        warn("Or download from:              https://nodejs.org/en/download")
    elif system == "Linux":
        warn("Install via your package manager:")
        warn("  Ubuntu/Debian:  sudo apt install nodejs npm")
        warn("  Fedora:         sudo dnf install nodejs npm")
        warn("  Arch:           sudo pacman -S nodejs npm")
        warn("  nvm (any distro): https://github.com/nvm-sh/nvm")
    else:
        warn("Download Node.js from:  https://nodejs.org/en/download")


def check_model() -> None:
    """Warn (but don't abort) if no .gguf model weights are present."""
    models_dir = BACKEND_DIR / "models"
    if not models_dir.exists() or not any(models_dir.glob("*.gguf")):
        warn("No model weights found in ./backend/models/")
        warn("The backend will start but cannot answer questions until a model is present.")
        warn("Run:  make fetch-model")


def install_frontend_deps() -> None:
    """Run `npm install` inside frontend/ if node_modules is absent."""
    if not (FRONTEND_DIR / "node_modules").exists():
        info("Frontend dependencies not installed — running npm install …")
        try:
            subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
            success("npm install complete.")
        except subprocess.CalledProcessError as exc:
            error(f"npm install failed: {exc}")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

_procs: list[subprocess.Popen] = []   # global so the signal handler can reach all children


def _shutdown(signum=None, frame=None) -> None:
    """
    Gracefully terminate all child processes on Ctrl-C or SIGTERM.

    Sends SIGTERM first (allowing each process to flush and clean up), then
    force-kills any that haven't exited within a 5-second grace period.
    """
    print()   # newline after the terminal's ^C echo
    info("Shutting down …")
    for proc in _procs:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    deadline = time.time() + 5
    for proc in _procs:
        remaining = deadline - time.time()
        if remaining > 0:
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()

    success("All processes stopped. Goodbye!")
    sys.exit(0)


def _stream_output(proc: subprocess.Popen, prefix: str, colour: str) -> None:
    """
    Forward a subprocess's stdout to our stdout with a coloured prefix tag.
    Runs in a daemon thread so it doesn't block the main thread.
    """
    assert proc.stdout is not None
    for line in proc.stdout:
        print(_c(colour, f"[{prefix}]"), line, end="")


def start_backend(port: int) -> subprocess.Popen:
    """
    Launch the Uvicorn ASGI server from the backend/ directory.

    We set cwd=BACKEND_DIR so that all relative paths inside the application
    (data/chroma_db, models/, data/uploads/) resolve correctly without
    requiring every internal path to be made absolute.
    """
    cmd = [
        str(VENV_PYTHON), "-m", "uvicorn",
        "api.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--reload",
    ]
    info(f"Starting backend   →  http://localhost:{port}")
    proc = subprocess.Popen(
        cmd,
        cwd=BACKEND_DIR,            # run from backend/ so relative paths resolve
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # merge stderr so startup errors appear inline
        text=True,
        bufsize=1,                  # line-buffered for immediate output
    )
    _procs.append(proc)
    threading.Thread(target=_stream_output, args=(proc, "backend", "34"), daemon=True).start()
    return proc


def start_frontend(backend_port: int) -> subprocess.Popen:
    """
    Launch the Vite dev server from the frontend/ directory.

    On WSL, 'localhost' in a Windows browser does not route to the WSL
    network interface. We detect the eth0 IP and use that instead, and write
    it to frontend/.env.local so the axios client picks it up automatically.
    This file is recreated on every launch so it always reflects the current
    WSL IP (which changes on every WSL restart).
    """
    host_ip = _get_host_ip()
    api_url = f"http://{host_ip}:{backend_port}/api"

    env_local = FRONTEND_DIR / ".env.local"
    env_local.write_text(f"VITE_API_URL={api_url}\n")

    env = {
        **os.environ,
        "VITE_API_URL": api_url,
    }
    info(f"Starting frontend  →  http://{host_ip}:5173")
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    _procs.append(proc)
    threading.Thread(target=_stream_output, args=(proc, "frontend", "35"), daemon=True).start()
    return proc



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScholarOS unified launcher — starts backend and frontend together.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--backend-only",  action="store_true", help="Start only the FastAPI backend")
    parser.add_argument("--frontend-only", action="store_true", help="Start only the Vite frontend")
    parser.add_argument("--no-browser",    action="store_true", help="Don't open the browser automatically")
    parser.add_argument("--port", type=int, default=8000, metavar="PORT",
                        help="Backend port (default: 8000)")
    args = parser.parse_args()

    if args.backend_only and args.frontend_only:
        error("--backend-only and --frontend-only are mutually exclusive.")
        sys.exit(1)

    run_backend  = not args.frontend_only
    run_frontend = not args.backend_only

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print()
    print(_c("1;36", "  ╔══════════════════════════════════╗"))
    print(_c("1;36", "  ║        ScholarOS Launcher         ║"))
    print(_c("1;36", "  ╚══════════════════════════════════╝"))
    print()

    # ── Preflight ──────────────────────────────────────────────────────────
    if run_backend:
        check_venv()
        check_model()

    if run_frontend:
        node_ver, npm_ver = check_node()
        success(f"Node.js {node_ver}  •  npm {npm_ver}")
        install_frontend_deps()

    # ── Launch ─────────────────────────────────────────────────────────────
    if run_backend:
        start_backend(args.port)
        time.sleep(1.5)   # give Uvicorn time to bind before printing the summary

    if run_frontend:
        start_frontend(args.port)
        time.sleep(3)     # give Vite time to bundle before opening the browser

    # ── Summary banner ─────────────────────────────────────────────────────
    print()
    print(_c("1;32", "  ┌─ ScholarOS is running ──────────────────────────┐"))
    if run_backend:
        print(_c("1;32", f"  │  Backend   →  http://localhost:{args.port}             │"))
    if run_frontend:
        print(_c("1;32",  "  │  Frontend  →  http://localhost:5173             │"))
    print(_c("1;32",      "  │                                                 │"))
    print(_c("1;32",      "  │  Press Ctrl-C to stop all servers               │"))
    print(_c("1;32",      "  └─────────────────────────────────────────────────┘"))
    print()

    # ── Open browser ───────────────────────────────────────────────────────
    if run_frontend and not args.no_browser:
        try:
            webbrowser.open("http://localhost:5173")
        except Exception:
            warn("Could not open browser automatically. Visit http://localhost:5173 manually.")

    # ── Wait — block until a child dies or the user presses Ctrl-C ─────────
    try:
        while True:
            for proc in _procs:
                if proc.poll() is not None:
                    error(f"A child process exited unexpectedly (code {proc.returncode}).")
                    _shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()