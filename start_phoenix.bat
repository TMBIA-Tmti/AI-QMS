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
    echo [ERROR] Arize Phoenix failed to install.
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

:: Start Phoenix server
echo [INFO] Starting Phoenix server on port %PHOENIX_PORT%...
echo [INFO] Dashboard: http://localhost:%PHOENIX_PORT%
echo [INFO] Press Ctrl+C to stop
echo.

:: Auto-open browser after short delay
start "" "http://localhost:%PHOENIX_PORT%"

cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m phoenix.server.main --port %PHOENIX_PORT% serve --grpc-port %PHOENIX_GRPC_PORT%

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
:: Subroutine: Find free ports for Phoenix
:: Uses individual checks to avoid for/L + goto batch parser bugs
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
echo.
echo [WARN] Port 6006 is occupied by another process.
echo [INFO] Auto-switching Phoenix HTTP to port %PHOENIX_PORT%
echo.

:phoenix_find_grpc
:: Find free gRPC port
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
