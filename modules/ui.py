"""Help, process_input, диагностика, main."""
import os
import sys
import subprocess
from pathlib import Path
from modules import state, debug
from modules.colors import (
    ok, info, warn, err, hint, sep,
    CYAN, BOLD, GREEN, YELLOW, BLUE, RESET,
)
from modules.config import (
    HOME, WINE_BIN, WINE_PREFIX, DXVK_DIR, WINETRICKS_BIN, ARIA2C_BIN,
    DEBUG_LOG, EXPECTED_COMMANDS, CURRENT_VERSION,
)
from modules.settings import (
    load_history, show_history_menu,
    load_settings, save_settings, apply_settings,
)
from modules.launcher import launch, find_exe
from modules.java import find_java, cmd_install_java
from modules.minecraft import (
    cmd_minecraft, setup_fabulously_optimized, setup_optifine,
    setup_prism, setup_legacy,
)
from modules.commands import (
    cmd_debug, cmd_debugreport, cmd_reset, cmd_vulkan, cmd_verify,
    cmd_update, cmd_desktop, cmd_log, cmd_settings, cmd_bin,
    cmd_steamfix, cmd_download,
    cmd_export, cmd_gpu_temp, cmd_free_games,
)
from modules.winetricks import cmd_fonts, download_winetricks
from modules.gamemode import cmd_gamemode
from modules.worlds import cmd_save_worlds, cmd_load_worlds, cmd_worlds_menu
from modules.shaders import cmd_shaders
from modules import background
from modules.prefix import get_wine_env
from modules.wine import (
    download_wine, download_dxvk, create_runexe,
)
from modules.debug import rotate_old_logs
from modules.art import print_art
from modules.config import ARIA2C_MIRRORS, MIN_ARIA2C_SIZE, BIN_DIR
from modules.download import try_download_manual


def _setup_readline():
    """Автодополнение путей по Tab в input(). Только Unix (Linux/macOS)."""
    try:
        import readline  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        # На Windows модуля нет — тихо выходим, автодополнение не работает
        return

    from modules.config import PRIORITY_DIRS

    def completer(text, state):
        if "/" in text:
            return None
        candidates = []
        for base in PRIORITY_DIRS + [Path.cwd()]:
            if not base.exists():
                continue
            try:
                for f in base.iterdir():
                    if f.name.lower().startswith(text.lower()):
                        candidates.append(f.name)
            except Exception:
                pass
        candidates = sorted(set(candidates))
        if state < len(candidates):
            return candidates[state]
        return None

    try:
        readline.set_completer(completer)          # type: ignore[attr-defined]
        readline.parse_and_bind("tab: complete")   # type: ignore[attr-defined]
        readline.set_completer_delims(" \t\n")     # type: ignore[attr-defined]
    except Exception:
        pass


