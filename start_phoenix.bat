@echo off
chcp 65001 >nul 2>&1
title AI-QMS - Phoenix Observability Server

echo ========================================================
echo  AI-QMS - Arize Phoenix LLM Observability
echo  Version: v3.4.0
echo  Date: 2026-02-25
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

:: Check if port 6006 is already in use
netstat -ano 2>nul | find ":6006" | find "LISTENING" >nul
if not errorlevel 1 (
    echo [INFO] Phoenix is already running on port 6006
    echo [INFO] Dashboard: http://localhost:6006
    echo.
    echo Opening browser...
    start "" "http://localhost:6006"
    echo.
    pause
    exit /b 0
)

:: Start Phoenix server
echo [INFO] Starting Phoenix server on port 6006...
echo [INFO] Dashboard: http://localhost:6006
echo [INFO] Press Ctrl+C to stop
echo.

:: Auto-open browser after short delay
start "" "http://localhost:6006"

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m phoenix.server.main serve

if errorlevel 1 (
    echo.
    echo [ERROR] Phoenix server failed to start.
    echo.
    echo Common issues:
    echo   1. Port 6006 already in use
    echo   2. Missing dependencies (run: pip install arize-phoenix)
    echo.
)
pause
