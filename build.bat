@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "RELEASE_VERSION=2.1.0"
set "PYTHON_CMD=python"
where python >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=py"
%PYTHON_CMD% --version
if errorlevel 1 goto failed
if exist "dist\%RELEASE_VERSION%" (
  echo Release output already exists. Move it aside before rebuilding.
  exit /b 1
)
echo Install requirements.txt and PyInstaller in your chosen environment before building.
%PYTHON_CMD% -m PyInstaller --clean --distpath "dist\%RELEASE_VERSION%" --workpath "build\%RELEASE_VERSION%" Hubble_Workbench.spec
if errorlevel 1 goto failed
echo Built dist\%RELEASE_VERSION%\Hubble_Workbench\Hubble_Workbench.exe
pause
exit /b 0
:failed
echo Build failed. Review the error above. No previous release was deleted.
pause
exit /b 1
