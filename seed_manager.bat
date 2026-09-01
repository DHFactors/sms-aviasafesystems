@echo off
echo ========================================
echo   AviaSAFE Seed Manager
echo ========================================
echo.
echo   ⚠️  REAL DATA IS IMMUTABLE AND SAFE  ⚠️
echo   Only demo data (is_demo=True) is affected
echo.
echo   1. Seed All (Demo Data)
echo   2. Seed Specific Module
echo   3. Seed Specific Tenant
echo   4. Dry Run (Preview)
echo   5. Unseed All (Demo Data Only)
echo.
echo ========================================
echo.
set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" python -m seeders.cli --all
if "%choice%"=="2" set /p module="Enter module name: " & python -m seeders.cli --module %module%
if "%choice%"=="3" set /p tenant="Enter tenant ID: " & python -m seeders.cli --all --tenants %tenant%
if "%choice%"=="4" python -m seeders.cli --all --dry-run
if "%choice%"=="5" python -m seeders.cli --unseed

echo.
echo ✅ Done!
echo ✅ Real data is preserved and immutable.
pause