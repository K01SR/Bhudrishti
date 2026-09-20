@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo Stopping Bhu-Drishti 3D Services
echo ==============================================================================
echo.

:: Stop processes listening on port 8000 (Backend)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [stop] Terminating backend process PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

:: Stop processes listening on port 3000 (Frontend)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    echo [stop] Terminating frontend process PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

:: If --docker or --all flag passed, stop docker containers as well
if /I "%~1"=="--docker" (
    docker compose stop postgres redis >nul 2>&1
)
if /I "%~1"=="--all" (
    docker compose stop postgres redis >nul 2>&1
)

echo.
echo [stop] Bhu-Drishti 3D stopped successfully.
endlocal
