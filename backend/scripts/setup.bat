@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: Ensure we execute from the backend directory even if double-clicked
cd /d "%~dp0\.."

echo ============================================================
echo  ScholarOS - Windows Setup
echo ============================================================
echo.

:: ── 1. Check Python ─────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found on PATH.
    echo         Download Python 3.10+ from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during installation.
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Found Python %PY_VER%

:: Extract major.minor for wheel selection (e.g. "3.11.2" -> "311")
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do set PY_TAG=cp%%a%%b
echo [OK] Using wheel tag: %PY_TAG%
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

:: ── 4. Install llama-cpp-python ──────────────────────────────────────────
:: Build the wheel URL dynamically from the detected Python version tag so
:: this works for Python 3.10, 3.11, and 3.12 without manual edits.
echo [3/5] Installing llama-cpp-python (pre-compiled CPU wheel)...
echo       Python tag detected: %PY_TAG%
echo.

set LLAMA_VERSION=0.2.75
set WHEEL_URL=https://github.com/abetlen/llama-cpp-python/releases/download/v%LLAMA_VERSION%/llama_cpp_python-%LLAMA_VERSION%-%PY_TAG%-%PY_TAG%-win_amd64.whl

pip install "%WHEEL_URL%" --quiet
if %errorlevel% neq 0 (
    echo.
    echo [WARN] Pre-compiled wheel not found for %PY_TAG%.
    echo        Falling back to source build — requires Visual Studio Build Tools.
    echo        Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo        Select "Desktop development with C++" and re-run this script.
    echo.
    echo        Attempting source build (this will take several minutes)...
    pip install llama-cpp-python
    if !errorlevel! neq 0 (
        echo [ERROR] llama-cpp-python installation failed.
        echo         See https://github.com/abetlen/llama-cpp-python for instructions.
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
        echo [WARN] .env.example not found — skipping .env creation.
    )
) else (
    echo [OK] .env already exists — skipping.
)
echo.

:: ── 7. Download model ────────────────────────────────────────────────────
echo Checking for model weights...
if exist models\*.gguf (
    echo [OK] Model weights already present in .\models\ — skipping download.
) else (
    echo Downloading Phi-3 Mini weights (~2.3 GB). This may take a while...
    python scripts\download_model.py --model default
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Model download failed.
        echo         Retry with:  python scripts\download_model.py
        echo         Smaller alt: python scripts\download_model.py --model fallback
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
echo  With GNU make:
echo    make run
echo.
pause