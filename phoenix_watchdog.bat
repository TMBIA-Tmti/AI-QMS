@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phoenix Watchdog

:: ============================================================
:: Phoenix Watchdog — auto-restarts Phoenix on crash
::
:: Arguments:
::   %1  Python executable path
::   %2  Phoenix HTTP port (default 6006)
::   %3  Phoenix gRPC port (default 4317)
::   %4  Project directory
::   %5  Log file path
::
:: Called by start_chainlit.bat. Runs in a minimized window.
:: Restarts Phoenix server automatically if it exits unexpectedly.
:: Logs all output to the session log file.
:: ============================================================

set "QMS_PYTHON=%~1"
set "PHOENIX_PORT=%~2"
set "PHOENIX_GRPC_PORT=%~3"
set "PROJECT_DIR=%~4"
set "PHOENIX_LOG=%~5"

if "%QMS_PYTHON%"=="" (
    echo [ERROR] No Python path provided. Usage: phoenix_watchdog.bat <python> <port> <grpc_port> <project_dir> <log_file>
    pause
    exit /b 1
)

if "%PHOENIX_PORT%"=="" set "PHOENIX_PORT=6006"
if "%PHOENIX_GRPC_PORT%"=="" set "PHOENIX_GRPC_PORT=4317"
if "%PROJECT_DIR%"=="" set "PROJECT_DIR=%~dp0"
if "%PHOENIX_LOG%"=="" set "PHOENIX_LOG=%PROJECT_DIR%logs\phoenix\phoenix.log"

echo ========================================================
echo  AI-QMS Phoenix Watchdog
echo  Phoenix HTTP:  http://localhost:%PHOENIX_PORT%
echo  Phoenix gRPC:  localhost:%PHOENIX_GRPC_PORT%
echo  Log file:      %PHOENIX_LOG%
echo  Auto-restart:  ON
echo  To stop:       Close this window (do NOT press Ctrl+C,
echo                 which would only kill Phoenix temporarily)
echo ========================================================
echo.

:: Remove any stale stop sentinel from a previous session
if exist "%PROJECT_DIR%.phoenix_stop" del "%PROJECT_DIR%.phoenix_stop" >nul 2>&1

>> "%PHOENIX_LOG%" echo ============================================================
>> "%PHOENIX_LOG%" echo [Watchdog] Started at %date% %time%
>> "%PHOENIX_LOG%" echo [Watchdog] Python: %QMS_PYTHON%
>> "%PHOENIX_LOG%" echo [Watchdog] HTTP port: %PHOENIX_PORT% / gRPC port: %PHOENIX_GRPC_PORT%
>> "%PHOENIX_LOG%" echo ============================================================

cd /d "%PROJECT_DIR%"
set "PHOENIX_RESTARTS=0"

:watchdog_loop
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

:: Run Phoenix — redirect stderr to log, stdout to console for live feedback.
:: NOTE: piping stdout+stderr loses the exit code (pipe returns last cmd's code).
:: Using stderr-only redirect preserves Phoenix's real exit code for restart logic.
"%QMS_PYTHON%" -m phoenix.server.main serve --grpc-port %PHOENIX_GRPC_PORT% 2>> "%PHOENIX_LOG%"
set "PHOENIX_EXIT=%errorlevel%"
>> "%PHOENIX_LOG%" echo [Watchdog] Run %PHOENIX_RESTARTS% exited code %PHOENIX_EXIT% at %date% %time%

:: Check for stop sentinel file (created externally to cleanly halt the watchdog)
if exist "%PROJECT_DIR%.phoenix_stop" (
    del "%PROJECT_DIR%.phoenix_stop" >nul 2>&1
    echo.
    echo [Watchdog] Stop signal received. Watchdog exiting.
    >> "%PHOENIX_LOG%" echo [Watchdog] Stop sentinel detected. Exiting at %date% %time%.
    goto :eof
)

:: errorlevel 0 = window closed or process exited cleanly → also stop (no restart)
if "%PHOENIX_EXIT%"=="0" (
    echo.
    echo [Watchdog] Phoenix exited cleanly. Watchdog stopping.
    >> "%PHOENIX_LOG%" echo [Watchdog] Clean exit. Watchdog stopped at %date% %time%.
    goto :eof
)

:: Non-zero exit = crash → restart
goto :watchdog_loop
