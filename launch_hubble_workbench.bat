@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_EXE="
call :try_python "C:\miniconda3\python.exe"
call :try_python "%USERPROFILE%\miniconda3\python.exe"
call :try_python "%USERPROFILE%\anaconda3\python.exe"

for /f "delims=" %%P in ('where python 2^>nul') do (
  if not defined PYTHON_EXE call :try_python "%%P"
)

if not defined PYTHON_EXE (
  echo.
  echo Hubble Workbench could not find a Python installation with Astropy and Astroquery.
  echo Run install_dependencies.bat, then launch the application with this file.
  echo.
  pause
  exit /b 1
)

echo Launching with:
"%PYTHON_EXE%" -c "import sys, astropy, astroquery; print(sys.executable); print('Astropy', astropy.__version__, '| Astroquery', astroquery.__version__)"
if /i "%~1"=="--check" exit /b 0
"%PYTHON_EXE%" hubble_workbench_v2_observatory_explorer.py
if errorlevel 1 (
  echo.
  echo Hubble Workbench exited with an error.
  pause
  exit /b 1
)
exit /b 0

:try_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import astropy, astroquery, numpy, PIL, tifffile" >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0
