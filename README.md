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

## Настройки окружения

### Где что хранится

Все данные скрипт пишет **только в домашнюю папку** (`$HOME`), ничего не требует
и не трогает системные директории:

| Путь | Назначение |
|---|---|
| `~/wine-portable/` | Wine AppImage, префиксы, bin-утилиты — всё ядро лаунчера |
| `~/wine-portable/prefix/` | Windows-префикс по умолчанию (`WINEPREFIX`) |
| `~/wine-portable/prefixes/` | Дополнительные префиксы |
| `~/wine-portable/logs/` | Логи запуска каждой игры + `debug.log` |
| `~/wine-portable/history.json` | История запусков |
| `~/wine-portable/settings.json` | Пользовательские настройки |
| `~/wine-portable/.mirror_cache` | Кэш доступности зеркал скачивания |
| `~/games/` | Каталог игр для поиска `.exe` |
| `~/prism/` | Prism Launcher |
| `~/java/` | Портативная JDK 17 (Temurin) |

Переопределить домашнюю папку можно стандартной переменной `HOME` —
всё вышеперечисленное «поедет» за ней.

### Переменные окружения

| Переменная | Эффект |
|---|---|
| `WI_DEBUG=1` | Подробный лог в `~/wine-portable/logs/debug.log` (то же самое, что флаг `--debug`) |
| `HOME` | Корень всех путей хранения (см. таблицу выше) |
| `WINEDEBUG`, `DXVK_HUD`, `MANGOHUD` … | Стандартные переменные Wine/DXVK/MangoHud — скрипт копирует твоё окружение (`os.environ.copy()`) и поверх ставит только нужное (`WINEPREFIX`, `WINEDLLOVERRIDES`), поэтому любые свои переменные можно задать в shell и они дойдут до игры |

### Полный конфиг

Логика выбора зеркал, версий DXVK/Winetricks/JDK, включение GameMode /
MangoHud / gamescope и другие тонкие настройки лежат в `modules/config.py`
(только константы, без логики). Меню `settings` внутри программы позволяет
менять пользовательские опции без правки кода.

> ⚠️ Не публикуй в репозитории личные токены/ключи из `config.py` — для этого
> создай локальный `.env` (он уже в `.gitignore`).

## Лицензия

MIT — см. [LICENSE](LICENSE).