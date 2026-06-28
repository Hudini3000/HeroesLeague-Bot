#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本：将 boss_auto_v8.py 打包成独立 .exe
使用方法：
  python build_exe.py
  生成的 .exe 在 dist/ 目录下
"""
import os
import sys
import subprocess

# PyInstaller 路径
PYINSTALLER = "pyinstaller"

# 脚本路径
SCRIPT = "boss_auto_v8.py"

# 模板图片路径
TEMPLATES = [
    ("templates/boss_icon.png", "templates"),
    ("templates/boss_list_btn.png", "templates"),
    ("templates/confirm_btn.png", "templates"),
    ("templates/go_btn.png", "templates"),
    ("templates/refreshed_text.png", "templates"),
]

# PyInstaller 参数
args = [
    PYINSTALLER,
    "--onefile",              # 打包成单个 .exe
    "--console",              # 显示控制台窗口（方便看日志）
    "--name", "勇者联盟挂机v8",  # .exe 文件名
    "--add-data", f"templates{os.pathsep}templates",  # 打包模板图片
    "--hidden-import", "cv2",
    "--hidden-import", "numpy",
    "--hidden-import", "pyautogui",
    "--hidden-import", "pygetwindow",
    SCRIPT,
]

print("=" * 60)
print("开始打包...")
print(f"命令: {' '.join(args)}")
print("=" * 60)

# 运行 PyInstaller
result = subprocess.run(args, cwd=os.path.dirname(__file__) or ".")

if result.returncode == 0:
    print("\n" + "=" * 60)
    print("✅ 打包成功！")
    print(f"输出目录: {os.path.join(os.path.dirname(__file__), 'dist')}")
    print("=" * 60)
else:
    print("\n" + "=" * 60)
    print("❌ 打包失败！")
    print("=" * 60)
    sys.exit(1)
