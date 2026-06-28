# Heroes League Boss Bot

Auto-clicker for Heroes League (勇者联盟) game - kills bosses automatically.

## Folders

| Folder | Description | Status |
|---|---|---|
| `v5-hsv/` | HSV color detection | archived |
| `v6-dual/` | dual detection + multi-scale | archived |
| `v7-orange/` | **latest** - orange HSV + row clustering | **active** |

## How to use (v7)

1. Open the game
2. Go to BOSS list (队伍/首领 tabs)
3. Double-click `v7-orange\diagnose.bat` to test detection (no clicking)
4. If diagnose looks good, double-click `v7-orange\start.bat` to run

Hotkeys while running:
- F2 = pause/resume
- F4 = stop

## File naming

- `start.bat` - run the bot
- `diagnose.bat` - scan only, no clicks
- `verify_hsv.bat` - test HSV algorithm offline
- `boss_auto_v7.py` - main script
- `templates/` - template images
