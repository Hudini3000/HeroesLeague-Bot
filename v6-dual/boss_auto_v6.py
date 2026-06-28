#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勇者联盟 - 首领自动挂机 v6.0 (双检测 + 多尺度模板)
=====================================================
v5 → v6 核心改动:
  1. **多尺度模板匹配**: refreshed_text.png 在 0.5x~2.0x 范围内逐级尝试
     彻底解决窗口放大/缩小后模板失效的问题
  2. **HSV 修正范围**: H:35-95, S:40+ (原 v5 的 H:40-75 漏掉了实测的 H:82-89)
  3. **自适用搜索区域**: list_region 根据实际截图尺寸自动换算
  4. **两种方法互相兜底**: 模板优先，HSV 备选，取检测到最多结果的方案

使用方法:
  1. 双击桌面文件夹里的 "首领挂机v6.bat"
  2. 热键: F1=初始化  F2=暂停/恢复  F4=停止

调试（只看不打）:
  python boss_auto_v6.py --diagnose
"""
import os
import sys
import time
import random
import json
import ctypes
import argparse
import threading
import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
from datetime import datetime

# Windows DPI
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Windows UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ============================================================
# 配置
# ============================================================
CONFIG = {
    "game_window_title": "勇者联盟",
    "confidence": 0.65,          # 模板匹配置信度
    "hsv_confidence": 0.015,       # HSV 绿色像素占比阈值（相对 ROI 面积）
    "click_offset": (3, 8),
    "after_click_delay": (0.1, 0.3),
    "loop_interval": (1, 2),
    "go_click_attempts": 10,
    # HSV 配置（实测调优 - 2026-06-27）
    # 已刷新 Row1: H=82-89, S=165-176  | Row2: H=61-64, S=120-128
    # 非刷新 Row3/4: H=9-11, S=100+ (橙红色，S>=60 可过滤)
    # 最佳实测配置: x10-45%, y18-60%, min_area=50, H40-95, S60+
    "hsv": {
        "h_min": 40, "h_max": 95,   # 精确覆盖实测 H=61-89
        "s_min": 60, "s_max": 255,  # S>=60 过滤掉橙红 S=100+ 的误报
        "v_min": 80, "v_max": 255,
        "min_area": 50,              # 最小绿色簇（像素数），实测最小 pill 约 200px
        "y_tolerance": 20,          # 同一行去重容差
    },
    # 搜索区域（实测最佳配置）
    "list_region": {
        "x1_pct": 0.10, "x2_pct": 0.45,  # 缩小到 pill 实际位置
        "y1_pct": 0.18, "y2_pct": 0.60,
    },
    # 模板多尺度搜索范围
    "template_scales": [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.6, 2.0],
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")
DEBUG_DIR = os.path.join(SCRIPT_DIR, "debug_v6")
os.makedirs(DEBUG_DIR, exist_ok=True)

# ============================================================
# 工具函数
# ============================================================
def rand(a, b):
    return random.uniform(a, b)

def randint(a, b):
    return random.randint(a, b)

def human_click(x, y):
    ox = randint(-CONFIG["click_offset"][1], CONFIG["click_offset"][1])
    oy = randint(-CONFIG["click_offset"][1], CONFIG["click_offset"][1])
    pyautogui.moveTo(x + ox, y + oy, rand(0.05, 0.15))
    time.sleep(rand(0.02, 0.06))
    pyautogui.click()
    time.sleep(rand(*CONFIG["after_click_delay"]))

def capture_window(win):
    if win is None:
        return None, None
    if win.isMinimized:
        win.restore()
        time.sleep(0.3)
    screenshot = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    return img, (win.left, win.top)

def find_template_multiscale(img, template_path, scales=None, min_conf=0.6):
    """多尺度模板匹配，返回最佳匹配的(中心x, 中心y, 置信度)或None"""
    if img is None or not os.path.exists(template_path):
        return None
    tpl = cv2.imread(template_path)
    if tpl is None:
        return None

    scales = scales or CONFIG["template_scales"]
    best = None

    for scale in scales:
        try:
            new_w = int(tpl.shape[1] * scale)
            new_h = int(tpl.shape[0] * scale)
            if new_w < 3 or new_h < 3 or new_w > img.shape[1] * 2 or new_h > img.shape[0] * 2:
                continue
            tpl_scaled = cv2.resize(tpl, (new_w, new_h))
            result = cv2.matchTemplate(img, tpl_scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= min_conf and (best is None or max_val > best[2]):
                best = (max_loc[0] + new_w // 2, max_loc[1] + new_h // 2, max_val)
        except Exception:
            continue
    return best

def find_all_templates_multiscale(img, template_path, scales=None, min_conf=0.6, max_results=4):
    """多尺度模板匹配，返回所有超过阈值的匹配位置"""
    if img is None or not os.path.exists(template_path):
        return []
    tpl = cv2.imread(template_path)
    if tpl is None:
        return []

    scales = scales or CONFIG["template_scales"]
    all_matches = []

    for scale in scales:
        try:
            new_w = int(tpl.shape[1] * scale)
            new_h = int(tpl.shape[0] * scale)
            if new_w < 3 or new_h < 3:
                continue
            tpl_scaled = cv2.resize(tpl, (new_w, new_h))
            result = cv2.matchTemplate(img, tpl_scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= min_conf:
                all_matches.append({
                    "x": max_loc[0] + new_w // 2,
                    "y": max_loc[1] + new_h // 2,
                    "conf": max_val,
                    "scale": scale
                })
        except Exception:
            continue

    # 去重（位置接近的只保留最高置信度）
    filtered = []
    for m in all_matches:
        keep = True
        for f in filtered:
            dist = abs(m["x"] - f["x"]) + abs(m["y"] - f["y"])
            if dist < 30:  # 30像素内算同一个
                if m["conf"] > f["conf"]:
                    f["x"], f["y"], f["conf"] = m["x"], m["y"], m["conf"]
                keep = False
                break
        if keep:
            filtered.append(m)

    filtered.sort(key=lambda x: x["conf"], reverse=True)
    return filtered[:max_results]

def find_hsv_bosses(img, debug_overlay=None):
    """HSV 颜色检测：找所有"已刷新"绿色 pill，返回 y 坐标列表"""
    if img is None:
        return []

    h, w = img.shape[:2]
    cfg = CONFIG["hsv"]
    reg = CONFIG["list_region"]

    # 换算实际像素区域
    x1 = int(w * reg["x1_pct"])
    x2 = int(w * reg["x2_pct"])
    y1 = int(h * reg["y1_pct"])
    y2 = int(h * reg["y2_pct"])

    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return []

    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv_roi,
        (cfg["h_min"], cfg["s_min"], cfg["v_min"]),
        (cfg["h_max"], cfg["s_max"], cfg["v_max"]))

    # 找连通域
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    bosses_y = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < cfg["min_area"]:
            continue
        cx = int(centroids[i][0])
        cy = int(centroids[i][1])

        # 去重：同一条 y 线（误差±y_tolerance）只保留一个
        too_close = False
        for by in bosses_y:
            if abs((cy + y1) - by) <= cfg["y_tolerance"]:
                too_close = True
                break
        if not too_close:
            bosses_y.append(cy + y1)  # 转换回全局 y 坐标

    bosses_y.sort()
    return bosses_y

def real_coords(origin, game_x, game_y):
    """游戏截图坐标 -> 屏幕绝对坐标"""
    return (origin[0] + int(game_x), origin[1] + int(game_y))

def get_boss_row_x(img_w):
    """根据截图宽度，返回 BOSS 名字的大致 x 坐标（pill 左侧一点）"""
    # 已刷新 pill 大概在 x=10%-38%, BOSS 名字在 pill 左边约 5%-15%
    return int(img_w * 0.12)

def get_boss_row_y_list(img_h, count=4):
    """根据截图高度，返回可能的 BOSS 行 y 坐标列表"""
    # BOSS 列表大概在 y=18%-58%，平均分布
    y1 = int(img_h * 0.18)
    y2 = int(img_h * 0.58)
    step = (y2 - y1) / max(count, 1)
    return [int(y1 + step * i + step * 0.5) for i in range(count)]

# ============================================================
# 核心流程
# ============================================================
class BossAutoBot:
    def __init__(self, diagnose=False):
        self.paused = False
        self.stopped = False
        self.total_bosses = 0
        self.start_time = time.time()
        self.diagnose = diagnose
        self.round_num = 0
        self.method_used = ""  # "template" or "hsv" or "both"

    def log(self, msg):
        elapsed = time.time() - self.start_time
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        try:
            print(f"[{h:02d}:{m:02d}:{s:02d}] {msg}")
        except Exception:
            clean = ''.join(c for c in msg if ord(c) < 0x10000)
            print(f"[{h:02d}:{m:02d}:{s:02d}] {clean}")

    def wait_if_paused(self):
        while self.paused and not self.stopped:
            time.sleep(0.2)

    def find_window(self):
        wins = gw.getWindowsWithTitle(CONFIG["game_window_title"])
        if not wins:
            wins = gw.getWindowsWithTitle("微信")
        if wins:
            return wins[0]
        return None

    def click_boss_list(self, win, origin):
        """点击首领列表入口按钮"""
        img, _ = capture_window(win)
        if img is None:
            return False

        btn = find_template_multiscale(
            img, os.path.join(TEMPLATES_DIR, "boss_list_btn.png"),
            min_conf=0.6
        )
        if btn:
            sx, sy = real_coords(origin, btn[0], btn[1])
            self.log(f"[btn] 点击首领列表 @ ({sx}, {sy})")
            human_click(sx, sy)
            time.sleep(rand(0.8, 1.5))
            return True
        self.log("[btn] 未找到首领列表按钮")
        return False

    def find_refreshed_bosses(self, win, origin):
        """
        步骤2: 同时用 模板匹配 + HSV 检测
        返回 [(screen_x, screen_y), ...] 点击位置列表
        """
        img, _ = capture_window(win)
        if img is None:
            return []

        h, w = img.shape[:2]
        refresh_tpl = os.path.join(TEMPLATES_DIR, "refreshed_text.png")
        reg = CONFIG["list_region"]

        # 计算 ROI
        roi_x1 = int(w * reg["x1_pct"])
        roi_x2 = int(w * reg["x2_pct"])
        roi_y1 = int(h * reg["y1_pct"])
        roi_y2 = int(h * reg["y2_pct"])
        roi = img[roi_y1:roi_y2, roi_x1:roi_x2]

        click_positions = []
        method = ""

        # ---- 方法1: 多尺度模板匹配 ----
        template_matches = []
        if os.path.exists(refresh_tpl):
            all_matches = find_all_templates_multiscale(
                roi, refresh_tpl,
                scales=CONFIG["template_scales"],
                min_conf=CONFIG["confidence"],
                max_results=4
            )
            for m in all_matches:
                # 转换回 roi 坐标
                click_x_global = roi_x1 + m["x"]
                click_y_global = roi_y1 + m["y"]
                # 点击的是 pill 左侧的 BOSS 名字
                boss_x = int(w * 0.12)
                boss_y = click_y_global
                screen_pos = real_coords(origin, boss_x, boss_y)
                template_matches.append({
                    "screen": screen_pos,
                    "roi_y": click_y_global,
                    "conf": m["conf"],
                    "method": "template"
                })

        # ---- 方法2: HSV 颜色检测 ----
        hsv_matches = []
        bosses_y = find_hsv_bosses(img)
        for cy in bosses_y:
            boss_x = int(w * 0.12)
            screen_pos = real_coords(origin, boss_x, cy)
            hsv_matches.append({
                "screen": screen_pos,
                "roi_y": cy,
                "conf": 1.0,
                "method": "hsv"
            })

        # ---- 合并：两种方法取最优 ----
        # 用 roi_y 做去重（同一行只留一个）
        all_candidates = template_matches + hsv_matches
        merged = {}
        for c in all_candidates:
            key = round(c["roi_y"] / 10) * 10  # 按10像素取整去重
            if key not in merged or c["conf"] > merged[key]["conf"]:
                merged[key] = c

        click_positions = [v["screen"] for v in merged.values()]

        # 记录用的哪种方法
        if template_matches and hsv_matches:
            method = f"模板({len(template_matches)})+HSV({len(hsv_matches)})"
        elif template_matches:
            method = f"模板({len(template_matches)})"
        elif hsv_matches:
            method = f"HSV({len(hsv_matches)})"
        else:
            method = "无"

        self.method_used = method

        # ---- 保存调试截图 ----
        self._save_debug(img, merged, roi_x1, roi_y1, w, h)

        if click_positions:
            self.log(f"[scan] 检测到 {len(click_positions)} 个已刷新BOSS ({method})")
        else:
            self.log(f"[scan] 未检测到已刷新BOSS ({method})")

        return click_positions

    def _save_debug(self, img, candidates, roi_x1, roi_y1, w, h):
        """保存带标注的调试截图"""
        self.round_num += 1
        debug_img = img.copy()

        # 画 ROI 区域
        cv2.rectangle(debug_img, (roi_x1, roi_y1), (int(w*CONFIG["list_region"]["x2_pct"]), int(h*CONFIG["list_region"]["y2_pct"])), (255, 100, 0), 1)

        # 画每个检测到的位置
        colors = [(0, 255, 255), (0, 165, 255), (0, 255, 0), (128, 255, 218)]
        for i, (key, c) in enumerate(candidates.items()):
            col = colors[i % len(colors)]
            cy = c["roi_y"]
            cx = int(w * 0.12)
            # BOSS 点击位置
            cv2.circle(debug_img, (cx, cy), 8, col, 2)
            cv2.putText(debug_img, f"BOSS{i+1}", (cx+10, cy+5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
            # pill 位置
            pill_x = int(w * 0.25)
            cv2.circle(debug_img, (pill_x, cy), 5, (0, 0, 255), 1)

        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(DEBUG_DIR, f"scan_{self.round_num:03d}_{ts}.png")
        cv2.imwrite(path, debug_img)

    def click_boss(self, win, origin, screen_x, screen_y):
        """步骤3: 点击具体 BOSS 条目"""
        self.log(f"[boss] 点击BOSS @ ({screen_x}, {screen_y})")
        human_click(screen_x, screen_y)
        time.sleep(rand(0.5, 1.0))

    def click_go(self, win, origin):
        """步骤4: 找"前往"按钮并点击（5秒内重试）"""
        img, _ = capture_window(win)
        if img is None:
            return False

        tpl_path = os.path.join(TEMPLATES_DIR, "go_btn.png")
        found = False
        for attempt in range(CONFIG["go_click_attempts"]):
            img, _ = capture_window(win)
            if img is None:
                break

            pos = find_template_multiscale(img, tpl_path, scales=[0.6, 0.8, 1.0, 1.2, 1.5], min_conf=0.6)
            if pos:
                sx, sy = real_coords(origin, pos[0], pos[1])
                self.log(f"[go] 前往 @ ({sx}, {sy}) [{attempt+1}/{CONFIG['go_click_attempts']}]")
                human_click(sx, sy)
                found = True
                time.sleep(rand(0.3, 0.6))
                break
            time.sleep(0.4)

        if not found:
            self.log("[go] 未找到前往按钮")
        return found

    def wait_for_battle(self, win, origin):
        """步骤5: 等待战斗结束"""
        self.log("[wait] 等待战斗...")
        wait_start = time.time()
        max_wait = 60  # 最多等60秒
        while time.time() - wait_start < max_wait:
            if self.stopped:
                return
            img, _ = capture_window(win)
            if img is None:
                time.sleep(1)
                continue
            # 找"确定"按钮（战斗结算）
            pos = find_template_multiscale(
                img, os.path.join(TEMPLATES_DIR, "confirm_btn.png"),
                scales=[0.6, 0.8, 1.0, 1.2, 1.5], min_conf=0.65
            )
            if pos:
                sx, sy = real_coords(origin, pos[0], pos[1])
                self.log(f"[ok] 战斗结束，点击确定 @ ({sx}, {sy})")
                human_click(sx, sy)
                time.sleep(rand(0.5, 1.0))
                return True
            time.sleep(rand(1.5, 2.5))
        self.log("[warn] 等待战斗超时")
        return False

    def run(self):
        self.log("="*50)
        self.log("勇者联盟 v6.0 启动 (双检测模式)")
        self.log("="*50)

        if self.diagnose:
            self.log("[DIAGNOSE] 只扫描，不点击")

        hotkey_init = "F1"
        hotkey_pause = "F2"
        hotkey_stop = "F4"

        self.log(f"热键: {hotkey_init}=初始化  {hotkey_pause}=暂停  {hotkey_stop}=停止")
        self.log("请将游戏界面保持在首领列表页面，按 F1 开始...")

        win = None
        origin = None

        while not self.stopped:
            self.wait_if_paused()

            if self.diagnose:
                win = self.find_window()
                if win:
                    origin = (win.left, win.top)
                    self.find_refreshed_bosses(win, origin)
                time.sleep(rand(*CONFIG["loop_interval"]))
                continue

            # 找窗口
            if win is None:
                win = self.find_window()
                if win is None:
                    self.log("[wait] 等待勇者联盟窗口...")
                    time.sleep(2)
                    continue
                origin = (win.left, win.top)
                self.log(f"[win] 找到窗口: {win.title}  ({win.left},{win.top}) {win.width}x{win.height}")

            # 点击首领列表
            if not self.click_boss_list(win, origin):
                time.sleep(1)
                win = None  # 窗口可能变了，重新找
                continue

            time.sleep(rand(0.5, 1.0))

            # 扫描已刷新BOSS
            positions = self.find_refreshed_bosses(win, origin)

            if not positions:
                self.log("[next] 本轮无已刷新BOSS，等待下一轮...")
                time.sleep(rand(*CONFIG["loop_interval"]))
                continue

            # 逐个处理
            for screen_x, screen_y in positions:
                if self.stopped:
                    break
                self.wait_if_paused()

                self.click_boss(win, origin, screen_x, screen_y)
                time.sleep(rand(0.3, 0.6))

                if self.click_go(win, origin):
                    self.wait_for_battle(win, origin)
                    self.total_bosses += 1
                    self.log(f"[done] 已击杀 #{self.total_bosses}")

                # 处理完一个BOSS后重新找窗口
                time.sleep(rand(0.5, 1.0))
                win = self.find_window()
                if win:
                    origin = (win.left, win.top)

            time.sleep(rand(*CONFIG["loop_interval"]))

        self.log("脚本已停止")

# ============================================================
# 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="勇者联盟 首领挂机 v6.0")
    parser.add_argument("--diagnose", action="store_true", help="只扫描不点击，保存调试截图")
    args = parser.parse_args()

    bot = BossAutoBot(diagnose=args.diagnose)
    bot.run()

if __name__ == "__main__":
    main()
