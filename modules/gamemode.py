"""GameMode."""
import shutil
import subprocess
from pathlib import Path
from modules.config import HOME
from modules.colors import ok, warn, hint


def gamemode_available():
    if not shutil.which("gamemoderun"):
        return False
    try:
        r = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=5)
        if "libgamemodeauto.so.0" in r.stdout:
            return True
    except Exception as e:
        debug.dbg_exc(e, "gamemode/gamemode_available")
    for path in ["/usr/lib", "/usr/lib64", "/usr/lib/x86_64-linux-gnu",
                 str(HOME / ".local/share"), "/app/lib"]:
        p = Path(path)
        if p.exists():
            try:
                if list(p.rglob("libgamemodeauto.so*")):
                    return True
            except Exception as e:
                debug.dbg_exc(e, "gamemode/gamemode_available")
    return False


def cmd_gamemode():
    from modules.settings import load_settings, save_settings
    settings = load_settings()
    if not shutil.which("gamemoderun"):
        warn("gamemoderun не найден")
        hint("Установи: flatpak --user install flathub com.feralinteractive.GameMode")
        return
    if not gamemode_available():
        warn("libgamemodeauto.so.0 отсутствует")
        return
    current = settings.get("use_gamemode", False)
    settings["use_gamemode"] = not current
    save_settings(settings)
    ok(f"GameMode {'вкл' if not current else 'выкл'}")
