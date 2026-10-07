"""Wine AppImage, DXVK, runexe."""
import shutil
import tarfile
from modules import debug
from modules.colors import ok, info, CYAN, RESET
from modules.config import (
    WINE_DIR, WINE_BIN, RUNEXE, DXVK_DIR, DXVK_VERSIONS, DXVK_OVERRIDES,
    WINE_MIRRORS, WINE_PREFIX, make_dxvk_mirrors,
)
from modules.download import download_file


def download_wine():
    success = download_file(WINE_MIRRORS, WINE_BIN, "Wine (AppImage)", min_size_mb=50)
    if success:
        WINE_BIN.chmod(0o755)
        ok("Wine скачан")
    return success


def create_runexe():
    content = (
        f'#!/bin/bash\n'
        f'export WINEPREFIX="{WINE_PREFIX}"\n'
        f'export WINEDLLOVERRIDES="{DXVK_OVERRIDES}"\n'
        f'exec "{WINE_BIN}" "$@"\n'
    )
    RUNEXE.write_text(content, encoding="utf-8")
    RUNEXE.chmod(0o755)
    ok("Создан runexe")


def download_dxvk(silent=False):
    if DXVK_DIR.exists() and (DXVK_DIR / "x64").exists():
        return True
    if not silent:
        info("Скачиваю DXVK...\n")
    dxvk_archive = WINE_DIR / "dxvk.tar.gz"
    success = False
    for version in DXVK_VERSIONS:
        if not silent:
            info(f"{CYAN}Пробую {version}{RESET}")
        mirrors = make_dxvk_mirrors(version)
        if download_file(mirrors, dxvk_archive, f"DXVK {version}", min_size_mb=5, silent=silent):
            success = True
            break
    if not success:
        return False
    try:
        with tarfile.open(dxvk_archive, "r:gz") as tar:
            tar.extractall(WINE_DIR)
        for d in WINE_DIR.iterdir():
            if d.is_dir() and d.name.startswith("dxvk-") and d.name != "dxvk":
                if DXVK_DIR.exists():
                    shutil.rmtree(DXVK_DIR)
                d.rename(DXVK_DIR)
                break
        try:
            dxvk_archive.unlink()
        except Exception:
            pass
        return True
    except Exception as e:
        debug.dbg_exc(e, "download_dxvk/extract")
        return False


def install_dxvk_to_wine(exe_path=None):
    """Ставит DXVK DLL в префикс.

    exe_path=None        → дефолтный префикс (WINE_PREFIX).
    exe_path=<Path>      → per-game «бутылка» (при USE_PER_GAME_PREFIX=True).
    """
    from modules.prefix import get_prefix_path
    prefix = get_prefix_path(exe_path)
    system32 = prefix / "drive_c" / "windows" / "system32"
    syswow64 = prefix / "drive_c" / "windows" / "syswow64"
    if not system32.exists() or not DXVK_DIR.exists():
        return False
    marker = prefix / ".dxvk_installed"
    if marker.exists():
        try:
            if marker.read_text(encoding="utf-8").strip() == str(DXVK_DIR):
                return True
        except Exception:
            pass
    try:
        is_64bit = syswow64.exists()
        x64 = DXVK_DIR / "x64"
        x32 = DXVK_DIR / "x32"
        if is_64bit:
            if x64.exists():
                for dll in x64.glob("*.dll"):
                    shutil.copy2(dll, system32 / dll.name)
            if x32.exists():
                for dll in x32.glob("*.dll"):
                    shutil.copy2(dll, syswow64 / dll.name)
        else:
            if x32.exists():
                for dll in x32.glob("*.dll"):
                    shutil.copy2(dll, system32 / dll.name)
        try:
            marker.write_text(str(DXVK_DIR), encoding="utf-8")
        except Exception:
            pass
        return True
    except Exception as e:
        debug.dbg_exc(e, "install_dxvk_to_wine")
        return False


def cmd_dxvk():
    from modules.colors import MAGENTA
    from modules.prefix import ensure_prefix
    if DXVK_DIR.exists():
        try:
            answer = input(f"{MAGENTA}Переустановить DXVK? [y/N]: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return
        if answer not in ("y", "yes", "д", "да"):
            return
        shutil.rmtree(DXVK_DIR, ignore_errors=True)
        marker = WINE_PREFIX / ".dxvk_installed"
        if marker.exists():
            marker.unlink()
    if download_dxvk():
        if ensure_prefix():
            install_dxvk_to_wine()


def cmd_update():
    from modules.colors import MAGENTA
    info("Обновление Wine/DXVK")
    try:
        answer = input(f"{MAGENTA}Перекачать? [y/N]: {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return
    if answer not in ("y", "yes", "д", "да"):
        return
    if WINE_BIN.exists():
        try:
            WINE_BIN.unlink()
        except Exception:
            pass
    if download_wine():
        ok("Wine обновлён")
    if DXVK_DIR.exists():
        shutil.rmtree(DXVK_DIR, ignore_errors=True)
    if download_dxvk():
        marker = WINE_PREFIX / ".dxvk_installed"
        if marker.exists():
            marker.unlink()
        install_dxvk_to_wine()
        ok("DXVK обновлён")
    create_runexe()
