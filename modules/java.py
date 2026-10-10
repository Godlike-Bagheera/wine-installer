"""Поиск и установка портативной JDK 17."""
import os
import subprocess
from pathlib import Path
from modules import debug, net
from modules.colors import ok, info, warn, err, hint, MAGENTA, BOLD, RESET
from modules.config import JAVA_DIR, JDK_MIRRORS
from modules.download import download_file


def _check_jdk(jdk_path):
    java_bin = jdk_path / "bin" / "java"
    if not java_bin.exists() or not os.access(java_bin, os.X_OK):
        return False
    try:
        r = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True, text=True, timeout=15,
        )
        out = r.stdout + r.stderr
        return r.returncode == 0 and "version" in out.lower()
    except Exception:
        return False


def find_java():
    from modules.config import HOME
    if JAVA_DIR.exists():
        for jdk in JAVA_DIR.glob("jdk-*"):
            if _check_jdk(jdk):
                return str(jdk / "bin" / "java"), str(jdk), "OK (портативная)"
    for base in [HOME / ".jdks", HOME / "jdks"]:
        if base.exists():
            for jdk in base.iterdir():
                if jdk.is_dir() and _check_jdk(jdk):
                    return str(jdk / "bin" / "java"), str(jdk), "OK (.jdks)"
    for root in ["/usr/lib/jvm", "/opt", "/usr/lib64/jvm"]:
        p = Path(root)
        if not p.exists():
            continue
        try:
            for lib in p.rglob("libawt_xawt.so"):
                jdk = lib.parent.parent
                if _check_jdk(jdk):
                    return str(jdk / "bin" / "java"), str(jdk), "OK (системная)"
        except Exception:
            continue
    import shutil
    java_path = shutil.which("java")
    if java_path:
        return java_path, None, "headless (без GUI)"
    return None, None, "не найдена"


def install_portable_java():
    info(f"{BOLD}Установка портативной JDK 17 (Temurin){RESET}")
    JAVA_DIR.mkdir(parents=True, exist_ok=True)
    for jdk in JAVA_DIR.glob("jdk-*"):
        if _check_jdk(jdk):
            ok(f"JDK уже есть: {jdk}")
            return True
    archive = JAVA_DIR / "jdk17.tar.gz"
    if not download_file(JDK_MIRRORS, archive, "JDK 17", min_size_mb=50):
        err("Не удалось скачать JDK")
        return False
    info("Распаковываю...")
    try:
        net.safe_extract_tar(archive, JAVA_DIR)
        archive.unlink()
    except Exception as e:
        debug.dbg_exc(e, "install_portable_java/extract")
        err(f"Распаковка: {e}")
        return False
    for jdk in JAVA_DIR.glob("jdk-*"):
        if _check_jdk(jdk):
            ok(f"JDK установлена: {jdk}")
            hint(f"Java: {jdk}/bin/java")
            return True
    err("JDK распакована, но не прошла проверку")
    return False


def cmd_install_java():
    java_bin, java_home, status = find_java()
    if java_home:
        ok(f"Java с GUI уже есть: {java_home}")
        return
    warn(f"Java: {status}")
    print()
    info("Для OptiFine installer нужна Java с GUI (AWT).")
    hint("Скачаю портативную JDK 17 в ~/java (200 МБ)?")
    try:
        answer = input(f"{MAGENTA}Скачать? [Y/n]: {RESET}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return
    if answer not in ("", "y", "yes", "д", "да"):
        info("Отменено.")
        return
    install_portable_java()
