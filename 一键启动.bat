@echo off
setlocal
title Community Elder Care Platform
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] Project Python environment not found:
    echo "%~dp0.venv\Scripts\python.exe"
    echo Please restore the project .venv environment first.
    pause
    exit /b 1
)

if not exist "%~dp0start.ps1" (
    echo [ERROR] start.ps1 was not found in the project folder.
    pause
    exit /b 1
)

echo Starting the platform with the project .venv environment...
echo Open http://127.0.0.1:5000 in your browser after the server starts.
echo Press Ctrl+C in this window to stop the service.
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "startup_exit=%errorlevel%"
echo.
echo The service has stopped. Any error details are shown above.
pause
exit /b %startup_exit%
