@echo off
chcp 65001 > nul
REM ============================================================
REM 勇者联盟挂机脚本 v8 - 守护进程（自动重启）
REM ============================================================
REM 功能：
REM   1. 启动 boss_auto_v8.py
REM   2. 检测脚本是否退出
REM   3. 如果脚本退出（包括凌晨4点自动重启），等待10秒后自动重启
REM   4. 无限循环，实现 24/7 挂机
REM
REM 使用方法：
REM   双击运行此文件，最小化即可
REM   按 Ctrl+C 可停止守护进程
REM ============================================================

set SCRIPT_DIR=%~dp0
set SCRIPT=%SCRIPT_DIR%boss_auto_v8.py
set PYTHON="D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe"
set LOG=%SCRIPT_DIR%watchdog_log.txt

echo [%date% %time%] 守护进程启动 > "%LOG%"
echo 脚本目录: %SCRIPT_DIR% >> "%LOG%"
echo 脚本文件: %SCRIPT% >> "%LOG%"
echo. >> "%LOG%"

:loop
REM 检查脚本是否存在
if not exist "%SCRIPT%" (
    echo [ERROR] 找不到脚本: %SCRIPT%
    echo [%date% %time%] [ERROR] 找不到脚本: %SCRIPT% >> "%LOG%"
    pause
    exit /b 1
)

REM 启动脚本
echo [%date% %time%] 正在启动脚本...
echo [%date% %time%] 正在启动脚本... >> "%LOG%"
start /wait "" %PYTHON% "%SCRIPT%"

REM 脚本已退出，检查退出原因
echo [%date% %time%] 脚本已退出，等待10秒后重启...
echo [%date% %time%] 脚本已退出，等待10秒后重启... >> "%LOG%"

REM 删除重启标记文件（让脚本在下次运行时可以重新重启）
del "%SCRIPT_DIR%.restart_marker" > nul 2>&1

REM 等待10秒
timeout /t 10 /nobreak > nul

REM 继续循环（自动重启）
goto loop
