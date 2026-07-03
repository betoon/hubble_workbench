@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  python hubble_workbench_v2_observatory_explorer.py
  goto :done
)

where py >nul 2>nul
if %errorlevel%==0 (
  py hubble_workbench_v2_observatory_explorer.py
  goto :done
)

echo Python was not found on PATH.
pause
exit /b 1

:done
