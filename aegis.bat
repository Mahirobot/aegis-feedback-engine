@echo off
setlocal

:: 1. Define Environment Name
set VENV_DIR=.venv

:: 2. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed. Please install Python 3.11+ first.
    pause
    exit /b
)

:: 3. Create Virtual Environment if it doesn't exist
if not exist %VENV_DIR% (
    echo [SETUP] Creating virtual environment...
    python -m venv %VENV_DIR%
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b
    )
    echo [SETUP] Done.
)

:: 4. Activate Environment
echo [INFO] Activating virtual environment...
call %VENV_DIR%\Scripts\activate.bat

:: 5. Install Dependencies (Only if we just created env or reqs changed)
:: For speed, we just try to install. Pip is fast if packages satisfy requirements.
echo [INFO] Checking dependencies...
pip install -r requirements.txt > nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)

:: 6. Launch Dashboard (Wait 3s for server to spin up)
echo [INFO] Launching Dashboard...
timeout /t 3 >nul
start http://127.0.0.1:8000

:: 7. Run Server
echo [INFO] Starting Server...
echo [INFO] Press Ctrl+C to stop.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

pause