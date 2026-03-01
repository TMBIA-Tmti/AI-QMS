@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 - Chainlit v3.5.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.5.0 (Chainlit + Phoenix)
echo  Date: 2026-02-28
echo ========================================================
echo.
echo  Architecture (Chainlit + Phoenix):
echo    Single App:         Chainlit (Port 3000)
echo    Chat Profiles:      Main Agent + Doc Control
echo    Local LLM:          Ollama (Port 11434)
echo    LLM Observability:  Phoenix (Port 6006)
echo.
echo  v3.5.0 - Regulatory Region Auto-Query, Disconnect Resilience, Eira AI Assistant
echo  v3.4.0 - Arize Phoenix LLM Observability, One-Click Launch + Auto-Update
echo  v3.3.0 - /web Web Search with Source Credibility Ranking
echo  v3.2.0 - 20-Language i18n, 16 LLM Providers, Chat Profiles
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
    call :find_free_phoenix_port
    :: Check if Phoenix is already running on detected port
    netstat -an 2>nul | find ":%PHOENIX_PORT%" | find "LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Starting Phoenix server on port %PHOENIX_PORT%...
        start "Phoenix Server" /min "%QMS_PYTHON%" -m phoenix.server.main serve --port %PHOENIX_PORT%
        timeout /t 3 >nul
        echo [OK] Phoenix started at http://localhost:%PHOENIX_PORT%
    ) else (
        echo [OK] Phoenix already running on port %PHOENIX_PORT%
    )
)

:: Pass Phoenix port to Python app via environment variable
:: This allows app.py to auto-connect to the correct Phoenix port
set "PHOENIX_COLLECTOR_ENDPOINT=http://localhost:%PHOENIX_PORT%/v1/traces"

:: Auto-detect free port for Chainlit
call :find_free_port

:: Start Chainlit
echo.
echo ========================================================
echo  Starting Chainlit App...
echo ========================================================
echo.
echo  Chainlit URL: http://localhost:%CHAINLIT_PORT%
echo  Phoenix URL:  http://localhost:%PHOENIX_PORT% (if available)
echo.
echo  Auto-Reload: ON (code changes auto-restart)
echo  Press Ctrl+C to stop
echo ========================================================
echo.

:: Browser is auto-opened by Chainlit itself (no manual start needed)

:: Run Chainlit from project directory
cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT% -w

if errorlevel 1 (
    echo.
    echo [ERROR] Chainlit terminated with error.
    echo Check the messages above for details.
    echo.
    echo Common issues:
    echo   1. Port %CHAINLIT_PORT% already in use
    echo   2. Missing dependencies (run: pip install -r requirements.txt)
    echo   3. Chainlit version issue (need 2.9.4+)
    echo.
)
pause
goto :eof

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
