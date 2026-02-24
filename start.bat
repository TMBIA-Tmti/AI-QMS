@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 Document Control - Launcher v3.0.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.0.0 (Chainlit)
echo  Date: 2026-02-11
echo ========================================================
echo.
echo  Architecture (v3.0.0 - Chainlit):
echo    Chainlit App:       Port 3000 (Single App, Chat Profiles)
echo    Local LLM:          Ollama (Port 11434)
echo.
echo  v3.0.0 Features:
echo    - Chainlit UI (replaces Gradio dual-app)
echo    - Chat Profiles: Main Agent + Doc Control
echo    - Multilingual Signature/Stamp Detection (15+ languages)
echo    - Document Obsolete Feature
echo    - LLM Model List Auto-Update on Startup
echo    - 16 LLM Providers (OpenAI, Anthropic, Google, Ollama...)
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

:: Show menu
echo ========================================================
echo  Select startup mode:
echo ========================================================
echo.
echo  [1] Start Chainlit App (Port 3000) - RECOMMENDED
echo  [2] Start Chainlit + Ollama
echo  [3] Check Services Status
echo  [4] Stop All Services
echo  [5] Legacy: Gradio Agents (Deprecated)
echo  [6] Exit
echo.
set /p choice="Enter choice (1-6): "

if "%choice%"=="1" goto start_chainlit
if "%choice%"=="2" goto start_all
if "%choice%"=="3" goto status
if "%choice%"=="4" goto stop_all
if "%choice%"=="5" goto legacy_gradio
if "%choice%"=="6" goto end
goto end

:start_chainlit
echo.
echo ========================================================
echo  Starting Chainlit App (Port 3000)
echo ========================================================
echo.
echo [INFO] Chainlit URL: http://localhost:3000
echo [INFO] Press Ctrl+C to stop
echo.

:: Check chainlit
"%QMS_ENV%\python.exe" -c "import chainlit; print(f'[OK] Chainlit {chainlit.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Chainlit not installed! Run: pip install chainlit
    pause
    goto end
)

echo [INFO] Opening browser automatically...
start "" "http://localhost:3000"

cd /d "%PROJECT_DIR%"
"%QMS_ENV%\python.exe" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0
goto check_error

:start_all
echo.
echo ========================================================
echo  Starting Chainlit + Ollama...
echo ========================================================
echo.

:: 1. Check Ollama
echo [1/2] Checking Ollama...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if errorlevel 1 (
    echo      Starting Ollama...
    start "" "C:\Users\MDR\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 3 >nul
) else (
    echo      Ollama already running
)

:: 2. Start Chainlit
echo [2/2] Starting Chainlit App...
echo.
echo ========================================================
echo  All Services Started!
echo ========================================================
echo.
echo  Chainlit App:           http://localhost:3000
echo  Ollama API:             http://localhost:11434
echo.
echo  Opening browser automatically...
echo  Press Ctrl+C to stop Chainlit
echo ========================================================
echo.

:: Auto-open browser
start "" "http://localhost:3000"

cd /d "%PROJECT_DIR%"
"%QMS_ENV%\python.exe" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0
goto check_error

:legacy_gradio
echo.
echo ========================================================
echo  [DEPRECATED] Gradio Agents (v2.7.0)
echo ========================================================
echo.
echo  NOTE: Gradio has been replaced by Chainlit in v3.0.0.
echo        Use option [1] for the new Chainlit interface.
echo.
echo  Continue with Gradio anyway? (y/n)
set /p legacy_choice="Choice: "
if /i not "%legacy_choice%"=="y" goto end

echo.
echo  [1] Main Agent Only (Port 3000)
echo  [2] Sub-Agent Only (Port 7860)
echo  [3] Both Agents
echo.
set /p gradio_choice="Enter choice (1-3): "

if "%gradio_choice%"=="1" (
    echo [INFO] Starting Main Agent (Gradio)...
    start "" "http://localhost:3000"
    cd /d "%PROJECT_DIR%"
    "%QMS_ENV%\python.exe" -m src.gradio_apps.main_agent
    goto check_error
)
if "%gradio_choice%"=="2" (
    echo [INFO] Starting Sub-Agent (Gradio)...
    start "" "http://localhost:7860"
    cd /d "%PROJECT_DIR%"
    "%QMS_ENV%\python.exe" -m src.gradio_apps.doc_control
    goto check_error
)
if "%gradio_choice%"=="3" (
    echo [INFO] Starting Both Agents (Gradio)...
    start "AI-QMS Sub-Agent" cmd /c "cd /d "%PROJECT_DIR%" && "%QMS_ENV%\python.exe" -m src.gradio_apps.doc_control"
    timeout /t 3 >nul
    start "" "http://localhost:3000"
    timeout /t 1 >nul
    start "" "http://localhost:7860"
    cd /d "%PROJECT_DIR%"
    "%QMS_ENV%\python.exe" -m src.gradio_apps.main_agent
    goto check_error
)
goto end

:status
echo.
echo ========================================================
echo  Services Status
echo ========================================================
echo.

:: Check Ollama
echo [Ollama]
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:11434
)
echo.

:: Check Chainlit (port 3000)
echo [Chainlit App]
netstat -ano 2>nul | find ":3000" | find "LISTENING" >nul
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:3000
)
echo.

:: Check Legacy Gradio Sub-Agent (port 7860)
echo [Legacy Sub-Agent - Gradio (Deprecated)]
netstat -ano 2>nul | find ":7860" | find "LISTENING" >nul
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:7860
)
echo.
pause
goto end

:stop_all
echo.
echo ========================================================
echo  Stopping All Services...
echo ========================================================
echo.

:: Stop Chainlit (port 3000)
echo [1/3] Stopping Chainlit App...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":3000" ^| find "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo      Done

:: Stop Legacy Sub-Agent (port 7860)
echo [2/3] Stopping Legacy Sub-Agent...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":7860" ^| find "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo      Done

:: Note about Ollama
echo [3/3] Ollama...
echo      (Ollama runs as system service, not stopping)

echo.
echo [SUCCESS] Services stopped.
echo.
pause
goto end

:check_error
if errorlevel 1 (
    echo.
    echo [ERROR] Application terminated with error.
    echo Check the messages above for details.
)
pause
goto end

:end
echo.
echo Goodbye!
