#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勇者联盟 - 首领自动挂机 v5.0 (HSV 颜色检测版)
================================================
v4 → v5 核心改动:
  1. **已刷新BOSS检测**: 从模板匹配 → HSV 颜色检测绿色 pill
     - 不再依赖 refreshed_text.png 模板
     - 窗口缩放、分辨率变化、字体变化 全部免疫
     - 颜色就是 iOS 风格的"成功绿" (#4CD964 类)
  2. **多BOSS并发扫描**: 一次扫描可同时识别 1-4 个已刷新BOSS
  3. **可视化调试**: 每轮扫描自动保存标注截图到 debug/
  4. **--diagnose 模式**: 只扫描不点击，验证颜色检测是否工作

使用方法:
  1. 双击桌面"首领挂机v5.bat"或: python boss_auto_v5.py
  2. 首次使用按 F1 启动初始化向导（捕获"首领"按钮位置）
  3. F1=初始化  F2=暂停/恢复  F4=停止

调试:
  python boss_auto_v5.py --diagnose
  → 只扫描+保存标注截图，不点击任何东西
"""
import os
import sys
import time
import random
import json
import ctypes
import argparse
import threading
from datetime import datetime

# Windows DPI 感知（必须在创建窗口之前调用）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Per-Monitor V1
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Windows GBK 编码修复
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
# 路径
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DEBUG_DIR = os.path.join(BASE_DIR, "debug")
CONFIG_PATH = os.path.join(BASE_DIR, "boss_config.json")

os.makedirs(DEBUG_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# ============================================================
# 配置
# ============================================================
DEFAULT_CONFIG = {
    "window_title": "勇者联盟",
    "fallback_titles": ["WeChat", "微信"],
    # 模板识别置信度（仅用于"首领"按钮、"前往"、"确认"等固定元素）
    "boss_btn_confidence": 0.55,
    "go_btn_confidence": 0.65,
    "confirm_btn_confidence": 0.65,
    # 颜色检测（HSV）
    "refreshed_color": {
        "h_min": 40, "h_max": 75,    # OpenCV H: 0-179
        "s_min": 120, "s_max": 255,  # 饱和度
        "v_min": 130, "v_max": 255,  # 亮度
    },
    # boss 列表区域（窗口内相对比例，0.0-1.0）
    "list_region": {
        "x1_pct": 0.00, "x2_pct": 0.45,
        "y1_pct": 0.115, "y2_pct": 0.50,
    },
    # 滚动
    "scroll_pixels": 280,
    "scroll_down_times": 3,
    "scroll_up_times": 3,
    # 冷却
    "recently_killed_window_sec": 300,
    # 时序（防风控）
    "timing": {
        "click_hold_min": 0.06,
        "click_hold_max": 0.18,
        "after_click_min": 0.3,
        "after_click_max": 0.8,
        "long_pause_prob": 0.05,   # 5%概率插入"思考时间"
        "long_pause_min": 2.0,
        "long_pause_max": 4.5,
    },
    # 窗口偏移
    "boss_button_offset": [130, 100],
}

# ============================================================
# 配置读写
# ============================================================
def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
            print(f"[CFG] 加载配置 {CONFIG_PATH}")
        except Exception as e:
            print(f"[WARN] 配置读取失败: {e}")
    else:
        print(f"[CFG] 使用默认配置")
    return cfg

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ============================================================
# 防风控：人类化鼠标/点击
# ============================================================
def human_mouse_move(end_x, end_y, duration=None):
    """贝塞尔曲线风格的鼠标移动"""
    if duration is None:
        duration = random.uniform(0.1, 0.3)
    try:
        start_x, start_y = pyautogui.position()
    except Exception:
        start_x, start_y = end_x, end_y
    steps = max(int(duration * 60), 8)
    # 控制点偏移（产生弧线）
    cx = (start_x + end_x) / 2 + random.randint(-80, 80)
    cy = (start_y + end_y) / 2 + random.randint(-80, 80)
    for i in range(steps + 1):
        if i == steps:
            px, py = end_x, end_y
        else:
            t = i / steps
            # 二次贝塞尔
            px = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * cx + t ** 2 * end_x
            py = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * cy + t ** 2 * end_y
        try:
            pyautogui.moveTo(int(px), int(py))
        except Exception:
            pass
        time.sleep(duration / steps)

def human_click(abs_x, abs_y, hold_min=0.06, hold_max=0.18):
    """人类化点击：移动→悬停→按下→保持→释放"""
    human_mouse_move(abs_x, abs_y, duration=random.uniform(0.1, 0.3))
    time.sleep(random.uniform(0.02, 0.08))
    hold = random.uniform(hold_min, hold_max)
    pyautogui.mouseDown()
    time.sleep(hold)
    pyautogui.mouseUp()
    time.sleep(random.uniform(hold_min * 0.5, hold_max * 0.8))

def random_action_delay(timing=None):
    """随机延迟 + 偶尔长停顿"""
    if timing is None:
        timing = DEFAULT_CONFIG["timing"]
    base = random.uniform(timing["after_click_min"], timing["after_click_max"])
    if random.random() < timing["long_pause_prob"]:
        base += random.uniform(timing["long_pause_min"], timing["long_pause_max"])
    time.sleep(base)

def human_drag(start_x, start_y, end_x, end_y, duration=0.35):
    """人类化拖动（用于滚动）"""
    steps = max(int(duration * 80), 12)
    # 拖动中微微抖动
    for i in range(steps + 1):
        t = i / steps
        x = start_x + (end_x - start_x) * t
        y = start_y + (end_y - start_y) * t
        if 0 < i < steps:
            x += random.randint(-2, 2)
            y += random.randint(-2, 2)
        pyautogui.moveTo(int(x), int(y))
        if i == 0:
            pyautogui.mouseDown()
        time.sleep(duration / steps)
    pyautogui.mouseUp()

# ============================================================
# 窗口管理
# ============================================================
class WindowManager:
    def __init__(self, title, fallback_titles=None):
        self.title = title
        self.fallback = fallback_titles or []

    def find(self):
        try:
            wins = gw.getWindowsWithTitle(self.title)
            if wins:
                return wins[0]
            for ft in self.fallback:
                wins = gw.getWindowsWithTitle(ft)
                if wins:
                    return wins[0]
        except Exception:
            pass
        return None

    def ensure_active(self, win):
        try:
            if win.isMinimized:
                win.restore()
                time.sleep(0.3)
            # 不强制置顶（避免抢焦点）
        except Exception:
            pass

    def capture(self, win):
        if win is None:
            return None
        try:
            self.ensure_active(win)
            screenshot = pyautogui.screenshot(
                region=(win.left, win.top, win.width, win.height))
            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            return None

# ============================================================
# 模板匹配（用于固定元素：首领按钮、前往、确认）
# ============================================================
def find_template(img, tpl_path, conf=0.6):
    if img is None or not os.path.exists(tpl_path):
        return None
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        return None
    h, w = tpl.shape[:2]
    if img.shape[0] < h or img.shape[1] < w:
        return None
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= conf:
        return (max_loc[0] + w // 2, max_loc[1] + h // 2, max_val)
    return None

def find_all_templates(img, tpl_path, conf=0.55, min_dist=30):
    if img is None or not os.path.exists(tpl_path):
        return []
    tpl = cv2.imread(tpl_path)
    if tpl is None:
        return []
    h, w = tpl.shape[:2]
    if img.shape[0] < h or img.shape[1] < w:
        return []
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= conf)
    matches = []
    used = []
    for pt in zip(*locations[::-1]):
        too_close = False
        for ux, uy in used:
            if abs(ux - pt[0]) < min_dist and abs(uy - pt[1]) < min_dist:
                too_close = True
                break
        if not too_close:
            used.append(pt)
            matches.append((pt[0] + w // 2, pt[1] + h // 2, result[pt[1], pt[0]]))
    return matches

# ============================================================
# 【核心 v5 新增】 HSV 颜色检测已刷新BOSS
# ============================================================
def find_refreshed_pills(img, color_cfg, region_cfg, debug_save=None):
    """
    通过 HSV 颜色检测绿色"已刷新"pill
    返回: [{"name_xy": (x, y), "pill_xy": (x, y), "row_y": y, "size": (w, h)}, ...]
    """
    if img is None:
        return []

    h, w = img.shape[:2]
    # 限定搜索范围到 boss 列表区域（基于比例，不受窗口缩放影响）
    x1 = int(w * region_cfg["x1_pct"])
    y1 = int(h * region_cfg["y1_pct"])
    x2 = int(w * region_cfg["x2_pct"])
    y2 = int(h * region_cfg["y2_pct"])
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # 绿色 pill 范围（OpenCV HSV: H∈[0,179], S/V∈[0,255]）
    lower = np.array([color_cfg["h_min"], color_cfg["s_min"], color_cfg["v_min"]], dtype=np.uint8)
    upper = np.array([color_cfg["h_max"], color_cfg["s_max"], color_cfg["v_max"]], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    # 形态学: 消除小噪点 + 填补 pill 内部小洞
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # 找轮廓
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 百分比过滤 (跟随窗口缩放)
    # 经验值: pill 宽 ≈ 8-12% 窗口宽, 高 ≈ 2-3% 窗口高
    min_pill_w = int(w * 0.04)
    max_pill_w = int(w * 0.18)
    min_pill_h = int(h * 0.012)
    max_pill_h = int(h * 0.035)
    # BOSS 名距 pill 左侧 ≈ 12% 窗口宽
    name_offset = int(w * 0.12)

    candidates = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect = cw / max(ch, 1)
        # pill 形状过滤（百分比 + 长宽比）
        if (min_pill_w <= cw <= max_pill_w and
            min_pill_h <= ch <= max_pill_h and
            1.4 <= aspect <= 6.5):
            pill_cx_roi = x + cw // 2
            pill_cy_roi = y + ch // 2
            pill_cx = pill_cx_roi + x1
            pill_cy = pill_cy_roi + y1
            # BOSS 名区域: pill 左侧 ~12% 窗口宽
            name_cx = pill_cx - name_offset
            name_cy = pill_cy
            # 防止越界
            if name_cx < 20:
                name_cx = max(25, pill_cx - name_offset // 2)
            candidates.append({
                'name_xy': (name_cx, name_cy),
                'pill_xy': (pill_cx, pill_cy),
                'row_y': pill_cy,
                'size': (cw, ch),
            })

    # 按 Y 排序
    candidates.sort(key=lambda c: c['row_y'])

    # Y 去重（同一行可能识别到多个小色块 → 取最明显的）
    unique = []
    for c in candidates:
        if not unique or abs(c['row_y'] - unique[-1]['row_y']) > 30:
            unique.append(c)

    # 调试可视化
    if debug_save:
        debug_img = img.copy()
        # 搜索区域
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (255, 0, 255), 2)
        cv2.putText(debug_img, "SEARCH", (x1 + 5, y1 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)
        for i, c in enumerate(unique):
            # 黄色圆: pill 中心
            cv2.circle(debug_img, c['pill_xy'], 10, (0, 255, 255), 2)
            # 红色圆: BOSS名点击点
            cv2.circle(debug_img, c['name_xy'], 8, (0, 0, 255), -1)
            cv2.putText(debug_img, f"#{i+1}",
                        (c['pill_xy'][0] + 15, c['pill_xy'][1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        # 时间戳
        ts = datetime.now().strftime("%H%M%S")
        cv2.putText(debug_img, ts, (w - 80, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imwrite(debug_save, debug_img)

    return unique

# ============================================================
# 初始化向导（F1）
# ============================================================
def init_wizard(win):
    """用户按 F1 时调用，捕获窗口偏移配置"""
    print("\n" + "=" * 50)
    print("【初始化向导】")
    print("=" * 50)
    print("请把鼠标移动到游戏窗口内'首领'按钮上，3秒后自动捕获...")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    abs_x, abs_y = pyautogui.position()
    rel_x = abs_x - win.left
    rel_y = abs_y - win.top
    print(f"  窗口: ({win.left}, {win.top})")
    print(f"  鼠标绝对坐标: ({abs_x}, {abs_y})")
    print(f"  相对窗口偏移: ({rel_x}, {rel_y})")
    cfg = {
        "boss_button_offset": [rel_x, rel_y],
        "window_rect": [win.left, win.top, win.width, win.height],
    }
    save_config(cfg)
    print(f"  ✓ 配置已保存")
    return cfg

# ============================================================
# 主机器人
# ============================================================
class BossAutoBotV5:
    def __init__(self, config, diagnose_mode=False):
        self.cfg = config
        self.diagnose_mode = diagnose_mode
        self.paused = False
        self.stopped = False
        self.total_bosses = 0
        self.start_time = time.time()
        self.win_mgr = WindowManager(
            config["window_title"],
            config.get("fallback_titles", []))
        self.win = None
        self.kill_log = []
        self.last_init_press = 0
        self.scan_count = 0
        self.empty_scan_count = 0

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
        if self.win is None:
            return False
        abs_x = self.win.left + offset_x + random.randint(-jitter, jitter)
        abs_y = self.win.top + offset_y + random.randint(-jitter, jitter)
        human_click(abs_x, abs_y,
                    hold_min=self.cfg["timing"]["click_hold_min"],
                    hold_max=self.cfg["timing"]["click_hold_max"])
        return True

    def is_on_boss_list(self):
        """判断是否在首领列表界面（看左上角'首领'按钮是否可点）"""
        img = self.win_mgr.capture(self.win)
        if img is None:
            return False
        btn = find_template(
            img,
            os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
            self.cfg["boss_btn_confidence"])
        return btn is not None

    def open_boss_list(self):
        """点击'首领'按钮打开列表"""
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
        # fallback
        offset = self.cfg.get("boss_button_offset", [130, 100])
        self.log(f"[BTN] 模板未识别，用配置偏移({offset[0]}, {offset[1]})")
        self.click_at_offset(offset[0], offset[1])
        time.sleep(random.uniform(0.8, 1.5))
        return True

    def scroll_list(self, direction='down'):
        """在列表区域拖动"""
        list_x = self.win.left + int(self.win.width * 0.20)
        list_y = self.win.top + int(self.win.height * 0.40)
        drag = self.cfg["scroll_pixels"]
        if direction == 'down':
            end_y = list_y + drag
        else:
            end_y = list_y - drag
        self.log(f"[SCROLL] {direction} ({list_x}, {list_y}) -> ({list_x}, {end_y})")
        human_drag(list_x, list_y, list_x, end_y, duration=random.uniform(0.3, 0.5))
        time.sleep(random.uniform(0.4, 0.7))

    # ----------- v5 新增: 颜色找BOSS -----------
    def find_bosses(self, save_debug=True):
        """
        用 HSV 颜色检测已刷新的BOSS
        返回: [{"name_xy": (x, y), "pill_xy": (x, y), ...}, ...]
        """
        img = self.win_mgr.capture(self.win)
        if img is None:
            return []
        debug_path = None
        if save_debug:
            ts = datetime.now().strftime("%H%M%S_%f")[:-3]
            debug_path = os.path.join(DEBUG_DIR, f"scan_{ts}.png")
        return find_refreshed_pills(
            img,
            self.cfg["refreshed_color"],
            self.cfg["list_region"],
            debug_save=debug_path)

    def is_recently_killed(self, by):
        """检查此 y 位置是否刚被打过（避免重复点已点过的）"""
        window_sec = self.cfg.get("recently_killed_window_sec", 300)
        now = time.time()
        for ts, y in self.kill_log:
            if now - ts < window_sec and abs(y - by) < 50:
                return True
        return False

    def click_boss_and_go(self, boss):
        """点击BOSS + 前往 + 确认"""
        name_x, name_y = boss['name_xy']
        # 转换到绝对屏幕坐标
        abs_x = self.win.left + name_x + random.randint(-5, 5)
        abs_y = self.win.top + name_y + random.randint(-5, 5)
        self.log(f"[CLICK] BOSS @ ({abs_x}, {abs_y}) pill={boss['size']}")
        human_click(abs_x, abs_y,
                    hold_min=self.cfg["timing"]["click_hold_min"],
                    hold_max=self.cfg["timing"]["click_hold_max"])
        time.sleep(random.uniform(0.4, 0.7))

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
                    self.kill_log.append((time.time(), boss_y))
                    cutoff = time.time() - 1500
                    self.kill_log = [(t, y) for t, y in self.kill_log if t > cutoff]
                    time.sleep(random.uniform(0.5, 1.0))
                    return True
            time.sleep(0.4)
        self.log("[TIMEOUT] 超时")
        return True

    def process_list(self):
        """处理列表 - 扫描→打一个→回列表→再扫描"""
        scroll_count = 0
        while not self.stopped:
            self.wait_if_paused()
            bosses = self.find_bosses()
            self.scan_count += 1
            fresh = [b for b in bosses if not self.is_recently_killed(b['row_y'])]

            if fresh:
                self.empty_scan_count = 0
                self.log(f"[FOUND] {len(bosses)}个已刷新 pill，排除{len(bosses)-len(fresh)}个冷却")
                # 优先打最上面的
                boss = fresh[0]
                self.log(f"  → 选 BOSS row_y={boss['row_y']}")
                if self.click_boss_and_go(boss):
                    self.wait_battle_end(boss['row_y'])
                    return True
                else:
                    time.sleep(random.uniform(0.5, 1.0))
                    continue

            # 无BOSS
            self.empty_scan_count += 1
            if scroll_count < self.cfg["scroll_down_times"]:
                scroll_count += 1
                self.log(f"[SCAN] 无BOSS，下滚 ({scroll_count}/{self.cfg['scroll_down_times']})")
                self.scroll_list('down')
            else:
                self.log("[SCAN] 到底了，回顶部")
                for _ in range(self.cfg["scroll_up_times"]):
                    self.scroll_list('up')
                    time.sleep(0.25)
                return False
        return False

    def run(self):
        print("=" * 55)
        print("[BOT] 首领自动挂机 v5.0 (HSV颜色检测)")
        print("=" * 55)
        print()
        # 模板检查
        for t in ["boss_list_btn.png", "go_btn.png", "confirm_btn.png"]:
            p = os.path.join(TEMPLATES_DIR, t)
            if os.path.exists(p):
                img = cv2.imread(p)
                if img is not None:
                    print(f"[OK] {t}: {img.shape[1]}x{img.shape[0]}")
            else:
                print(f"[WARN] 缺模板: {t}")
        # 不再需要 refreshed_text.png！颜色检测代替

        # 窗口
        if not self.find_window():
            print(f"[ERR] 未找到窗口 '{self.cfg['window_title']}'")
            print("      请先打开微信并进入游戏")
            return
        print()
        print(f"[OK] 窗口: {self.win.title}")
        print(f"     位置: ({self.win.left}, {self.win.top}) {self.win.width}x{self.win.height}")
        print()
        print("[INFO] 颜色检测配置:")
        print(f"       HSV H={self.cfg['refreshed_color']['h_min']}-{self.cfg['refreshed_color']['h_max']}")
        print(f"       S={self.cfg['refreshed_color']['s_min']}-{self.cfg['refreshed_color']['s_max']}")
        print(f"       V={self.cfg['refreshed_color']['v_min']}-{self.cfg['refreshed_color']['v_max']}")
        print(f"       搜索区域: x={self.cfg['list_region']['x1_pct']*100:.0f}-{self.cfg['list_region']['x2_pct']*100:.0f}%, "
              f"y={self.cfg['list_region']['y1_pct']*100:.0f}-{self.cfg['list_region']['y2_pct']*100:.0f}%")
        print()
        print("首次使用请按 F1 启动初始化向导（捕获'首领'按钮位置）")
        print("  F1=初始化  F2=暂停  F4=停止")
        print(f"  调试截图保存: {DEBUG_DIR}\\")
        print()

        if self.diagnose_mode:
            self.run_diagnose()
            return

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
            self.log(f"[STAT] 击杀: {self.total_bosses} | 扫描: {self.scan_count} | {h:02d}:{m:02d}:{s:02d}")

        print(f"\n[END] 停止! 击杀 {self.total_bosses} 个")

    def run_diagnose(self):
        """诊断模式: 只扫描+保存截图,不点击"""
        print("=" * 55)
        print("[DIAGNOSE] 诊断模式 - 只扫描不点击")
        print("=" * 55)
        print("按 Ctrl+C 退出")
        print()
        # 打开列表
        print("[1] 打开首领列表...")
        if not self.is_on_boss_list():
            self.open_boss_list()
        time.sleep(1.5)

        round_num = 0
        while not self.stopped:
            round_num += 1
            print(f"\n--- 扫描 #{round_num} ---")
            bosses = self.find_bosses(save_debug=True)
            if bosses:
                print(f"  ✅ 找到 {len(bosses)} 个已刷新 BOSS:")
                for i, b in enumerate(bosses):
                    print(f"    #{i+1} row_y={b['row_y']} pill={b['size']} "
                          f"点击点={b['name_xy']}")
            else:
                print(f"  ❌ 0 个 BOSS")
                # 提示用户在搜索区域画了黄色框
                # 如果有绿色但形状不对，也会显示
            # 滚动一次
            if round_num % 4 == 0:
                print(f"  [滚回顶部]")
                for _ in range(3):
                    self.scroll_list('up')
                    time.sleep(0.3)
            else:
                self.scroll_list('down')
            time.sleep(1.5)

    def hotkey_listener(self):
        try:
            import keyboard as kb
        except ImportError:
            self.log("[WARN] keyboard 未安装，热键不可用")
            return
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


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="首领自动挂机 v5.0")
    parser.add_argument("--diagnose", action="store_true",
                        help="诊断模式: 只扫描+截图,不点击")
    args = parser.parse_args()

    print("=" * 55)
    print(f"[v5.0] 启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    cfg = load_config()
    bot = BossAutoBotV5(cfg, diagnose_mode=args.diagnose)
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[EXIT] 用户中断")
    except Exception as e:
        print(f"\n[ERROR] {repr(e)}")
        import traceback
        traceback.print_exc()
