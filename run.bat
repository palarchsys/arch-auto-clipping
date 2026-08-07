@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERREUR] Environnement virtuel introuvable.
  echo Lancez d'abord:  install.bat
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" main.py
set "EXITCODE=%ERRORLEVEL%"
if not %EXITCODE%==0 (
  echo.
  echo [ERREUR] Le programme s'est arrete avec le code %EXITCODE%.
  pause
)
endlocal & exit /b %EXITCODE%
