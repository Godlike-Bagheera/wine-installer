"""settings.json, history.json."""
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from modules import state, debug
from modules.config import (
    SETTINGS_FILE, HISTORY_FILE, DEFAULT_SETTINGS,
)
from modules.colors import GREEN, RED, DIM, CYAN, BOLD, RESET


@contextmanager
def _file_lock(target):
    """Простой advisory-лок через O_EXCL (для history.json).

    Не даёт двум процессам лаунчера перезаписать файл друг друга.
    Лок валиден только внутри одного хоста; stale-локи старше 30 с
    считаются брошенными и снимаются. При любой ошибке лочения работаем
    без лока (best effort — данные важнее блокировки).
    """
    lock = target.with_name(target.name + ".lock")
    fd = None
    deadline = time.time() + 5.0
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 30:
                        lock.unlink()      # stale-лок от упавшего процесса
                        continue
                except OSError:
                    break                  # не наш хост/права — работаем без лока
                if time.time() >= deadline:
                    debug.dbg(f"file_lock: таймаут ожидания {lock}", level="WARN")
                    break
                time.sleep(0.1)
    except OSError as e:
        debug.dbg_exc(e, f"file_lock/{target.name}")
    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
                lock.unlink()
            except OSError:
                pass


def _atomic_write_text(target, text):
    """Атомарная запись: во временный файл в той же папке + os.replace."""
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)   # атомарна в пределах одной ФС


def load_settings():
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        debug.dbg_exc(e, "load_settings")
        return dict(DEFAULT_SETTINGS)


def save_settings(data):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(
            SETTINGS_FILE,
            json.dumps(data, ensure_ascii=False, indent=2),
        )
    except Exception as e:
        debug.dbg_exc(e, "save_settings")


def apply_settings():
    s = load_settings()
    state.QUIET_MODE = s.get("quiet_mode", False)
    if s.get("debug_mode", False) and not state.DEBUG_MODE:
        state.DEBUG_MODE = True
        debug.dbg("Дебаг включён из настроек")


def load_history():
    if not HISTORY_FILE.exists():
        return {"games": [], "last_game": None}
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        data.setdefault("games", [])
        data.setdefault("last_game", None)
        return data
    except Exception as e:
        debug.dbg_exc(e, "load_history")
        return {"games": [], "last_game": None}


def save_history(data):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _file_lock(HISTORY_FILE):
            _atomic_write_text(
                HISTORY_FILE,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
    except Exception as e:
        debug.dbg_exc(e, "save_history")


def update_history(exe_path, status=None, duration=None):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _file_lock(HISTORY_FILE):
            data = load_history()
            path_str = str(exe_path)
            found = False
            for g in data["games"]:
                if g.get("path") == path_str:
                    g["count"] = g.get("count", 0) + 1
                    g["last"] = time.time()
                    if status:
                        g["status"] = status
                    if duration:
                        g["total_seconds"] = g.get("total_seconds", 0) + duration
                    found = True
                    break
            if not found:
                data["games"].append({
                    "path": path_str, "count": 1, "last": time.time(),
                    "status": status or "unknown",
                    "total_seconds": int(duration or 0),
                })
            data["last_game"] = path_str
            data["games"].sort(key=lambda g: (-g.get("count", 0), -g.get("last", 0)))
            data["games"] = data["games"][:15]
            _atomic_write_text(
                HISTORY_FILE,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
    except Exception as e:
        debug.dbg_exc(e, "update_history")


def show_history_menu():
    data = load_history()
    games = data.get("games", [])
    if not games:
        return
    print(f"{BOLD}История запусков:{RESET}")
    for i, g in enumerate(games, 1):
        p = Path(g["path"])
        last = g.get("last", 0)
        status = g.get("status", "unknown")
        total_sec = g.get("total_seconds", 0)
        status_icon = {"ok": f"{GREEN}✓{RESET}", "crash": f"{RED}✗{RESET}"}.get(status, " ")
        when = ""
        if last:
            delta = time.time() - last
            if delta < 3600:
                when = f"{int(delta/60)} мин назад"
            elif delta < 86400:
                when = f"{int(delta/3600)} ч назад"
            else:
                when = f"{int(delta/86400)} дн назад"
        time_str = f" {DIM}[{int(total_sec//60)}м]{RESET}" if total_sec >= 60 else ""
        print(f"  {CYAN}{i:2d}{RESET}) {status_icon} {p.name} {DIM}({when}){RESET}{time_str}")
    print()
