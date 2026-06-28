@echo off
chcp 65001 >nul
title 勇者联盟 v6 - 双检测多尺度
cd /d "%~dp0"
echo.
echo ================================
echo  勇者联盟 首领挂机 v6.0
echo  双检测: 模板匹配 + HSV 颜色
echo ================================
echo.
"D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" boss_auto_v6.py
echo.
pause
