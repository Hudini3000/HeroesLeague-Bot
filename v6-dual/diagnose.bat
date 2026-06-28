@echo off
chcp 65001 >nul
title 勇者联盟 v6 - 诊断模式
cd /d "%~dp0"
echo.
echo ================================
echo  勇者联盟 v6 - 诊断模式
echo  只扫描，保存截图，不点击
echo ================================
echo.
"D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" boss_auto_v6.py --diagnose
echo.
pause