def print_help():
    line = "─" * 52
    print(f"{BOLD}{line}{RESET}")
    print(f"{BOLD}  Команды v{CURRENT_VERSION}{RESET}")
    print(f"{BOLD}{line}{RESET}")
    print(f"{BOLD}Игры:{RESET}")
    print(f"  {CYAN}<имя.exe>{RESET}         — запустить игру (фоновый режим)")
    print(f"  {CYAN}<номер>{RESET}             — из истории")
    print(f"  {CYAN}!!{RESET}                  — последнюю игру")
    print(f"  {CYAN}desktop <имя.exe>{RESET}  — ярлык на рабочем столе")
    print(f"  {CYAN}download <URL>{RESET}     — скачать/распаковать архив")
    print(f"{BOLD}Фоновый режим:{RESET}")
    print(f"  {CYAN}gamestatus{RESET}          — статус запущенных игр")
    print(f"  {CYAN}games{RESET}               — список активных игр")
    print(f"  {CYAN}stopgame{RESET}           — остановить все игры")
    print(f"  {CYAN}waitgame{RESET}           — дождаться завершения игр")
    print(f"{BOLD}Minecraft:{RESET}")
    print(f"  {CYAN}minecraft{RESET}            — меню (все варианты)")
    print(f"  {CYAN}fo{RESET}                   — Fabulously Optimized")
    print(f"  {CYAN}optifine{RESET}             — OptiFine")
    print(f"  {CYAN}prism{RESET}                — Prism Launcher")
    print(f"  {CYAN}legacy{RESET}               — Legacy Launcher")
    print(f"  {CYAN}shaders{RESET}             — установить шейдер-пак")
    print(f"  {CYAN}install-java{RESET}         — портативная JDK 17")
    print(f"{BOLD}Миры (Диск D, RED OS):{RESET}")
    print(f"  {CYAN}worlds / миры{RESET}        — меню миров (диск D)")
    print(f"  {CYAN}saveworlds{RESET}          — сохранить миры на Диск D")
    print(f"  {CYAN}loadworlds{RESET}          — загрузить миры с Диска D")
    print(f"{BOLD}Утилиты:{RESET}")
    print(f"  {CYAN}fonts{RESET}               — corefonts")
    print(f"  {CYAN}steamfix <имя.exe>{RESET} — заглушка steam_api.dll")
    print(f"  {CYAN}gamemode{RESET}            — GameMode вкл/выкл")
    print(f"  {CYAN}vulkan{RESET}              — проверка Vulkan")
    print(f"  {CYAN}verify{RESET}              — целостность")
    print(f"  {CYAN}update{RESET}              — переустановить Wine/DXVK")
    print(f"  {CYAN}dxvk{RESET}                — только DXVK")
    print(f"  {CYAN}reset{RESET}               — удалить префикс")
    print(f"  {CYAN}bin{RESET}                 — содержимое bin/")
    print(f"{BOLD}Настройки:{RESET}")
    print(f"  {CYAN}settings{RESET}            — показать")
    print(f"  {CYAN}settings quiet|gamemode|debug on|off{RESET}")
    print(f"  {CYAN}quiet{RESET}               — тихий режим")
    print(f"{BOLD}Отладка:{RESET}")
    print(f"  {CYAN}debug{RESET}               — статус")
    print(f"  {CYAN}debug on|off{RESET}       — вкл/выкл")
    print(f"  {CYAN}debugreport{RESET}         — архив логов")
    print(f"{BOLD}Прочее:{RESET}")
    print(f"  {CYAN}history{RESET}, {CYAN}log{RESET}         — история / последний лог")
    print(f"  {CYAN}export{RESET}              — экспорт истории и настроек")
    print(f"  {CYAN}gpu-temp{RESET}            — температура и загрузка GPU")
    print(f"  {CYAN}freegames{RESET}           — каталог бесплатных игр")
    print(f"  {CYAN}help{RESET}, {CYAN}?{RESET}             — эта справка")
    print(f"  {CYAN}exit{RESET}, {CYAN}q{RESET}             — выход")
    print()


def check_all_commands():
    try:
        import inspect
        src = inspect.getsource(process_input)
        missing = []
        for cmd in EXPECTED_COMMANDS:
            if cmd not in src:
                missing.append(cmd)
        if missing:
            warn(f"Потеряны команды: {missing}")
        else:
            debug.dbg(f"Все {len(EXPECTED_COMMANDS)} команд обрабатываются")
    except Exception as e:
        debug.dbg_exc(e, "check_all_commands")


