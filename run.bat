@echo off
cd /d "%~dp0"

set PY=python
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python not found. Install it from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" in the installer.
        pause
        exit /b 1
    )
    set PY=py -3
)

if not exist ".venv\Scripts\activate.bat" (
    echo First run: creating environment and installing Ursina, please wait...
    %PY% -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Install failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
) else (
    call ".venv\Scripts\activate.bat"
)

python main.py %*
if errorlevel 1 pause
