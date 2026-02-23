@echo off
setlocal EnableDelayedExpansion
title Logistics Support App

REM ============================================================
REM ROOT / PATHS
REM ============================================================
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "VENV_DIR=%ROOT_DIR%\.venv"
set "STREAMLIT_PORT=8501"

set "LOG_BASE_DIR=\\therestaurantstore.com\920\Data\Logistics\Logistics App\Logs"
set "USER_LOG_DIR=%LOG_BASE_DIR%\%USERNAME%\pages"
if not exist "%USER_LOG_DIR%" mkdir "%USER_LOG_DIR%"
set "LAUNCHER_LOG_FILE=%USER_LOG_DIR%\launcher.log"
set "STARTUP_RUN_LOG_FILE=%USER_LOG_DIR%\startup_runner.log"
set "STREAMLIT_LOG_FILE=%USER_LOG_DIR%\streamlit.log"

REM ============================================================
REM LOG HEADER
REM ============================================================
(
  echo ============================================================
  echo [%date% %time%] Launcher start
  echo ROOT_DIR=%ROOT_DIR%
  echo VENV_DIR=%VENV_DIR%
  echo PORT=%STREAMLIT_PORT%
  echo LOG_BASE_DIR=%LOG_BASE_DIR%
  echo USER_LOG_DIR=%USER_LOG_DIR%
  echo LAUNCHER_LOG=%LAUNCHER_LOG_FILE%
  echo STARTUP_RUN_LOG=%STARTUP_RUN_LOG_FILE%
  echo STREAMLIT_LOG=%STREAMLIT_LOG_FILE%
  echo ============================================================
) >> "%LAUNCHER_LOG_FILE%"

REM ============================================================
REM VALIDATION
REM ============================================================
if not exist "%ROOT_DIR%\app.py" (
  echo [%date% %time%] ERROR: app.py not found>> "%LAUNCHER_LOG_FILE%"
  echo ERROR: app.py not found in root directory.
  pause
  exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [%date% %time%] ERROR: venv missing>> "%LAUNCHER_LOG_FILE%"
  echo ERROR: Virtual environment not found. Run setup.bat first.
  pause
  exit /b 1
)

REM ============================================================
REM OPTIONAL GIT UPDATE (FAIL-OPEN)
REM ============================================================
call :LOG "Starting Git check..."

where git >nul 2>&1
if errorlevel 1 (
  call :LOG "Git not available. Skipping updates."
  goto LAUNCH
)

if not exist "%ROOT_DIR%\.git" (
  call :LOG "Not a git repo. Skipping updates."
  goto LAUNCH
)

pushd "%ROOT_DIR%" >> "%LAUNCHER_LOG_FILE%" 2>&1

call :LOG "Testing Git remote..."
git ls-remote --heads origin >> "%LAUNCHER_LOG_FILE%" 2>&1
if errorlevel 1 (
  call :LOG "Git remote/auth failed. Skipping updates."
  popd
  goto LAUNCH
)

call :LOG "Fetching updates..."
git fetch --prune >> "%LAUNCHER_LOG_FILE%" 2>&1
if errorlevel 1 (
  call :LOG "Git fetch failed. Skipping updates."
  popd
  goto LAUNCH
)

git status -uno | findstr /C:"behind" >nul
if errorlevel 1 (
  call :LOG "No updates detected."
) else (
  call :LOG "Updates detected. Pulling..."
  git pull --ff-only >> "%LAUNCHER_LOG_FILE%" 2>&1
  if errorlevel 1 (
    call :LOG "Git pull failed. Using local version."
  ) else (
    call :LOG "Git pull successful."
  )
)

popd

REM ============================================================
REM LAUNCH STREAMLIT
REM ============================================================
:LAUNCH
call :LOG "Launching Streamlit..."

netstat -ano | findstr /R /C:":%STREAMLIT_PORT% .*LISTENING" >nul
if %ERRORLEVEL%==0 (
  call :LOG "App already running. Opening browser."
  start "" "http://localhost:%STREAMLIT_PORT%"
  exit /b 0
)

"%VENV_DIR%\Scripts\python.exe" -c "import streamlit" >> "%LAUNCHER_LOG_FILE%" 2>&1
if errorlevel 1 (
  call :LOG "ERROR: Streamlit not installed."
  echo ERROR: Streamlit missing. Run setup.bat.
  pause
  exit /b 1
)

if not exist "%ROOT_DIR%\startup.py" (
  call :LOG "ERROR: startup.py not found."
  echo ERROR: startup.py not found in root directory.
  pause
  exit /b 1
)

call :LOG "Running startup.py..."
set "STARTUP_CALLER=StartApp.bat"
"%VENV_DIR%\Scripts\python.exe" "%ROOT_DIR%\startup.py" >> "%STARTUP_RUN_LOG_FILE%" 2>&1
if errorlevel 1 (
  call :LOG "ERROR: startup.py failed."
  echo ERROR: startup.py failed. Check %STARTUP_RUN_LOG_FILE% and %USER_LOG_DIR%\startup.log for details.
  pause
  exit /b 1
)
call :LOG "startup.py completed."

call :LOG "Starting server..."
start "" /B "%VENV_DIR%\Scripts\pythonw.exe" -m streamlit run "app.py" ^
  --server.port=%STREAMLIT_PORT% ^
  --server.headless=true ^
  --browser.gatherUsageStats=false ^
  >> "%STREAMLIT_LOG_FILE%" 2>&1

timeout /t 2 >nul
start "" "http://localhost:%STREAMLIT_PORT%"
exit /b 0

REM ============================================================
REM LOG FUNCTION
REM ============================================================
:LOG
echo [%date% %time%] %~1>> "%LAUNCHER_LOG_FILE%"
echo %~1
exit /b 0
