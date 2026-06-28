#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勇者联盟 - 首领自动挂机脚本 v4.0（防风控版）
================================================
相对 v3.0 的核心升级:
  ✅ 窗口绑定 - 不再写死屏幕绝对坐标，所有点击用窗口偏移
  ✅ DPI 适配 - SetProcessDpiAwareness(2) 防 125%/150% 缩放错位
  ✅ 防风控 - 贝塞尔曲线移动 + 可变点击时长 + 偶尔长停顿
  ✅ F1 初始化向导 - 鼠标悬停捕获元素位置
  ✅ 配置可分享 - boss_config.json 保存偏移量
  ✅ 20 分钟冷却追踪 - is_recently_killed() 防重复打同一个BOSS

用法:
  1. 首次运行按 F1 启动初始化向导（鼠标悬停'首领'按钮）
  2. 日常运行直接双击桌面"首领挂机v4.bat"
  热键:
    F1 = 初始化向导
    F2 = 暂停/恢复
    F4 = 停止
"""
import ctypes

# === DPI 适配必须在所有 GUI 库导入之前 ===
try:
    # Per-Monitor DPI Awareness (Win 10 1703+)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        # Fallback for older systems
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import os
import sys
import json
import time
import math
import random
import threading
import datetime

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw

# ============================================================
# 配置
# ============================================================
CONFIG_FILE = "boss_config.json"

DEFAULT_CONFIG = {
    "window_title":   "勇者联盟",
    "fallback_titles":["微信"],

    # 窗口内相对坐标（由 F1 向导设置）
    "boss_button_offset": [130, 100],

    # 模板匹配置信度
    "boss_btn_confidence":    0.55,
    "refreshed_confidence":   0.55,
    "go_btn_confidence":      0.65,
    "confirm_btn_confidence": 0.65,

    # 滚动参数
    "scroll_pixels":      180,
    "scroll_down_times":  4,
    "scroll_up_times":    4,

    # 风控参数 - 模拟人类操作
    "timing": {
        "min_action_delay":  0.4,    # 动作间最小延迟(秒)
        "max_action_delay":  1.5,    # 动作间最大延迟(秒)
        "click_hold_min":    0.05,   # 按下时长最小
        "click_hold_max":    0.18,   # 按下时长最大
        "move_duration_min": 0.15,   # 鼠标移动最小耗时
        "move_duration_max": 0.5,    # 鼠标移动最大耗时
        "long_pause_chance": 0.10,   # 10% 概率长停顿(像在"看"屏幕)
    },

    # 20 分钟冷却 - 防止短时间内重复打同一个BOSS
    "recently_killed_window_sec": 300,  # 5 分钟内同位置BOSS视为已打过
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
CONFIG_PATH = os.path.join(BASE_DIR, CONFIG_FILE)


# ============================================================
# 配置加载/保存
# ============================================================
def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # 合并默认值
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            # timing 子项
            for k, v in DEFAULT_CONFIG["timing"].items():
                if k not in cfg.get("timing", {}):
                    cfg.setdefault("timing", {})[k] = v
            return cfg
        except Exception as e:
            print(f"[WARN] 配置读取失败: {e}，用默认")
    return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy


def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ERR] 保存配置失败: {e}")
        return False


# ============================================================
# 反检测 - 人类行为模拟
# ============================================================
def human_mouse_move(end_x, end_y, duration=None):
    """贝塞尔曲线移动鼠标 - 模拟人类手势（非直线）"""
    if duration is None:
        timing = DEFAULT_CONFIG["timing"]
        duration = random.uniform(timing["move_duration_min"],
                                  timing["move_duration_max"])

    start_x, start_y = pyautogui.position()
    dx = end_x - start_x
    dy = end_y - start_y
    distance = math.sqrt(dx * dx + dy * dy)

    # 距离太短直接走
    if distance < 30:
        pyautogui.moveTo(end_x, end_y, duration=duration * 0.6)
        time.sleep(duration * 0.4)
        return

    # 控制点：垂直于运动方向偏移，模拟手部弧线
    mid_x = (start_x + end_x) / 2
    mid_y = (start_y + end_y) / 2
    perp_x = -dy / distance
    perp_y = dx / distance
    offset_mag = random.uniform(0.1, 0.35) * distance
    ctrl_x = mid_x + perp_x * offset_mag + random.uniform(-40, 40)
    ctrl_y = mid_y + perp_y * offset_mag + random.uniform(-40, 40)

    # 二次贝塞尔曲线
    steps = max(15, int(duration * 50))
    for i in range(steps + 1):
        t = i / steps
        # ease-in-out
        eased_t = t * t * (3 - 2 * t)
        x = (1 - eased_t) ** 2 * start_x + \
            2 * (1 - eased_t) * eased_t * ctrl_x + \
            eased_t ** 2 * end_x
        y = (1 - eased_t) ** 2 * start_y + \
            2 * (1 - eased_t) * eased_t * ctrl_y + \
            eased_t ** 2 * end_y
        pyautogui.moveTo(int(x), int(y))
        time.sleep(duration / steps)

    # 微调对齐（人类落点会"补正"）
    if random.random() < 0.5:
        pyautogui.moveTo(end_x + random.randint(-2, 2),
                         end_y + random.randint(-2, 2),
                         duration=0.05)


def human_click(abs_x, abs_y, hold_min=0.05, hold_max=0.18):
    """像真人一样点击 - 移动曲线 + 按下抖动 + 可变时长"""
    move_dur = random.uniform(0.15, 0.45)
    human_mouse_move(abs_x, abs_y, duration=move_dur)

    # 按下
    pyautogui.mouseDown()
    # 按下时 30% 概率有微动
    if random.random() < 0.3:
        time.sleep(0.02)
        pyautogui.moveTo(abs_x + random.randint(-1, 1),
                         abs_y + random.randint(-1, 1))
    # 按住（模拟人类按下时长差异）
    hold = random.uniform(hold_min, hold_max)
    time.sleep(hold)
    pyautogui.mouseUp()

    # 后置小延迟
    time.sleep(random.uniform(0.05, 0.15))


def random_action_delay(timing=None):
    """动作间随机延迟，偶尔出现长停顿"""
    if timing is None:
        timing = DEFAULT_CONFIG["timing"]
    if random.random() < timing["long_pause_chance"]:
        # 10% 概率长停顿 2-5 秒（模拟"阅读"屏幕）
        time.sleep(random.uniform(2.0, 5.0))
    else:
        time.sleep(random.uniform(timing["min_action_delay"],
                                  timing["max_action_delay"]))


def human_drag(start_x, start_y, end_x, end_y, duration=0.35):
    """模拟人手拖动（带缓动）"""
    pyautogui.moveTo(start_x, start_y)
    time.sleep(0.08)
    pyautogui.mouseDown(button='left')
    time.sleep(0.08)
    steps = max(10, int(duration * 30))
    for i in range(1, steps + 1):
        t = i / steps
        eased = 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2
        x = start_x + (end_x - start_x) * eased
        y = start_y + (end_y - start_y) * eased
        pyautogui.moveTo(int(x), int(y))
        time.sleep(duration / steps)
    time.sleep(0.08)
    pyautogui.mouseUp(button='left')


# ============================================================
# 窗口管理
# ============================================================
class WindowManager:
    def __init__(self, title, fallback_titles=None):
        self.title = title
        self.fallback_titles = fallback_titles or []

    def find(self):
        """查找游戏窗口"""
        for t in [self.title] + self.fallback_titles:
            wins = gw.getWindowsWithTitle(t)
            if wins:
                win = wins[0]
                if win.width > 100 and win.height > 100:
                    return win
        return None

    def ensure_active(self, win):
        if win.isMinimized:
            win.restore()
            time.sleep(0.3)
        try:
            win.activate()
        except Exception:
            pass
        time.sleep(0.1)

    def capture(self, win):
        """截取窗口图像 (BGR)"""
        if win is None:
            return None
        if win.isMinimized:
            win.restore()
            time.sleep(0.3)
        try:
            screenshot = pyautogui.screenshot(
                region=(win.left, win.top, win.width, win.height))
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"[WARN] 截图失败: {e}")
            return None


# ============================================================
# 图像匹配
# ============================================================
def find_template(img, tpl_path, conf=0.6):
    """找最佳匹配"""
    if img is None or not os.path.exists(tpl_path):
        return None
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        return None
    th, tw = tpl.shape[:2]
    if img.shape[0] < th or img.shape[1] < tw:
        return None
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= conf:
        return (max_loc[0] + tw // 2, max_loc[1] + th // 2, float(max_val))
    return None


def find_all_templates(img, tpl_path, conf=0.55, min_dist=30):
    """找所有匹配，NMS去重，按y排序"""
    if img is None or not os.path.exists(tpl_path):
        return []
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        return []
    th, tw = tpl.shape[:2]
    if img.shape[0] < th or img.shape[1] < tw:
        return []
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= conf)
    candidates = [(int(x), int(y), float(result[y, x])) for x, y in zip(xs, ys)]
    if not candidates:
        return []
    candidates.sort(key=lambda c: -c[2])
    final = []
    for x, y, c in candidates:
        dup = False
        for fx, fy, fc in final:
            if abs(x - fx) < min_dist and abs(y - fy) < min_dist:
                dup = True
                break
        if not dup:
            final.append((x, y, c))
    return [(x + tw // 2, y + th // 2, c) for x, y, c in final]


# ============================================================
# 初始化向导 (F1)
# ============================================================
def init_wizard(win):
    """F1 触发的初始化向导 - 用鼠标指定'首领'按钮位置"""
    print("\n" + "=" * 50)
    print("[INIT] 初始化向导")
    print("=" * 50)
    print(f"  窗口: {win.title} @ ({win.left}, {win.top}) {win.width}x{win.height}")
    print()
    print("→ 步骤 1/1: 定位'首领'按钮")
    print("  5秒后开始，请把鼠标悬停在游戏里的'首领'按钮上")
    print()
    for i in range(5, 0, -1):
        print(f"  {i} 秒...", end='\r')
        time.sleep(1)

    cur_x, cur_y = pyautogui.position()
    rel_x = cur_x - win.left
    rel_y = cur_y - win.top
    print(f"  捕获: 屏幕({cur_x}, {cur_y}) → 窗口偏移({rel_x}, {rel_y})")

    cfg = load_config()
    cfg["boss_button_offset"] = [rel_x, rel_y]
    save_config(cfg)
    print(f"\n[OK] 配置已保存到 {CONFIG_PATH}")
    print("    以后窗口拖到任何位置都能用这个偏移点击！\n")
    return cfg


# ============================================================
# 主机器人
# ============================================================
class BossAutoBotV4:
    def __init__(self, config):
        self.cfg = config
        self.paused = False
        self.stopped = False
        self.total_bosses = 0
        self.start_time = time.time()
        self.win_mgr = WindowManager(
            config["window_title"],
            config.get("fallback_titles", []))
        self.win = None
        self.kill_log = []  # [(timestamp, boss_y), ...]
        self.last_init_press = 0

    def log(self, msg):
        elapsed = time.time() - self.start_time
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        try:
            print(f"[{h:02d}:{m:02d}:{s:02d}] {msg}")
        except UnicodeEncodeError:
            safe = msg.encode('ascii', 'replace').decode('ascii')
            print(f"[{h:02d}:{m:02d}:{s:02d}] {safe}")

    def wait_if_paused(self):
        while self.paused and not self.stopped:
            time.sleep(0.2)

    def find_window(self):
        self.win = self.win_mgr.find()
        if self.win:
            self.win_mgr.ensure_active(self.win)
        return self.win is not None

    def click_at_offset(self, offset_x, offset_y, jitter=4):
        """基于窗口偏移的点击（添加风控）"""
        if self.win is None:
            return False
        abs_x = self.win.left + offset_x + random.randint(-jitter, jitter)
        abs_y = self.win.top + offset_y + random.randint(-jitter, jitter)
        human_click(abs_x, abs_y,
                   hold_min=self.cfg["timing"]["click_hold_min"],
                   hold_max=self.cfg["timing"]["click_hold_max"])
        return True

    def is_on_boss_list(self):
        """判断是否在首领列表界面"""
        img = self.win_mgr.capture(self.win)
        if img is None:
            return False
        btn = find_template(
            img,
            os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
            self.cfg["boss_btn_confidence"])
        return btn is not None

    def open_boss_list(self):
        """点击'首领'按钮打开列表 - 优先模板识别，失败用配置偏移"""
        # 优先用模板匹配
        img = self.win_mgr.capture(self.win)
        if img is not None:
            btn = find_template(
                img,
                os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
                self.cfg["boss_btn_confidence"])
            if btn:
                abs_x = self.win.left + btn[0]
                abs_y = self.win.top + btn[1]
                self.log(f"[BTN] 模板识别'首领' @ ({abs_x}, {abs_y}) conf={btn[2]:.2f}")
                human_click(abs_x, abs_y,
                          hold_min=self.cfg["timing"]["click_hold_min"],
                          hold_max=self.cfg["timing"]["click_hold_max"])
                time.sleep(random.uniform(0.8, 1.5))
                return True

        # 模板失败 → 用配置的偏移
        offset = self.cfg.get("boss_button_offset", [130, 100])
        self.log(f"[BTN] 模板未识别，用配置偏移({offset[0]}, {offset[1]})")
        self.click_at_offset(offset[0], offset[1])
        time.sleep(random.uniform(0.8, 1.5))
        return True

    def scroll_list(self, direction='down'):
        """在列表区域拖动"""
        # 列表区域：左侧 25%，垂直 40% 处
        list_x = self.win.left + int(self.win.width * 0.25)
        list_y = self.win.top + int(self.win.height * 0.40)
        drag = self.cfg["scroll_pixels"]
        if direction == 'down':
            end_y = list_y + drag
        else:
            end_y = list_y - drag
        self.log(f"[SCROLL] {direction} ({list_x}, {list_y}) -> ({list_x}, {end_y})")
        human_drag(list_x, list_y, list_x, end_y, duration=0.3)
        time.sleep(random.uniform(0.3, 0.6))

    def find_bosses(self):
        """找已刷新BOSS"""
        img = self.win_mgr.capture(self.win)
        if img is None:
            return []
        return find_all_templates(
            img,
            os.path.join(TEMPLATES_DIR, "refreshed_text.png"),
            conf=self.cfg["refreshed_confidence"],
            min_dist=40)

    def is_recently_killed(self, by):
        """检查此 y 位置的BOSS是否刚被打过"""
        window_sec = self.cfg.get("recently_killed_window_sec", 300)
        now = time.time()
        for ts, y in self.kill_log:
            if now - ts < window_sec and abs(y - by) < 50:
                return True
        return False

    def click_boss_and_go(self, boss_pos):
        """点击BOSS + 前往 + 确认"""
        bx, by, conf = boss_pos
        # 点击BOSS名/头像区域
        click_x = self.win.left + bx - 80 + random.randint(-5, 5)
        click_y = self.win.top + by + random.randint(-5, 5)
        self.log(f"[CLICK] BOSS @ ({click_x}, {click_y}) conf={conf:.2f}")
        human_click(click_x, click_y,
                   hold_min=self.cfg["timing"]["click_hold_min"],
                   hold_max=self.cfg["timing"]["click_hold_max"])
        time.sleep(random.uniform(0.3, 0.5))

        # 找"前往"
        for i in range(15):
            if self.stopped:
                return False
            self.wait_if_paused()
            img = self.win_mgr.capture(self.win)
            if img is None:
                time.sleep(0.2)
                continue
            go = find_template(
                img,
                os.path.join(TEMPLATES_DIR, "go_btn.png"),
                self.cfg["go_btn_confidence"])
            if go:
                sx = self.win.left + go[0]
                sy = self.win.top + go[1]
                self.log(f"[GO] 前往 @ ({sx}, {sy})")
                human_click(sx, sy,
                          hold_min=self.cfg["timing"]["click_hold_min"],
                          hold_max=self.cfg["timing"]["click_hold_max"])
                time.sleep(random.uniform(0.3, 0.5))
                self.click_confirm()
                return True
            time.sleep(0.25)
        self.log("[WARN] 未找到'前往'按钮")
        return False

    def click_confirm(self):
        """点击传送确认"""
        for i in range(10):
            if self.stopped:
                return False
            self.wait_if_paused()
            img = self.win_mgr.capture(self.win)
            if img is None:
                time.sleep(0.2)
                continue
            cf = find_template(
                img,
                os.path.join(TEMPLATES_DIR, "confirm_btn.png"),
                self.cfg["confirm_btn_confidence"])
            if cf:
                sx = self.win.left + cf[0]
                sy = self.win.top + cf[1]
                self.log(f"[OK] 确认传送 @ ({sx}, {sy})")
                human_click(sx, sy,
                          hold_min=self.cfg["timing"]["click_hold_min"],
                          hold_max=self.cfg["timing"]["click_hold_max"])
                return True
            time.sleep(0.2)
        return False

    def wait_battle_end(self, boss_y=0):
        """等待战斗结束"""
        self.log("[BATTLE] 战斗中...")
        start = time.time()
        last_log = 0
        while time.time() - start < 120:
            if self.stopped:
                return False
            self.wait_if_paused()
            elapsed = time.time() - start
            if int(elapsed) % 10 == 0 and int(elapsed) != last_log:
                self.log(f"  [BATTLE] {int(elapsed)}秒...")
                last_log = int(elapsed)
            img = self.win_mgr.capture(self.win)
            if img is not None:
                btn = find_template(
                    img,
                    os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
                    self.cfg["boss_btn_confidence"] - 0.05)
                if btn and elapsed > 5:
                    self.log(f"[DONE] 战斗结束！{int(elapsed)}秒")
                    self.total_bosses += 1
                    # 记录这次击杀的 y 位置
                    self.kill_log.append((time.time(), boss_y))
                    # 清理过期记录
                    cutoff = time.time() - 1500
                    self.kill_log = [(t, y) for t, y in self.kill_log if t > cutoff]
                    time.sleep(random.uniform(0.5, 1.0))
                    return True
            time.sleep(0.4)
        self.log("[TIMEOUT] 超时")
        return True

    def process_list(self):
        """处理列表 - 顶部扫 → 向下滚 → 回顶"""
        scroll_count = 0
        while not self.stopped:
            self.wait_if_paused()
            bosses = self.find_bosses()
            fresh = [b for b in bosses if not self.is_recently_killed(b[1])]
            if fresh:
                self.log(f"[FOUND] {len(bosses)}个已刷新 (排除{len(bosses)-len(fresh)}个冷却)")
                boss = fresh[0]
                if self.click_boss_and_go(boss):
                    self.wait_battle_end(boss[1])
                    return True
                else:
                    time.sleep(random.uniform(0.5, 1.0))
                    continue
            if scroll_count < self.cfg["scroll_down_times"]:
                scroll_count += 1
                self.log(f"[SCAN] 无BOSS，下滚 ({scroll_count}/{self.cfg['scroll_down_times']})")
                self.scroll_list('down')
            else:
                self.log("[SCAN] 到底了，回顶部")
                for _ in range(self.cfg["scroll_up_times"]):
                    self.scroll_list('up')
                    time.sleep(0.2)
                return False
        return False

    def run(self):
        print("=" * 55)
        print("[BOT] 首领自动挂机 v4.0 (防风控版)")
        print("=" * 55)
        print()
        # 模板检查
        if not os.path.exists(os.path.join(TEMPLATES_DIR, "boss_list_btn.png")):
            print("[ERR] 模板不存在，请先运行 capture_boss_templates.py")
            return
        for t in ["boss_list_btn.png", "refreshed_text.png",
                  "go_btn.png", "confirm_btn.png"]:
            p = os.path.join(TEMPLATES_DIR, t)
            if os.path.exists(p):
                img = cv2.imread(p)
                if img is not None:
                    print(f"[OK] {t}: {img.shape[1]}x{img.shape[0]}")
        # 窗口
        if not self.find_window():
            print(f"[ERR] 未找到窗口 '{self.cfg['window_title']}'")
            print("      请先打开微信并进入游戏")
            return
        print()
        print(f"[OK] 窗口: {self.win.title}")
        print(f"     位置: ({self.win.left}, {self.win.top}) {self.win.width}x{self.win.height}")
        print()
        print("首次使用请按 F1 启动初始化向导（捕获'首领'按钮位置）")
        print("  F1=初始化  F2=暂停  F4=停止")
        print()
        print("3秒后开始...")
        time.sleep(3)

        threading.Thread(target=self.hotkey_listener, daemon=True).start()

        self.start_time = time.time()
        cycle = 0

        while not self.stopped:
            self.wait_if_paused()
            cycle += 1

            if not self.find_window():
                self.log("[WARN] 窗口丢失，等待...")
                time.sleep(3)
                continue

            self.log(f"\n========== 第{cycle}轮 ==========")

            # Step 1: 打开列表
            if not self.is_on_boss_list():
                self.log("[STEP1] 打开首领列表")
                self.open_boss_list()
                time.sleep(random.uniform(0.8, 1.2))
            else:
                self.log("[STEP1] 已在列表")

            # Step 2: 处理
            self.log("[STEP2] 扫描列表")
            found = self.process_list()
            if not found:
                self.log("[WAIT] 本轮无BOSS，等3秒")
                time.sleep(random.uniform(2.5, 4.0))

            elapsed = time.time() - self.start_time
            m, s = divmod(int(elapsed), 60)
            h, m = divmod(m, 60)
            self.log(f"[STAT] 击杀: {self.total_bosses} | {h:02d}:{m:02d}:{s:02d}")

        print(f"\n[END] 停止! 击杀 {self.total_bosses} 个")

    def hotkey_listener(self):
        import keyboard as kb
        while not self.stopped:
            try:
                if kb.is_pressed('F1'):
                    if time.time() - self.last_init_press > 2:
                        self.last_init_press = time.time()
                        print("\n[INIT] 进入初始化向导...")
                        if self.find_window():
                            new_cfg = init_wizard(self.win)
                            self.cfg.update(new_cfg)
                            print("[OK] 初始化完成，继续运行\n")
                    time.sleep(0.5)
                if kb.is_pressed('F2'):
                    self.paused = not self.paused
                    print("[PAUSED]" if self.paused else "[RUNNING]")
                    time.sleep(0.5)
                if kb.is_pressed('F4'):
                    self.stopped = True
                    break
            except Exception:
                pass
            time.sleep(0.1)


if __name__ == "__main__":
    cfg = load_config()
    bot = BossAutoBotV4(cfg)
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[EXIT] 用户中断")
    except Exception as e:
        print(f"\n[ERROR] {repr(e)}")
        import traceback
        traceback.print_exc()
