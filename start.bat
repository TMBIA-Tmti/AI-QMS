@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 Document Control - Launcher v3.4.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.4.0 (Chainlit + Phoenix)
echo  Date: 2026-02-25
echo ========================================================
echo.
echo  Architecture (v3.3.0 - Chainlit):
echo    Chainlit App:       Port 3000 (Single App, Chat Profiles)
echo    Local LLM:          Ollama (Port 11434)
echo    Phoenix:            Port 6006 (LLM Observability)
echo.
echo  v3.4.0 Features:
echo    - Chainlit UI (replaces Gradio dual-app)
echo    - Chat Profiles: Main Agent + Doc Control
echo    - Multilingual Signature/Stamp Detection (15+ languages)
echo    - Document Obsolete Feature
echo    - LLM Model List Auto-Update on Startup
echo    - 16 LLM Providers (OpenAI, Anthropic, Google, Ollama...)
echo    - /web Web Search with Source Credibility Ranking
echo    - 20-Language i18n Support
echo    - Arize Phoenix LLM Observability (Tracing, Prompts)
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
        goto :found_python
    )
)

:: Try conda activate approach
where conda >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('conda run -n QMS where python 2^>nul') do (
        if exist "%%i" (
            set "QMS_PYTHON=%%i"
            goto :found_python
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
    goto :found_python
)

echo [ERROR] Python not found!
echo.
echo Please install Python 3.11 and create the QMS environment:
echo   conda create -n QMS python=3.11 --yes
echo   conda activate QMS
echo   pip install -r requirements.txt
echo.
pause
exit /b 1

:found_python
echo [OK] Python: %QMS_PYTHON%
echo.

:: Auto-accept Conda Terms of Service (required since Miniconda 25.1.1)
:: This prevents CondaToSNonInteractiveError when creating/updating environments.
where conda >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Accepting Conda Terms of Service...
    call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >nul 2>&1
    call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >nul 2>&1
    call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2 >nul 2>&1
    echo [OK] Conda TOS accepted.
)
echo.

:: Auto-update: check for new/missing packages from requirements.txt
echo [INFO] Checking dependencies...
"%QMS_PYTHON%" -c "import phoenix; from openinference.instrumentation.litellm import LiteLLMInstrumentor" 2>nul
if errorlevel 1 (
    echo [INFO] New packages detected. Installing updates from requirements.txt...
    "%QMS_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" --quiet --disable-pip-version-check 2>nul
    if errorlevel 1 (
        echo [WARN] Some packages failed to install. App will continue with available features.
    ) else (
        echo [OK] Dependencies updated successfully.
    )
) else (
    echo [OK] All dependencies up to date.
)
echo.

:: Show menu
echo ========================================================
echo  Select startup mode:
echo ========================================================
echo.
echo  [1] Start Chainlit App (Port 3000) - RECOMMENDED
echo  [2] Start Chainlit + Ollama
echo  [3] Start Chainlit + Phoenix (Observability)
echo  [4] Check Services Status
echo  [5] Stop All Services
echo  [6] Legacy: Gradio Agents (Deprecated)
echo  [7] Exit
echo.
set /p choice="Enter choice (1-7): "

if "%choice%"=="1" goto start_chainlit
if "%choice%"=="2" goto start_all
if "%choice%"=="3" goto start_phoenix
if "%choice%"=="4" goto status
if "%choice%"=="5" goto stop_all
if "%choice%"=="6" goto legacy_gradio
if "%choice%"=="7" goto end
goto end

:start_chainlit
call :find_free_port
echo.
echo ========================================================
echo  Starting Chainlit App (Port %CHAINLIT_PORT%)
echo ========================================================
echo.
echo [INFO] Chainlit URL: http://localhost:%CHAINLIT_PORT%
echo [INFO] Auto-Reload: ON (code changes auto-restart)
echo [INFO] Press Ctrl+C to stop
echo.

:: Check chainlit
"%QMS_PYTHON%" -c "import chainlit; print(f'[OK] Chainlit {chainlit.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Chainlit not installed! Run: pip install chainlit
    pause
    goto end
)

:: Browser is auto-opened by Chainlit itself (no manual start needed)

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT% -w
goto check_error

:start_all
call :find_free_port
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
    where ollama >nul 2>&1
    if not errorlevel 1 (
        start "" ollama serve
    ) else (
        echo      [WARN] Ollama not found. Please install from https://ollama.com
    )
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
echo  Chainlit App:           http://localhost:%CHAINLIT_PORT%
echo  Ollama API:             http://localhost:11434
echo.
echo  Auto-Reload: ON (code changes auto-restart)
echo  Press Ctrl+C to stop Chainlit
echo ========================================================
echo.

