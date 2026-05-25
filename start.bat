@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 Document Control - Launcher v3.6.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.6.0 (Chainlit + Phoenix)
echo  Date: 2026-04-19
echo ========================================================
echo.
echo  Architecture (Chainlit):
echo    Chainlit App:       Port 3000 (Single App, Chat Profiles)
echo    Local LLM:          Ollama (Port 11434)
echo    Phoenix:            Port 6006 (LLM Observability)
echo.
echo  v3.6.0 - Full i18n: zh/ja/en across all UI, reports, Word/Excel, pipeline, ISO clauses
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

:: ─── CMD session log ─────────────────────────────────────────────────────────
if not exist "%PROJECT_DIR%logs\cmd" mkdir "%PROJECT_DIR%logs\cmd"
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "SESSION_STAMP=%%t"
set "CMD_LOG=%PROJECT_DIR%logs\cmd\%SESSION_STAMP%_start.log"
>> "%CMD_LOG%" echo =============================================
>> "%CMD_LOG%" echo SESSION START: %SESSION_STAMP%
>> "%CMD_LOG%" echo Script: start.bat
>> "%CMD_LOG%" echo =============================================
:: ─────────────────────────────────────────────────────────────────────────────

:: ── No-disconnect settings ────────────────────────────────────────────────────
:: UVICORN_TIMEOUT_KEEP_ALIVE=0  → HTTP keep-alive never expires (fixes HTML page drop)
:: UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=300 → allow 5 min for graceful shutdown
:: These env vars are inherited by all child processes (Chainlit, Phoenix)
set "UVICORN_TIMEOUT_KEEP_ALIVE=0"
set "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=300"
:: ─────────────────────────────────────────────────────────────────────────────

:: Auto-accept Conda Terms of Service (required since Miniconda 25.1.1)
where conda >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Accepting Conda Terms of Service...
    call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main < nul >nul 2>&1
    call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r < nul >nul 2>&1
    call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2 < nul >nul 2>&1
    echo [OK] Conda TOS accepted.
)
echo.

:: Auto-update: always sync all packages from requirements.txt
echo [INFO] Checking dependencies...
"%QMS_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" --quiet --disable-pip-version-check < nul 2>nul
if errorlevel 1 (
    echo [WARN] Some packages failed to install. App will continue with available features.
) else (
    echo [OK] All dependencies up to date.
)
echo.

:: Auto-cleanup: Kill orphaned Chainlit Python processes on ports 3000-3010
:: This prevents port conflicts from previous sessions that were closed improperly
set "KILLED_ANY=0"
for /L %%p in (3000,1,3010) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p .*LISTENING"') do (
        tasklist /FI "PID eq %%a" /FO CSV /NH 2>nul | findstr /I "python" >nul
        if not errorlevel 1 (
            echo [INFO] Found orphaned Python process on port %%p ^(PID %%a^). Cleaning up...
            taskkill /PID %%a /F >nul 2>&1
            set "KILLED_ANY=1"
        )
    )
)
:: Wait for OS to release ports after kill (TIME_WAIT state)
:: Polls every second until all ports 3000-3010 are free, or 10s has elapsed.
:: NOTE: Labels inside compound if-blocks are invalid in CMD — loop lives at top level.
if not "%KILLED_ANY%"=="1" goto :wait_ports_done
echo [INFO] Waiting for ports to be released...
set "WAIT_SEC=0"

:wait_ports_loop
set "PORTS_BUSY=0"
for /L %%p in (3000,1,3010) do (
    netstat -ano 2>nul | findstr ":%%p .*LISTENING" >nul
    if not errorlevel 1 set "PORTS_BUSY=1"
)
if "%PORTS_BUSY%"=="0" goto :wait_ports_done
if %WAIT_SEC% GEQ 10 goto :wait_ports_done
timeout /t 1 /nobreak >nul
set /a WAIT_SEC+=1
goto :wait_ports_loop

:wait_ports_done

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
echo [INFO] Auto-Reload: OFF (disabled to prevent UI disconnect during analysis)
echo [INFO] Press Ctrl+C to stop
echo.

:: Check chainlit
"%QMS_PYTHON%" -c "import chainlit; print(f'[OK] Chainlit {chainlit.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Chainlit not installed! Run: pip install chainlit
    pause
    goto end
)

cd /d "%PROJECT_DIR%"
set "CHAINLIT_RESTARTS=0"

