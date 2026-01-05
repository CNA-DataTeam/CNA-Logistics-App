@echo off
title Logistics Support Task Tracker

REM ================================
REM RESOLVE CURRENT APP DIRECTORY
REM ================================
set "APP_DIR=%~dp0"
set "VENV_DIR=%APP_DIR%\.venv"

REM Remove trailing backslash
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

REM ================================
REM MOVE TO APP DIRECTORY
REM ================================
cd /d "%APP_DIR%" || (
    echo ERROR: Unable to access application directory:
    echo %APP_DIR%
    pause
    exit /b 1
)

echo =========================================
echo Logistics Support Task Tracker
echo Location:
echo %APP_DIR%
echo =========================================

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
REM START STREAMLIT
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