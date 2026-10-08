"""Поиск .exe и запуск через Wine (+ gamescope, MangoHud, TTS)."""
import os
import re
import time
import shutil
import subprocess
from pathlib import Path
from modules import debug
from modules.colors import info, warn, err, hint, BOLD, RESET
from modules.config import (
    HOME, WINE_BIN, LOG_DIR, PRIORITY_DIRS, EXCLUDE_DIRS,
    SUPPORTED_EXT, MAX_RETRIES, OK_RUN_SECONDS, CRASH_SHOW_LOG_SECONDS,
    USE_GAMESCOPE, USE_TTS_NOTIFY,
)
from modules.prefix import ensure_prefix, get_wine_env
from modules.wine import install_dxvk_to_wine
from modules.winetricks import (
    detect_missing_libs, install_via_winetricks, filter_line,
)
from modules.settings import load_settings, update_history
from modules.gamemode import gamemode_available


def get_log_path(exe_path):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = re.sub(r"[^\w\-]", "_", exe_path.stem)[:40]
    return LOG_DIR / f"{name}_{stamp}.log"


def show_log(log_path, lines=40):
    from modules.colors import DIM
    if not log_path.exists() or log_path.stat().st_size == 0:
        warn("Лог пустой.")
        return
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        tail = content.splitlines()[-lines:]
        print(f"{DIM}{'─' * 60}{RESET}")
        print(f"{BOLD}Последние {len(tail)} строк лога:{RESET}")
        print(f"{DIM}{'─' * 60}{RESET}")
        for line in tail:
            print(line)
        print(f"{DIM}{'─' * 60}{RESET}")
        hint(f"Полный лог: {log_path}")
    except Exception as e:
        debug.dbg_exc(e, "show_log")
        err(f"Не прочитать лог: {e}")


def scan_dir(base, targets, max_depth):
    found = []
    base_depth = len(base.parts)
    try:
        for root, dirs, files in os.walk(base):
            current_depth = len(Path(root).parts) - base_depth
            if current_depth >= max_depth:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for fn in files:
                if fn.lower() in targets:
                    found.append(Path(root) / fn)
    except (PermissionError, OSError):
        pass
    return found


def find_exe(name):
    import sys
    p = Path(name).expanduser()
    if p.is_absolute():
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            return [p]
        if not p.suffix:
            for ext in SUPPORTED_EXT:
                candidate = Path(str(p) + ext)
                if candidate.is_file():
                    return [candidate]
        return []
    target_name = Path(name.lower().strip()).name
    targets = set()
    if target_name.endswith(SUPPORTED_EXT):
        targets.add(target_name)
    else:
        for ext in SUPPORTED_EXT:
            targets.add(target_name + ext)
    for base in PRIORITY_DIRS:
        if base.exists():
            sys.stdout.write(f"\r  ищу в {base}...                    ")
            sys.stdout.flush()
            res = scan_dir(base, targets, max_depth=5)
            if res:
                print()
                return res
    sys.stdout.write(f"\r  ищу в {HOME}...                    ")
    sys.stdout.flush()
    res = scan_dir(HOME, targets, max_depth=3)
    print()
    return res


