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
from modules.launcher import (
    launch, find_exe, stop_all_games,
    cmd_game_status, cmd_stopgame, cmd_waitgame, cmd_games_list,
)
from modules.java import find_java, cmd_install_java
from modules.minecraft import (
    cmd_minecraft, setup_fabulously_optimized, setup_optifine,
    setup_prism, setup_legacy, cmd_fo_autofix,
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
from modules import gamestate
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
    # Динамическая рамка: ширина считается от содержимого, не «едет» при v2.10+
    title = f"  Команды v{CURRENT_VERSION}"
    width = max(len(title), len("  Wine Installer + Game Launcher")) + 2
    border = "═" * width
    print(f"{BOLD}╔{border}╗")
    print(f"║{title.ljust(width)}║")
    print(f"╚{border}╝{RESET}")
    print(f"{BOLD}── Игры ──────────────────────────────────────────{RESET}")
    print(f"  {CYAN}<имя.exe>{RESET}         — запустить игру")
    print(f"  {CYAN}<номер>{RESET}             — из истории")
    print(f"  {CYAN}!!{RESET}                  — последнюю игру")
    print(f"  {CYAN}desktop <имя.exe>{RESET}  — ярлык на рабочем столе")
    print(f"  {CYAN}download <URL>{RESET}     — скачать/распаковать архив")
    print(f"{BOLD}── Фоновые игры ──────────────────────────────────{RESET}")
    print(f"  {CYAN}gamestatus{RESET}           — активные игры (pid, время)")
    print(f"  {CYAN}games{RESET}                — история + активные")
    print(f"  {CYAN}stopgame <имя|all>{RESET} — остановить игру(ы)")
    print(f"  {CYAN}waitgame <имя>{RESET}      — дождаться выхода из игры")
    print(f"{BOLD}── Minecraft ─────────────────────────────────────{RESET}")
    print(f"  {CYAN}minecraft{RESET}            — меню (все варианты)")
    print(f"  {CYAN}fo{RESET}                   — Fabulously Optimized")
    print(f"  {CYAN}fo-autofix{RESET}           — диагностика/починка .minecraft")
    print(f"  {CYAN}optifine{RESET}             — OptiFine")
    print(f"  {CYAN}prism{RESET}                — Prism Launcher")
    print(f"  {CYAN}legacy{RESET}               — Legacy Launcher")
    print(f"  {CYAN}shaders{RESET}              — установить шейдер-пак (shaderpacks)")
    print(f"  {CYAN}shaders <URL>{RESET}       — пак по прямой ссылке (.zip)")
    print(f"  {CYAN}install-java{RESET}         — портативная JDK 17")
    print(f"{BOLD}── Миры (Диск D, RED OS) ─────────────────────────{RESET}")
    print(f"  {CYAN}worlds{RESET}              — меню миров (диск D)")
    print(f"  {CYAN}saveworlds{RESET}          — сохранить миры на Диск D")
    print(f"  {CYAN}loadworlds{RESET}          — загрузить миры с Диска D")
    print(f"{BOLD}── Утилиты ───────────────────────────────────────{RESET}")
    print(f"  {CYAN}fonts{RESET}               — corefonts")
    print(f"  {CYAN}steamfix <имя.exe>{RESET} — заглушка steam_api.dll")
    print(f"  {CYAN}gamemode{RESET}            — GameMode вкл/выкл")
    print(f"  {CYAN}vulkan{RESET}              — проверка Vulkan")
    print(f"  {CYAN}verify{RESET}              — целостность")
    print(f"  {CYAN}update{RESET}              — переустановить Wine/DXVK")
    print(f"  {CYAN}dxvk{RESET}                — только DXVK")
    print(f"  {CYAN}reset{RESET}               — удалить префикс")
    print(f"  {CYAN}bin{RESET}                 — содержимое bin/")
    print(f"{BOLD}── Настройки ─────────────────────────────────────{RESET}")
    print(f"  {CYAN}settings{RESET}            — показать")
    print(f"  {CYAN}settings quiet|gamemode|debug on|off{RESET}")
    print(f"  {CYAN}quiet{RESET}               — тихий режим")
    print(f"{BOLD}── Отладка ───────────────────────────────────────{RESET}")
    print(f"  {CYAN}debug{RESET}               — статус")
    print(f"  {CYAN}debug on|off{RESET}       — вкл/выкл")
    print(f"  {CYAN}debugreport{RESET}         — архив логов")
    print(f"{BOLD}── Прочее ────────────────────────────────────────{RESET}")
    print(f"  {CYAN}history{RESET}, {CYAN}log{RESET}         — история / последний лог")
    print(f"  {CYAN}help{RESET}, {CYAN}?{RESET}             — эта справка")
    print(f"  {CYAN}exit{RESET}, {CYAN}q{RESET}             — выход (игры остановятся)")
    print(f"{BOLD}── Дополнительно ────────────────────────────────{RESET}")
    print(f"  {CYAN}export{RESET}              — экспорт истории и настроек")
    print(f"  {CYAN}gpu-temp{RESET}            — температура и загрузка GPU")
    print(f"  {CYAN}freegames{RESET}           — каталог бесплатных игр")
    print()


def check_all_commands():
    """EXPECTED_COMMANDS против реестра COMMAND_REGISTRY/ARGS_COMMANDS.

    Сверка по данным, а не по исходнику process_input (антипаттерн с
    inspect.getsource убран): каждая ожидаемая команда должна быть ключом
    одного из двух реестров.
    """
    try:
        missing = [c for c in EXPECTED_COMMANDS
                   if c not in COMMAND_REGISTRY and c not in ARGS_COMMANDS]
        if missing:
            warn(f"Потеряны команды: {missing}")
        else:
            debug.dbg(f"Все {len(EXPECTED_COMMANDS)} команд обрабатываются")
    except Exception as e:
        debug.dbg_exc(e, "check_all_commands")


# ─────────────────────────────────────────────────────────────────────
#  РЕЕСТР КОМАНД (dict вместо цепочки if/elif):
#  нормализованное имя/синоним -> handler.
#  Точные команды — в COMMAND_REGISTRY; команды с аргументом — в ARGS_COMMANDS
#  (ключ в начале строки, хвост передаётся аргументом).
#  check_all_commands и тесты сверяют с этим реестром EXPECTED_COMMANDS —
#  без inspect.getsource(process_input).
#  ВАЖНО: handlers берутся по имени модуля (ui.cmd_stopgame(...)), а не по
#  прямой ссылке — тогда monkeypatch в тестах продолжает работать.
# ─────────────────────────────────────────────────────────────────────
COMMAND_REGISTRY = {
    # ── точные команды (без аргумента) ──
    "help": print_help, "?": print_help,
    "помощь": print_help, "справка": print_help,
    "debugreport": cmd_debugreport, "отладка": cmd_debugreport,
    "games": lambda a="": cmd_games_list(), "игры": lambda a="": cmd_games_list(),
    "minecraft": lambda a="": cmd_minecraft(), "майнкрафт": lambda a="": cmd_minecraft(),
    "fo": lambda a="": setup_fabulously_optimized(),
    "майнкрафт fo": lambda a="": setup_fabulously_optimized(),
    "minecraft fo": lambda a="": setup_fabulously_optimized(),
    "fo-autofix": lambda a="": cmd_fo_autofix(), "foautofix": lambda a="": cmd_fo_autofix(),
    "фо-автофикс": lambda a="": cmd_fo_autofix(), "автофикс": lambda a="": cmd_fo_autofix(),
    "optifine": lambda a="": setup_optifine(), "оф": lambda a="": setup_optifine(),
    "майнкрафт optifine": lambda a="": setup_optifine(),
    "minecraft optifine": lambda a="": setup_optifine(),
    "prism": lambda a="": setup_prism(), "майнкрафт prism": lambda a="": setup_prism(),
    "minecraft prism": lambda a="": setup_prism(),
    "legacy": lambda a="": setup_legacy(), "майнкрафт legacy": lambda a="": setup_legacy(),
    "minecraft legacy": lambda a="": setup_legacy(),
    "saveworlds": lambda a="": cmd_save_worlds(), "сохранитьмиры": lambda a="": cmd_save_worlds(),
    "миры на диск": lambda a="": cmd_save_worlds(), "worlds-save": lambda a="": cmd_save_worlds(),
    "loadworlds": lambda a="": cmd_load_worlds(), "загрузитьмиры": lambda a="": cmd_load_worlds(),
    "миры с диска": lambda a="": cmd_load_worlds(), "worlds-load": lambda a="": cmd_load_worlds(),
    "worlds": lambda a="": cmd_worlds_menu(), "миры": lambda a="": cmd_worlds_menu(),
    "дискd": lambda a="": cmd_worlds_menu(), "диск d": lambda a="": cmd_worlds_menu(),
    "fonts": lambda a="": cmd_fonts(), "шрифты": lambda a="": cmd_fonts(),
    "gamemode": lambda a="": cmd_gamemode(),
    "vulkan": lambda a="": cmd_vulkan(), "вулкан": lambda a="": cmd_vulkan(),
    "verify": lambda a="": cmd_verify(), "проверка": lambda a="": cmd_verify(),
    "update": lambda a="": cmd_update(), "обновить": lambda a="": cmd_update(),
    "history": lambda a="": show_history_menu(), "история": lambda a="": show_history_menu(),
    "reset": lambda a="": cmd_reset(), "сброс": lambda a="": cmd_reset(),
    "log": lambda a="": cmd_log(), "лог": lambda a="": cmd_log(),
    "bin": lambda a="": cmd_bin(), "утилиты": lambda a="": cmd_bin(),
    "install-java": lambda a="": cmd_install_java(), "java": lambda a="": cmd_install_java(),
    "gpu-temp": lambda a="": cmd_gpu_temp(), "gtemp": lambda a="": cmd_gpu_temp(),
    "темп": lambda a="": cmd_gpu_temp(),
    "freegames": lambda a="": cmd_free_games(), "free": lambda a="": cmd_free_games(),
    "free-games": lambda a="": cmd_free_games(), "фри": lambda a="": cmd_free_games(),
    "gamestatus": lambda a="": cmd_game_status(),
    "состояниеигр": lambda a="": cmd_game_status(),
    "статусигр": lambda a="": cmd_game_status(),
    "dxvk": lambda a="": _cmd_dxvk(),
    "quiet": lambda a="": _cmd_quiet(), "тихо": lambda a="": _cmd_quiet(),
}


def _cmd_dxvk():
    from modules.wine import cmd_dxvk
    cmd_dxvk()


def _cmd_quiet():
    state.QUIET_MODE = not state.QUIET_MODE
    s = load_settings()
    s["quiet_mode"] = state.QUIET_MODE
    save_settings(s)
    ok(f"Тихий режим {'вкл' if state.QUIET_MODE else 'выкл'}")


# Команды с аргументом: ключ в начале строки, хвост — аргумент handler'у.
ARGS_COMMANDS = {
    "settings": cmd_settings, "настройки": cmd_settings,
    "debug": cmd_debug,
    "stopgame": cmd_stopgame, "остановитьигру": cmd_stopgame, "стопигра": cmd_stopgame,
    "waitgame": cmd_waitgame, "ждатьигру": cmd_waitgame,
    "shaders": cmd_shaders, "шейдеры": cmd_shaders, "шейдер": cmd_shaders,
    "export": cmd_export, "экспорт": cmd_export,
    "desktop": cmd_desktop, "ярлык": cmd_desktop,
    "steamfix": cmd_steamfix,
    "download": cmd_download, "скачать": cmd_download,
}

# Выход из REPL
EXIT_COMMANDS = ("exit", "quit", "q", "выход")


def resolve_command(low):
    """(handler, arg) по нормализованной строке ввода или (None, None)."""
    if low in COMMAND_REGISTRY:
        return COMMAND_REGISTRY[low], ""
    for key in ARGS_COMMANDS:
        if low == key or low.startswith(key + " "):
            return ARGS_COMMANDS[key], low[len(key):].strip()
    # префиксные exact-команды (как в прежнем startswith-разборе)
    for key in ("gamestatus", "состояниеигр", "статусигр"):
        if low.startswith(key):
            return COMMAND_REGISTRY[key], ""
    # русские синонимы могут быть написаны слитно с аргументом: "стопигра mine"
    nospace = low.replace(" ", "")
    for key in ("остановитьигру", "стопигра", "ждатьигру"):
        if nospace.startswith(key) and len(nospace) > len(key):
            idx = low.find(key)
            tail = low[idx + len(key):]
            if tail.startswith(" "):
                tail = tail[1:]
            else:
                tail = tail.strip()
            return ARGS_COMMANDS[key], tail
    return None, None


def process_input(name, last_exe):
    low = name.lower().strip()
    if not low:
        return last_exe, True
    if low in EXIT_COMMANDS:
        return last_exe, False
    handler, args = resolve_command(low)
    if handler is not None:
        # desktop/steamfix раньше требовали, что строка НЕ начинается с "/":
        # «/home/user/desktop game.exe» — это путь к игре, а не команда.
        first = low.split(maxsplit=1)[0] if low else ""
        if first in ("desktop", "ярлык", "steamfix") and name.startswith("/"):
            pass  # падаем в поиск игры ниже
        elif low in ("desktop", "ярлык") and not args:
            warn("desktop <имя.exe>")
            return last_exe, True
        else:
            handler(args)
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
    title1 = f"  Wine Installer + Game Launcher  v{CURRENT_VERSION}"
    title2 = "  Wine + DXVK + Minecraft + Debug + JDK"
    width = max(len(title1), len(title2)) + 2
    border = "═" * width
    print(f"{BLUE}╔{border}╗")
    print(f"║{title1.ljust(width)}║")
    print(f"║{title2.ljust(width)}║")
    print(f"╚{border}╝{RESET}\n")

    # Настройки → state.* ДО ротации: LOG_KEEP_DAYS и QUIET_MODE уже действуют
    apply_settings()

    # Ротация старых логов (живой debug.log защищён внутри rotate_old_logs)
    try:
        rotate_old_logs()
    except Exception as e:
        debug.dbg_exc(e, "rotate_old_logs")

    # Tab-автодополнение путей
    _setup_readline()

    debug.dbg("=" * 60)
    debug.dbg(f"ЗАПУСК v{CURRENT_VERSION}, DEBUG={state.DEBUG_MODE}, argv={sys.argv}")
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
        # Статус активных фоновых игр над приглашением
        active = gamestate.running()
        for line in gamestate.status_lines():
            print(line)
        prompt = (f"{YELLOW}Игра [{len(active)} игр(ы) в фоне]> {RESET}"
                  if active else f"{YELLOW}Игра > {RESET}")
        try:
            name = input(prompt).strip()
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
    # Exit-guard: при выходе останавливаем все активные фоновые игры
    try:
        stop_all_games()
    except Exception as e:
        debug.dbg_exc(e, "main/stop_all_games")
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
