"""Все команды, вызываемые из главного меню."""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from modules import debug
from modules.colors import (
    ok, info, warn, err, hint,
    CYAN, BOLD, DIM, MAGENTA, YELLOW, RESET,
)
from modules.config import (
    HOME, WINE_DIR, WINE_BIN, WINE_PREFIX, LOG_DIR, DEBUG_LOG,
    BIN_DIR, WINETRICKS_BIN, ARIA2C_BIN, DXVK_DIR, SETTINGS_FILE,
    HISTORY_FILE, GAMES_DIR, DESKTOP_DIRS, SHORTCUTS_DIR,
    DXVK_OVERRIDES, FREE_GAMES, CURRENT_VERSION,
)
from modules.prefix import get_wine_env
from modules.wine import install_dxvk_to_wine
from modules.gamemode import gamemode_available
from modules.java import find_java
from modules.launcher import find_exe
from modules.settings import (
    load_settings, save_settings, apply_settings,
)
from modules.download import download_file


# ═══════════════════════════════════════════════════════════════════
#  ОТЛАДКА
# ═══════════════════════════════════════════════════════════════════


def cmd_debug(args):
    from modules import state
    args = args.strip().lower()
    if args in ("on", "вкл", "1"):
        state.DEBUG_MODE = True
        s = load_settings()
        s["debug_mode"] = True
        save_settings(s)
        ok("Дебаг включён")
        hint(f"Файл: {DEBUG_LOG}")
        return
    if args in ("off", "выкл", "0"):
        state.DEBUG_MODE = False
        s = load_settings()
        s["debug_mode"] = False
        save_settings(s)
        ok("Дебаг выключен")
        return
    if args in ("report", "отчёт"):
        cmd_debugreport()
        return
    print(f"{BOLD}Статус отладки:{RESET}")
    print(f"  Дебаг: {'включён' if state.DEBUG_MODE else 'выключен'}")
    if DEBUG_LOG.exists():
        print(f"  debug.log: {DEBUG_LOG.stat().st_size//1024} КБ")
    print("  Флаг: --debug")
    print()


