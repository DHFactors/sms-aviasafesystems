@echo off
setlocal
title AviaSAFE SMS - Local Demo Backend

rem ============================================================
rem  AviaSAFE SMS — one-click local demo backend (Docker)
rem  Builds the FastAPI container and runs it on port 8000,
rem  loading secrets from backend\.env.demo
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   AviaSAFE SMS - Local Demo Startup
echo ============================================
echo.

rem -- Preflight: Docker present and running --------------------
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker was not found on this PC.
    echo         Install Docker Desktop, start it, then run this file again.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is installed but not running.
    echo         Start Docker Desktop, wait for "running", then retry.
    pause
    exit /b 1
)

rem -- Preflight: env file exists --------------------------------
if not exist "backend\.env.demo" (
    echo [ERROR] backend\.env.demo is missing.
    echo.
    echo   Fix in 10 seconds:
    echo     1. copy backend\.env.demo.example backend\.env.demo
    echo     2. open backend\.env.demo in Notepad
    echo     3. paste the Firebase values from the Render beta dashboard
    echo     4. save, then run start_demo.bat again
    pause
    exit /b 1
)

rem -- Free the port if a previous demo run is still around ------
docker rm -f aviasafe-local-backend >nul 2>&1

rem -- Build ------------------------------------------------------
echo [1/3] Building Docker image ^(first run takes several minutes^)...
docker build -f backend/Dockerfile -t aviasafe-demo-api:latest backend
if errorlevel 1 (
    echo [ERROR] Docker build failed. See messages above.
    pause
    exit /b 1
)

rem -- Run --------------------------------------------------------
echo [2/3] Starting container on port 8000...
echo.
echo     Demo Backend running at http://localhost:8000
echo     ^(Press Ctrl+C here to stop the demo backend^)
echo.
docker run --rm -it -p 8000:8000 --env-file backend/.env.demo --name aviasafe-local-backend aviasafe-demo-api:latest

rem docker run keeps running until Ctrl+C; anything below is teardown.
echo.
echo [3/3] Demo backend stopped.
pause
