"""Wine-префикс, пути, окружение, per-game «бутылки»."""
import os
import re
import time
import subprocess
from pathlib import Path
from modules import debug, state
from modules.colors import ok, info, err, BOLD, RESET
from modules.config import (
    WINE_PREFIX, WINE_BIN, DXVK_DIR, DXVK_OVERRIDES,
    PREFIXES_DIR, HOME, DEFAULT_PREFIX,
)


def get_prefix_path(exe_path=None):
    # Флаг читаем из state (ставится settings.apply_settings из settings.json),
    # а не из константы config — иначе настройка не применялась бы без рестарта.
    if state.USE_PER_GAME_PREFIX and exe_path is not None:
        safe_name = re.sub(r"[^\w\-]", "_", Path(exe_path).stem)[:40]
        return PREFIXES_DIR / safe_name
    return WINE_PREFIX


def get_wine_env(use_dxvk=True, exe_path=None):
    prefix = get_prefix_path(exe_path)
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    if use_dxvk and DXVK_DIR.exists():
        env["WINEDLLOVERRIDES"] = DXVK_OVERRIDES
    if state.USE_DXVK_HUD:
        env["DXVK_HUD"] = "fps,frametimes,gpuload,devinfo"
    if state.USE_MANGOHUD:
        env["MANGOHUD"] = "1"
    return env


def ensure_prefix(force_boot=False, exe_path=None):
    prefix = get_prefix_path(exe_path)
    system32 = prefix / "drive_c" / "windows" / "system32"
    marker = prefix / ".wineboot_done"

    if marker.exists() and system32.exists() and not force_boot:
        return True

    if not system32.exists():
        if state.USE_PER_GAME_PREFIX and exe_path is not None:
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
        except Exception as e:
            debug.dbg_exc(e, "prefix")
        ok("Префикс готов")
        return True

    err("Префикс не создан")
    return False


def get_minecraft_game_path():
    return str(
        WINE_PREFIX / "drive_c" / "users" / "stud" / "AppData" /
        "Roaming" / ".tlauncher" / "legacy" / "Minecraft" / "game"
    )


# ═══════════════════════════════════════════════════════════════════
#  ПОИСК .minecraft (реальные директории игры на системе)
# ═══════════════════════════════════════════════════════════════════

_MC_MARKERS = ("versions", "assets", "libraries")
# Папки с бэкапами миров (см. modules/worlds.py): их содержимое — копии
# реальных директорий игры, сами по себе игровыми каталогами не являются.
_MC_BACKUP_MARKER = "minecraft-worlds"


def _in_worlds_backup(p):
    """True, если путь лежит внутри папки-бэкапа миров «minecraft-worlds».

    Иначе find_minecraft_dirs() принимает скопированные вместе с мирами
    версии/ за настоящую директуру игры (проблема: saveworlds начинает
    копировать бэкап сам в себя, а loadworlds грузит миры в бэкап)."""
    try:
        parts = [x.lower() for x in Path(p).resolve().parts]
    except OSError:
        parts = [x.lower() for x in Path(p).parts]
    return _MC_BACKUP_MARKER in parts


def _looks_like_mc_dir(p):
    """Папка похожа на директорию Minecraft: называется .minecraft/ game/
    и содержит хотя бы один маркер (versions/assets/libraries), либо в ней
    есть versions/ c json-профилями. Пути внутри бэкапа миров отбрасываются."""
    try:
        if not p.is_dir():
            return False
        if _in_worlds_backup(p):
            return False
        names = {p.name.lower(), (p.parent.name + "/" + p.name).lower()}
        marker_ok = any((p / m).is_dir() for m in _MC_MARKERS)
        named_ok = (
            p.name.lower() == ".minecraft"
            or "minecraft" in p.name.lower()
            or "minecraft/game" in " ".join(names)
            or p.name.lower() == "game" and p.parent.name.lower() in (".tlauncher", "legacy", "minecraft")
        )
        if not (marker_ok or named_ok):
            return False
        # если названа как mc, но маркеров нет — всё равно годится (свежий install)
        return True
    except Exception:
        return False


