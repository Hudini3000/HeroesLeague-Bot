@echo off
chcp 65001 > nul
REM ============================================================
REM 勇者联盟挂机脚本 v8 - 直接启动（不守护）
REM ============================================================
REM 功能：
REM   直接启动 boss_auto_v8.py，退出后不自动重启
REM   适合需要手动控制重启的场景
REM
REM 使用方法：
REM   双击运行此文件
REM   按 F4 停止脚本
REM ============================================================

set SCRIPT_DIR=%~dp0
set SCRIPT=%SCRIPT_DIR%boss_auto_v8.py
set PYTHON="D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe"

if not exist "%SCRIPT%" (
    echo [ERROR] 找不到脚本: %SCRIPT%
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
%PYTHON% "%SCRIPT%"

echo.
echo 脚本已退出，按任意键关闭窗口...
pause > nul
