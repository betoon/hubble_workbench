@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  python -m pip install -r requirements.txt
  goto :done
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -m pip install -r requirements.txt
  goto :done
)

echo Python was not found on PATH.
pause
exit /b 1

:done
echo.
echo Hubble Workbench dependencies are installed.
pause
