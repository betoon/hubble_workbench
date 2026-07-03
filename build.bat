@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_ENTRY=hubble_workbench_v2_observatory_explorer.py"

echo.
echo === Hubble Workbench clean build ===
echo Folder: %CD%
echo Entry: %APP_ENTRY%
echo.

if not exist "%APP_ENTRY%" (
  echo ERROR: %APP_ENTRY% was not found here.
  pause
  exit /b 1
)

set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"
if "%PYTHON_CMD%"=="" (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py"
)
if "%PYTHON_CMD%"=="" (
  echo ERROR: Python was not found.
  pause
  exit /b 1
)

echo Using:
%PYTHON_CMD% --version
if errorlevel 1 goto failed

echo.
echo Installing/refreshing required packages...
%PYTHON_CMD% -m pip install --upgrade pyinstaller astroquery astropy pyvo numpy Pillow tifffile requests
if errorlevel 1 goto failed

echo.
echo Cleaning old build output...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "__pycache__" rmdir /s /q "__pycache__"

echo.
echo Building Hubble_Workbench.exe with astronomy packages included...
%PYTHON_CMD% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name Hubble_Workbench ^
  --collect-all astropy ^
  --collect-all astroquery ^
  --collect-all pyvo ^
  --collect-submodules astroquery ^
  --collect-submodules pyvo ^
  --hidden-import astroquery ^
  --hidden-import astroquery.mast ^
  --hidden-import astroquery.mast.observations ^
  --hidden-import pyvo ^
  --hidden-import requests ^
  --add-data "The Complete Messier List.txt;." ^
  "%APP_ENTRY%"
if errorlevel 1 goto failed

if not exist "dist\Hubble_Workbench\downloads" mkdir "dist\Hubble_Workbench\downloads"
if not exist "dist\Hubble_Workbench\outputs" mkdir "dist\Hubble_Workbench\outputs"
if not exist "dist\Hubble_Workbench\notes" mkdir "dist\Hubble_Workbench\notes"

echo.
echo SUCCESS.
echo Run:
echo %CD%\dist\Hubble_Workbench\Hubble_Workbench.exe
echo.
pause
exit /b 0

:failed
echo.
echo Build failed. Please send me the lines above this message.
pause
exit /b 1