def process_input(name, last_exe):
    low = name.lower().strip()
    if not low:
        return last_exe, True
    if low in ("exit", "quit", "q", "выход"):
        return last_exe, False
    if low in ("help", "?", "помощь", "справка"):
        print_help()
        return last_exe, True
    if low.startswith("settings") or low.startswith("настройки"):
        args = name.split(maxsplit=1)[1] if " " in name else ""
        cmd_settings(args)
        return last_exe, True
    if low.startswith("debug") and low != "debugreport":
        args = name.split(maxsplit=1)[1] if " " in name else ""
        cmd_debug(args)
        return last_exe, True
    if low in ("debugreport", "отладка"):
        cmd_debugreport()
        return last_exe, True
    if low in ("export", "экспорт"):
        cmd_export(name.split(maxsplit=1)[1] if " " in name else "")
        return last_exe, True
    if low in ("gpu-temp", "gtemp", "темп"):
        cmd_gpu_temp()
        return last_exe, True
    if low in ("freegames", "free", "free-games", "фри"):
        cmd_free_games()
        return last_exe, True
    if low in ("install-java", "java"):
        cmd_install_java()
        return last_exe, True
    if low in ("bin", "утилиты"):
        cmd_bin()
        return last_exe, True
    if low in ("verify", "проверка"):
        cmd_verify()
        return last_exe, True
    if low in ("update", "обновить"):
        cmd_update()
        return last_exe, True
    if low in ("history", "история"):
        show_history_menu()
        return last_exe, True
    if low in ("quiet", "тихо"):
        state.QUIET_MODE = not state.QUIET_MODE
        s = load_settings()
        s["quiet_mode"] = state.QUIET_MODE
        save_settings(s)
        ok(f"Тихий режим {'вкл' if state.QUIET_MODE else 'выкл'}")
        return last_exe, True
    if low in ("reset", "сброс"):
        cmd_reset()
        return last_exe, True
    if low == "dxvk":
        from modules.wine import cmd_dxvk
        cmd_dxvk()
        return last_exe, True
    if low in ("vulkan", "вулкан"):
        cmd_vulkan()
        return last_exe, True
    if low in ("fonts", "шрифты"):
        cmd_fonts()
        return last_exe, True
    if low == "gamemode":
        cmd_gamemode()
        return last_exe, True
    if low in ("log", "лог"):
        cmd_log()
        return last_exe, True
    if low in ("minecraft", "майнкрафт"):
        cmd_minecraft()
        return last_exe, True
    if low in ("minecraft fo", "майнкрафт fo", "fo"):
        setup_fabulously_optimized()
        return last_exe, True
    if low in ("minecraft optifine", "майнкрафт optifine", "optifine", "оф"):
        setup_optifine()
        return last_exe, True
    if low in ("minecraft prism", "майнкрафт prism", "prism"):
        setup_prism()
        return last_exe, True
    if low in ("minecraft legacy", "майнкрафт legacy", "legacy"):
        setup_legacy()
        return last_exe, True
    if low in ("saveworlds", "сохранитьмиры", "миры на диск", "worlds-save"):
        cmd_save_worlds()
        return last_exe, True
    if low in ("loadworlds", "загрузитьмиры", "миры с диска", "worlds-load"):
        cmd_load_worlds()
        return last_exe, True
    if low in ("worlds", "миры", "дискd", "диск d"):
        cmd_worlds_menu()
        return last_exe, True
    if low in ("desktop", "ярлык"):
        warn("desktop <имя.exe>")
        return last_exe, True
    if (low.startswith("desktop ") or low.startswith("ярлык ")) and not name.startswith("/"):
        parts = name.split(maxsplit=1)
        if len(parts) == 2:
            cmd_desktop(parts[1])
        return last_exe, True
    if low.startswith("steamfix ") and not name.startswith("/"):
        parts = name.split(maxsplit=1)
        if len(parts) == 2:
            cmd_steamfix(parts[1])
        return last_exe, True
    if low.startswith("download ") or low.startswith("скачать "):
        parts = name.split(maxsplit=1)
        if len(parts) == 2:
            cmd_download(parts[1].strip())
        return last_exe, True
    if low == "!!":
        if not last_exe:
            warn("Нет истории")
            return last_exe, True
        path = Path(last_exe)
        if not path.exists():
            err(f"Файл не существует: {path}")
            return last_exe, True
        launch(path)
        return str(path), True
    if low.isdigit():
        data = load_history()
        games = data.get("games", [])
        num = int(low)
        if 1 <= num <= len(games):
            path = Path(games[num - 1]["path"])
            if not path.exists():
                err(f"Файл не существует: {path}")
                return last_exe, True
            launch(path)
            return str(path), True
        err(f"Нет игры #{num}")
        return last_exe, True
    info(f"Ищу '{name}'...")
    results = find_exe(name)
    if not results:
        err(f"'{name}' не найден.")
        return last_exe, True
    if len(results) == 1:
        chosen = results[0]
    else:
        for i, r in enumerate(results, 1):
            print(f"  {i}) {r}")
        try:
            idx = int(input("Номер: ").strip()) - 1
            if 0 <= idx < len(results):
                chosen = results[idx]
            else:
                err("Неверный номер")
                return last_exe, True
        except (ValueError, KeyboardInterrupt):
            err("Отменено")
            return last_exe, True
    launch(chosen)
    return str(chosen), True


