@echo off
echo ============================================
echo   Booting AviaSAFE Live Demo
echo ============================================

echo [1/4] Checking Docker Engine...
docker info >nul 2>&1
if %errorlevel% equ 0 goto DOCKER_READY

echo Docker is offline. Launching Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo Waiting for Docker to wake up (this usually takes 15-30 seconds)...

:WAITLOOP
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto WAITLOOP
echo Docker is now online!

:DOCKER_READY
echo Docker is already running (or just booted).

echo [2/4] Starting Backend Container...
start "AviaSAFE_Backend" cmd /k "start_demo.bat"

echo [3/4] Starting Frontend Server...
start "AviaSAFE_Frontend" cmd /k "firebase serve --only hosting"

echo Waiting 7 seconds for services to initialize...
timeout /t 7 /nobreak > nul

echo [4/4] Opening Browser to Landing Page...
start http://localhost:5005

echo.
echo ============================================
echo   Demo is LIVE! 
echo ============================================
:: Note: 'pause' has been removed so this window closes automatically!