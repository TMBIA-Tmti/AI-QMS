@echo off
chcp 65001 >nul 2>&1
title AI-QMS - Chainlit Quick Start

echo ================================================================
echo  AI-QMS - AI Quality Management System
echo  ISO 13485 Medical Device QMS
echo  Quick Start (Chainlit, Port 3000)
echo ================================================================
echo.

set "PROJECT_DIR=%~dp0"
set "QMS_PYTHON="

for %%P in (
    "%USERPROFILE%\miniconda3\envs\QMS\python.exe"
    "%USERPROFILE%\anaconda3\envs\QMS\python.exe"
    "%LOCALAPPDATA%\miniconda3\envs\QMS\python.exe"
    "C:\miniconda3\envs\QMS\python.exe"
    "C:\ProgramData\miniconda3\envs\QMS\python.exe"
) do (
    if exist %%P (
        set "QMS_PYTHON=%%~P"
        goto :found
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    set "QMS_PYTHON=python"
    goto :found
)

echo [ERROR] Python not found!
echo Please create QMS environment: conda create -n QMS python=3.11
pause
exit /b 1

:found
echo [OK] Python: %QMS_PYTHON%

"%QMS_PYTHON%" -c "import chainlit; print(f'[OK] Chainlit {chainlit.__version__}')" 2>nul
if errorlevel 1 (
    echo [ERROR] Chainlit not installed! Run: pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo  URL: http://localhost:3000
echo  Press Ctrl+C to stop
echo.

start "" "http://localhost:3000"
cd /d "%PROJECT_DIR%"
"%QMS_PYTHON%" -m chainlit run src/chainlit_app/app.py --port 3000 --host 0.0.0.0

if errorlevel 1 (
    echo.
    echo [ERROR] Chainlit terminated with error.
    echo Check: pip install -r requirements.txt
)
pause
