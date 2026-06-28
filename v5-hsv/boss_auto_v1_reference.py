#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勇者联盟 - 首领自动挂机脚本 v3.0
==================================
按用户要求重新设计：
  1. 启动时游戏在任意界面，脚本自动点击"首领"按钮打开列表
  2. 列表默认在顶部，单次显示4个BOSS
  3. 流程：顶部4个 → 向下滚3-4次 → 无BOSS则向上滚回顶部
  4. 全程循环，直到手动停止

使用方法:
  双击桌面"首领挂机.bat"
  热键: F2=暂停/恢复  F4=停止
"""
import os
import sys
import time
import random
import threading
import datetime

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw

# 配置
CONFIG = {
    "boss_btn_confidence":   0.55,    # 首领按钮（更宽松）
    "refreshed_confidence":  0.55,    # 已刷新文字
    "go_btn_confidence":     0.65,    # 前往按钮
    "confirm_btn_confidence":0.65,    # 传送确认
    
    "bosses_per_page":       4,       # 每页显示4个BOSS
    "scroll_down_times":     4,       # 向下滚4次
    "scroll_up_times":       4,       # 向上滚4次回顶
    "scroll_pixels":         180,     # 每次滚动距离
    
    "loop_interval": (0.8, 1.5),
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

def rand(a, b): return random.uniform(a, b)
def randint(a, b): return random.randint(a, b)

def human_click(x, y, max_offset=3):
    """带随机偏移的点击"""
    ox, oy = randint(-max_offset, max_offset), randint(-max_offset, max_offset)
    pyautogui.moveTo(x + ox, y + oy, rand(0.05, 0.12))
    time.sleep(rand(0.02, 0.05))
    pyautogui.click()
    time.sleep(rand(0.05, 0.12))

def human_drag(start_x, start_y, end_x, end_y, duration=0.35):
    """模拟人手拖动"""
    pyautogui.moveTo(start_x, start_y)
    time.sleep(0.05)
    pyautogui.mouseDown(button='left')
    time.sleep(0.05)
    steps = max(8, int(duration * 25))
    for i in range(1, steps + 1):
        t = i / steps
        eased = 2*t*t if t < 0.5 else 1 - pow(-2*t + 2, 2)/2
        x = start_x + (end_x - start_x) * eased
        y = start_y + (end_y - start_y) * eased
        pyautogui.moveTo(int(x), int(y))
        time.sleep(duration / steps)
    time.sleep(0.05)
    pyautogui.mouseUp(button='left')

def capture_window(win):
    """截取窗口，返回 (图像, 窗口对象)"""
    if win is None:
        return None, None
    if win.isMinimized:
        win.restore()
        time.sleep(0.3)
    try:
        win.activate()
    except:
        pass
    screenshot = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    return img, win

def find_template(img, template_path, confidence=0.6):
    """找最佳匹配，返回 (cx, cy, conf) 或 None"""
    if img is None or not os.path.exists(template_path):
        return None
    tpl = cv2.imread(template_path)
    if tpl is None:
        return None
    th, tw = tpl.shape[:2]
    if img.shape[0] < th or img.shape[1] < tw:
        return None
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= confidence:
        return (max_loc[0] + tw // 2, max_loc[1] + th // 2, float(max_val))
    return None

def find_all_templates(img, template_path, confidence=0.55, min_dist=30):
    """找所有匹配，NMS去重，返回 [(cx, cy, conf), ...] 按y排序"""
    if img is None or not os.path.exists(template_path):
        return []
    tpl = cv2.imread(template_path)
    if tpl is None:
        return []
    th, tw = tpl.shape[:2]
    if img.shape[0] < th or img.shape[1] < tw:
        return []
    
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= confidence)
    
    candidates = [(int(x), int(y), float(result[y, x])) for x, y in zip(xs, ys)]
    if not candidates:
        return []
    
    # NMS
    candidates.sort(key=lambda c: -c[2])
    final = []
    for x, y, conf in candidates:
        dup = False
        for fx, fy, fc in final:
            if abs(x - fx) < min_dist and abs(y - fy) < min_dist:
                dup = True
                break
        if not dup:
            final.append((x, y, conf))
    
    # 转中心坐标，按y排序
    out = [(x + tw//2, y + th//2, c) for x, y, c in final]
    out.sort(key=lambda m: m[1])
    return out

def check_templates():
    required = ["boss_list_btn.png", "refreshed_text.png", "go_btn.png", "confirm_btn.png"]
    missing = []
    for t in required:
        path = os.path.join(TEMPLATES_DIR, t)
        if not os.path.exists(path):
            missing.append(t)
        else:
            img = cv2.imread(path)
            if img is None:
                missing.append(f"{t}(损坏)")
            else:
                print(f"[OK] {t}: {img.shape[1]}x{img.shape[0]}")
    if missing:
        print("[ERR] 缺少或损坏的模板:")
        for m in missing:
            print(f"   - {m}")
        return False
    return True

class BossAutoBot:
    def __init__(self):
        self.paused = False
        self.stopped = False
        self.total_bosses = 0
        self.start_time = time.time()
        self.win = None
        
    def log(self, msg):
        elapsed = time.time() - self.start_time
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        try:
            print(f"[{h:02d}:{m:02d}:{s:02d}] {msg}")
        except:
            safe = ''.join(c for c in msg if ord(c) < 128)
            print(f"[{h:02d}:{m:02d}:{s:02d}] {safe}")
    
    def wait_if_paused(self):
        while self.paused and not self.stopped:
            time.sleep(0.2)
    
    def find_game_window(self):
        """找游戏窗口"""
        titles = ["勇者联盟", "微信"]
        for t in titles:
            wins = gw.getWindowsWithTitle(t)
            if wins:
                return wins[0]
        return None
    
    def click_boss_button(self):
        """点击左上角"首领"按钮"""
        img, _ = capture_window(self.win)
        if img is None:
            return False
        
        btn = find_template(
            img,
            os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
            CONFIG["boss_btn_confidence"]
        )
        if btn:
            # 窗口内坐标转屏幕坐标
            sx = self.win.left + btn[0]
            sy = self.win.top + btn[1]
            self.log(f"[BTN] 点击首领按钮 @ ({sx}, {sy}) conf={btn[2]:.2f}")
            human_click(sx, sy)
            return True
        return False
    
    def scroll_list(self, direction='down'):
        """在列表区域拖动滚动
        direction='down': 向下拖动鼠标 = 列表向上滚 = 看下面的BOSS
        direction='up': 向上拖动鼠标 = 列表向下滚 = 看上面的BOSS
        """
        # 列表区域：窗口中间偏左，y在中间偏上位置
        # 根据截图，首领列表在左侧，宽度约1/3屏幕
        list_x = self.win.left + int(self.win.width * 0.25)  # 左侧1/4处
        list_y = self.win.top + int(self.win.height * 0.35)  # 从上往下35%
        
        drag = CONFIG["scroll_pixels"]
        if direction == 'down':
            end_y = list_y + drag
        else:
            end_y = list_y - drag
        
        self.log(f"[SCROLL] {direction}: ({list_x}, {list_y}) -> ({list_x}, {end_y})")
        human_drag(list_x, list_y, list_x, end_y, duration=0.3)
        time.sleep(rand(0.3, 0.6))
    
    def find_refreshed_bosses(self):
        """在当前画面找所有已刷新BOSS"""
        img, _ = capture_window(self.win)
        if img is None:
            return []
        
        bosses = find_all_templates(
            img,
            os.path.join(TEMPLATES_DIR, "refreshed_text.png"),
            confidence=CONFIG["refreshed_confidence"],
            min_dist=40
        )
        return bosses
    
    def click_boss_and_go(self, boss_pos):
        """点击BOSS，然后快速点前往和确认"""
        bx, by, conf = boss_pos
        
        # "已刷新"在右侧，往左约80px点BOSS名字/头像区域
        click_x = self.win.left + bx - 80 + randint(-5, 5)
        click_y = self.win.top + by + randint(-5, 5)
        
        self.log(f"[CLICK] 点击BOSS @ ({click_x}, {click_y}) conf={conf:.2f}")
        human_click(click_x, click_y)
        time.sleep(rand(0.2, 0.4))
        
        # 快速找"前往"按钮（5秒内）
        for i in range(15):
            if self.stopped:
                return False
            self.wait_if_paused()
            
            img, _ = capture_window(self.win)
            if img is None:
                time.sleep(0.2)
                continue
            
            go = find_template(
                img,
                os.path.join(TEMPLATES_DIR, "go_btn.png"),
                CONFIG["go_btn_confidence"]
            )
            if go:
                sx = self.win.left + go[0]
                sy = self.win.top + go[1]
                self.log(f"[GO] 点击前往 @ ({sx}, {sy})")
                human_click(sx, sy)
                
                # 点确认传送
                time.sleep(rand(0.2, 0.4))
                self.click_confirm()
                return True
            
            time.sleep(0.25)
        
        self.log("[WARN] 未找到前往按钮")
        return False
    
    def click_confirm(self):
        """点击传送确认"""
        for i in range(10):
            if self.stopped:
                return False
            self.wait_if_paused()
            
            img, _ = capture_window(self.win)
            if img is None:
                time.sleep(0.2)
                continue
            
            cf = find_template(
                img,
                os.path.join(TEMPLATES_DIR, "confirm_btn.png"),
                CONFIG["confirm_btn_confidence"]
            )
            if cf:
                sx = self.win.left + cf[0]
                sy = self.win.top + cf[1]
                self.log(f"[OK] 点击确认传送 @ ({sx}, {sy})")
                human_click(sx, sy)
                return True
            
            time.sleep(0.2)
        return False
    
    def wait_battle_end(self):
        """等待战斗结束（首领按钮重新出现）"""
        self.log("[BATTLE] 战斗中...")
        start = time.time()
        last_log = 0
        
        while time.time() - start < 120:  # 2分钟超时
            if self.stopped:
                return False
            self.wait_if_paused()
            
            elapsed = time.time() - start
            if int(elapsed) % 10 == 0 and int(elapsed) != last_log:
                self.log(f"  [BATTLE] {int(elapsed)}秒...")
                last_log = int(elapsed)
            
            img, _ = capture_window(self.win)
            if img is None:
                time.sleep(0.5)
                continue
            
            # 首领按钮出现 = 回到主界面 = 战斗结束
            btn = find_template(
                img,
                os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
                CONFIG["boss_btn_confidence"] - 0.05
            )
            if btn and elapsed > 5:
                self.log(f"[DONE] 战斗结束！用时{int(elapsed)}秒")
                self.total_bosses += 1
                time.sleep(rand(0.5, 1.0))
                return True
            
            time.sleep(0.4)
        
        self.log("[TIMEOUT] 战斗超时")
        return True
    
    def process_boss_list(self):
        """处理首领列表：顶部4个 → 向下滚4次 → 无则回顶"""
        scroll_down_count = 0
        
        while not self.stopped:
            self.wait_if_paused()
            
            # 找当前画面的已刷新BOSS
            bosses = self.find_refreshed_bosses()
            
            if bosses:
                self.log(f"[FOUND] 发现 {len(bosses)} 个已刷新BOSS")
                # 处理最上面的一个
                boss = bosses[0]
                if self.click_boss_and_go(boss):
                    self.wait_battle_end()
                    # 战斗完回到主界面，需要重新打开首领列表
                    return True  # 返回主循环，重新打开列表
                else:
                    # 前往失败，继续找下一个
                    time.sleep(rand(0.5, 1.0))
                    continue
            
            # 当前画面没有已刷新BOSS
            if scroll_down_count < CONFIG["scroll_down_times"]:
                scroll_down_count += 1
                self.log(f"[SCAN] 无BOSS，向下滚动 ({scroll_down_count}/{CONFIG['scroll_down_times']})")
                self.scroll_list('down')
            else:
                # 已经向下滚了4次，还是没BOSS，回顶部
                self.log("[SCAN] 向下搜索完毕，无BOSS，回顶部")
                for i in range(CONFIG["scroll_up_times"]):
                    self.scroll_list('up')
                    time.sleep(0.2)
                self.log("[SCAN] 已回顶部，完成一轮扫描")
                return False  # 本轮扫描结束，无BOSS可打
        
        return False
    
    def run(self):
        print("=" * 50)
        print("[BOT] 勇者联盟 - 首领自动挂机 v3.0")
        print("=" * 50)
        print()
        
        if not check_templates():
            print("\n请先运行 capture_boss_templates.py 截取模板")
            return
        
        self.win = self.find_game_window()
        if self.win is None:
            print("[ERR] 未找到游戏窗口（查找'勇者联盟'或'微信'）")
            return
        
        print(f"[OK] 窗口: {self.win.title}")
        print(f"     位置: ({self.win.left}, {self.win.top}) {self.win.width}x{self.win.height}")
        
        if self.win.isMinimized:
            self.win.restore()
        try:
            self.win.activate()
        except:
            pass
        
        print()
        print("3秒后开始...")
        print("热键: F2=暂停/恢复  F4=停止")
        print()
        time.sleep(3)
        
        # 启动热键监听
        threading.Thread(target=self.hotkey_listener, daemon=True).start()
        
        self.start_time = time.time()
        cycle = 0
        
        while not self.stopped:
            self.wait_if_paused()
            cycle += 1
            
            # 检查窗口
            self.win = self.find_game_window()
            if self.win is None:
                self.log("[WARN] 窗口丢失，等待...")
                time.sleep(3)
                continue
            
            self.log(f"\n========== 第{cycle}轮 ==========")
            
            # Step 1: 点击首领按钮打开列表
            self.log("[STEP1] 点击首领按钮...")
            if not self.click_boss_button():
                self.log("[WARN] 未找到首领按钮，可能已在列表界面或窗口被遮挡")
                # 尝试直接处理列表
            else:
                time.sleep(rand(1.0, 1.5))  # 等待列表打开
            
            # Step 2: 处理列表（找BOSS → 向下滚4次 → 回顶）
            self.log("[STEP2] 扫描首领列表...")
            found = self.process_boss_list()
            
            if not found:
                # 本轮没打到BOSS，等待一下再开始下一轮
                self.log("[WAIT] 本轮无BOSS可打，等待继续...")
                time.sleep(rand(2.0, 3.0))
            
            # 统计
            elapsed = time.time() - self.start_time
            m, s = divmod(int(elapsed), 60)
            h, m = divmod(m, 60)
            self.log(f"[STAT] 击杀: {self.total_bosses} | 耗时: {h:02d}:{m:02d}:{s:02d}")
        
        print(f"\n[END] 已停止! 共击杀 {self.total_bosses} 个BOSS")
    
    def hotkey_listener(self):
        import keyboard as kb
        while not self.stopped:
            try:
                if kb.is_pressed('F2'):
                    self.paused = not self.paused
                    print("[PAUSED]" if self.paused else "[RUNNING]")
                    time.sleep(0.5)
                if kb.is_pressed('F4'):
                    self.stopped = True
                    break
            except:
                pass
            time.sleep(0.1)


if __name__ == "__main__":
    bot = BossAutoBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[EXIT] 用户中断")
    except Exception as e:
        print(f"\n[ERROR] {repr(e)}")
        import traceback
        traceback.print_exc()