:: Browser is auto-opened by Chainlit itself (no manual start needed)

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT% -w
goto check_error

:start_phoenix
call :find_free_port
call :find_free_phoenix_port
echo.
echo ========================================================
echo  Starting Chainlit + Phoenix (LLM Observability)...
echo ========================================================
echo.

:: 1. Start Phoenix server in background
echo [1/2] Starting Phoenix Observability Server...
netstat -ano 2>nul | find ":%PHOENIX_PORT%" | find "LISTENING" >nul
if not errorlevel 1 (
    echo      Phoenix already running on port %PHOENIX_PORT%
) else (
    echo      Starting Phoenix on port %PHOENIX_PORT%...
    start "AI-QMS Phoenix" cmd /c "cd /d "%PROJECT_DIR%" && "%QMS_PYTHON%" -m phoenix.server.main serve --port %PHOENIX_PORT%"
    timeout /t 3 >nul
)
echo.

:: 2. Start Chainlit
echo [2/2] Starting Chainlit App...
echo.
echo ========================================================
echo  All Services Started!
echo ========================================================
echo.
echo  Chainlit App:           http://localhost:%CHAINLIT_PORT%
echo  Phoenix Dashboard:      http://localhost:%PHOENIX_PORT%
echo.
echo  Auto-Reload: ON (code changes auto-restart)
echo  Press Ctrl+C to stop Chainlit
echo ========================================================
echo.

:: Open Phoenix dashboard only; Chainlit auto-opens its own browser
start "" "http://localhost:%PHOENIX_PORT%"

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT% -w
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
    "%QMS_PYTHON%" -m src.gradio_apps.main_agent
    goto check_error
)
if "%gradio_choice%"=="2" (
    echo [INFO] Starting Sub-Agent (Gradio)...
    start "" "http://localhost:7860"
    cd /d "%PROJECT_DIR%"
    "%QMS_PYTHON%" -m src.gradio_apps.doc_control
    goto check_error
)
if "%gradio_choice%"=="3" (
    echo [INFO] Starting Both Agents (Gradio)...
    start "AI-QMS Sub-Agent" cmd /c "cd /d "%PROJECT_DIR%" && "%QMS_PYTHON%" -m src.gradio_apps.doc_control"
    timeout /t 3 >nul
    start "" "http://localhost:3000"
    timeout /t 1 >nul
    start "" "http://localhost:7860"
    cd /d "%PROJECT_DIR%"
    "%QMS_PYTHON%" -m src.gradio_apps.main_agent
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

:: Check Chainlit (scan ports 3000-3010 for chainlit process)
echo [Chainlit App]
call :check_chainlit_status
if "%CHAINLIT_FOUND_PORT%"=="" (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:%CHAINLIT_FOUND_PORT%
)
echo.

:: Check Phoenix (scan ports 6006-6016 for phoenix process)
echo [Phoenix Observability]
call :check_phoenix_status
if "%PHOENIX_FOUND_PORT%"=="" (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:%PHOENIX_FOUND_PORT%
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

:: Stop Chainlit (scan ports 3000-3010 for chainlit process)
echo [1/4] Stopping Chainlit App...
call :stop_chainlit_ports

:: Stop Phoenix (scan ports 6006-6016 for phoenix process)
echo [2/4] Stopping Phoenix...
call :stop_phoenix_ports

:: Stop Legacy Sub-Agent (port 7860)
echo [3/4] Stopping Legacy Sub-Agent...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":7860" ^| find "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo      Done

:: Note about Ollama
echo [4/4] Ollama...
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
    echo.
    echo Troubleshooting:
    echo   1. Port in use: netstat -ano ^| find ":3000"
    echo   2. Missing deps: pip install -r requirements.txt
    echo   3. Python version: python --version (need 3.11+)
    echo.
)
pause
goto end

:: ============================================================
:: Subroutine: Find a free port for Chainlit (3000-3010)
:: Sets %CHAINLIT_PORT% to the first available port.
:: If port 3000 is occupied by another process, warns user.
:: ============================================================
:find_free_port
set "CHAINLIT_PORT=3000"
for /L %%p in (3000,1,3010) do (
    netstat -ano 2>nul | find ":%%p " | find "LISTENING" >nul
    if errorlevel 1 (
        set "CHAINLIT_PORT=%%p"
        goto :port_found
    )
)
:: All ports 3000-3010 occupied — use 3000 and let Chainlit report the error
set "CHAINLIT_PORT=3000"
echo [WARN] Ports 3000-3010 are all in use! Chainlit may fail to start.
echo [WARN] Please free a port: netstat -ano ^| find "LISTENING" ^| find ":300"
goto :port_display

:port_found
if "%CHAINLIT_PORT%"=="3000" goto :port_display

:: Port 3000 was occupied — show warning with details
echo.
echo [WARN] Port 3000 is occupied by another process:
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":3000 " ^| find "LISTENING"') do (
    for /f "tokens=1,* delims=," %%n in ('wmic process where "ProcessId=%%a" get Name^,CommandLine /format:csv 2^>nul ^| find ","') do (
        echo        PID %%a — %%n
    )
)
echo [INFO] Auto-switching Chainlit to port %CHAINLIT_PORT%
echo.

