@echo off
REM setup_finrag.bat - One-click setup launcher for FinRAG (Windows)

echo Setting up FinRAG...
echo.

REM Run PowerShell setup script with execution policy bypass
powershell.exe -ExecutionPolicy Bypass -File "%~dp0setup_finrag.ps1"

REM Keep window open if there was an error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Setup failed with error code %ERRORLEVEL%
    pause
)