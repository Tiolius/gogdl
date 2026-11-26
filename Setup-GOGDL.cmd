@echo off
setlocal
cd /d "%~dp0"
where python.exe >nul 2>&1
if errorlevel 1 (
    py -3 -m pip install --target ".gogdl-runtime" -r requirements.txt
) else (
    python.exe -m pip install --target ".gogdl-runtime" -r requirements.txt
)
if errorlevel 1 pause