def cmd_debugreport():
    import tarfile
    info(f"{BOLD}Сбор отчёта...{RESET}")
    report_dir = WINE_DIR / "debug-report"
    if report_dir.exists():
        shutil.rmtree(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    if DEBUG_LOG.exists():
        shutil.copy2(DEBUG_LOG, report_dir / "debug.log")
        ok("debug.log")
    if SETTINGS_FILE.exists():
        shutil.copy2(SETTINGS_FILE, report_dir / "settings.json")
    if HISTORY_FILE.exists():
        shutil.copy2(HISTORY_FILE, report_dir / "history.json")
    if LOG_DIR.exists():
        logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        game_logs = [l for l in logs if l.name != "debug.log"][:5]
        if game_logs:
            (report_dir / "game-logs").mkdir(exist_ok=True)
            for l in game_logs:
                shutil.copy2(l, report_dir / "game-logs" / l.name)
            ok(f"{len(game_logs)} игровых логов")
    sysinfo = []
    sysinfo.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    sysinfo.append(f"Version: v{CURRENT_VERSION}")
    sysinfo.append(f"Python: {sys.version}")
    sysinfo.append(f"Platform: {sys.platform}")
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(("NAME=", "VERSION=", "ID=")):
                    sysinfo.append(line.strip())
    except Exception as e:
        debug.dbg_exc(e, "commands/cmd_debugreport")
    sysinfo.append(f"Home: {HOME}")
    sysinfo.append(f"Wine dir: {WINE_DIR}")
    sysinfo.append(f"Wine exists: {WINE_BIN.exists()}")
    sysinfo.append(f"Wine size: {WINE_BIN.stat().st_size if WINE_BIN.exists() else 0}")
    sysinfo.append(f"Prefix exists: {WINE_PREFIX.exists()}")
    sysinfo.append(f"DXVK exists: {DXVK_DIR.exists()}")
    sysinfo.append(f"winetricks: {WINETRICKS_BIN.exists()}")
    sysinfo.append(f"aria2c: {ARIA2C_BIN.exists()}")
    try:
        df = shutil.disk_usage(HOME)
        sysinfo.append(f"Disk free: {df.free / 1024 / 1024 / 1024:.2f} GB")
    except Exception as e:
        debug.dbg_exc(e, "commands/cmd_debugreport")
    try:
        r = subprocess.run([str(WINE_BIN), "--version"], env=get_wine_env(),
                           capture_output=True, text=True, timeout=15)
        sysinfo.append(f"Wine --version: {r.stdout.strip()} {r.stderr.strip()}")
    except Exception as e:
        sysinfo.append(f"Wine --version: ERROR {e}")
    java_bin, java_home, java_status = find_java()
    sysinfo.append(f"Java: {java_bin}")
    sysinfo.append(f"Java home: {java_home}")
    sysinfo.append(f"Java status: {java_status}")
    (report_dir / "system-info.txt").write_text("\n".join(sysinfo), encoding="utf-8")
    ok("system-info.txt")
    archive = WINE_DIR / "debug-report.tar.gz"
    if archive.exists():
        archive.unlink()
    try:
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(report_dir, arcname="debug-report")
        shutil.rmtree(report_dir, ignore_errors=True)
        ok(f"Отчёт: {archive} ({archive.stat().st_size // 1024} КБ)")
        print()
        hint("Скинь этот файл разработчику:")
        print(f"  {CYAN}{archive}{RESET}")
        print()
    except Exception as e:
        debug.dbg_exc(e, "cmd_debugreport/tar")
        err(f"Архив: {e}")


# ═══════════════════════════════════════════════════════════════════
#  СИСТЕМНЫЕ
# ═══════════════════════════════════════════════════════════════════


def cmd_reset():
    if not WINE_PREFIX.exists():
        warn("Префикс отсутствует.")
        return
    try:
        answer = input(f"{MAGENTA}Удалить Wine-префикс? [y/N]: {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return
    if answer not in ("y", "yes", "д", "да"):
        return
    try:
        subprocess.run([str(WINE_BIN), "wineserver", "-k"],
                       env=get_wine_env(), timeout=10, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        debug.dbg_exc(e, "commands/cmd_reset")
    time.sleep(1)
    try:
        shutil.rmtree(WINE_PREFIX)
        ok("Префикс удалён")
    except Exception as e:
        err(f"Не удалить: {e}")


def cmd_vulkan():
    try:
        r = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            ok("Vulkan работает")
        else:
            warn("Vulkan не работает")
    except FileNotFoundError:
        warn("vulkaninfo не установлен")
    except Exception:
        warn("Vulkan не работает")


def cmd_verify():
    info(f"{BOLD}Проверка целостности...{RESET}")
    problems = 0
    if WINE_BIN.exists() and os.access(WINE_BIN, os.X_OK):
        try:
            r = subprocess.run([str(WINE_BIN), "--version"], env=get_wine_env(),
                               capture_output=True, text=True, timeout=30)
            out = (r.stdout + r.stderr).strip()
            if r.returncode == 0 and "wine" in out.lower():
                ok(f"Wine: {out.splitlines()[0]}")
            else:
                err("Wine не отвечает")
                problems += 1
        except Exception as e:
            err(f"Wine: {e}")
            problems += 1
    else:
        err("Wine отсутствует")
        problems += 1
    if DXVK_DIR.exists():
        ok("DXVK: OK")
    else:
        warn("DXVK не установлен")
        problems += 1
    if (WINE_PREFIX / "drive_c" / "windows" / "system32").exists():
        ok("Префикс: OK")
        if DXVK_DIR.exists() and install_dxvk_to_wine():
            ok("DXVK активен")
    else:
        hint("Префикс не создан (появится при первом запуске игры)")
    if WINETRICKS_BIN.exists():
        ok(f"winetricks: {WINETRICKS_BIN.stat().st_size//1024} КБ")
    else:
        warn("winetricks отсутствует")
    if ARIA2C_BIN.exists():
        ok(f"aria2c: {ARIA2C_BIN.stat().st_size//1024//1024} МБ")
    else:
        warn("aria2c отсутствует")
    java_bin, java_home, java_status = find_java()
    if java_home:
        ok(f"Java GUI: {java_home}")
    else:
        warn(f"Java: {java_status}")
        hint("Установи: install-java")
    print()
    if problems == 0:
        ok("Всё в порядке")
    else:
        warn(f"Проблем: {problems}")


def cmd_update():
    from modules.wine import cmd_update as wine_update
    wine_update()


# ═══════════════════════════════════════════════════════════════════
#  ЯРЛЫКИ / ЛОГИ / НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════


def get_desktop_dir():
    for d in DESKTOP_DIRS:
        if d.exists():
            return d
    return None


def create_desktop_shortcut(exe_path):
    desktop = get_desktop_dir()
    if not desktop:
        err("Рабочий стол не найден")
        return False
    SHORTCUTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "_", exe_path.stem)
    wrapper = SHORTCUTS_DIR / f"{safe_name}.sh"
    wrapper_content = (
        f'#!/bin/bash\n'
        f'export WINEPREFIX="{WINE_PREFIX}"\n'
        f'export WINEDLLOVERRIDES="{DXVK_OVERRIDES}"\n'
        f'cd "{exe_path.parent}" || exit 1\n'
        f'exec "{WINE_BIN}" "{exe_path.name}"\n'
    )
    wrapper.write_text(wrapper_content, encoding="utf-8")
    wrapper.chmod(0o755)
    desktop_file = desktop / f"{exe_path.stem}.desktop"
    desktop_content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={exe_path.stem}\n"
        f"Exec={wrapper}\n"
        "Icon=applications-games\n"
        "Terminal=false\n"
        "Categories=Game;\n"
    )
    desktop_file.write_text(desktop_content, encoding="utf-8")
    desktop_file.chmod(0o755)
    ok(f"Ярлык: {desktop_file}")
    return True


def cmd_desktop(name):
    info(f"Ищу '{name}'...")
    results = find_exe(name)
    if not results:
        err(f"'{name}' не найден.")
        return
    if len(results) > 1:
        for i, r in enumerate(results, 1):
            print(f"  {i}) {r}")
        try:
            idx = int(input("Номер: ").strip()) - 1
            if 0 <= idx < len(results):
                create_desktop_shortcut(results[idx])
        except (ValueError, KeyboardInterrupt):
            err("Отменено")
        return
    create_desktop_shortcut(results[0])


def cmd_log():
    from modules.settings import load_history
    from modules.launcher import show_log
    data = load_history()
    last = data.get("last_game")
    if not last:
        warn("Нет истории")
        return
    last_path = Path(last)
    if not LOG_DIR.exists():
        warn("Логи отсутствуют")
        return
    prefix = re.sub(r"[^\w\-]", "_", last_path.stem)[:40]
    candidates = sorted(LOG_DIR.glob(f"{prefix}_*.log"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        all_logs = sorted([l for l in LOG_DIR.glob("*.log") if l.name != "debug.log"],
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if not all_logs:
            warn("Логов нет")
            return
        show_log(all_logs[0])
        return
    show_log(candidates[0])


def cmd_settings(args=""):
    from modules import state
    s = load_settings()
    if not args:
        gm_ok = gamemode_available()
        java_bin, java_home, java_status = find_java()
        print(f"{BOLD}Настройки:{RESET}")
        print(f"  Тихий режим:  {CYAN}{'вкл' if s.get('quiet_mode') else 'выкл'}{RESET}")
        print(f"  GameMode:     {CYAN}{'вкл' if s.get('use_gamemode') else 'выкл'}{RESET}"
              + (f"  {DIM}(библиотека {'есть' if gm_ok else 'нет'}){RESET}" if s.get('use_gamemode') else ""))
        print(f"  Дебаг:        {CYAN}{'вкл' if state.DEBUG_MODE else 'выкл'}{RESET}")
        print(f"  Java:         {CYAN}{java_status}{RESET}")
        print(f"  Префикс:      {DIM}{WINE_PREFIX}{RESET}")
        print(f"  Debug лог:    {DIM}{DEBUG_LOG}{RESET}")
        print()
        hint("settings quiet|gamemode|debug on|off")
        return
    parts = args.split()
    if len(parts) == 2:
        key, value = parts
        value_on = value.lower() in ("on", "true", "1", "yes", "да", "вкл")
        value_off = value.lower() in ("off", "false", "0", "no", "нет", "выкл")
        if key in ("quiet", "тихо") and (value_on or value_off):
            s["quiet_mode"] = value_on
            save_settings(s)
            apply_settings()
            ok(f"Тихий режим {'вкл' if value_on else 'выкл'}")
            return
        if key == "gamemode" and (value_on or value_off):
            s["use_gamemode"] = value_on
            save_settings(s)
            ok(f"GameMode {'вкл' if value_on else 'выкл'}")
            return
        if key in ("debug", "дебаг") and (value_on or value_off):
            cmd_debug("on" if value_on else "off")
            return
    warn("settings quiet|gamemode|debug on|off")


def cmd_bin():
    print(f"{BOLD}{BIN_DIR}:{RESET}")
    if not BIN_DIR.exists():
        warn("Папка отсутствует")
        return
    items = list(BIN_DIR.iterdir())
    if not items:
        warn("Пусто")
        return
    for f in sorted(items):
        size = f.stat().st_size
        size_str = f"{size/1024/1024:.1f} МБ" if size > 1024*1024 else f"{size/1024:.0f} КБ"
        mark = "✓" if os.access(f, os.X_OK) else " "
        print(f"  [{mark}] {f.name}  {DIM}({size_str}){RESET}")
    print()


# ═══════════════════════════════════════════════════════════════════
#  STEAM / DOWNLOAD
# ═══════════════════════════════════════════════════════════════════


def cmd_steamfix(name):
    info(f"Ищу '{name}'...")
    found_any = False
    for candidate in [WINE_PREFIX / "drive_c" / "windows" / "system32",
                      WINE_PREFIX / "drive_c" / "windows" / "syswow64"]:
        if candidate.exists():
            try:
                if list(candidate.glob("steam_api*.dll")):
                    found_any = True
                    break
            except Exception as e:
                debug.dbg_exc(e, "commands/cmd_steamfix")
    if not found_any:
        warn("steam_api.dll нет в префиксе — команда бесполезна")
        hint("Скачай Goldberg: https://github.com/Detanup01/gbe_fork/releases")
        hint("Положи steam_api.dll и steam_api64.dll рядом с .exe игры")
        return
    results = find_exe(name)
    if not results:
        err(f"Файл '{name}' не найден.")
        return
    if len(results) > 1:
        for i, r in enumerate(results, 1):
            print(f"  {i}) {r}")
        try:
            idx = int(input("Номер: ").strip()) - 1
            if not (0 <= idx < len(results)):
                err("Неверный номер")
                return
            exe = results[idx]
        except (ValueError, KeyboardInterrupt):
            err("Отменено")
            return
    else:
        exe = results[0]
    target_dir = exe.parent
    info(f"Папка игры: {target_dir}")
    syswow64 = WINE_PREFIX / "drive_c" / "windows" / "syswow64"
    system32 = WINE_PREFIX / "drive_c" / "windows" / "system32"
    copied = 0
    for dll_name, src_dirs in [("steam_api.dll", [syswow64, system32]),
                                ("steam_api64.dll", [system32, syswow64])]:
        dest = target_dir / dll_name
        if dest.exists():
            info(f"{dll_name} уже есть")
            continue
        for src_dir in src_dirs:
            src = src_dir / dll_name
            if src.exists():
                try:
                    shutil.copy2(src, dest)
                    ok(f"Скопирован {dll_name}")
                    copied += 1
                    break
                except Exception as e:
                    warn(f"Не скопировать {dll_name}: {e}")
    appid_file = target_dir / "steam_appid.txt"
    if not appid_file.exists():
        appid_file.write_text("480\n", encoding="utf-8")
        ok("Создан steam_appid.txt (480)")
        copied += 1
    if copied == 0:
        warn("Ничего не скопировано")
    else:
        ok(f"Steam-заглушка ({copied} изменений)")


def cmd_download(args):
    import zipfile
    import tarfile
    if not args:
        warn("download [--no-extract] <URL>")
        return
    no_extract = False
    url = args.strip()
    if url.startswith("--no-extract"):
        no_extract = True
        url = url[len("--no-extract"):].strip()
    if not url:
        warn("Не указан URL")
        return
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    fname = url.split("/")[-1].split("?")[0] or "download.bin"
    local = GAMES_DIR / fname
    info(f"Скачиваю: {url}")
    if not download_file([("direct", url)], local, fname, min_size_mb=1):
        err("Не удалось скачать")
        return
    ok(f"Скачано: {local.stat().st_size/1024/1024:.1f} МБ")
    if no_extract:
        return
    base_name = re.sub(r"\.(zip|rar|7z|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz)$", "", fname, flags=re.I)
    extract_dir = GAMES_DIR / base_name
    if extract_dir.exists():
        i = 1
        while (GAMES_DIR / f"{base_name}_{i}").exists():
            i += 1
        extract_dir = GAMES_DIR / f"{base_name}_{i}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    info(f"Распаковываю в {extract_dir}")
    low = fname.lower()
    success = False
    try:
        if low.endswith(".zip"):
            with zipfile.ZipFile(local, "r") as z:
                z.extractall(extract_dir)
            success = True
        elif low.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz")):
            with tarfile.open(local) as t:
                t.extractall(extract_dir)
            success = True
        else:
            err(f"Формат не поддержан (rar/7z — вручную): {fname}")
            return
    except Exception as e:
        err(f"Распаковка: {e}")
        return
    if not success:
        return
    ok(f"Распаковано в {extract_dir}")
    exes = []
    for root, dirs, files in os.walk(extract_dir):
        for fn in files:
            if fn.lower().endswith((".exe", ".msi", ".lnk")):
                exes.append(Path(root) / fn)
    if not exes:
        warn("Нет .exe/.msi/.lnk")
        return
    real_exes = [e for e in exes
                 if "setup" not in e.name.lower()
                 and "install" not in e.name.lower()
                 and "unins" not in e.name.lower()]
    if real_exes:
        exes = real_exes
    if len(exes) == 1:
        chosen = exes[0]
    else:
        for i, e in enumerate(exes, 1):
            print(f"  {i}) {e.name}")
        try:
            idx = int(input("Номер: ").strip()) - 1
            if not (0 <= idx < len(exes)):
                err("Неверный номер")
                return
            chosen = exes[idx]
        except (ValueError, KeyboardInterrupt):
            err("Отменено")
            return
    from modules.settings import update_history
    from modules.launcher import launch
    update_history(chosen)
    launch(chosen)


# ═══════════════════════════════════════════════════════════════════
#  ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ v2.6
# ═══════════════════════════════════════════════════════════════════


def cmd_export(args=""):
    """Экспорт истории и настроек в tar.gz."""
    import tarfile
    archive = WINE_DIR / "wine-config-export.tar.gz"
    if archive.exists():
        archive.unlink()
    files_to_pack = []
    if HISTORY_FILE.exists():
        files_to_pack.append(HISTORY_FILE)
    if SETTINGS_FILE.exists():
        files_to_pack.append(SETTINGS_FILE)
    if not files_to_pack:
        warn("Нечего экспортировать — нет истории и настроек")
        return
    try:
        with tarfile.open(archive, "w:gz") as tar:
            for f in files_to_pack:
                tar.add(f, arcname=f.name)
        ok(f"Экспорт: {archive} ({archive.stat().st_size // 1024} КБ)")
        hint("Перенеси этот файл на другой ПК и распакуй вручную в ~/wine-portable/")
    except Exception as e:
        debug.dbg_exc(e, "cmd_export")
        err(f"Экспорт: {e}")


def cmd_gpu_temp():
    """Показать температуру GPU (nvidia-smi или sensors)."""
    import shutil
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            r = subprocess.run(
                [nvidia, "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                parts = [p.strip() for p in r.stdout.strip().split(",")]
                if len(parts) >= 4:
                    temp, util, mem_u, mem_t = parts[:4]
                    ok(f"NVIDIA GPU: {temp}°C, загрузка {util}%, память {mem_u}/{mem_t} МБ")
                    return
        except Exception as e:
            debug.dbg_exc(e, "cmd_gpu_temp/nvidia")
    sensors = shutil.which("sensors")
    if sensors:
        try:
            r = subprocess.run([sensors], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                found = False
                for line in r.stdout.splitlines():
                    if "temp" in line.lower() or "°C" in line:
                        print("  " + line)
                        found = True
                if found:
                    return
        except Exception as e:
            debug.dbg_exc(e, "cmd_gpu_temp/sensors")
    warn("Ни nvidia-smi, ни sensors не найдены")
    hint("Установи: flatpak --user install flathub org.kde.ksensors  (или lm_sensors в системе)")


def cmd_free_games():
    """Каталог бесплатных игр — можно скачать одной командой."""
    print(f"\n{BOLD}Бесплатные игры:{RESET}")
    for i, (name, url) in enumerate(FREE_GAMES, 1):
        print(f"  {CYAN}{i:2d}{RESET}) {name}")
    print()
    hint("Введи номер, чтобы скачать и распаковать, или Enter для отмены")
    try:
        choice = input(f"{YELLOW}Номер: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        return
    if not choice:
        return
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(FREE_GAMES)):
            err("Неверный номер")
            return
    except ValueError:
        err("Не число")
        return
    name, url = FREE_GAMES[idx]
    info(f"Выбрана: {name}")
    cmd_download(url)