:port_display
exit /b 0

:: ============================================================
:: Subroutine: Check if Chainlit is running on ports 3000-3010
:: Sets %CHAINLIT_FOUND_PORT% if found, empty if not.
:: ============================================================
:check_chainlit_status
set "CHAINLIT_FOUND_PORT="
for /L %%p in (3000,1,3010) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%p" ^| find "LISTENING"') do (
        wmic process where "ProcessId=%%a" get CommandLine 2>nul | find "chainlit" >nul
        if not errorlevel 1 (
            set "CHAINLIT_FOUND_PORT=%%p"
            goto :check_chainlit_done
        )
    )
)
:check_chainlit_done
exit /b 0

:: ============================================================
:: Subroutine: Stop Chainlit on ports 3000-3010
:: ============================================================
:stop_chainlit_ports
for /L %%p in (3000,1,3010) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%p" ^| find "LISTENING"') do (
        wmic process where "ProcessId=%%a" get CommandLine 2>nul | find "chainlit" >nul
        if not errorlevel 1 (
            taskkill /PID %%a /F >nul 2>&1
        )
    )
)
echo      Done
exit /b 0

:: ============================================================
:: Subroutine: Find a free port for Phoenix (6006-6016)
:: Sets %PHOENIX_PORT% to the first available port.
:: ============================================================
:find_free_phoenix_port
set "PHOENIX_PORT=6006"
for /L %%p in (6006,1,6016) do (
    netstat -ano 2>nul | find ":%%p " | find "LISTENING" >nul
    if errorlevel 1 (
        set "PHOENIX_PORT=%%p"
        goto :phoenix_port_found
    )
)
set "PHOENIX_PORT=6006"
echo [WARN] Ports 6006-6016 are all in use! Phoenix may fail to start.
goto :phoenix_port_display

:phoenix_port_found
if "%PHOENIX_PORT%"=="6006" goto :phoenix_port_display
echo.
echo [WARN] Port 6006 is occupied by another process:
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":6006 " ^| find "LISTENING"') do (
    for /f "tokens=1,* delims=," %%n in ('wmic process where "ProcessId=%%a" get Name^,CommandLine /format:csv 2^>nul ^| find ","') do (
        echo        PID %%a — %%n
    )
)
echo [INFO] Auto-switching Phoenix to port %PHOENIX_PORT%
echo.

:phoenix_port_display
exit /b 0

:: ============================================================
:: Subroutine: Check if Phoenix is running on ports 6006-6016
:: Sets %PHOENIX_FOUND_PORT% if found, empty if not.
:: ============================================================
:check_phoenix_status
set "PHOENIX_FOUND_PORT="
for /L %%p in (6006,1,6016) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%p" ^| find "LISTENING"') do (
        wmic process where "ProcessId=%%a" get CommandLine 2>nul | find "phoenix" >nul
        if not errorlevel 1 (
            set "PHOENIX_FOUND_PORT=%%p"
            goto :check_phoenix_done
        )
    )
)
:check_phoenix_done
exit /b 0

:: ============================================================
:: Subroutine: Stop Phoenix on ports 6006-6016
:: ============================================================
:stop_phoenix_ports
for /L %%p in (6006,1,6016) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%p" ^| find "LISTENING"') do (
        wmic process where "ProcessId=%%a" get CommandLine 2>nul | find "phoenix" >nul
        if not errorlevel 1 (
            taskkill /PID %%a /F >nul 2>&1
        )
    )
)
echo      Done
exit /b 0

:end
echo.
echo Goodbye!
