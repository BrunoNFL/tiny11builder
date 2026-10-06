@echo off
rem SetupComplete.cmd - Tiny11 debloat runner
if exist "%SystemRoot%\Setup\Scripts\tiny11-debloat.ps1" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SystemRoot%\Setup\Scripts\tiny11-debloat.ps1"
)
exit /b 0
