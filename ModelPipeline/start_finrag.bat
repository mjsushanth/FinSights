@echo off
REM start_finrag.bat - One-click launcher for FinRAG (Windows)
REM This wrapper calls the PowerShell script with proper execution policy

echo Starting FinRAG...
echo.

REM Run PowerShell script with bypass execution policy
powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_finrag.ps1"

REM Keep window open if there was an error
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Script failed with error code %ERRORLEVEL%
    pause
)
