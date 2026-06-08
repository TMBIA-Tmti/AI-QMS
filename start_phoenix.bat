@echo off
chcp 65001 >nul 2>&1

:: ============================================================
:: AI-QMS Phoenix Server - v3.7.0 (2026-06-09)
::
:: Dual-mode script:
::
::   MODE A - Standalone (no args, user double-clicks):
::     - Auto-detects Python/conda environment
::     - Checks/updates dependencies
::     - Finds free port
::     - Opens browser
::     - Runs Phoenix in foreground with watchdog restart loop
::
::   MODE B - Watchdog (5 args, called by start_chainlit.bat):
::     - Skips all setup (Python/port/log already provided)
::     - Runs Phoenix restart loop silently in background window
::     - Arguments: <python> <http_port> <grpc_port> <project_dir> <log_file>
::
:: Both modes share the same watchdog restart loop at :phoenix_loop.
:: ============================================================

:: Detect mode: if first argument is present, skip setup
if not "%~1"=="" goto :watchdog_mode

:: ============================================================
:: MODE A: Standalone launcher
:: ============================================================
title AI-QMS - Phoenix Observability Server v3.7.0

echo ========================================================
echo  AI-QMS - Arize Phoenix LLM Observability
echo  Version: v3.7.0
echo  Date: 2026-06-09
echo ========================================================
echo.
echo  Phoenix provides:
echo    - LLM call tracing (inputs, outputs, tokens, latency)
echo    - Prompt analysis and debugging
echo    - Trace visualization and filtering
echo    - Evaluation and annotation support
echo.
echo  Dashboard: http://localhost:6006
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
        goto :standalone_found_python
    )
)

:: Try conda activate approach
where conda >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('conda run -n QMS where python 2^>nul') do (
        if exist "%%i" (
            set "QMS_PYTHON=%%i"
            goto :standalone_found_python
        )
    )
)

:: Try system Python as fallback
where python >nul 2>&1
if not errorlevel 1 (
    echo [WARN] QMS conda environment not found.
    echo [WARN] Using system Python.
    echo.
    set "QMS_PYTHON=python"
    goto :standalone_found_python
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

:standalone_found_python
echo [OK] Python: %QMS_PYTHON%
echo.

:: --- Phoenix session log ---------------------------------------------------
if not exist "%PROJECT_DIR%logs\phoenix" mkdir "%PROJECT_DIR%logs\phoenix"
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "SESSION_STAMP=%%t"
set "PHOENIX_LOG=%PROJECT_DIR%logs\phoenix\%SESSION_STAMP%_phoenix.log"
echo [LOG] Phoenix log: logs\phoenix\%SESSION_STAMP%_phoenix.log
echo SESSION START: %SESSION_STAMP% > "%PHOENIX_LOG%"
:: ---------------------------------------------------------------------------

:: -- No-disconnect settings -------------------------------------------------
set "UVICORN_TIMEOUT_KEEP_ALIVE=0"
set "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=300"
:: ---------------------------------------------------------------------------

:: Auto-update: always sync all packages from requirements.txt
echo [INFO] Checking dependencies...
"%QMS_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" --quiet --disable-pip-version-check < nul 2>nul
if errorlevel 1 (
    echo [WARN] Some packages failed to install. App will continue with available features.
) else (
    echo [OK] All dependencies up to date.
)
echo.

:: Check if Phoenix is installed
"%QMS_PYTHON%" -c "import phoenix; print(f'[OK] Phoenix version: {phoenix.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Arize Phoenix not installed.
    echo.
    echo Please install manually:
    echo   conda activate QMS
    echo   pip install arize-phoenix arize-phoenix-otel openinference-instrumentation-litellm
    echo.
    pause
    exit /b 1
)

:: Auto-detect free port for Phoenix
call :find_free_phoenix_port

:: Check if Phoenix is already running (HTTP port)
netstat -ano 2>nul | findstr ":%PHOENIX_PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo [INFO] Phoenix is already running on port %PHOENIX_PORT%
    echo [INFO] Dashboard: http://localhost:%PHOENIX_PORT%
    echo.
    echo Opening browser...
    start "" "http://localhost:%PHOENIX_PORT%"
    echo.
    pause
    exit /b 0
)

:: Open browser (Phoenix starts in a few seconds)
start "" "http://localhost:%PHOENIX_PORT%"

echo [INFO] Starting Phoenix server on port %PHOENIX_PORT% (gRPC: %PHOENIX_GRPC_PORT%)
echo [INFO] Auto-restart ON - will recover from crashes automatically
echo [INFO] Press Ctrl+C to stop
echo.

cd /d "%PROJECT_DIR%" >nul 2>&1
:: Remove any stale stop sentinel
if exist "%PROJECT_DIR%.phoenix_stop" del "%PROJECT_DIR%.phoenix_stop" >nul 2>&1

set "PHOENIX_RESTARTS=0"
goto :phoenix_loop

:: ============================================================
:: MODE B: Watchdog (called by start_chainlit.bat with 5 args)
:: ============================================================
:watchdog_mode
title AI-QMS Phoenix Watchdog