:main_watchdog_loop
if %CHAINLIT_RESTARTS% GTR 0 (
    echo.
    echo [WATCHDOG] Chainlit crashed ^(run %CHAINLIT_RESTARTS%^). Restarting in 5s...
    >> "%CMD_LOG%" echo [Chainlit] Run %CHAINLIT_RESTARTS% CRASHED at %date% %time%
    timeout /t 5 /nobreak >nul
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%CHAINLIT_PORT% .*LISTENING"') do (
        tasklist /FI "PID eq %%a" /FO CSV /NH 2>nul | findstr /I "python" >nul
        if not errorlevel 1 taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)
set /a CHAINLIT_RESTARTS+=1
>> "%CMD_LOG%" echo [Chainlit] Run %CHAINLIT_RESTARTS% starting at %date% %time% on port %CHAINLIT_PORT%
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT%
if errorlevel 1 goto main_watchdog_loop
>> "%CMD_LOG%" echo SESSION END (clean stop): %date% %time%
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
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | findstr /I "ollama.exe" >NUL
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
echo  Chainlit App:           http://localhost:%CHAINLIT_PORT%
echo  Ollama API:             http://localhost:11434
echo.
echo  Press Ctrl+C to stop Chainlit
echo.

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT%
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
netstat -ano 2>nul | findstr ":%PHOENIX_PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo      Phoenix already running on port %PHOENIX_PORT%
    set "PHOENIX_LAUNCHED=1"
) else (
    echo      Starting Phoenix on port %PHOENIX_PORT% (gRPC: %PHOENIX_GRPC_PORT%^)...
    if not exist "%PROJECT_DIR%logs\phoenix" mkdir "%PROJECT_DIR%logs\phoenix"
    set "PHOENIX_LOG=%PROJECT_DIR%logs\phoenix\%SESSION_STAMP%_phoenix.log"
    echo [LOG] Phoenix log: logs\phoenix\%SESSION_STAMP%_phoenix.log
    >> "%CMD_LOG%" echo [Phoenix] Starting on port %PHOENIX_PORT% - log: logs\phoenix\%SESSION_STAMP%_phoenix.log
    start "AI-QMS Phoenix" /min cmd /c ""%QMS_PYTHON%" -m phoenix.server.main serve --grpc-port %PHOENIX_GRPC_PORT% >> "%PHOENIX_LOG%" 2>&1"
    call :wait_for_phoenix
)

:: Pass Phoenix port to Python app via environment variable
if "%PHOENIX_LAUNCHED%"=="1" (
    set "PHOENIX_COLLECTOR_ENDPOINT=http://localhost:%PHOENIX_PORT%/v1/traces"
)
echo.

:: 2. Start Chainlit
echo [2/2] Starting Chainlit App...
echo.
echo  Chainlit App:           http://localhost:%CHAINLIT_PORT%
echo  Phoenix Dashboard:      http://localhost:%PHOENIX_PORT%
echo.
echo  Press Ctrl+C to stop Chainlit
echo.

start "" "http://localhost:%PHOENIX_PORT%"

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT%
goto check_error


:status
echo.
echo ========================================================
echo  Services Status
echo ========================================================
echo.

echo [Ollama]
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | findstr /I "ollama.exe" >NUL
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:11434
)
echo.

echo [Chainlit App]
netstat -ano 2>nul | findstr ":3000 .*LISTENING" >nul
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:3000
)
echo.

echo [Phoenix Observability]
netstat -ano 2>nul | findstr ":6006 .*LISTENING" >nul
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:6006
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

:: Stop Python processes on Chainlit ports (3000-3010)
echo [1/3] Stopping Chainlit App...
for /L %%p in (3000,1,3010) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p .*LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
    )
)
echo      Done

:: Stop Python processes on Phoenix ports (6006-6016)
echo [2/3] Stopping Phoenix...
for /L %%p in (6006,1,6016) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p .*LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
    )
)
echo      Done

echo [3/3] Ollama...
echo      (Ollama runs as system service, not stopping)

echo.
echo [SUCCESS] Services stopped.
echo.
pause
goto end

:check_error
echo.
echo ========================================================
if errorlevel 1 (
    echo [ERROR] Application terminated with error.
    echo.
    echo Troubleshooting:
    echo   1. Port in use: netstat -ano ^| findstr ":3000"
    echo   2. Missing deps: pip install -r requirements.txt
    echo   3. Python version: python --version (need 3.11+)
) else (
    echo [INFO] Application has stopped.
)
echo ========================================================
echo.
echo Press any key to exit...
pause >nul
goto end

