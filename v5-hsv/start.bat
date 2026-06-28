@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 勇者联盟 - 首领挂机 v5
echo ==============================
echo   勇者联盟 首领挂机 v5
echo   HSV颜色检测 · 自动滚屏
echo ==============================
echo.
echo 运行中... 关闭此窗口停止
"D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" boss_auto_v5.py
echo.
echo 运行结束，按任意键退出
pause >nul
