@echo off
setlocal
title Logistics Support App Setup

REM ============================================================
REM ROOT / PATHS
REM ============================================================
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "VENV_DIR=%ROOT_DIR%\.venv"
set "REQ_FILE=%ROOT_DIR%\requirements.txt"
set "LOG_BASE_DIR=\\therestaurantstore.com\920\Data\Logistics\Logistics App\Logs"
set "USER_LOG_DIR=%LOG_BASE_DIR%\%USERNAME%\pages"
if not exist "%USER_LOG_DIR%" mkdir "%USER_LOG_DIR%"
set "LOG_FILE=%USER_LOG_DIR%\setup.log"

(
  echo ============================================================
  echo [%date% %time%] Setup start
  echo ROOT_DIR=%ROOT_DIR%
  echo VENV_DIR=%VENV_DIR%
  echo REQ_FILE=%REQ_FILE%
  echo LOG_BASE_DIR=%LOG_BASE_DIR%
  echo USER_LOG_DIR=%USER_LOG_DIR%
  echo LOG_FILE=%LOG_FILE%
  echo ============================================================
) >> "%LOG_FILE%"

REM ============================================================
REM VALIDATE PYTHON
REM ============================================================
where python >nul 2>&1
if errorlevel 1 (
  call :LOG "ERROR: Python not found in PATH."
  echo ERROR: Python not found in PATH.
  pause
  exit /b 1
)

REM ============================================================
REM CREATE VENV (IF MISSING)
REM ============================================================
if not exist "%VENV_DIR%\Scripts\python.exe" (
  call :LOG "Creating virtual environment..."
  echo Creating virtual environment...
  python -m venv "%VENV_DIR%" >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    call :LOG "ERROR: Failed to create virtual environment."
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
  )
) else (
  call :LOG "Virtual environment already exists."
  echo Virtual environment already exists.
)

REM ============================================================
REM INSTALL DEPENDENCIES
REM ============================================================
if not exist "%REQ_FILE%" (
  call :LOG "ERROR: requirements.txt not found."
  echo ERROR: requirements.txt not found.
  pause
  exit /b 1
)

call :LOG "Installing dependencies..."
echo Installing dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%REQ_FILE%" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
  call :LOG "ERROR: Dependency installation failed."
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)

REM ============================================================
REM DONE
REM ============================================================
call :LOG "Setup completed successfully."
echo.
echo ============================================
echo Setup complete.
echo Run StartApp.bat to launch the application.
echo ============================================
pause
exit /b 0

REM ============================================================
REM LOG FUNCTION
REM ============================================================
:LOG
echo [%date% %time%] %~1>> "%LOG_FILE%"
echo %~1
exit /b 0
