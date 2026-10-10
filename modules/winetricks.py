"""winetricks + авто-фиксы DLL."""
import os
import re
import subprocess
import urllib.request
from modules import debug, net
from modules.colors import ok, info, warn, err, fix, DIM, RESET
from modules.config import (
    BIN_DIR, WINETRICKS_BIN, MIN_WINETRICKS_SIZE,
    WINETRICKS_MIRRORS, CONNECT_TIMEOUT, WINE_BIN,
)
from modules.prefix import ensure_prefix, get_wine_env


DLL_FIXES = [
    (re.compile(r"OpenAL32\.dll", re.I),               ["openal"]),
    (re.compile(r"d3dx9_\d+\.dll", re.I),              ["d3dx9"]),
    (re.compile(r"d3dx10_\d+\.dll", re.I),             ["d3dx10"]),
    (re.compile(r"d3dx11_\d+\.dll", re.I),             ["d3dx11"]),
    (re.compile(r"d3dcompiler_\d+\.dll", re.I),        ["d3dcompiler_43", "d3dcompiler_47"]),
    (re.compile(r"xaudio2_\d+\.dll", re.I),            ["xact"]),
    (re.compile(r"msvcp140(_\d+)?\.dll", re.I),        ["vcrun2019"]),
    (re.compile(r"vcruntime140(_\d+)?\.dll", re.I),    ["vcrun2019"]),
    (re.compile(r"msvcp120\.dll|msvcr120\.dll", re.I), ["vcrun2013"]),
    (re.compile(r"msvcp110\.dll|msvcr110\.dll", re.I), ["vcrun2012"]),
    (re.compile(r"msvcp100\.dll|msvcr100\.dll", re.I), ["vcrun2010"]),
    (re.compile(r"msvcp90\.dll|msvcr90\.dll", re.I),   ["vcrun2008"]),
    (re.compile(r"msvcp80\.dll|msvcr80\.dll", re.I),   ["vcrun2005"]),
    (re.compile(r"mfc42\.dll", re.I),                  ["mfc42"]),
    (re.compile(r"riched20\.dll", re.I),               ["riched20"]),
    (re.compile(r"wmp\.dll", re.I),                    ["wmp9"]),
    (re.compile(r"quartz\.dll", re.I),                 ["quartz"]),
    (re.compile(r"dsound\.dll", re.I),                 ["dsound"]),
    (re.compile(r"dinput8\.dll", re.I),                ["dinput"]),
    (re.compile(r"gdiplus\.dll", re.I),                ["gdiplus"]),
    (re.compile(r"msxml3\.dll", re.I),                 ["msxml3"]),
    (re.compile(r"msxml4\.dll", re.I),                 ["msxml4"]),
    (re.compile(r"msxml6\.dll", re.I),                 ["msxml6"]),
    (re.compile(r"windowscodecs\.dll", re.I),          ["windowscodecs"]),
    (re.compile(r"api-ms-win-crt", re.I),              ["vcrun2019"]),
]

NOISY_PATTERNS = (
    "fixme:", "wine: Read", "wine: Write",
    "err:ole:StdMarshalImpl_MarshalInterface",
    "err:ole:CoMarshalInterface",
    "err:ole:apartment_get_local_server_stream",
    "err:ole:start_rpcss",
    "err:setupapi:do_file_copyW",
)


def filter_line(line):
    from modules import state
    if not state.QUIET_MODE:
        return line
    for p in NOISY_PATTERNS:
        if p in line:
            return None
    return line


def detect_missing_libs(line):
    pkgs = []
    low = line.lower()
    # Ловим и "err:", и "error:", и "not found", и "failed"
    if not re.search(r"\berr(or)?\b|not found|failed", low):
        return pkgs
    for pattern, packages in DLL_FIXES:
        if pattern.search(line):
            pkgs.extend(packages)
    return pkgs


def download_winetricks():
    if WINETRICKS_BIN.exists() and WINETRICKS_BIN.stat().st_size > MIN_WINETRICKS_SIZE:
        return True
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    info("Скачиваю winetricks...")
    for name, url in WINETRICKS_MIRRORS:
        debug.dbg(f"winetricks: {name}")
        try:
            ctx = net.ssl_ctx()
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            r = urllib.request.urlopen(req, context=ctx, timeout=CONNECT_TIMEOUT)
            data = r.read()
            r.close()
            if len(data) > MIN_WINETRICKS_SIZE:
                WINETRICKS_BIN.write_bytes(data)
                WINETRICKS_BIN.chmod(0o755)
                ok(f"winetricks ({len(data)//1024} КБ)")
                return True
        except Exception as e:
            debug.dbg_exc(e, f"download_winetricks/{name}")
    err("winetricks не скачался")
    return False


def run_winetricks(args, exe_path=None):
    env = get_wine_env(use_dxvk=False, exe_path=exe_path)
    if WINETRICKS_BIN.exists() and os.access(WINETRICKS_BIN, os.X_OK):
        env["WINE"] = str(WINE_BIN)
        return subprocess.Popen(
            [str(WINETRICKS_BIN)] + args, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace",
        )
    return subprocess.Popen(
        [str(WINE_BIN), "winetricks"] + args, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
        encoding="utf-8", errors="replace",
    )


def install_via_winetricks(pkgs, already_installed, exe_path=None):
    to_install = [p for p in pkgs if p not in already_installed]
    if not to_install:
        return False
    if not ensure_prefix(exe_path=exe_path):
        err("Префикс не готов")
        return False
    fix(f"Доустанавливаю: {', '.join(to_install)}")
    proc = None
    try:
        proc = run_winetricks(["-q"] + to_install, exe_path=exe_path)
    except Exception as e:
        debug.dbg_exc(e, "install_via_winetricks/run")
        err(f"Не запустить: {e}")
        return False
    if proc.stdout is None:
        proc.wait()
        return False
    KEYWORDS = ("Executing", "Downloading", "Installing", "warning", "Extracting", "Running")
    import sys
    try:
        for line in proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            if any(k in line for k in KEYWORDS):
                sys.stdout.write(f"  {DIM}{stripped[:120]}{RESET}\n")
                sys.stdout.flush()
            else:
                sys.stdout.write(f"{DIM}.{RESET}")
                sys.stdout.flush()
        proc.wait()
        print()
    except KeyboardInterrupt:
        warn("Установка прервана")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception as e:
                debug.dbg_exc(e, "winetricks")
        raise
    if proc.returncode == 0:
        ok(f"Установлено: {', '.join(to_install)}")
        already_installed.update(to_install)
        return True
    warn(f"winetricks код {proc.returncode}")
    already_installed.update(to_install)
    return False


def cmd_fonts():
    if not WINETRICKS_BIN.exists():
        warn("winetricks не скачан")
        if not download_winetricks():
            return
    info("Устанавливаю corefonts...")
    install_via_winetricks(["corefonts"], set())