:: ============================================================
:: Subroutine: Find a free port for Chainlit (3000-3010)
:: Uses individual checks to avoid for/L + goto batch parser bugs
:: ============================================================
:find_free_port
set "CHAINLIT_PORT=3000"
call :check_port 3000 && goto :port_found
call :check_port 3001 && goto :port_found
call :check_port 3002 && goto :port_found
call :check_port 3003 && goto :port_found
call :check_port 3004 && goto :port_found
call :check_port 3005 && goto :port_found
call :check_port 3006 && goto :port_found
call :check_port 3007 && goto :port_found
call :check_port 3008 && goto :port_found
call :check_port 3009 && goto :port_found
call :check_port 3010 && goto :port_found
set "CHAINLIT_PORT=3000"
echo [WARN] Ports 3000-3010 are all in use! Chainlit may fail to start.
goto :port_display

:port_found
:: Write chosen port to data/.chainlit_port so other tools can discover it
if not exist "data" mkdir data
echo %CHAINLIT_PORT%> "data\.chainlit_port"
if "%CHAINLIT_PORT%"=="3000" goto :port_display
echo.
echo [WARN] Port 3000 is occupied. Auto-switching to port %CHAINLIT_PORT%
echo.

:port_display
exit /b 0

:: Check if a single port is free. Sets CHAINLIT_PORT and returns 0 if free, 1 if busy.
:check_port
netstat -ano 2>nul | findstr ":%1 .*LISTENING" >nul
if errorlevel 1 (
    set "CHAINLIT_PORT=%1"
    exit /b 0
)
exit /b 1

:: ============================================================
:: Subroutine: Find free ports for Phoenix
:: ============================================================
:find_free_phoenix_port
set "PHOENIX_PORT=6006"
set "PHOENIX_GRPC_PORT=4317"
:: Find free HTTP port
call :check_phoenix_http 6006 && goto :phoenix_http_found
call :check_phoenix_http 6007 && goto :phoenix_http_found
call :check_phoenix_http 6008 && goto :phoenix_http_found
call :check_phoenix_http 6009 && goto :phoenix_http_found
call :check_phoenix_http 6010 && goto :phoenix_http_found
call :check_phoenix_http 6011 && goto :phoenix_http_found
call :check_phoenix_http 6012 && goto :phoenix_http_found
call :check_phoenix_http 6013 && goto :phoenix_http_found
call :check_phoenix_http 6014 && goto :phoenix_http_found
call :check_phoenix_http 6015 && goto :phoenix_http_found
call :check_phoenix_http 6016 && goto :phoenix_http_found
set "PHOENIX_PORT=6006"
echo [WARN] Ports 6006-6016 are all in use! Phoenix may fail to start.
goto :phoenix_find_grpc

:phoenix_http_found
if "%PHOENIX_PORT%"=="6006" goto :phoenix_find_grpc
echo [WARN] Port 6006 is occupied. Auto-switching Phoenix to port %PHOENIX_PORT%

:phoenix_find_grpc
call :check_phoenix_grpc 4317 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4318 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4319 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4320 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4321 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4322 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4323 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4324 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4325 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4326 && goto :phoenix_grpc_found
call :check_phoenix_grpc 4327 && goto :phoenix_grpc_found
set "PHOENIX_GRPC_PORT=4317"
echo [WARN] gRPC ports 4317-4327 are all in use!
goto :phoenix_port_display

:phoenix_grpc_found
if "%PHOENIX_GRPC_PORT%"=="4317" goto :phoenix_port_display
echo [INFO] Auto-switching Phoenix gRPC to port %PHOENIX_GRPC_PORT%

:phoenix_port_display
exit /b 0

:check_phoenix_http
netstat -ano 2>nul | findstr ":%1 .*LISTENING" >nul
if errorlevel 1 (
    set "PHOENIX_PORT=%1"
    exit /b 0
)
exit /b 1

:check_phoenix_grpc
netstat -ano 2>nul | findstr ":%1 .*LISTENING" >nul
if errorlevel 1 (
    set "PHOENIX_GRPC_PORT=%1"
    exit /b 0
)
exit /b 1

::  ============================================================
:: Subroutine: Poll port until Phoenix is listening (max 15s)
:: Sets PHOENIX_LAUNCHED=1 on success, prints WARN on timeout
:: ============================================================
:wait_for_phoenix
set "PHOENIX_WAIT_COUNT=0"
:phoenix_wait_loop
netstat -ano 2>nul | findstr ":%PHOENIX_PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo      [OK] Phoenix ready on port %PHOENIX_PORT%
    set "PHOENIX_LAUNCHED=1"
    exit /b 0
)
set /a PHOENIX_WAIT_COUNT+=1
if %PHOENIX_WAIT_COUNT% GEQ 30 (
    echo      [WARN] Phoenix did not start within 30 seconds. Traces will not be collected.
    echo      [WARN] Check the "AI-QMS Phoenix" window for errors.
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :phoenix_wait_loop

:end
echo.
echo Goodbye!
pause