set "QMS_PYTHON=%~1"
set "PHOENIX_PORT=%~2"
set "PHOENIX_GRPC_PORT=%~3"
set "PROJECT_DIR=%~4"
set "PHOENIX_LOG=%~5"

if "%PHOENIX_PORT%"=="" set "PHOENIX_PORT=6006"
if "%PHOENIX_GRPC_PORT%"=="" set "PHOENIX_GRPC_PORT=4317"
if "%PROJECT_DIR%"=="" set "PROJECT_DIR=%~dp0"

:: If caller did not supply a log path, fall back to a timestamped file
:: (not the bare "phoenix.log") so each run keeps its own history instead
:: of overwriting the previous session's log.
if "%PHOENIX_LOG%"=="" if not exist "%PROJECT_DIR%logs\phoenix" mkdir "%PROJECT_DIR%logs\phoenix"
if "%PHOENIX_LOG%"=="" for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "PHOENIX_LOG=%PROJECT_DIR%logs\phoenix\%%t_phoenix.log"

echo ========================================================
echo  AI-QMS Phoenix Watchdog
echo  Phoenix HTTP:  http://localhost:%PHOENIX_PORT%
echo  Phoenix gRPC:  localhost:%PHOENIX_GRPC_PORT%
echo  Log file:      %PHOENIX_LOG%
echo  Auto-restart:  ON
echo  To stop:       Close this window
echo ========================================================
echo.

:: Remove any stale stop sentinel from a previous session
if exist "%PROJECT_DIR%.phoenix_stop" del "%PROJECT_DIR%.phoenix_stop" >nul 2>&1

>> "%PHOENIX_LOG%" echo ============================================================
>> "%PHOENIX_LOG%" echo [Watchdog] Started at %date% %time%
>> "%PHOENIX_LOG%" echo [Watchdog] Python: %QMS_PYTHON%
>> "%PHOENIX_LOG%" echo [Watchdog] HTTP port: %PHOENIX_PORT% / gRPC port: %PHOENIX_GRPC_PORT%
>> "%PHOENIX_LOG%" echo ============================================================

cd /d "%PROJECT_DIR%" >nul 2>&1
set "PHOENIX_RESTARTS=0"

:: ============================================================
:: Shared watchdog loop (used by both MODE A and MODE B)
:: ============================================================
:phoenix_loop
if %PHOENIX_RESTARTS% GTR 0 (
    echo.
    echo [Watchdog] Phoenix stopped unexpectedly ^(run %PHOENIX_RESTARTS%^).
    echo [Watchdog] Restarting in 10 seconds... Press Ctrl+C to stop.
    >> "%PHOENIX_LOG%" echo [Watchdog] Run %PHOENIX_RESTARTS% CRASHED at %date% %time%. Restarting in 10s.
    timeout /t 10 /nobreak >nul

    :: Kill any zombie on the port before restart
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PHOENIX_PORT% .*LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

set /a PHOENIX_RESTARTS+=1
echo [Watchdog] Starting Phoenix (run %PHOENIX_RESTARTS%)...
>> "%PHOENIX_LOG%" echo [Watchdog] Run %PHOENIX_RESTARTS% starting at %date% %time%

:: Run Phoenix - stderr->log, stdout->console (preserves exit code for restart logic)
"%QMS_PYTHON%" -m phoenix.server.main serve --grpc-port %PHOENIX_GRPC_PORT% 2>> "%PHOENIX_LOG%"
set "PHOENIX_EXIT=%errorlevel%"
>> "%PHOENIX_LOG%" echo [Watchdog] Run %PHOENIX_RESTARTS% exited code %PHOENIX_EXIT% at %date% %time%

:: Check for stop sentinel file
if exist "%PROJECT_DIR%.phoenix_stop" (
    del "%PROJECT_DIR%.phoenix_stop" >nul 2>&1
    echo.
    echo [Watchdog] Stop signal received. Exiting.
    >> "%PHOENIX_LOG%" echo [Watchdog] Stop sentinel detected. Exiting at %date% %time%.
    goto :eof
)

:: Exit code 0 = clean stop (Ctrl+C or window close) - do NOT restart
if "%PHOENIX_EXIT%"=="0" (
    echo.
    echo [Watchdog] Phoenix exited cleanly. Stopping.
    >> "%PHOENIX_LOG%" echo [Watchdog] Clean exit. Stopped at %date% %time%.
    goto :eof
)

:: Non-zero exit = crash -> restart
goto :phoenix_loop

:: ============================================================
:: Subroutine: Find free ports for Phoenix
:: ============================================================
:find_free_phoenix_port
set "PHOENIX_PORT=6006"
set "PHOENIX_GRPC_PORT=4317"
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
echo.
echo [WARN] Port 6006 is occupied. Auto-switching Phoenix to port %PHOENIX_PORT%
echo.

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
echo [WARN] gRPC ports 4317-4327 are all in use! Phoenix may fail to start.
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
