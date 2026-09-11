@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================
echo   Arch's Auto Clipping - Installation
echo ============================================
echo.

REM --- Recherche de Python ---
set "PYTHON="
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if %ERRORLEVEL%==0 set "PYTHON=py -3"
)
if not defined PYTHON (
  where python >nul 2>&1
  if %ERRORLEVEL%==0 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if %ERRORLEVEL%==0 set "PYTHON=python"
  )
)
if not defined PYTHON (
  where python3 >nul 2>&1
  if %ERRORLEVEL%==0 (
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if %ERRORLEVEL%==0 set "PYTHON=python3"
  )
)

if not defined PYTHON (
  echo [ERREUR] Python 3.10+ introuvable dans le PATH.
  echo.
  echo Telechargez et installez le Python Install Manager:
  echo   https://www.python.org/ftp/python/pymanager/python-manager-26.3.msix
  echo.
  echo Lors de l'installation repondez: Y / Y / Y / N
  echo Puis relancez install.bat
  echo Details: DOCUMENTATION.md
  echo.
  pause
  exit /b 1
)

echo [OK] Interpreteur: %PYTHON%
%PYTHON% --version
echo.

REM --- Creation du venv ---
if exist ".venv\Scripts\python.exe" (
  echo [INFO] Environnement virtuel .venv deja present.
) else (
  echo [..] Creation du venv dans .venv ...
  %PYTHON% -m venv .venv
  if errorlevel 1 (
    echo [ERREUR] Impossible de creer le venv.
    pause
    exit /b 1
  )
  echo [OK] Venv cree: %CD%\.venv
)
echo.

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERREUR] %VENV_PY% introuvable apres creation du venv.
  pause
  exit /b 1
)

REM --- Mise a jour pip + dependances ---
echo [..] Mise a jour de pip ...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERREUR] Echec mise a jour pip.
  pause
  exit /b 1
)

echo.
echo [..] Installation des dependances (requirements.txt) ...
"%VENV_PY%" -m pip install --upgrade -r "%CD%\requirements.txt"
if errorlevel 1 (
  echo [ERREUR] Echec installation des dependances.
  pause
  exit /b 1
)

REM --- Dossiers de travail ---
if not exist "files" mkdir files
if not exist "download" mkdir download
if not exist "clips" mkdir clips
if not exist "processeds" mkdir processeds
if not exist "tools" mkdir tools

REM ============================================================
REM  Binaires Windows -> tools\ (via scripts\fetch_tools.py)
REM ============================================================
echo.
echo [..] Telechargement / installation des binaires dans tools\ ...
"%VENV_PY%" "%CD%\scripts\fetch_tools.py"
if errorlevel 1 (
  echo.
  echo [ERREUR] Echec installation des binaires dans tools\
  echo   Verifiez la connexion Internet, puis relancez install.bat
  echo   Ou copiez manuellement ffmpeg.exe et ffprobe.exe dans tools\
  echo.
  pause
  exit /b 1
)

echo.
echo [..] Contenu de tools\ :
dir /b "tools"
echo.

if not exist "tools\ffmpeg.exe" (
  echo [ERREUR] tools\ffmpeg.exe toujours absent apres install.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   Arch's Auto Clipping - Installation terminee.
echo   Lancez le programme avec:  run.bat
echo.
echo   Binaires locaux:
echo     %CD%\tools\ffmpeg.exe
echo     %CD%\tools\ffprobe.exe
echo ============================================
echo.
pause
endlocal
exit /b 0
