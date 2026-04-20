@echo off
chcp 65001 >nul 2>&1
title AI-QMS Phase 1 - Chainlit v3.6.0

echo ========================================================
echo  AI-QMS Phase 1 Document Control System
echo  Version: v3.6.0 (Chainlit + Phoenix)
echo  Date: 2026-04-19
echo ========================================================
echo.
echo  Architecture (Chainlit + Phoenix):
echo    Single App:         Chainlit (Port 3000)
echo    Chat Profiles:      Main Agent + Doc Control
echo    Local LLM:          Ollama (Port 11434)
echo    LLM Observability:  Phoenix (Port 6006)
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
for /L %%p in (3000,1,3010) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p .*LISTENING"') do (
        tasklist /FI "PID eq %%a" /FO CSV /NH 2>nul | findstr /I "python" >nul
        if not errorlevel 1 (
            echo [INFO] Found orphaned Python process on port %%p ^(PID %%a^). Cleaning up...
            taskkill /PID %%a /F >nul 2>&1
        )
    )
)

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
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | findstr /I "ollama.exe" >NUL
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
    netstat -an 2>nul | findstr ":%PHOENIX_PORT% .*LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Starting Phoenix server on port %PHOENIX_PORT% (gRPC: %PHOENIX_GRPC_PORT%^)...
        start "Phoenix Server" /min "%QMS_PYTHON%" -m phoenix.server.main --port %PHOENIX_PORT% serve --grpc-port %PHOENIX_GRPC_PORT%
        timeout /t 3 >nul
        echo [OK] Phoenix started at http://localhost:%PHOENIX_PORT%
    ) else (
        echo [OK] Phoenix already running on port %PHOENIX_PORT%
    )
)

:: Pass Phoenix port to Python app via environment variable
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
echo  Auto-Reload: OFF (disabled to prevent UI disconnect during analysis)
echo  Press Ctrl+C to stop
echo ========================================================
echo.

:: Run Chainlit from project directory
cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port %CHAINLIT_PORT%

echo.
echo ========================================================
if errorlevel 1 (
    echo [ERROR] Chainlit terminated with error.
    echo Check the messages above for details.
    echo.
    echo Common issues:
    echo   1. Port %CHAINLIT_PORT% already in use
    echo   2. Missing dependencies (run: pip install -r requirements.txt)
    echo   3. Chainlit version issue (need 2.9.4+)
) else (
    echo [INFO] Chainlit has stopped.
)
echo ========================================================
echo.
echo Press any key to exit...
pause >nul
goto :eof

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
if "%CHAINLIT_PORT%"=="3000" goto :port_display
echo.
echo [WARN] Port 3000 is occupied. Auto-switching Chainlit to port %CHAINLIT_PORT%
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
