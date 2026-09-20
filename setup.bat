@echo off
setlocal enabledelayedexpansion

rem Optional: paste the git URL of this repository below to let the script clone it.
rem Example: set "REPO_URL=git@github.com:yourorg/bhu-drishti-3d.git"
set "REPO_URL="
set "REPO_DIR=BhuDrishti-3D"

docker version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [error] Docker is not installed or not running.
    echo Install Docker Desktop from https://www.docker.com/products/docker-desktop/
    echo then open it (WSL2 backend) and re-run this script.
    exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose version >nul 2>&1
    if errorlevel 1 (
        echo [error] Docker Compose not found - enable it in Docker Desktop Settings ^> General.
        exit /b 1
    )
    set "DC=docker-compose"
) else (
    set "DC=docker compose"
)

if not exist docker-compose.yml (
    if not "%REPO_URL%"=="" (
        echo [setup] Project files not found - cloning repository...
        git clone "%REPO_URL%" "%REPO_DIR%"
        cd "%REPO_DIR%"
    ) else (
        echo [warn] No docker-compose.yml found in %cd% and REPO_URL is empty.
        echo [warn] Set REPO_URL at the top of this script, or run it from inside the project folder.
        exit /b 1
    )
)

if not exist .env (
    copy .env.example .env >nul
    echo [setup] Created .env from .env.example
)
if not exist data mkdir data

echo [setup] Pulling base images (PostGIS, Redis)...
%DC% pull

echo [setup] Building backend + frontend images...
%DC% build

echo.
echo [setup] Done. Open http://localhost:3000 when the stack is running (see start.bat).
endlocal