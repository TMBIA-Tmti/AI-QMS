@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 - Chainlit v3.4.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.4.0 (Chainlit + Phoenix)
echo  Date: 2026-02-25
echo ========================================================
echo.
echo  Architecture (v3.4.0 - Chainlit + Phoenix):
echo    Single App:         Chainlit (Port 3000)
echo    Chat Profiles:      Main Agent + Doc Control
echo    Local LLM:          Ollama (Port 11434)
echo    LLM Observability:  Phoenix (Port 6006)
echo.
echo  v3.4.0 Features:
echo    - Chainlit UI (replaces Gradio dual-app)
echo    - Chat Profiles: Main Agent + Doc Control
echo    - Arize Phoenix LLM Observability (auto-start)
echo    - OpenTelemetry Auto-Instrumentation
echo    - Multilingual Signature/Stamp Detection (15+ languages)
echo    - Document Obsolete Feature
echo    - LLM Model List Auto-Update on Startup
echo    - 16 LLM Providers (OpenAI, Anthropic, Google, Ollama...)
echo    - /web Web Search with Source Credibility Ranking
echo    - 20-Language i18n Support
echo    - File Upload with OCR Processing
echo    - Audit Log with SHA-256 Hash Chain
echo.
echo ========================================================

:: Set paths
set "PROJECT_DIR=%~dp0"
set "QMS_PYTHON="

:: Auto-detect Conda QMS environment
for %%P in (
    "%USERPROFILE%\miniconda3\envs\QMS\python.exe"
    "%USERPROFILE%\anaconda3\envs\QMS\python.exe"
    "%LOCALAPPDATA%\miniconda3\envs\QMS\python.exe"
    "C:\miniconda3\envs\QMS\python.exe"
    "C:\ProgramData\miniconda3\envs\QMS\python.exe"
    "C:\ProgramData\anaconda3\envs\QMS\python.exe"
) do (
    if exist %%P (
        set "QMS_PYTHON=%%~P"
        goto :found
    )
)

:: Try conda activate approach
where conda >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('conda run -n QMS where python 2^>nul') do (
        if exist "%%i" (
            set "QMS_PYTHON=%%i"
            goto :found
        )
    )
)

:: Try system Python as fallback
where python >nul 2>&1
if not errorlevel 1 (
    echo [WARN] QMS conda environment not found.
    echo [WARN] Using system Python. Some features may not work.
    echo.
    set "QMS_PYTHON=python"
    goto :found
)

echo [ERROR] Python not found!
echo.
echo Please create QMS environment:
echo   conda create -n QMS python=3.11 --yes
echo   conda activate QMS
echo   pip install -r requirements.txt
echo.
pause
exit /b 1

:found
echo [OK] Python: %QMS_PYTHON%
echo.

:: Check if chainlit is installed
"%QMS_PYTHON%" -c "import chainlit; print(f'[OK] Chainlit version: {chainlit.__version__}')" 2>nul
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
    where ollama >nul 2>&1
    if not errorlevel 1 (
        start "" ollama serve
    ) else (
        echo [WARN] Ollama not found. Please install from https://ollama.com
    )
    timeout /t 3 >nul
) else (
    echo [OK] Ollama already running
)

:: Check and Start Phoenix
echo.
echo [INFO] Checking Phoenix LLM Observability...
"%QMS_PYTHON%" -c "import phoenix; print(f'[OK] Phoenix version: {phoenix.__version__}')" 2>nul
if errorlevel 1 (
    echo [WARN] Phoenix not installed. LLM observability will be disabled.
    echo [WARN] Install with: pip install arize-phoenix arize-phoenix-otel openinference-instrumentation-litellm
    echo.
) else (
    :: Check if Phoenix is already running on port 6006
    netstat -an 2>nul | find ":6006" | find "LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Starting Phoenix server on port 6006...
        start "Phoenix Server" /min "%QMS_PYTHON%" -m phoenix.server.main serve --port 6006
        timeout /t 3 >nul
        echo [OK] Phoenix started at http://localhost:6006
    ) else (
        echo [OK] Phoenix already running on port 6006
    )
)

:: Start Chainlit
echo.
echo ========================================================
echo  Starting Chainlit App...
echo ========================================================
echo.
echo  Chainlit URL: http://localhost:3000
echo  Phoenix URL:  http://localhost:6006 (if available)
echo.
echo  Opening browser automatically...
echo  Press Ctrl+C to stop
echo ========================================================
echo.

:: Auto-open browser after short delay
start "" "http://localhost:3000"

:: Run Chainlit from project directory
cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0

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
