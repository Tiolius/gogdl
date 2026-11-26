@echo off
if not exist "%~dp0.gogdl-runtime\webview\lib\Microsoft.Web.WebView2.Core.dll" (
    echo Run Setup-GOGDL.cmd before starting GOGDL.
    pause
    exit /b 1
)
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0GOGDL-Web.pyw"
    exit /b
)
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0GOGDL-Web.pyw"
    exit /b
)
echo Python 3.11 or newer and Microsoft Edge WebView2 are required.
pause
