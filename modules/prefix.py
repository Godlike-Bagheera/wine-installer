"""Wine-префикс, пути, окружение, per-game «бутылки»."""
import os
import re
import time
import subprocess
from pathlib import Path
from modules import debug
from modules.colors import ok, info, warn, err, hint, BOLD, RESET
from modules.config import (
    WINE_PREFIX, WINE_BIN, DXVK_DIR, DXVK_OVERRIDES,
    WINE_DIR, PREFIXES_DIR, USE_PER_GAME_PREFIX,
    USE_DXVK_HUD, USE_MANGOHUD,
)


def get_prefix_path(exe_path=None):
    if USE_PER_GAME_PREFIX and exe_path is not None:
        safe_name = re.sub(r"[^\w\-]", "_", Path(exe_path).stem)[:40]
        return PREFIXES_DIR / safe_name
    return WINE_PREFIX


def get_wine_env(use_dxvk=True, exe_path=None):
    prefix = get_prefix_path(exe_path)
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    if use_dxvk and DXVK_DIR.exists():
        env["WINEDLLOVERRIDES"] = DXVK_OVERRIDES
    if USE_DXVK_HUD:
        env["DXVK_HUD"] = "fps,frametimes,gpuload,devinfo"
    if USE_MANGOHUD:
        env["MANGOHUD"] = "1"
    return env


def ensure_prefix(force_boot=False, exe_path=None):
    prefix = get_prefix_path(exe_path)
    system32 = prefix / "drive_c" / "windows" / "system32"
    marker = prefix / ".wineboot_done"

    if marker.exists() and system32.exists() and not force_boot:
        return True

    if not system32.exists():
        if USE_PER_GAME_PREFIX and exe_path is not None:
            info(f"{BOLD}Создаю отдельную «бутылку» для {Path(exe_path).stem} (1–3 минуты)...{RESET}")
        else:
            info(f"{BOLD}Создаю Wine-префикс (1–3 минуты)...{RESET}")
    else:
        info(f"{BOLD}Обновляю Wine-префикс...{RESET}")

    try:
        subprocess.run(
            [str(WINE_BIN), "wineboot", "-u"],
            env=get_wine_env(use_dxvk=False, exe_path=exe_path),
            timeout=300, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        debug.dbg_exc(e, "ensure_prefix/wineboot")
        err(f"wineboot не сработал: {e}")
        return False

    if system32.exists():
        try:
            marker.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass
        ok("Префикс готов")
        return True

    err("Префикс не создан")
    return False


def get_minecraft_game_path():
    return str(
        WINE_PREFIX / "drive_c" / "users" / "stud" / "AppData" /
        "Roaming" / ".tlauncher" / "legacy" / "Minecraft" / "game"
    )


def show_minecraft_paths():
    from modules.colors import CYAN
    game_linux = get_minecraft_game_path()
    game_win = r"C:\users\stud\AppData\Roaming\.tlauncher\legacy\Minecraft\game"
    print(f"\n{BOLD}Пути Minecraft:{RESET}")
    print(f"  Linux (для OptiFine через java):")
    print(f"    {CYAN}{game_linux}{RESET}")
    print(f"  Windows (для .exe):")
    print(f"    {CYAN}{game_win}{RESET}")
    print()