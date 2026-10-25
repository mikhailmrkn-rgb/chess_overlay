@echo off
setlocal
title Chess Overlay
cd /d "%~dp0"

rem ---- 1. Find Python -------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (python --version >nul 2>&1 && set "PY=python")
if not defined PY goto nopython

rem ---- 2. Python packages (first run only) -----------------------------------
%PY% -c "import numpy, mss, tkinter" >nul 2>&1
if not errorlevel 1 goto haveparts
echo Installing the Python packages numpy and mss (first run only)...
%PY% -m pip install --user --disable-pip-version-check numpy mss
if errorlevel 1 %PY% -m pip install --disable-pip-version-check numpy mss
%PY% -c "import numpy, mss, tkinter" >nul 2>&1
if errorlevel 1 goto pipfail
:haveparts

rem ---- 3. Go (the app downloads the Stockfish engine by itself on first run)
:run
echo Starting Chess Overlay. Keep this window open - closing it quits the app.
%PY% "%~dp0chess_overlay.py"
if errorlevel 1 pause
exit /b 0

:nopython
echo.
echo Python 3 isn't installed (or isn't on PATH).
echo Install it from https://www.python.org/downloads/ - tick "Add python.exe to PATH" -
echo then double-click this file again.
echo.
pause
exit /b 1

:pipfail
echo.
echo Couldn't install the Python packages. Try running this in a terminal:
echo     %PY% -m pip install numpy mss
echo If it says tkinter is missing, re-run the Python installer and tick "tcl/tk and IDLE".
echo.
pause
exit /b 1
