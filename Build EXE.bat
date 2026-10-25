@echo off
setlocal
title Building Chess Overlay.exe
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (python --version >nul 2>&1 && set "PY=python")
if not defined PY goto nopython

echo Building "Chess Overlay.exe" - this takes 1 to 3 minutes. Keep this window open.
echo.
%PY% "%~dp0build_exe.py"
if errorlevel 1 goto failed
echo.
pause
exit /b 0

:failed
echo.
echo The build didn't finish - see the messages above.
pause
exit /b 1

:nopython
echo.
echo Python 3 isn't installed (or isn't on PATH). It's only needed to BUILD the .exe -
echo the finished .exe runs without it.
echo Install Python from https://www.python.org/downloads/ - tick "Add python.exe to PATH" -
echo then double-click this file again.
echo.
pause
exit /b 1
