@echo off
REM Build Arch's Auto Clipping (onedir) — a executer sur Windows 11
setlocal
cd /d "%~dp0"

echo === Arch's Auto Clipping build ===

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Venv absent - lancement de install.bat ...
  call "%~dp0install.bat"
)

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERREUR] .venv introuvable. Lancez install.bat d'abord.
  exit /b 1
)

"%VENV_PY%" -m pip install pyinstaller>=6.0.0
if errorlevel 1 (
  echo Echec installation PyInstaller
  exit /b 1
)

"%VENV_PY%" -m PyInstaller --noconfirm jungo_clip.spec
if errorlevel 1 (
  echo Echec PyInstaller
  exit /b 1
)

REM Dossiers de travail a cote de l'exe
if not exist "dist\jungo_clip\files" mkdir "dist\jungo_clip\files"
if not exist "dist\jungo_clip\download" mkdir "dist\jungo_clip\download"
if not exist "dist\jungo_clip\clips" mkdir "dist\jungo_clip\clips"
if not exist "dist\jungo_clip\processeds" mkdir "dist\jungo_clip\processeds"

echo.
echo Build OK: dist\jungo_clip\jungo_clip.exe  (Arch's Auto Clipping)
echo Placez ffmpeg.exe et ffprobe.exe dans dist\jungo_clip\ (ou dans le PATH).
echo Placez vos CSV dans dist\jungo_clip\files\
echo.
endlocal
