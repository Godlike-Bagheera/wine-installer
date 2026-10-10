#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wine Installer + Game Launcher

Запуск:
    python3 wine.py
    python3 wine.py --debug
    python3 wine.py --help
    python3 wine.py --version

Модули в папке modules/.
"""
import os
import sys
import traceback
from pathlib import Path

# Форсируем рабочую директорию = папка скрипта (можно запускать откуда угодно)
SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)
sys.path.insert(0, str(SCRIPT_DIR))

# ---------- ЕДИНЫЙ ИСТОЧНИК ВЕРСИИ ----------
from modules.config import CURRENT_VERSION as VERSION  # noqa: E402


def _print_art():
    """Печатает ASCII-арт из ascii-art.txt (в корне)."""
    art_path = SCRIPT_DIR / "ascii-art.txt"
    try:
        art = art_path.read_text(encoding="utf-8").rstrip("\n")
        if art:
            print(f"\033[96m{art}\033[0m")
    except Exception as e:
        debug.dbg_exc(e, "wine/_print_art")


if "--version" in sys.argv:
    print(f"Wine Installer + Game Launcher v{VERSION}")
    sys.exit(0)

if "--help" in sys.argv or "-h" in sys.argv:
    _print_art()
    print(f"Wine Installer + Game Launcher v{VERSION}")
    print()
    print("Использование: python3 wine.py [опции]")
    print()
    print("Опции:")
    print("  --debug     подробное логирование в ~/wine-portable/logs/debug.log")
    print("  --version   показать версию и выйти")
    print("  --help, -h  эта справка")
    print()
    print("Примеры:")
    print("  python3 wine.py")
    print("  python3 wine.py --debug")
    print("  bash install.sh --debug")
    sys.exit(0)

# ---------- WARNING ПРО ROOT ----------
if os.geteuid() == 0:
    print("\033[91m[✗]\033[0m Не запускай скрипт через sudo/root!")
    print("\033[96m[→]\033[0m Wine создаст префикс от root, и обычный пользователь не сможет им пользоваться.")
    print("\033[96m[→]\033[0m Запусти от обычного пользователя.")
    sys.exit(1)

# ---------- ЗАПУСК ----------
from modules import debug, state  # noqa: E402


def main():
    from modules.ui import main as ui_main
    ui_main()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print()
    except Exception as e:
        debug.dbg_exc(e, "main/top")
        print()
        from modules.colors import err, hint
        from modules.config import DEBUG_LOG
        err(f"Скрипт упал: {e}")
        if state.DEBUG_MODE:
            traceback.print_exc()
            hint(f"Лог: {DEBUG_LOG}")
            hint("Отчёт: перезапусти и введи `debugreport`")
        sys.exit(1)
