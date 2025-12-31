@echo off
title Logistics Support Task Tracker

REM ================================
REM CONFIG
REM ================================
set APP_DIR=C:\Projects\Task Tracker
set VENV_DIR=%APP_DIR%\.venv

REM ================================
REM MOVE TO APP DIRECTORY
REM ================================
cd /d "%APP_DIR%" || (
    echo ERROR: Application directory not found:
    echo %APP_DIR%
    pause
    exit /b 1
)

REM ================================
REM CHECK GIT
REM ================================
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Git is not available on this machine.
    echo Please install Git for Windows and try again.
    pause
    exit /b 1
)

REM ================================
REM UPDATE FROM GITHUB
REM ================================
echo.
echo Updating application from GitHub...
git pull origin main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo WARNING: Could not update from GitHub.
    echo The app will run using the existing local version.
    echo.
)

REM ================================
REM ACTIVATE VIRTUAL ENV
REM ================================
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate"

REM ================================
REM START STREAMLIT (AUTO-OPEN BROWSER)
REM ================================
echo.
echo Starting Logistics Support Task Tracker...
echo Browser will open automatically.
echo.

python -m streamlit run app.py ^
    --server.headless=false

REM ================================
REM CLEAN EXIT
REM ================================
echo.
echo Application closed.
pause
