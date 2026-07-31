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
  echo Python was not found.
  echo Install Python or Miniconda, then run this file again.
  pause
  exit /b 1
)

echo Installing Hubble Workbench dependencies with:
"%PYTHON_EXE%" -c "import sys; print(sys.executable)"
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo Hubble Workbench dependencies are installed.
echo Verifying the selected Python environment...
"%PYTHON_EXE%" -c "import astropy, astroquery, numpy, PIL, tifffile; print('Astropy', astropy.__version__, '| Astroquery', astroquery.__version__)"
if errorlevel 1 (
  echo Dependency verification failed.
  pause
  exit /b 1
)
pause
exit /b 0

:try_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=%~1"
exit /b 0
