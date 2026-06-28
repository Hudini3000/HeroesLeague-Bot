@echo off
chcp 65001 >nul 2>&1
echo ================================================
echo v7 HSV检测验证（用已有截图测试，不依赖游戏窗口）
echo ================================================
echo.
"D:\Program Files\QClaw\v0.2.29.592\resources\python\python.exe" -c "
import sys, os
sys.path.insert(0, r'$env:USERPROFILE\.qclaw\workspace')

import cv2, numpy as np

game = cv2.imread(r'C:\Users\Administrator\.qclaw\workspace\game_only.jpg')
gh, gw = game.shape[:2]
print(f'截图: {gw}x{gh}')

hsv = cv2.cvtColor(game, cv2.COLOR_BGR2HSV)

# 参数
x1, x2 = int(gw*0.00), int(gw*0.58)
y1, y2 = int(gh*0.11), int(gh*0.60)
roi = game[y1:y2, x1:x2]
roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
roi_h, roi_w = roi_hsv.shape[:2]
max_roi_y = int(roi_h * 0.52)

def cluster(blobs, min_gap=25):
    if not blobs: return []
    blobs = sorted(blobs, key=lambda b: b[0])
    rows, current, prev_y = [], [blobs[0]], blobs[0][0]
    for b in blobs[1:]:
        if b[0] - prev_y <= min_gap:
            current.append(b); prev_y = b[0]
        else:
            rows.append(current); current = [b]; prev_y = b[0]
    rows.append(current)
    result = []
    for row in rows:
        ys = [r[0] for r in row]
        median_y = sorted(ys)[len(ys)//2]
        best = max(row, key=lambda r: r[1] if abs(r[0]-median_y)<=min_gap else 0)
        result.append((median_y, best[2], best[1]))
    return result

# normal 阈值
mask = cv2.inRange(roi_hsv, (10, 120, 150), (30, 255, 255))
num, labs, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
blobs = []
for i in range(1, num):
    area = stats[i, cv2.CC_STAT_AREA]
    if area < 25: continue
    cx, cy = int(cents[i][0]), int(cents[i][1])
    if cx < int(roi_w * 0.35): continue
    if cy > max_roi_y: continue
    blobs.append((cy, area, cx))

clustered = cluster(blobs)
print(f'Hack detected: {len(clustered)} bosses:')
for i, (cy_r, cx_r, area) in enumerate(clustered[:4]):
    gy = y1 + cy_r
    gx = int(gw * 0.12)
    print(f'  BOSS {i+1}: screen=({gx},{gy}) roi_y={cy_r} area={area}')

# 保存可视化
dbg = roi.copy()
colors2 = [(0,255,0),(255,0,0),(0,0,255),(255,255,0)]
for i, (cy_r, cx_r, _) in enumerate(clustered[:4]):
    col = colors2[i]
    cv2.circle(dbg, (cx_r, cy_r), 12, col, 2)
    cv2.line(dbg, (int(roi_w*0.35), cy_r), (roi_w-5, cy_r), col, 1)
    cv2.putText(dbg, f'B{i+1} y={cy_r}', (int(roi_w*0.36), cy_r+5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
cv2.imwrite(r'C:\Users\Administrator\.qclaw\workspace\debug\v7_confirmed.png', dbg)
print('Saved: debug/v7_confirmed.png')
"
pause