def print_diagnostics():
    sep()
    info(f"{BOLD}Диагностика системы{RESET}")
    print()
    items = [
        ("Wine AppImage", WINE_BIN.exists(),
         f"{WINE_BIN.stat().st_size//1024//1024 if WINE_BIN.exists() else 0} МБ"),
        ("DXVK", DXVK_DIR.exists(), ""),
        ("Префикс", (WINE_PREFIX / "drive_c").exists(), ""),
        ("winetricks", WINETRICKS_BIN.exists(),
         f"{WINETRICKS_BIN.stat().st_size//1024 if WINETRICKS_BIN.exists() else 0} КБ"),
        ("aria2c", ARIA2C_BIN.exists(),
         f"{ARIA2C_BIN.stat().st_size//1024//1024 if ARIA2C_BIN.exists() else 0} МБ"),
    ]
    for name, exists, extra in items:
        if exists:
            ok(f"{name}: {extra}" if extra else f"{name}: OK")
        else:
            if name == "Префикс":
                hint(f"{name}: не создан (появится при первом запуске игры)")
            else:
                warn(f"{name}: отсутствует")
    java_bin, java_home, java_status = find_java()
    if java_home:
        ok(f"Java GUI: {java_home}")
    else:
        warn(f"Java: {java_status}")
        hint(f"Хочешь поставить OptiFine? Введи: {CYAN}install-java{RESET}")
    if state.DEBUG_MODE:
        ok(f"Дебаг: включён → {DEBUG_LOG}")
    print()


