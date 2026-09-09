@echo off
setlocal
cd /d "%~dp0"

if not exist "rbxmanager\__main__.py" (
    echo This file has to sit next to the rbxmanager folder.
    echo Copy the whole Roblox Account Manager folder, not just run.bat.
    pause
    exit /b 1
)

rem pythonw runs it without a console window; python is the fallback
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw -m rbxmanager
    exit /b 0
)

where python >nul 2>&1
if %errorlevel%==0 (
    python -m rbxmanager
    exit /b 0
)

echo Python 3 was not found.
echo Install it from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH" during setup, then run this again.
pause
exit /b 1
