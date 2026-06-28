#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勇者联盟 - 首领自动挂机 截图助手
采集3个模板即可运行
"""
import pyautogui
import os
import time
import keyboard

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

TEMPLATES = [
    ("boss_list_btn.png", "左上角「首领列表」按钮"),
    ("refreshed_text.png", "BOSS名字旁边的「已刷新」三个字"),
    ("go_btn.png", "弹出界面中的「前往」按钮"),
    ("confirm_btn.png", "传送弹窗中的黄色「确认」按钮"),
]

existing = [t[0] for t in TEMPLATES if os.path.exists(os.path.join(TEMPLATES_DIR, t[0]))]

print("=" * 50)
print("📸 勇者联盟 - 模板截图助手")
print("=" * 50)
print()
print("操作说明:")
print("  1. 打开游戏到对应界面")
print("  2. 鼠标移到目标元素上")
print("  3. 按 S 键截图（截取周围80x80区域）")
print("  4. 按 Q 退出")
print()
print("需要采集的模板:")

for i, (filename, desc) in enumerate(TEMPLATES, 1):
    done = "✅" if filename in existing else "⬜"
    print(f"  {done} {i}. {filename}  - {desc}")

print()
print(f"  已完成: {len(existing)}/{len(TEMPLATES)}")
print()

current_target = 0
for i, (filename, desc) in enumerate(TEMPLATES):
    if filename not in existing:
        current_target = i
        break
else:
    print("🎉 所有模板已采集完毕，按 Q 退出或直接运行主脚本")
    current_target = -1

if current_target >= 0:
    fn, desc = TEMPLATES[current_target]
    print(f"🎯 当前目标 [{current_target+1}/{len(TEMPLATES)}]: {fn}")
    print(f"   说明: {desc}")
    print(f"   将鼠标移到该元素上 → 按 S 截图")

print()
print("热键: S=截图  Q=退出")
print("-" * 50)

while True:
    event = keyboard.read_event(suppress=True)
    if event.event_type == 'down':
        if event.name == 's' and current_target >= 0:
            x, y = pyautogui.position()
            region = (x - 40, y - 40, 80, 80)
            filename = TEMPLATES[current_target][0]
            filepath = os.path.join(TEMPLATES_DIR, filename)
            screenshot = pyautogui.screenshot(region=region)
            screenshot.save(filepath)
            print(f"  ✅ 已保存: {filename}")
            existing.append(filename)
            
            # 找下一个未采集的
            current_target = -1
            for i, (fn2, desc2) in enumerate(TEMPLATES):
                if fn2 not in existing:
                    current_target = i
                    break
            
            if current_target >= 0:
                fn2, desc2 = TEMPLATES[current_target]
                print(f"🎯 下一个 [{current_target+1}/{len(TEMPLATES)}]: {fn2}")
                print(f"   说明: {desc2}")
                print(f"   将鼠标移到该元素上 → 按 S 截图")
            else:
                print("🎉 全部模板采集完成！可以运行主脚本了")
        
        elif event.name == 'q':
            print("👋 退出截图助手")
            break
