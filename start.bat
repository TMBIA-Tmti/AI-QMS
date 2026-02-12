@echo off
chcp 65001 >nul 2>&1
title AI-QMS - AI Quality Management System for Medical Devices

echo ================================================================
echo.
echo     ___    ____       ____  __  ___ ____
echo    /   ^|  /  _/      / __ \/  ^|/  // ___/
echo   / /^| ^|  / /  ____ / / / / /^|_/ / \__ \
echo  / ___ ^|_/ /  /___// /_/ / /  / / ___/ /
echo /_/  ^|_/___/       \___\_/_/  /_/ /____/
echo.
echo  AI-Powered Quality Management System
echo  ISO 13485 Medical Device QMS
echo.
echo ================================================================
echo.

set "PROJECT_DIR=%~dp0"

:: Auto-detect Conda environment
set "QMS_PYTHON="

:: Try common conda paths
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

echo ================================================================
echo  Select startup mode:
echo ================================================================
echo.
echo  [1] Start AI-QMS (Chainlit, Port 3000) - RECOMMENDED
echo  [2] Start AI-QMS + Ollama (Local LLM)
echo  [3] Check Services Status
echo  [4] Stop All Services
echo  [5] Exit
echo.
set /p choice="Enter choice (1-5): "

if "%choice%"=="1" goto start_chainlit
if "%choice%"=="2" goto start_all
if "%choice%"=="3" goto status
if "%choice%"=="4" goto stop_all
if "%choice%"=="5" goto end
goto end

:start_chainlit
echo.
echo ================================================================
echo  Starting AI-QMS (Chainlit, Port 3000)
echo ================================================================
echo.

"%QMS_PYTHON%" -c "import chainlit; print(f'[OK] Chainlit {chainlit.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Chainlit not installed!
    echo Run: pip install -r requirements.txt
    pause
    goto end
)

echo [INFO] URL: http://localhost:3000
echo [INFO] Press Ctrl+C to stop
echo.

start "" "http://localhost:3000"
cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0
goto check_error

:start_all
echo.
echo ================================================================
echo  Starting AI-QMS + Ollama
echo ================================================================
echo.

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

echo [2/2] Starting Chainlit App...
echo.
echo  AI-QMS:    http://localhost:3000
echo  Ollama:    http://localhost:11434
echo.

start "" "http://localhost:3000"
cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0
goto check_error

:status
echo.
echo ================================================================
echo  Services Status
echo ================================================================
echo.

echo [Ollama]
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:11434
)
echo.

echo [AI-QMS Chainlit]
netstat -ano 2>nul | find ":3000" | find "LISTENING" >nul
if errorlevel 1 (
    echo   Status: STOPPED
) else (
    echo   Status: RUNNING
    echo   URL: http://localhost:3000
)
echo.
pause
goto end

:stop_all
echo.
echo ================================================================
echo  Stopping All Services...
echo ================================================================
echo.

echo [1/2] Stopping AI-QMS (Port 3000)...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find ":3000" ^| find "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo      Done

echo [2/2] Ollama (system service, not stopping)
echo.
echo [OK] Services stopped.
echo.
pause
goto end

:check_error
if errorlevel 1 (
    echo.
    echo [ERROR] Application terminated with error.
    echo.
    echo Troubleshooting:
    echo   1. Port 3000 in use: netstat -ano ^| find ":3000"
    echo   2. Missing deps: pip install -r requirements.txt
    echo   3. Python version: python --version (need 3.11+)
    echo.
)
pause
goto end

:end
echo.
echo Goodbye!
