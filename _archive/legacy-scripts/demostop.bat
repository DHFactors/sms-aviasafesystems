@echo off
echo ============================================
echo   Shutting Down AviaSAFE Live Demo
echo ============================================

echo [1/4] Stopping Backend Docker Container...
docker stop aviasafe-local-backend >nul 2>&1

echo [2/4] Cleaning up Terminal Windows...
taskkill /FI "WINDOWTITLE eq AviaSAFE_Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AviaSAFE_Frontend*" /T /F >nul 2>&1

echo [3/4] Releasing Ports (Killing Node)...
:: This is the silver bullet for your port 5005 issue. 
:: It ensures Firebase is completely eradicated from memory.
taskkill /F /IM node.exe >nul 2>&1

echo [4/4] Closing Docker Desktop...
:: Forces the Docker application to close completely
taskkill /F /IM "Docker Desktop.exe" >nul 2>&1

echo.
echo ============================================
echo   Demo Environment completely shut down.
echo ============================================
:: Note: 'pause' has been removed so it exits cleanly!