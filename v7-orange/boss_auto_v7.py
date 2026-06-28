#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勇者联盟 - 首领自动挂机脚本 v7
===============================
从零重写，解决窗口大小变化和"已刷新"颜色识别问题。

核心逻辑：
  1. 找游戏窗口（勇者联盟）→ 截图
  2. 找"首领"tab位置（boss_list_btn.png 多尺度模板匹配）
  3. 在BOSS列表区域，用HSV橙色检测（H=10-30, S>=100, V>=150）找"已刷新"
  4. 找到4个BOSS行 → 从上到下依次处理
  5. 点击BOSS名字区域 → 弹出"前往"按钮
  6. 快速点击"前往"（多尺度）→ 等待战斗
  7. 循环

使用方法：
  python boss_auto_v7.py
  热键: F1=初始化  F2=暂停/继续  F4=停止
  诊断模式: python boss_auto_v7.py --diagnose
"""
import os
import sys
import time
import random
import threading

# Windows UTF-8 输出
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
CONFIG = {
    "game_window_title": "勇者联盟",
    "confidence": 0.70,            # 模板匹配置信度（多尺度时会调整）
    "multi_scale": [0.6, 0.8, 1.0, 1.2, 1.4],  # 多尺度系数
    "click_offset": 6,            # 点击随机偏移半径
    "after_click_delay": (0.1, 0.3),
    "loop_interval": (0.8, 1.5),
    "go_click_attempts": 15,       # "前往"按钮最多尝试次数
    "battle_timeout": 60,           # 单次战斗最大等待秒数
}

# HSV 橙色阈值（"已刷新"文字）
HSV_ORANGE = {
    "h_min": 10, "h_max": 30,   # 橙色色相范围
    "s_min": 100,                # 最小饱和度
    "v_min": 150,                # 最小亮度
    # 如果用上面找不到，降低到:
    "s_fallback": 80,
    "v_fallback": 120,
}

# BOSS列表区域（相对于游戏窗口的百分比）
BOSS_LIST_REGION = {
    "x1_pct": 0.00, "x2_pct": 0.58,   # BOSS名字区 x范围 0%-58%
    "y1_pct": 0.11, "y2_pct": 0.60,   # BOSS列表 y范围 11%-60%
    "click_x_pct": 0.12,              # 点击BOSS名字的x位置（窗口宽度的12%）
    "row_sep": 55,                    # BOSS行间距（像素，在标准分辨率下）
}

# 每行BOSS的y偏移（从上到下，标准分辨率720x1280下每行间距约56px）
# 这些是相对于BOSS_LIST_REGION顶部的偏移
BOSS_ROW_OFFSETS_STD = [0, 58, 116, 174]  # 4个BOSS的标准偏移

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# ============================================================
# 工具函数
# ============================================================
def rand(a, b):
    return random.uniform(a, b)

def randint_neg(n):
    return random.randint(-n, n)

def human_click(x, y, offset=6):
    """带随机偏移的点击"""
    px = x + randint_neg(offset)
    py = y + randint_neg(offset)
    pyautogui.moveTo(px, py, rand(0.05, 0.15))
    time.sleep(rand(0.02, 0.06))
    pyautogui.click()
    time.sleep(rand(*CONFIG["after_click_delay"]))

def capture_window(win):
    """截取窗口截图，返回(BGR图像, 左上角绝对坐标)"""
    if win is None:
        return None, None
    if win.isMinimized:
        win.restore()
        time.sleep(0.3)
    screenshot = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    return img, (win.left, win.top)

def find_template_multiscale(img, template_path, confidences=None):
    """
    多尺度模板匹配，返回(中心x, 中心y, 最高置信度)或None
    适合窗口大小变化时的鲁棒匹配
    """
    if img is None or not os.path.exists(template_path):
        return None
    tpl = cv2.imread(template_path)
    if tpl is None:
        return None

    th, tw = tpl.shape[:2]
    best = None

    for scale in CONFIG["multi_scale"]:
        scaled_w = int(tw * scale)
        scaled_h = int(th * scale)
        if scaled_w < 5 or scaled_h < 5 or scaled_w > img.shape[1] or scaled_h > img.shape[0]:
            continue
        tpl_scaled = cv2.resize(tpl, (scaled_w, scaled_h))
        result = cv2.matchTemplate(img, tpl_scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        conf_list = confidences or [CONFIG["confidence"]]
        if any(max_val >= conf for conf in conf_list):
            cx = max_loc[0] + scaled_w // 2
            cy = max_loc[1] + scaled_h // 2
            if best is None or max_val > best[2]:
                best = (cx, cy, max_val)
    return best

def real_coords(origin, x, y):
    """游戏截图坐标 → 屏幕绝对坐标"""
    return (origin[0] + x, origin[1] + y)

def elapsed():
    t = int(time.time() - started)
    h, m = divmod(t // 60, 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

started = time.time()

def log(msg):
    try:
        print(f"[{elapsed()}] {msg}")
    except Exception:
        clean = ''.join(c for c in msg if ord(c) < 0x10000)
        print(f"[{elapsed()}] {clean}")

# ============================================================
# 检查模板
# ============================================================
def check_templates():
    required = ["boss_list_btn.png", "go_btn.png", "confirm_btn.png"]
    missing = []
    for t in required:
        if not os.path.exists(os.path.join(TEMPLATES_DIR, t)):
            missing.append(t)
    if missing:
        print(f"[WARN] Missing templates: {missing} (may still work without)")
    else:
        print(f"[OK] Templates: {len(required)}/{len(required)}")

# ============================================================
# HSV 橙色检测（找"已刷新"）
# ============================================================
def _cluster_blobs_by_row(blobs, min_gap=25):
    """把blob列表按y坐标聚合成行，返回每行的代表blob (y, area, x)"""
    if not blobs:
        return []
    blobs = sorted(blobs, key=lambda b: b[0])
    rows = []
    current = [blobs[0]]
    prev_y = blobs[0][0]
    for b in blobs[1:]:
        if b[0] - prev_y <= min_gap:
            current.append(b)
            prev_y = b[0]
        else:
            rows.append(current)
            current = [b]
            prev_y = b[0]
    rows.append(current)
    # 每行取y中位数+面积最大的blob的x
    result = []
    for row_blobs in rows:
        ys = [b[0] for b in row_blobs]
        median_y = sorted(ys)[len(ys)//2]
        best = max(row_blobs, key=lambda b: b[1] if abs(b[0]-median_y) <= min_gap else 0)
        result.append((median_y, best[2], best[1]))
    return result


def find_refreshed_bosses_hsv(img, game_h, game_w, diagnose=False):
    """
    用HSV橙色检测找"已刷新"的BOSS行。
    返回: [(click_x, click_y, confidence), ...] 或 []
    使用"按行聚类"策略，最多返回4个BOSS。
    """
    reg = BOSS_LIST_REGION
    x1 = int(game_w * reg["x1_pct"])
    x2 = int(game_w * reg["x2_pct"])
    y1 = int(game_h * reg["y1_pct"])
    y2 = int(game_h * reg["y2_pct"])

    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return []

    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    roi_h, roi_w = roi_hsv.shape[:2]

    # BOSS最多4个；第4个BOSS的理论位置不超过列表区的55%
    max_roi_y = int(roi_h * 0.52)

    # 阈值列表（从宽松到严格）
    thresholds = [
        (HSV_ORANGE["s_fallback"], HSV_ORANGE["v_fallback"], "fallback"),
        (HSV_ORANGE["s_min"], HSV_ORANGE["v_min"], "config"),
        (120, 150, "normal"),
        (150, 180, "strict"),
    ]

    for s_min, v_min, name in thresholds:
        mask = cv2.inRange(hsv_roi, (HSV_ORANGE["h_min"], s_min, v_min),
                           (HSV_ORANGE["h_max"], 255, 255))

        num, labs, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)

        # 收集所有blob
        blobs = []
        for i in range(1, num):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 25:
                continue
            cx = int(cents[i][0])
            cy = int(cents[i][1])
            # 必须在右侧（BOSS名字右边）
            if cx < int(roi_w * 0.35):
                continue
            # 必须在BOSS列表范围内
            if cy > max_roi_y:
                continue
            blobs.append((cy, area, cx))

        if not blobs:
            continue

        # 按行聚类
        clustered = _cluster_blobs_by_row(blobs, min_gap=25)

        # 取最多4个（从上到下）
        clustered = clustered[:4]

        if len(clustered) >= 1:
            results = []
            for cy_roi, cx_roi, area in clustered:
                click_x = int(game_w * reg["click_x_pct"])
                click_y = y1 + cy_roi
                results.append((click_x, click_y, min(1.0, area / 200)))

            log(f"  HSV [{name}] s>={s_min} v>={v_min}: found {len(results)} bosses")

            if diagnose:
                dbg = roi.copy()
                dbg_colors = [(0,255,0),(255,0,0),(0,0,255),(255,255,0)]
                for i, (cy_r, cx_r, _) in enumerate(clustered):
                    col = dbg_colors[i % len(dbg_colors)]
                    cv2.circle(dbg, (cx_r, cy_r), 12, col, 2)
                    cv2.line(dbg, (int(roi_w*0.35), cy_r), (roi_w-5, cy_r), col, 1)
                    cv2.putText(dbg, f"B{i+1} y={cy_r}", (int(roi_w*0.36), cy_r+5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
                cv2.rectangle(dbg, (0,0),(int(roi_w*0.35),roi_h),(255,0,0),1)
                cv2.rectangle(dbg, (int(roi_w*0.35),0),(roi_w,roi_h),(0,0,255),1)
                cv2.rectangle(dbg, (0,max_roi_y),(roi_w,roi_h),(0,255,255),1)
                os.makedirs("debug", exist_ok=True)
                cv2.imwrite(f"debug/hsv_diagnose_{name}.png", dbg)

            return results

    return []

# ============================================================
# 找"首领"tab（用于验证我们在正确的界面）
# ============================================================
def find_boss_tab(img, game_w, game_h):
    """用模板匹配找"首领"tab位置"""
    tpl_path = os.path.join(TEMPLATES_DIR, "boss_list_btn.png")
    if not os.path.exists(tpl_path):
        # 用颜色特征：在BOSS列表顶部找"首领"tab
        # Tab通常在窗口顶部y=50-80附近，x在右侧
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 找亮色区域（tab文字是白色/黄色）
        _, bright = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        num, labs, stats, cents = cv2.connectedComponentsWithStats(bright, connectivity=8)
        for i in range(1, num):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 50 or area > 2000:
                continue
            cx, cy = int(cents[i][0]), int(cents[i][1])
            # Tab在顶部y=40-90
            if 0.03 * game_h < cy < 0.12 * game_h:
                return (cx, cy)
        return None

    result = find_template_multiscale(img, tpl_path)
    if result:
        return (result[0], result[1])
    return None

# ============================================================
# 找"前往"按钮
# ============================================================
def find_go_button(img, game_w, game_h):
    """多尺度找'前往'按钮 + HSV兜底"""
    tpl_path = os.path.join(TEMPLATES_DIR, "go_btn.png")
    if os.path.exists(tpl_path):
        result = find_template_multiscale(img, tpl_path, confidences=[0.55, 0.60, 0.65, 0.70])
        if result:
            return (result[0], result[1])

    # 兜底1：找亮黄色/橙色按钮（"前往"通常是黄色）
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 亮黄+亮橙
    yellow = cv2.inRange(hsv, (15, 100, 150), (40, 255, 255))
    # 限制在下半屏
    mask = np.zeros_like(yellow)
    mask[int(game_h*0.4):, :] = yellow[int(game_h*0.4):, :]
    num, labs, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best = None
    for i in range(1, num):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 500:  # 按钮必须足够大
            continue
        cx, cy = int(cents[i][0]), int(cents[i][1])
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        # 按钮形状：宽>高，宽高比 2-5
        if w < h * 2 or w > h * 6:
            continue
        if best is None or area > best[2]:
            best = (cx, cy, area)
    if best:
        return (best[0], best[1])
    return None

# ============================================================
# 找"确定"按钮
# ============================================================
def find_confirm_button(img, game_w, game_h):
    """找确认/确定按钮：模板匹配 + HSV橙色文字兜底"""
    tpl_path = os.path.join(TEMPLATES_DIR, "confirm_btn.png")
    if os.path.exists(tpl_path):
        result = find_template_multiscale(img, tpl_path, confidences=[0.55, 0.60, 0.65])
        if result:
            return (result[0], result[1])

    # 兜底：找"确定"按钮 - 橙色文字 + 黄橙背景
    # 橙色文字 H=15-30, S>=120, V>=200
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    orange_text = cv2.inRange(hsv, (15, 120, 200), (30, 255, 255))
    num, labs, stats, cents = cv2.connectedComponentsWithStats(orange_text, connectivity=8)

    # 找最大的橙色文字块（"确定"是两个字)
    best = None
    for i in range(1, num):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 50:
            continue
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        # "确定"文字区域：宽度40-150，高度15-50
        if w < 30 or w > 200 or h < 10 or h > 60:
            continue
        cx, cy = int(cents[i][0]), int(cents[i][1])
        # 在窗口中下部
        if cy < game_h * 0.4 or cy > game_h * 0.95:
            continue
        if best is None or area > best[2]:
            best = (cx, cy, area)
    if best:
        return (best[0], best[1])
    return None

# ============================================================
# 等待战斗结束
# ============================================================
def wait_for_battle_end(win, origin, timeout=60):
    """
    真正等战斗结束：每0.5秒轮询"确定"按钮，超时则跳过。
    避免固定等12-18秒（战斗可能提前/延后结束）。
    """
    start = time.time()
    last_log = start

    while time.time() - start < timeout:
        img, _ = capture_window(win)
        if img is None:
            time.sleep(0.5)
            continue

        h, w = img.shape[:2]
        confirm_pos = find_confirm_button(img, w, h)
        if confirm_pos:
            sx, sy = real_coords(origin, confirm_pos[0], confirm_pos[1])
            elapsed = time.time() - start
            log(f"  战斗结束({elapsed:.0f}s)！点击确定 @ ({sx}, {sy})")
            human_click(sx, sy)
            time.sleep(rand(1.5, 2.5))  # 等结算动画
            return True

        # 每5秒打印一次进度
        elapsed = time.time() - start
        if elapsed - last_log >= 5:
            log(f"  战斗中... ({elapsed:.0f}s)")
            last_log = elapsed

        time.sleep(0.5)

    log(f"  [WARN] 战斗超时({timeout}s)，跳过")
    return False

# ============================================================
# 诊断模式
# ============================================================
def diagnose_mode():
    """只扫描，不点击——用于验证检测是否正确"""
    os.makedirs("debug", exist_ok=True)
    log("=== 诊断模式 ===")
    check_templates()

    win = find_window()
    if win is None:
        log("[ERROR] 找不到游戏窗口")
        return

    log(f"找到窗口: '{win.title}' @ ({win.left},{win.top}) {win.width}x{win.height}")
    img, origin = capture_window(win)
    if img is None:
        log("[ERROR] 无法截图")
        return

    gh, gw = img.shape[:2]
    log(f"截图尺寸: {gw}x{gh}")

    # 保存截图
    ts = time.strftime("%H%M%S")
    cv2.imwrite(f"debug/screenshot_{ts}.png", img)
    log(f"已保存: debug/screenshot_{ts}.png")

    # 检查首领tab
    tab_pos = find_boss_tab(img, gw, gh)
    if tab_pos:
        log(f"找到首领tab @ ({tab_pos[0]}, {tab_pos[1]})")
    else:
        log("[WARN] 未找到首领tab")

    # HSV检测
    log("正在HSV橙色检测...")
    bosses = find_refreshed_bosses_hsv(img, gh, gw, diagnose=True)
    if bosses:
        log(f"检测到 {len(bosses)} 个已刷新BOSS:")
        for i, (bx, by, conf) in enumerate(bosses):
            log(f"  BOSS {i+1}: screen({bx}, {by})")
    else:
        log("[ERROR] 未检测到任何已刷新BOSS")

    # 试检测"前往"按钮（可能会找到也可能不会）
    log("\n试检测按钮（仅检测，不点击）...")
    go_pos = find_go_button(img, gw, gh)
    if go_pos:
        log(f"  前往按钮 @ ({go_pos[0]}, {go_pos[1]})")
    else:
        log("  未找到前往按钮（正常，在BOSS列表界面不应该出现）")

    confirm_pos = find_confirm_button(img, gw, gh)
    if confirm_pos:
        log(f"  确定按钮 @ ({confirm_pos[0]}, {confirm_pos[1]})")
    else:
        log("  未找到确定按钮（正常，在BOSS列表界面不应该出现）")

    log("\n诊断完成！查看 debug/ 目录下的图片")
    log("  - screenshot_*.png: 窗口截图")
    log("  - hsv_diagnose_*.png: HSV检测结果（绿色圆圈=检测到的BOSS行）")

# ============================================================
# 窗口查找
# ============================================================
def find_window():
    """找游戏窗口"""
    wins = gw.getWindowsWithTitle(CONFIG["game_window_title"])
    if wins:
        return wins[0]
    # fallback：找任何包含"勇者"或"联盟"的窗口
    for win in gw.getAllWindows():
        title = win.title
        if title and any(k in title for k in ["勇者", "联盟", "Hero"]):
            return win
    return None

# ============================================================
# 主流程
# ============================================================
class BossBot:
    def __init__(self):
        self.paused = False
        self.stopped = False
        self.total = 0

    def wait_pause(self):
        while self.paused and not self.stopped:
            time.sleep(0.2)

    def click_boss_in_list(self, win, origin, bx, by):
        """点击BOSS列表中的某个BOSS"""
        sx, sy = real_coords(origin, bx, by)
        log(f"  点击BOSS @ ({sx}, {sy})")
        human_click(sx, sy, offset=CONFIG["click_offset"])
        time.sleep(rand(0.8, 1.5))

    def try_go_button(self, win, origin):
        """尝试点击'前往'按钮，多次点击"""
        for attempt in range(CONFIG["go_click_attempts"]):
            if self.stopped:
                return False
            self.wait_pause()

            img, _ = capture_window(win)
            if img is None:
                time.sleep(0.3)
                continue

            pos = find_go_button(img, win.width, win.height)
            if pos:
                sx, sy = real_coords(origin, pos[0], pos[1])
                log(f"  [尝试{attempt+1}] 找到前往！点击 @ ({sx}, {sy})")
                human_click(sx, sy, offset=CONFIG["click_offset"])
                return True
            time.sleep(rand(0.3, 0.6))

        log("  未找到前往按钮")
        return False

    def run(self):
        log("=== 勇者联盟首领挂机 v7 启动 ===")
        log("热键: F2=暂停  F4=停止")
        check_templates()

        while not self.stopped:
            self.wait_pause()
            win = find_window()
            if win is None:
                log("[ERROR] 找不到游戏窗口，等待...")
                time.sleep(3)
                continue

            img, origin = capture_window(win)
            if img is None:
                log("[ERROR] 截图失败，等待...")
                time.sleep(2)
                continue

            gh, gw = img.shape[:2]

            # 步骤1：HSV橙色检测找已刷新BOSS
            bosses = find_refreshed_bosses_hsv(img, gh, gw)
            if not bosses:
                log("  [扫描] 未检测到已刷新BOSS，等待刷新...")
                time.sleep(rand(*CONFIG["loop_interval"]))
                continue

            log(f"  [扫描] 检测到 {len(bosses)} 个已刷新BOSS，开始处理")
            for i, (bx, by, _) in enumerate(bosses):
                if self.stopped:
                    break
                self.wait_pause()
                self.total += 1
                log(f"  >>> 击杀 #{self.total}: BOSS {i+1}/{len(bosses)}")

                # 点击BOSS
                self.click_boss_in_list(win, origin, bx, by)

                # 点"前往"
                if self.try_go_button(win, origin):
                    # 立刻开始轮询等"确定"按钮出现（真正等战斗结束）
                    log("  等待战斗结束...")
                    wait_for_battle_end(win, origin, timeout=60)
                    # 等结算完成后，额外等一下再处理下一个BOSS
                    time.sleep(rand(0.5, 1.5))
                else:
                    # 没点到前往，ESC退回
                    pyautogui.press('escape')
                    time.sleep(rand(0.5, 1.0))

                time.sleep(rand(0.5, 1.0))

            time.sleep(rand(*CONFIG["loop_interval"]))

        log("=== 脚本已停止 ===")

# ============================================================
# 键盘监听（后台线程）
# ============================================================
def keyboard_listener(bot):
    import msvcrt
    log("键盘监听已启动: F2=暂停  F4=停止")

    while True:
        try:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key in [b'\x00', b'\xe0']:  # 功能键前缀
                    key = msvcrt.getch()
                    if key == b'\x3c':  # F2 scancode
                        bot.paused = not bot.paused
                        state = "暂停" if bot.paused else "继续"
                        log(f"=== {state} ===")
                    elif key == b'\x3e':  # F4 scancode
                        log("=== 收到停止信号 ===")
                        bot.stopped = True
                        break
        except Exception:
            pass
        time.sleep(0.1)

# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    if "--diagnose" in sys.argv:
        diagnose_mode()
    else:
        bot = BossBot()
        listener = threading.Thread(target=keyboard_listener, args=(bot,), daemon=True)
        listener.start()
        bot.run()
