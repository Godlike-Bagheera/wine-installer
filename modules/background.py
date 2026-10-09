"""Фоновый (неблокирующий) режим запуска игр.

Игра запускается через subprocess.Popen, терминал лаунчера остаётся
доступным для команд. Модуль хранит активные процессы и даёт команды:
    gamestatus / stopgame / waitgame / games

Exit-guard: при выходе из скрипта (sys.exit, EOF, исключение в main_loop)
активные игры корректно останавливаются (terminate -> kill), чтобы не
оставлять «сирот».

Также здесь живёт патч запускающих функций: оригинальный launch() блокирует
меню до конца игры (proc.wait). В фоновом режиме запуск возвращает управление
максимум за ~10 секунд вместо ожидания всей сессии игры.
"""
import time
import atexit
import threading
import subprocess
from pathlib import Path

from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, BOLD, RESET

# Максимум секунд, которые мы «смотрим» на старт игры, прежде чем отдать
# управление меню. Живая игра больше не блокирует меню на 25+ секунд.
STARTUP_WATCH_SECONDS = 10.0

# Все фоновые процессы: {pid: {"proc": Popen, "name": str, "started": float}}
_processes = {}
_lock = threading.Lock()
_guard_installed = False


def _reap_finished():
    """Убирает из списка уже завершившиеся процессы (вызывать под локом)."""
    finished = []
    for pid, rec in list(_processes.items()):
        try:
            if rec["proc"].poll() is not None:
                finished.append(pid)
        except Exception:
            finished.append(pid)
    for pid in finished:
        _processes.pop(pid, None)


def register(proc, name):
    """Регистрирует активный процесс как фоновую игру."""
    with _lock:
        _processes[proc.pid] = {
            "proc": proc,
            "name": name,
            "started": time.time(),
        }
    install_exit_guard()
    debug.dbg(f"background: registered pid={proc.pid} name={name}")


def active_processes():
    """Список живых фоновых процессов [(pid, name, uptime_s)]."""
    with _lock:
        _reap_finished()
        now = time.time()
        return [(pid, rec["name"], now - rec["started"])
                for pid, rec in sorted(_processes.items())]


def has_active_game():
    return bool(active_processes())


def stop_all(timeout=5.0):
    """Корректно останавливает все активные игры: terminate, затем kill."""
    stopped_one = False
    with _lock:
        items = list(_processes.items())
    for pid, rec in items:
        proc = rec["proc"]
        name = rec.get("name", f"pid {pid}")
        if proc.poll() is not None:
            continue
        info(f"Останавливаю '{name}' (pid {pid})...")
        try:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                warn(f"'{name}' не закрылась — убиваю.")
                proc.kill()
                proc.wait(timeout=timeout)
            stopped_one = True
            ok(f"'{name}' остановлена.")
        except Exception as e:
            debug.dbg_exc(e, f"stop_all/{pid}")
            # Всё равно пробуем добить
            try:
                proc.kill()
            except Exception:
                pass
    with _lock:
        _reap_finished()
    return stopped_one


def install_exit_guard():
    """Ставит atexit-хук: при выходе из скрипта активная игра останавливается."""
    global _guard_installed
    if _guard_installed:
        return
    _guard_installed = True

    def _guard():
        try:
            if _processes:
                debug.dbg(f"exit-guard: останавливаю {len(_processes)} игру(игр)")
                stop_all()
        except Exception as e:
            debug.dbg_exc(e, "exit_guard")

    atexit.register(_guard)
    debug.dbg("exit-guard installed")


