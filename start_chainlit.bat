@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 - Chainlit v3.0.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.0.0 (Chainlit)
echo  Date: 2026-02-11
echo ========================================================
echo.
echo  Architecture (v3.0.0 - Chainlit):
echo    Single App:         Chainlit (Port 3000)
echo    Chat Profiles:      Main Agent + Doc Control
echo    Local LLM:          Ollama (Port 11434)
echo.
echo  v3.0.0 Features:
echo    - Chainlit UI (replaces Gradio dual-app)
echo    - Chat Profiles: Main Agent + Doc Control
echo    - Multilingual Signature/Stamp Detection (15+ languages)
echo    - Document Obsolete Feature
echo    - LLM Model List Auto-Update on Startup
echo    - 16 LLM Providers (OpenAI, Anthropic, Google, Ollama...)
echo    - File Upload with OCR Processing
echo    - Audit Log with SHA-256 Hash Chain
echo.
echo ========================================================

:: Set paths
set "CONDA_PATH=C:\Users\MDR\miniconda3"
set "QMS_ENV=%CONDA_PATH%\envs\QMS"
set "PROJECT_DIR=%~dp0"

:: Check if QMS environment exists
if not exist "%QMS_ENV%\python.exe" (
    echo [ERROR] QMS environment not found!
    echo.
    echo Please create it with:
    echo   conda create -n QMS python=3.11 --yes
    echo   conda activate QMS
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [OK] QMS Environment: %QMS_ENV%
echo.

:: Check if chainlit is installed
"%QMS_ENV%\python.exe" -c "import chainlit; print(f'[OK] Chainlit version: {chainlit.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Chainlit not installed!
    echo.
    echo Please install it with:
    echo   conda activate QMS
    echo   pip install chainlit
    echo.
    pause
    exit /b 1
)

:: Check Ollama
echo.
echo [INFO] Checking Ollama...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if errorlevel 1 (
    echo [INFO] Starting Ollama...
    start "" "C:\Users\MDR\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 3 >nul
) else (
    echo [OK] Ollama already running
)

:: Start Chainlit
echo.
echo ========================================================
echo  Starting Chainlit App...
echo ========================================================
echo.
echo  URL: http://localhost:3000
echo.
echo  Opening browser automatically...
echo  Press Ctrl+C to stop
echo ========================================================
echo.

:: Auto-open browser after short delay
start "" "http://localhost:3000"

:: Run Chainlit from project directory
cd /d "%PROJECT_DIR%"
"%QMS_ENV%\python.exe" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0

if errorlevel 1 (
    echo.
    echo [ERROR] Chainlit terminated with error.
    echo Check the messages above for details.
    echo.
    echo Common issues:
    echo   1. Port 3000 already in use
    echo   2. Missing dependencies (run: pip install -r requirements.txt)
    echo   3. Chainlit version issue (need 2.9.4+)
    echo.
)
pause
