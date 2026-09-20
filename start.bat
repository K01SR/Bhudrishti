@echo off
setlocal enabledelayedexpansion

title Bhu-Drishti 3D Launcher

echo ==============================================================================
echo Bhu-Drishti 3D: Windows Native Launcher
echo Starts FastAPI Backend and Vite Frontend natively
echo ==============================================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

if not exist logs mkdir logs

:: 1. Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [error] Python is not found in PATH. Please install Python 3.10+ from python.org.
    pause
    exit /b 1
)

:: 2. Check Node & npm
where node >nul 2>&1
if errorlevel 1 (
    echo [error] Node.js is not found in PATH. Please install Node.js from nodejs.org.
    pause
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [error] npm is not found in PATH. Please install npm.
    pause
    exit /b 1
)

echo [start] Found Python and Node.js.

:: 3. Setup Python Virtual Environment
if not exist "backend\.venv\Scripts\python.exe" (
    echo [start] Creating Python virtualenv at backend\.venv...
    python -m venv backend\.venv
    backend\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
    echo [start] Installing backend dependencies from backend\requirements.txt...
    backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    backend\.venv\Scripts\python.exe -m pip install greenlet "psycopg[binary]>=3.1.0"
)

:: 4. Setup Frontend Dependencies
if not exist "frontend\node_modules" (
    echo [start] Installing frontend npm packages...
    pushd frontend
    call npm install
    popd
)

:: 5. Check if Docker is available for backing DB
where docker >nul 2>&1
if not errorlevel 1 (
    echo [start] Starting backing database containers (PostGIS + Redis)...
    docker compose up -d postgres redis >nul 2>&1
)

:: 6. Set Environment Variables
set "POSTGRES_SERVER=127.0.0.1"
set "POSTGRES_PORT=5432"
set "POSTGRES_USER=bhudrishti"
set "POSTGRES_PASSWORD=bhudrishti_secure_spatial_2026"
set "POSTGRES_DB=bhudrishti_3d"
set "REDIS_HOST=127.0.0.1"
set "REDIS_PORT=6379"
set "LOCAL_STORAGE_PATH=%TEMP%\bhudrishti_storage"
set "VITE_PROXY_TARGET=http://127.0.0.1:8000"
set "PYTHONPATH=%ROOT_DIR%backend"

if not exist "%TEMP%\bhudrishti_storage" mkdir "%TEMP%\bhudrishti_storage"

:: 7. Launch Backend in new window
echo [start] Launching FastAPI backend on http://127.0.0.1:8000...
start "Bhu-Drishti Backend (FastAPI)" cmd /c "cd /d "%ROOT_DIR%" && set PYTHONPATH=%ROOT_DIR%backend && set POSTGRES_SERVER=127.0.0.1 && set REDIS_HOST=127.0.0.1 && backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload"

:: 8. Launch Frontend in new window
echo [start] Launching Vite frontend on http://localhost:3000...
start "Bhu-Drishti Frontend (Vite)" cmd /c "cd /d "%ROOT_DIR%frontend" && set VITE_PROXY_TARGET=http://127.0.0.1:8000 && npm run dev -- --host 127.0.0.1 --port 3000"

echo.
echo ==============================================================================
echo Bhu-Drishti 3D is running!
echo.
echo   Frontend UI : http://localhost:3000
echo   Backend API : http://127.0.0.1:8000
echo   API Docs    : http://127.0.0.1:8000/docs
echo.
echo To stop services, run: stop.bat
echo ==============================================================================
echo.

endlocal