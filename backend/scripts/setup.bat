@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: Ensure we are executing from the 'backend' directory, even if double-clicked
cd /d "%~dp0\.."

echo ============================================================
echo  ScholarOS - Windows Setup
echo ============================================================
echo.

:: ── 1. Check Python is available ────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found on PATH.
    echo         Download Python 3.10+ from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during installation.
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Found Python %PY_VER%
echo.

:: ── 2. Create virtual environment ───────────────────────────────────────
echo [1/5] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    exit /b %errorlevel%
)
echo [OK] Virtual environment created.
echo.

:: ── 3. Activate and upgrade pip ─────────────────────────────────────────
echo [2/5] Activating environment and upgrading pip...
call venv\Scripts\activate
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b %errorlevel%
)
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo [ERROR] pip upgrade failed.
    exit /b %errorlevel%
)
echo [OK] pip ready.
echo.

:: ── 4. Install llama-cpp-python (pre-compiled, no C++ compiler needed) ──
echo [3/5] Installing llama-cpp-python (pre-compiled CPU wheel)...
echo       This avoids the need for Visual Studio Build Tools.
echo.

set WHEEL_URL=https://github.com/abetlen/llama-cpp-python/releases/download/v0.2.75/llama_cpp_python-0.2.75-cp310-cp310-win_amd64.whl

pip install "%WHEEL_URL%" --quiet
if %errorlevel% neq 0 (
    echo.
    echo [WARN] Pre-compiled wheel install failed.
    echo        Falling back to source build. This requires Visual Studio Build Tools.
    echo        Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo        Select "Desktop development with C++" workload, then re-run this script.
    echo.
    echo        Attempting source build (this will take several minutes)...
    pip install llama-cpp-python
    if !errorlevel! neq 0 (
        echo [ERROR] llama-cpp-python installation failed.
        echo         See https://github.com/abetlen/llama-cpp-python for manual instructions.
        exit /b 1
    )
)
echo [OK] llama-cpp-python installed.
echo.

:: ── 5. Install remaining dependencies ───────────────────────────────────
echo [4/5] Installing ScholarOS core dependencies...
pip install -e ".[dev]" --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    echo         Check the error above and ensure you have a working internet connection.
    exit /b %errorlevel%
)
echo [OK] All dependencies installed.
echo.

:: ── 6. Environment variables ─────────────────────────────────────────────
echo [5/5] Setting up environment config...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [OK] Created .env from .env.example
    ) else (
        echo [WARN] .env.example not found -- skipping .env creation.
    )
) else (
    echo [OK] .env already exists -- skipping.
)
echo.

:: ── 7. Download model (skip if already present) ──────────────────────────
echo Checking for model weights...
if exist models\*.gguf (
    echo [OK] Model weights already present in .\models\ -- skipping download.
) else (
    echo Downloading Phi-3 Mini weights (~2.3 GB). This may take a while...
    python scripts\download_model.py --model default
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Model download failed.
        echo         You can retry later with:  python scripts\download_model.py
        echo         Or download a smaller model with:  python scripts\download_model.py --model fallback
        exit /b %errorlevel%
    )
)
echo.

:: ── Done ─────────────────────────────────────────────────────────────────
echo ============================================================
echo  Setup complete!
echo ============================================================
echo.
echo  To start the ScholarOS backend:
echo.
echo    1. Activate the environment (if not already active):
echo       venv\Scripts\activate
echo.
echo    2. Start the server:
echo       python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
echo.
echo  If you have GNU make installed:
echo    make run
echo.
pause