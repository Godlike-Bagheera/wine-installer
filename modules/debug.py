"""Логирование в debug.log + ротация старых логов."""
import time
import traceback
from modules import state
from modules.config import DEBUG_LOG, LOG_DIR, LOG_KEEP_DAYS


def dbg(msg, level="INFO"):
    if not state.DEBUG_MODE:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] [{level}] {msg}\n")
    except Exception:
        pass


def dbg_exc(e, context=""):
    if not state.DEBUG_MODE:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{stamp}] [ERROR] {context}: {e}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


def rotate_old_logs():
    """Удаляет игровые логи старше LOG_KEEP_DAYS дней."""
    if not LOG_DIR.exists():
        return
    cutoff = time.time() - LOG_KEEP_DAYS * 86400
    removed = 0
    for f in LOG_DIR.glob("*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    if removed > 0:
        # Локальный импорт — colors тянет debug, обходим циклический импорт
        from modules.colors import hint
        hint(f"Очищено {removed} старых логов (>{LOG_KEEP_DAYS} дней)")
