@echo off
title Logistics Support Task Tracker – Setup

REM ================================
REM CONFIG (MUST MATCH START FILE)
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

echo =========================================
echo Logistics Task Tracker - First-Time Setup
echo =========================================

REM ================================
REM CHECK PYTHON
REM ================================
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not on PATH.
    echo Please install Python 3.10+ and re-run setup.
    pause
    exit /b 1
)

REM ================================
REM CREATE VIRTUAL ENV
REM ================================
if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
)

REM ================================
REM ACTIVATE VENV
REM ================================
call "%VENV_DIR%\Scripts\activate"

REM ================================
REM INSTALL DEPENDENCIES
REM ================================
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete.
echo You can now double-click Start_Task_Tracker.bat
echo.
pause