def _tts_say(text):
    if not USE_TTS_NOTIFY:
        return
    spd = shutil.which("spd-say")
    if not spd:
        return
    try:
        subprocess.Popen([spd, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _build_cmd(path, use_gm):
    suffix = path.suffix.lower()
    if suffix == ".lnk":
        base_cmd = [str(WINE_BIN), "start", "/unix", str(path)]
    elif suffix == ".msi":
        base_cmd = [str(WINE_BIN), "msiexec", "/i", str(path)]
    else:
        base_cmd = [str(WINE_BIN), str(path)]

    if use_gm:
        base_cmd = ["gamemoderun"] + base_cmd

    if USE_GAMESCOPE:
        gs = shutil.which("gamescope")
        if gs:
            base_cmd = [gs, "-W", "1920", "-H", "1080", "-f", "--"] + base_cmd

    return base_cmd


def launch(path):
    log_path = get_log_path(path)
    settings = load_settings()
    use_gm = settings.get("use_gamemode", False) and gamemode_available()
    info(f"Движок: {BOLD}Wine{RESET}")
    if use_gm:
        info(f"GameMode: {BOLD}включён{RESET}")
    info(f"Запускаю: {path}")
    hint(f"Лог: {log_path}")
    if not ensure_prefix(exe_path=path):
        warn("Префикс не готов")
    from modules.config import DXVK_DIR
    prefix = get_wine_env(exe_path=path)["WINEPREFIX"]
    if DXVK_DIR.exists() and (Path(prefix) / "drive_c" / "windows" / "system32").exists():
        install_dxvk_to_wine(exe_path=path)
    print()
    _tts_say(f"Запускаю {path.stem}")

    installed_pkgs = set()
    wine_env = get_wine_env(exe_path=path)
    final_status = "crash"
    total_duration = 0.0
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            info(f"Повторная попытка {attempt}/{MAX_RETRIES}")
        missing_pkgs = set()
        start_time = time.time()
        mode = "w" if attempt == 1 else "a"
        try:
            with open(log_path, mode, encoding="utf-8", errors="replace") as logf:
                if attempt > 1:
                    logf.write(f"\n\n=== ПОПЫТКА {attempt} ===\n\n")
                cmd = _build_cmd(path, use_gm)
                debug.dbg(f"Launch: {cmd}")
                proc = subprocess.Popen(
                    cmd, cwd=str(path.parent), env=wine_env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding="utf-8", errors="replace",
                )
                if proc.stdout is None:
                    proc.wait()
                    # Засчитываем время даже если stdout недоступен
                    total_duration += time.time() - start_time
                    continue
                import sys
                try:
                    for line in proc.stdout:
                        logf.write(line)
                        logf.flush()
                        shown = filter_line(line)
                        if shown is not None:
                            sys.stdout.write(shown)
                            sys.stdout.flush()
                        for pkg in detect_missing_libs(line):
                            missing_pkgs.add(pkg)
                except KeyboardInterrupt:
                    warn("Прервано (Ctrl+C)")
                    hint("Лаунчер мог не успеть создать папки в game/")
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    total_duration += time.time() - start_time
                    update_history(path, status="unknown", duration=total_duration)
                    return
                proc.wait()
        except Exception as e:
            debug.dbg_exc(e, f"launch/attempt{attempt}")
            err(f"Ошибка запуска: {e}")
            update_history(path, status="crash", duration=total_duration)
            return
        duration = time.time() - start_time
        total_duration += duration
        if duration >= OK_RUN_SECONDS:
            final_status = "ok"
            if not missing_pkgs:
                update_history(path, status="ok", duration=total_duration)
                _tts_say(f"{path.stem} закрылась")
                return
            warn(f"Отсутствуют библиотеки: {', '.join(sorted(missing_pkgs))}")
            from modules.config import AUTO_FIX
            if not AUTO_FIX:
                update_history(path, status="ok", duration=total_duration)
                return
            try:
                from modules.colors import MAGENTA
                answer = input(f"{MAGENTA}Доустановить и перезапустить? [y/N]: {RESET}").strip().lower()
            except (KeyboardInterrupt, EOFError):
                update_history(path, status="ok", duration=total_duration)
                return
            if answer not in ("y", "yes", "д", "да"):
                update_history(path, status="ok", duration=total_duration)
                return
        if not missing_pkgs:
            if duration < CRASH_SHOW_LOG_SECONDS:
                print()
                warn(f"Игра завершилась за {duration:.1f} с — упала.")
                hint("Открываю лог...")
                time.sleep(0.5)
                show_log(log_path)
            update_history(path, status=final_status, duration=total_duration)
            _tts_say(f"{path.stem} завершилась с ошибкой")
            return
        try:
            install_via_winetricks(missing_pkgs, installed_pkgs, exe_path=path)
        except KeyboardInterrupt:
            update_history(path, status="unknown", duration=total_duration)
            return
        print()
    warn(f"Лимит попыток ({MAX_RETRIES})")
    if log_path.exists():
        show_log(log_path)
    update_history(path, status="crash", duration=total_duration)
