@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 Document Control - Launcher v3.5.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.5.0 (Chainlit + Phoenix)
echo  Date: 2026-02-28
echo ========================================================
echo.
echo  Architecture (Chainlit):
echo    Chainlit App:       Port 3000 (Single App, Chat Profiles)
echo    Local LLM:          Ollama (Port 11434)
echo    Phoenix:            Port 6006 (LLM Observability)
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

:: Auto-update: always sync all packages from requirements.txt
echo [INFO] Checking dependencies...
"%QMS_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    echo [WARN] Some packages failed to install. App will continue with available features.
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
echo  [6] Exit
echo.
set /p choice="Enter choice (1-6): "

if "%choice%"=="1" goto start_chainlit
if "%choice%"=="2" goto start_all
if "%choice%"=="3" goto start_phoenix
if "%choice%"=="4" goto status
if "%choice%"=="5" goto stop_all
if "%choice%"=="6" goto end
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
set "PHOENIX_LAUNCHED=0"
netstat -ano 2>nul | find ":%PHOENIX_PORT%" | find "LISTENING" >nul
if not errorlevel 1 (
    echo      Phoenix already running on port %PHOENIX_PORT%
    set "PHOENIX_LAUNCHED=1"
) else (
    echo      Starting Phoenix on port %PHOENIX_PORT% (gRPC: %PHOENIX_GRPC_PORT%^)...
    start "AI-QMS Phoenix" cmd /c "cd /d "%PROJECT_DIR%" && "%QMS_PYTHON%" -m phoenix.server.main --port %PHOENIX_PORT% serve --grpc-port %PHOENIX_GRPC_PORT%"
    timeout /t 3 >nul
    set "PHOENIX_LAUNCHED=1"
)

:: Pass Phoenix port to Python app via environment variable (only if Phoenix is available)
if "%PHOENIX_LAUNCHED%"=="1" (
    set "PHOENIX_COLLECTOR_ENDPOINT=http://localhost:%PHOENIX_PORT%/v1/traces"
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

pause
goto end

:stop_all
echo.
echo ========================================================
echo  Stopping All Services...
echo ========================================================
echo.

:: Stop Chainlit (scan ports 3000-3010 for chainlit process)
echo [1/3] Stopping Chainlit App...
call :stop_chainlit_ports

:: Stop Phoenix (scan ports 6006-6016 for phoenix process)
echo [2/3] Stopping Phoenix...
call :stop_phoenix_ports


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
:: First check if another Chainlit is already running on any port 3000-3010
for /L %%p in (3000,1,3010) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":%%p " ^| find "LISTENING"') do (
        wmic process where "ProcessId=%%a" get CommandLine 2>nul | find "chainlit" >nul
        if not errorlevel 1 (
            echo [INFO] Chainlit is already running on port %%p (PID %%a^).
            echo [INFO] URL: http://localhost:%%p
            echo [INFO] If you want to restart, close the existing instance first.
            set "CHAINLIT_PORT=%%p"
            goto :port_display
        )
    )
)
:: No existing Chainlit found — find a free port
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
:: Subroutine: Find free ports for Phoenix
:: Sets %PHOENIX_PORT% (HTTP 6006-6016) and %PHOENIX_GRPC_PORT% (gRPC 4317-4327)
:: ============================================================
:find_free_phoenix_port
set "PHOENIX_PORT=6006"
set "PHOENIX_GRPC_PORT=4317"
:: Find free HTTP port
for /L %%p in (6006,1,6016) do (
    netstat -ano 2>nul | find ":%%p " | find "LISTENING" >nul
    if errorlevel 1 (
        set "PHOENIX_PORT=%%p"
        goto :phoenix_http_found
    )
)
set "PHOENIX_PORT=6006"
echo [WARN] Ports 6006-6016 are all in use! Phoenix may fail to start.
goto :phoenix_find_grpc

:phoenix_http_found
if "%PHOENIX_PORT%"=="6006" goto :phoenix_find_grpc
echo.
echo [WARN] Port 6006 is occupied by another process:
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":6006 " ^| find "LISTENING"') do (
    for /f "tokens=1,* delims=," %%n in ('wmic process where "ProcessId=%%a" get Name^,CommandLine /format:csv 2^>nul ^| find ","') do (
        echo        PID %%a — %%n
    )
)
echo [INFO] Auto-switching Phoenix HTTP to port %PHOENIX_PORT%
echo.

:phoenix_find_grpc
:: Find free gRPC port
for /L %%p in (4317,1,4327) do (
    netstat -ano 2>nul | find ":%%p " | find "LISTENING" >nul
    if errorlevel 1 (
        set "PHOENIX_GRPC_PORT=%%p"
        goto :phoenix_grpc_found
    )
)
set "PHOENIX_GRPC_PORT=4317"
echo [WARN] gRPC ports 4317-4327 are all in use! Phoenix may fail to start.
goto :phoenix_port_display

:phoenix_grpc_found
if "%PHOENIX_GRPC_PORT%"=="4317" goto :phoenix_port_display
echo [INFO] Auto-switching Phoenix gRPC to port %PHOENIX_GRPC_PORT%

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