def main():
    # ASCII-арт из ascii-art.txt
    print_art(CYAN)
    print(f"{BLUE}╔══════════════════════════════════════════════════╗")
    print(f"║  Wine Installer + Game Launcher  v{CURRENT_VERSION}            ║")
    print("║  Wine + DXVK + Minecraft + Debug + JDK           ║")
    print(f"╚══════════════════════════════════════════════════╝{RESET}\n")

    # Ротация старых логов
    try:
        rotate_old_logs()
    except Exception:
        pass

    # Tab-автодополнение путей
    _setup_readline()

    debug.dbg("=" * 60)
    debug.dbg(f"ЗАПУСК v{CURRENT_VERSION}, DEBUG={state.DEBUG_MODE}, argv={sys.argv}")
    apply_settings()
    check_all_commands()
    if state.DEBUG_MODE:
        info(f"Дебаг включён → {DEBUG_LOG}")
        print()
    if not check_disk_space():
        sys.exit(1)
    ensure_bin_tools()
    create_runexe()
    if not (WINE_BIN.exists() and os.access(WINE_BIN, os.X_OK)):
        sep()
        info(f"{BOLD}Скачиваю Wine...{RESET}")
        if not download_wine():
            err("Wine не скачался")
            sys.exit(1)
    if not (DXVK_DIR.exists() and (DXVK_DIR / "x64").exists()):
        sep()
        info(f"{BOLD}Скачиваю DXVK...{RESET}")
        download_dxvk()
    sep()
    info("Проверяю Wine...")
    try:
        result = subprocess.run([str(WINE_BIN), "--version"], env=get_wine_env(),
                                capture_output=True, text=True, timeout=30)
        out = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "wine" in out.lower():
            ok(f"Wine: {out.splitlines()[0]}")
        else:
            err("Wine не отвечает")
            sys.exit(1)
    except Exception as e:
        debug.dbg_exc(e, "main/wine-version")
        err(f"Wine: {e}")
        sys.exit(1)
    print_diagnostics()
    print_help()
    sep()
    print(f"{GREEN}Готово!{RESET} Пиши игру или команду.")
    if state.DEBUG_MODE:
        hint("Дебаг вкл. При проблеме: `debugreport`")
    print()
    last_exe = load_history().get("last_game")
    while True:
        show_history_menu()
        try:
            name = input(f"{YELLOW}Игра > {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        try:
            last_exe, cont = process_input(name, last_exe)
        except KeyboardInterrupt:
            print()
            continue
        except Exception as e:
            debug.dbg_exc(e, "main/process_input")
            err(f"Ошибка: {e}")
            continue
        if not cont:
            break
        print()
    print(f"\n{GREEN}Пока!{RESET}")
    debug.dbg("Завершение")


def check_disk_space():
    import shutil
    try:
        stat = shutil.disk_usage(HOME)
        free_gb = stat.free / 1024 / 1024 / 1024
        debug.dbg(f"Свободно {free_gb:.2f} ГБ")
        if free_gb < 1:
            err(f"Мало места: {free_gb:.2f} ГБ")
            return False
        return True
    except Exception as e:
        debug.dbg_exc(e, "check_disk_space")
        return True


def ensure_bin_tools():
    try:
        has_wt = WINETRICKS_BIN.exists() and WINETRICKS_BIN.stat().st_size > 100 * 1024
        has_ar = ARIA2C_BIN.exists() and ARIA2C_BIN.stat().st_size > 500 * 1024
    except OSError as e:
        debug.dbg_exc(e, "ensure_bin_tools/stat")
        warn(f"Не могу проверить утилиты ({e}) — пропускаю автозагрузку")
        return
    if not has_wt or not has_ar:
        info(f"{BOLD}Проверка утилит...{RESET}")
        if not has_wt:
            download_winetricks()
        if not has_ar:
            download_aria2c()


def download_aria2c():
    import tarfile
    import shutil as sh
    if ARIA2C_BIN.exists() and ARIA2C_BIN.stat().st_size > MIN_ARIA2C_SIZE:
        return True
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    info("Скачиваю aria2c...")
    archive = None
    success = False
    for name, url in ARIA2C_MIRRORS:
        debug.dbg(f"aria2c: {name}")
        if url.endswith(".tar.gz"):
            archive = BIN_DIR / "aria2.tar.gz"
        elif url.endswith(".tar.bz2"):
            archive = BIN_DIR / "aria2.tar.bz2"
        else:
            continue
        if archive.exists():
            try:
                archive.unlink()
            except Exception:
                pass
        if try_download_manual(name, url, archive, silent=False):
            if archive.exists() and archive.stat().st_size > MIN_ARIA2C_SIZE:
                success = True
                break
    if not success or archive is None:
        err("aria2c не скачался")
        return False
    try:
        tmp_dir = BIN_DIR / "aria2_extract"
        if tmp_dir.exists():
            sh.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)
        if archive.name.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(tmp_dir)
        elif archive.name.endswith(".tar.bz2"):
            with tarfile.open(archive, "r:bz2") as tar:
                tar.extractall(tmp_dir)
        found = False
        for f in tmp_dir.rglob("aria2c"):
            if f.is_file():
                sh.copy2(f, ARIA2C_BIN)
                ARIA2C_BIN.chmod(0o755)
                found = True
                break
        sh.rmtree(tmp_dir, ignore_errors=True)
        try:
            archive.unlink()
        except Exception:
            pass
        if found:
            ok("aria2c установлен")
            return True
        err("В архиве нет aria2c")
        return False
    except Exception as e:
        debug.dbg_exc(e, "download_aria2c/extract")
        err(f"Распаковка: {e}")
        return False
