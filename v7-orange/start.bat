@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   Heroes League Boss Bot v7 (orange)
echo   - wait for battle end before next boss
echo ========================================
echo.
echo   [1] diagnose (scan only, no click)
echo   [2] start bot
echo.
set /p choice="choice (1/2): "
if "%choice%"=="1" (
    "D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" "%~dp0boss_auto_v7.py" --diagnose
) else (
    "D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" "%~dp0boss_auto_v7.py"
)
pause
