# Wine Installer + Game Launcher

Запуск Windows-игр на Linux без sudo. Плюс установка Minecraft
(Legacy / Prism / Fabulously Optimized / OptiFine).

## Установка

**GitFlic (основной):**
```bash
git clone https://gitflic.ru/project/guroo/wine-installer.git
cd wine-installer
python3 wine.py
```

**GitHub (зеркало):**
```bash
git clone https://github.com/Godlike-Bagheera/wine-installer.git
cd wine-installer
python3 wine.py
```

Или просто одной строкой:
```bash
bash install.sh
```

## Возможности

- 🎮 Запуск `.exe` / `.msi` / `.lnk` через Wine AppImage
- 🚀 DXVK (d3d9 / d3d10 / d3d11) + автоматическая установка в префикс
- 🧩 Winetricks: автофиксы отсутствующих DLL (vcrun*, d3dx*, xact, ...)
- ⛏ Minecraft: Prism, Legacy Launcher, Fabulously Optimized, OptiFine, Fabric
- ☕ Портативная JDK 17 (Temurin) для OptiFine installer
- 🎯 GameMode, MangoHud, gamescope (опционально, через `config.py`)
- 📜 История запусков, логи на каждую игру, `debugreport`
- 🌍 Мультизеркала (ghfast.top / ghproxy.net / …) + докачка + slow-mode
- 📦 Экспорт истории/настроек (`export`)
- 🌡  Температура GPU (`gpu-temp`) — nvidia-smi или sensors
- 🆓 Каталог бесплатных игр (`freegames`)
- 🔔 Проверка обновлений (GitFlic / GitHub — переключатель в `config.py`)

## Команды

Введи `help` внутри программы — увидишь полную справку.

## Требования

- Linux x86_64
- Python 3.9+
- ~2 ГБ свободного места
- Без root / sudo (Wine работает от пользователя)

## Лицензия

MIT — см. [LICENSE](LICENSE).