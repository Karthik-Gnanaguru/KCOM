@echo off
:: ──────────────────────────────────────────────────────────────────────────────
:: KCom — Windows build script
:: Produces: dist\KCom\KCom.exe  (directory bundle)
::
:: Usage (from project root):
::   build\build_windows.bat
:: ──────────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo == KCom Windows Build ============================================

:: ── Locate a working Python interpreter ──────────────────────────────────
::    Try the Python Launcher first (py -3), then plain "python".
::    The Microsoft Store stub on fresh Windows installs is detected and
::    rejected here with a helpful message.
set "PY="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 (
        :: Reject the Microsoft Store stub (it exits 9009 with no output)
        for /f "tokens=*" %%v in ('python --version 2^>nul') do set "PYVER=%%v"
        if defined PYVER set "PY=python"
    )
)
if not defined PY (
    echo.
    echo ERROR: Python 3.11+ was not found on PATH.
    echo.
    echo   1. Download Python 3.11+ ^(64-bit^) from https://www.python.org/downloads/windows/
    echo   2. During install, tick "Add python.exe to PATH".
    echo   3. If Windows shows the Microsoft Store stub, disable it under:
    echo        Settings ^> Apps ^> Advanced app settings ^> App execution aliases
    echo      and turn OFF both "python.exe" and "python3.exe".
    echo   4. Open a NEW PowerShell window and re-run this script.
    echo.
    exit /b 1
)

%PY% --version
echo Using : %PY%
echo Root  : %CD%
echo.

:: ── Install runtime + build tooling so PyInstaller can bundle everything ─
%PY% -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip upgrade failed.
    exit /b 1
)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: installing requirements.txt failed.
    exit /b 1
)
%PY% -m pip install "pyinstaller>=6.8.0"
if errorlevel 1 (
    echo ERROR: installing PyInstaller failed.
    exit /b 1
)

:: ── Clean previous artefacts ─────────────────────────────────────────────
if exist dist rmdir /s /q dist
if exist build\__pycache__ rmdir /s /q build\__pycache__

:: ── Build ────────────────────────────────────────────────────────────────
%PY% -m PyInstaller build\kcom.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    exit /b 1
)

:: ── Strip unused Qt6 modules to slim the bundle ──────────────────────────
if exist dist\KCom (
    %PY% build\post_clean.py dist\KCom
)

echo.
echo == Build complete ================================================
echo Output: %CD%\dist\KCom\KCom.exe
dir dist\KCom\KCom.exe

endlocal
