@echo off
echo =========================================
echo Logistics Task Tracker - First-Time Setup
echo =========================================

REM Check Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo Python is not installed.
    echo Please install Python 3.10+ and re-run setup.
    pause
    exit /b
)

REM Create virtual environment
IF NOT EXIST ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate venv
call .venv\Scripts\activate

REM Install dependencies
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete.
echo You can now double-click Start_Task_Tracker.bat
pause