def find_minecraft_dirs(limit=12):
    """Ищет папки .minecraft (и аналоги Legacy/Prism) по типичным местам:
    HOME, Roaming-префиксы Wine. Возвращает список Path, отсортированный:
    сначала папки с непустым versions/, затем остальные."""
    candidates = []

    def add(p):
        try:
            p = Path(p)
            rp = str(p.resolve())
            if _looks_like_mc_dir(p) and rp not in seen:
                seen.add(rp)
                candidates.append(p)
        except Exception as e:
            debug.dbg_exc(e, "prefix")
    seen = set()

    # 1) Прямые типовые пути
    direct = [
        HOME / ".minecraft",
        WINE_PREFIX / "drive_c" / "users" / "stud" / ".minecraft",
        WINE_PREFIX / "drive_c" / "users" / "stud" / "AppData" / "Roaming" / ".minecraft",
        WINE_PREFIX / "drive_c" / "users" / "stud" / "AppData" / "Roaming" / ".tlauncher" / "legacy" / "Minecraft" / "game",
        Path("/root/.minecraft"),
    ]
    for d in direct:
        add(d)

    # 2) Все префиксы wine-portable/prefixes/*/drive_c/users/<user>/...
    try:
        for pref in [DEFAULT_PREFIX, *PREFIXES_DIR.glob("*")]:
            users_dir = pref / "drive_c" / "users"
            if not users_dir.is_dir():
                continue
            for user in users_dir.iterdir():
                add(user / ".minecraft")
                add(user / "AppData" / "Roaming" / ".minecraft")
                add(user / "AppData" / "Roaming" / ".tlauncher" / "legacy" / "Minecraft" / "game")
    except Exception as e:
        debug.dbg_exc(e, "prefix")
    # 3) Ограниченный обход HOME глубиной 3 на предмет папок .minecraft
    try:
        skip = {"wine-portable", ".cache", ".local", ".config", ".git",
                "node_modules", "__pycache__", ".mozilla", ".thunderbird",
                ".steam", ".var", ".npm", ".cargo", ".rustup", "snap", "flatpak"}
        for a in HOME.iterdir():
            try:
                if not a.is_dir() or a.name in skip or a.name.startswith("."):
                    continue
                add(a / ".minecraft")
                for b in a.iterdir():
                    try:
                        if b.is_dir() and b.name.lower() == ".minecraft":
                            add(b)
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception as e:
        debug.dbg_exc(e, "prefix")
    def score(p):
        try:
            vdir = p / "versions"
            n = len([d for d in vdir.iterdir() if d.is_dir()]) if vdir.is_dir() else -1
        except Exception:
            n = -1
        return (-n, str(p))

    candidates.sort(key=score)
    return candidates[:limit]


def choose_minecraft_dir(auto=True):
    """Возвращает выбранную директорию игры (Path) или None.
    Если найдена одна — использует её; если несколько — спрашивает."""
    found = find_minecraft_dirs()
    if not found:
        return None
    if len(found) == 1 or auto:
        if len(found) > 1:
            info(f"Найдено несколько директорий игры, беру первую: {found[0]}")
        return found[0]
    print(f"{BOLD}Найдено несколько папок Minecraft:{RESET}")
    for i, p in enumerate(found, 1):
        print(f"  {i}) {p}")
    try:
        choice = input("Выбор [1]: ").strip() or "1"
        return found[int(choice) - 1]
    except (ValueError, IndexError, KeyboardInterrupt, EOFError):
        return found[0]


def show_minecraft_paths():
    from modules.colors import CYAN
    game_linux = get_minecraft_game_path()
    game_win = r"C:\users\stud\AppData\Roaming\.tlauncher\legacy\Minecraft\game"
    print(f"\n{BOLD}Пути Minecraft:{RESET}")
    print("  Linux (для OptiFine через java):")
    print(f"    {CYAN}{game_linux}{RESET}")
    print("  Windows (для .exe):")
    print(f"    {CYAN}{game_win}{RESET}")
    found = find_minecraft_dirs()
    if found:
        print("  Найденные реальные папки игры:")
        for p in found:
            print(f"    {CYAN}{p}{RESET}")
    else:
        print("  Папки .minecraft на системе не найдены.")
    print()
