@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\migrate_windows.ps1" -Mode Generate %*
set "video_exit=%errorlevel%"
pause
exit /b %video_exit%
