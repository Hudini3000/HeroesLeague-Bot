# 勇者联盟首领自动挂机脚本

[![GitHub release](https://img.shields.io/github/release/Hudini3000/HeroesLeague-Bot.svg)](https://github.com/Hudini3000/HeroesLeague-Bot/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/Hudini3000/HeroesLeague-Bot/total)](https://github.com/Hudini3000/HeroesLeague-Bot/releases)

自动刷首领脚本，支持 HSV 颜色检测、多尺度模板匹配、自动重启等功能。

---

## 🚀 快速开始（普通用户）

### 方法一：下载独立 .exe（推荐，无需 Python）

1. **下载 .exe**  
   前往 [Releases](https://github.com/Hudini3000/HeroesLeague-Bot/releases) 页面，下载最新版本的 `.exe` 文件

2. **打开游戏**  
   启动"勇者联盟"游戏，进入首领列表界面

3. **运行脚本**  
   双击下载的 `.exe` 文件

4. **开始挂机**  
   看到日志输出就是成功了！按 `F2` 暂停，按 `F4` 停止

---

### 方法二：使用 Python 脚本（开发者）

1. **安装依赖**  
   ```bash
   pip install opencv-python numpy pyautogui pygetwindow
   ```

2. **下载脚本**  
   ```bash
   git clone https://github.com/Hudini3000/HeroesLeague-Bot.git
   cd HeroesLeague-Bot/v8-auto-restart
   ```

3. **运行**  
   ```bash
   python boss_auto_v8.py
   ```

---

## 📋 功能特点

- ✅ **HSV 颜色检测**：不依赖模板匹配，窗口缩放也能识别
- ✅ **多尺度模板匹配**：适配不同分辨率
- ✅ **自动重启**：凌晨 4 点自动退出并重启（释放内存）
- ✅ **守护进程**：脚本崩溃自动重启
- ✅ **战斗结束检测**：等"确定"按钮出现再打下一个

---

## 🎯 版本说明

| 版本 | 特点 | 推荐 |
|------|------|------|
| v5   | HSV 颜色检测 | ⭐⭐ |
| v6   | 双检测（模板+HSV） | ⭐⭐ |
| v7   | 橙色检测 + 多尺度匹配 | ⭐⭐⭐ |
| v8   | 自动重启 + 独立 .exe | ⭐⭐⭐⭐⭐ |

---

## ⌨️ 热键说明

| 热键 | 功能 |
|------|------|
| F2   | 暂停/继续 |
| F4   | 停止脚本 |

---

## ⚠️ 注意事项

1. **游戏窗口不能最小化**（脚本需要截图）
2. **屏幕分辨率最好不要变**（模板匹配依赖分辨率）
3. **杀毒软件可能报病毒**（这是误报，因为脚本模拟鼠标点击）
4. **网络不稳定时可能掉线**（建议定期检查游戏状态）

---

## 🐛 故障排查

### 1. 提示"找不到游戏窗口"
→ 确保游戏已打开，窗口标题是"勇者联盟"

### 2. 提示"缺少模板图片"
→ 确保 .exe 文件和 `templates` 文件夹在同一个目录

### 3. 脚本在 4 点没有重启
→ 确保脚本在运行状态（没按 F2 暂停）

---

## 📝 更新日志

详见各版本文件夹下的 `changelog.md` 或 `README.md`

---

## 📧 联系作者

如有问题或建议，欢迎提交 [Issue](https://github.com/Hudini3000/HeroesLeague-Bot/issues)！

---

**祝你挂机愉快！** 🎮
