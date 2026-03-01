@echo off
chcp 65001 >nul 2>&1
title AI-QMS - Phoenix Observability Server

echo ========================================================
echo  AI-QMS - Arize Phoenix LLM Observability
echo  Version: v3.5.0
echo  Date: 2026-02-28
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
    echo [WARN] Using system Python.
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

:: Check if Phoenix is installed
"%QMS_PYTHON%" -c "import phoenix; print(f'[OK] Phoenix version: {phoenix.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Arize Phoenix not installed!
    echo.
    echo Please install it with:
    echo   conda activate QMS
    echo   pip install arize-phoenix arize-phoenix-otel openinference-instrumentation-litellm
    echo.
    pause
    exit /b 1
)

:: Auto-detect free port for Phoenix
call :find_free_phoenix_port

:: Check if Phoenix is already running on detected port
netstat -ano 2>nul | find ":%PHOENIX_PORT%" | find "LISTENING" >nul
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

:: Start Phoenix server
echo [INFO] Starting Phoenix server on port %PHOENIX_PORT%...
echo [INFO] Dashboard: http://localhost:%PHOENIX_PORT%
echo [INFO] Press Ctrl+C to stop
echo.

:: Auto-open browser after short delay
start "" "http://localhost:%PHOENIX_PORT%"

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m phoenix.server.main --port %PHOENIX_PORT% serve

if errorlevel 1 (
    echo.
    echo [ERROR] Phoenix server failed to start.
    echo.
    echo Common issues:
    echo   1. Port %PHOENIX_PORT% already in use
    echo   2. Missing dependencies (run: pip install arize-phoenix)
    echo.
)
pause
goto :eof

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
