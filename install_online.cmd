@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_online.ps1" %*
set "install_exit=%errorlevel%"
pause
exit /b %install_exit%