def patch_blocking_launchers():
    """Делает запускающие функции неблокирующими (Popen вместо proc.wait()).

    Идемпотентно: повторный вызов ничего не делает. Патчится launcher.launch
    так, что после старта процесса он регистрируется в фоне, а наблюдение за
    первыми секундами работы ограничено STARTUP_WATCH_SECONDS (не 25+).
    Возвращает True, если патч применён/уже применён."""
    if getattr(patch_blocking_launchers, "_done", False):
        return True
    try:
        from modules import launcher as _launcher_mod
    except Exception as e:  # pragma: no cover
        debug.dbg_exc(e, "patch_blocking_launchers")
        return False

    original_launch = _launcher_mod.launch

    def background_launch(path):
        """Неблокирующий запуск: стартует игру и возвращает управление меню."""
        path = Path(path)
        try:
            from modules.prefix import ensure_prefix, get_wine_env
            env = get_wine_env(exe_path=path)
            ensure_prefix(exe_path=path)
            cmd = _launcher_mod._build_cmd(path, use_gm=False)
            logf = open(_launcher_mod.get_log_path(path), "w", encoding="utf-8",
                        errors="replace")
            proc = subprocess.Popen(
                cmd, cwd=str(path.parent), env=env,
                stdout=logf, stderr=subprocess.STDOUT,
            )
            register(proc, path.stem)
            _launcher_mod.update_history(path, status="ok", duration=0)
            ok(f"Игра '{path.stem}' запущена в фоне (pid {proc.pid}).")
            hint("Команды: gamestatus, stopgame, waitgame, games")
            # Короткое наблюдение: если упала мгновенно — покажем хвост лога,
            # но НЕ ждём дольше STARTUP_WATCH_SECONDS.
            deadline = time.time() + STARTUP_WATCH_SECONDS
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
            if proc.poll() is not None and proc.returncode != 0:
                warn(f"Похоже, игра упала сразу (код {proc.returncode}).")
                _launcher_mod.show_log(_launcher_mod.get_log_path(path), lines=15)
            return proc
        except Exception as e:
            debug.dbg_exc(e, "background_launch")
            err(f"Фоновый запуск не удался ({e}) — пробую обычный режим.")
            return original_launch(path)

    _launcher_mod.launch = background_launch
    patch_blocking_launchers._done = True
    patch_blocking_launchers._original = original_launch
    debug.dbg("launch patched to non-blocking (Popen)")
    return True


def unpatch_blocking_launchers():
    """Возвращает исходную блокирующую launch() (для тестов/тихого режима)."""
    original = getattr(patch_blocking_launchers, "_original", None)
    if original is None:
        return False
    from modules import launcher as _launcher_mod
    _launcher_mod.launch = original
    patch_blocking_launchers._done = False
    return True


# ---------- КОМАНДЫ ПОЛЬЗОВАТЕЛЯ ----------

def cmd_gamestatus():
    """gamestatus — показать состояние фоновых игр."""
    print(f"\n{BOLD}═══ СТАТУС ИГР ═══{RESET}")
    procs = active_processes()
    if not procs:
        info("Активных фоновых игр нет.")
        hint("Запусти игру — она уйдёт в фон, терминал останется свободен.")
        return
    for pid, name, uptime in procs:
        mins, secs = divmod(int(uptime), 60)
        print(f"  {CYAN}{name}{RESET}: работает (pid {pid}, {mins}м {secs}с)")


# Алиас: games показывает то же, что и gamestatus (список игр)
cmd_games = cmd_gamestatus


def cmd_stopgame():
    """stopgame — корректно остановить все фоновые игры."""
    procs = active_processes()
    if not procs:
        info("Останавливать нечего — активных игр нет.")
        return
    stopped_one = stop_all()
    if stopped_one:
        ok("Все игры остановлены.")
    else:
        info("Процессы уже завершились сами.")


def cmd_waitgame():
    """waitgame — дождаться завершения фоновых игр (пока они есть)."""
    procs = active_processes()
    if not procs:
        info("Нет активных игр — ждать нечего.")
        return
    info("Жду завершения игр (Ctrl+C — перестать ждать)...")
    try:
        while True:
            with _lock:
                _reap_finished()
                items = list(_processes.values())
            if not items:
                break
            for rec in items:
                try:
                    rec["proc"].wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    break
            time.sleep(0.5)
        ok("Все игры завершились.")
    except KeyboardInterrupt:
        print()
        warn("Больше не жду (игры продолжают работать в фоне).")
