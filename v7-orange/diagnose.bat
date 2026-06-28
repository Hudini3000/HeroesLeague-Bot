@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   Heroes League v7 - diagnose
echo ========================================
echo.
"D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" "%~dp0boss_auto_v7.py" --diagnose
pause
