@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\migrate_windows.ps1" -Mode Export %*
set "migration_exit=%errorlevel%"
pause
exit /b %migration_exit%
