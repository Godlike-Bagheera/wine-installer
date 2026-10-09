"""Установка шейдер-паков для Minecraft (Complementary, BSL и др.).

Логика:
1. Определяем запущенную/установленную версию Minecraft:
   - активные фоновые игры лаунчера (modules.gamestate);
   - процессы java/wine с minecraft в командной строке;
   - папки .minecraft — по времени последнего изменения (последняя игра).
2. Предлагаем популярные паки: живой каталог через Modrinth API + офлайн-
   список (на случай школьной сети без интернета).
3. Скачанный zip валидируется (сигнатура PK, наличие файлов шейдеров)
   и кладётся в shaderpacks/ выбранной игры.

Шейдеры работают с OptiFine / Iris / Fabulously Optimized.
"""
import json
import re
import shutil
import zipfile
import subprocess
from pathlib import Path

from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, YELLOW, BOLD, RESET
from modules.config import WINE_DIR, make_github_mirrors
from modules.download import download_file
from modules.prefix import find_minecraft_dirs

MODRINTH_SEARCH = ("https://api.modrinth.com/v2/search?"
                   "query={query}&facets=%5B%5B%22project_type%3Ashader%22%5D%5D"
                   "&limit=8&index=relevance")

# Офлайн-каталог: если Modrinth API недоступен (школа, нет сети).
OFFLINE_SHADERS = [
    {
        "name": "ComplementaryReimagined",
        "desc": "самый популярный универсальный пак (низкие/средние требования)",
        "url": "https://github.com/ComplementaryDevelopment/ComplementaryReimagined/"
               "releases/latest/download/ComplementaryReimagined_r5.4.zip",
        "alt_urls": [],
    },
    {
        "name": "BSL Shaders",
        "desc": "мягкое освещение, средняя нагрузка",
        "url": "https://github.com/AngelScene/bsl/releases/latest/download/BSL.zip",
        "alt_urls": [],
    },
    {
        "name": "Chocapic13 V9",
        "desc": "классика, хорошо идёт на слабых ПК",
        "url": "https://github.com/Doctordog4/Chocapic13-Shaders-V9-Edition/"
               "releases/latest/download/Chocapic13_V9_Edition.zip",
        "alt_urls": [],
    },
    {
        "name": "Nostalgia Shader",
        "desc": "ретро-вид «как в старых версиях»",
        "url": "https://www.minecraft-shaders.com/sites/default/files/"
               "downloads/NostalgiaShader_v34.2.zip",
        "alt_urls": [],
    },
]


def _ssl_ctx():
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ─────────────────────────────────────────────────────────────────────
#  Определение версии Minecraft (запущенная / последняя установленная)
# ─────────────────────────────────────────────────────────────────────

def detect_running_mc_version():
    """Ищет запущенный процесс Minecraft (java с -cp ... или wine).

    Возвращает dict {"version": str|None, "dir": Path|None, "running": bool}.
    """
    result = {"version": None, "dir": None, "running": False}
    # 1) фоновые игры самого лаунчера (реестр gamestate)
    try:
        from modules import gamestate
        for name, g in gamestate.running().items():
            low = (name + " " + g["path"]).lower()
            if "minecraft" in low or "tlauncher" in low or "prism" in low:
                result["running"] = True
                result["dir"] = _mc_dir_from_path(Path(g["path"]))
                break
    except Exception as e:
        debug.dbg(f"detect_running_mc gamestate: {e}")
    # 2) процессы системы
    try:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception as e:
        debug.dbg(f"detect_running_mc ps: {e}")
        return result
    for line in out.splitlines():
        low = line.lower()
        if "minecraft" not in low and "tlauncher" not in low and ".minecraft" not in low:
            continue
        if "grep " in low or "wine.py" in low or "shaders" in low:
            continue
        result["running"] = True
        m = re.search(r"versions[/\\](1[.\w\-]+?)[/\\]", line)
        if m and not result["version"]:
            result["version"] = m.group(1)
        m2 = re.search(r"([^\s\"']*/\.minecraft)", line)
        if m2 and result["dir"] is None:
            d = Path(m2.group(1)).expanduser()
            if d.is_dir():
                result["dir"] = d
        if result["version"] or result["dir"]:
            break
    return result


def _mc_dir_from_path(p):
    """По пути .exe/.jar игры определяет папку .minecraft рядом с ней."""
    try:
        for parent in [p] + list(p.parents):
            if parent.name.lower() in (".minecraft", "game") or \
               "minecraft" in parent.name.lower():
                if parent.is_dir():
                    return parent
    except OSError:
        pass
    return None


def installed_mc_versions(mc_dir):
    """Версии из <mc>/versions (по дате modification — свежие сверху)."""
    versions = []
    try:
        vdir = Path(mc_dir) / "versions"
        if not vdir.is_dir():
            return versions
        for v in vdir.iterdir():
            if v.is_dir() and ((v / "version.json").exists() or (v / f"{v.name}.json").exists()):
                try:
                    versions.append((v.stat().st_mtime, v.name))
                except OSError:
                    versions.append((0, v.name))
    except OSError as e:
        debug.dbg(f"installed_mc_versions: {e}")
    versions.sort(reverse=True)
    return [name for _, name in versions]


def pick_target_mc():
    """Куда ставить шейдеры: сначала запущенная игра, потом самая свежая .minecraft."""
    run = detect_running_mc_version()
    if run["running"]:
        info("Обнаружен запущенный Minecraft.")
        if run["version"]:
            info(f"Версия игры: {CYAN}{run['version']}{RESET}")
        if run["dir"] is not None:
            return run["dir"], run.get("version")
    dirs = find_minecraft_dirs(limit=12)
    if not dirs:
        return None, run.get("version")
    # самая «свежая» по времени модификации
    def key(d):
        try:
            return d.stat().st_mtime
        except OSError:
            return 0
    best = max(dirs, key=key)
    vers = installed_mc_versions(best)
    if run.get("version"):
        return best, run["version"]
    return best, (vers[0] if vers else None)


# ─────────────────────────────────────────────────────────────────────
#  Каталог шейдеров: Modrinth API + офлайн
# ─────────────────────────────────────────────────────────────────────

def fetch_modrinth_shaders(query="shader"):
    """Список [{name, downloads, desc, files:[urls]}] или [] при ошибке сети."""
    import urllib.request
    url = MODRINTH_SEARCH.format(query=query)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wine-installer/2.6"})
        with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        debug.dbg(f"modrinth search: {e}")
        return []
    packs = []
    for hit in data.get("hits", [])[:8]:
        files = hit.get("files") or []
        urls = [f.get("url") for f in files if f.get("url")]
        if not urls:
            # у search-результата файлов может не быть — берём список версий проекта
            pid = hit.get("project_id") or hit.get("slug")
            try:
                pv = urllib.request.Request(
                    f"https://api.modrinth.com/v2/project/{pid}/version?loaders=%5B%5D",
                    headers={"User-Agent": "wine-installer/2.6"})
                with urllib.request.urlopen(pv, context=_ssl_ctx(), timeout=15) as r2:
                    vlist = json.loads(r2.read().decode("utf-8", errors="replace"))
                for v in vlist[:1]:
                    urls = [f.get("url") for f in v.get("files", []) if f.get("url")]
            except Exception as e:
                debug.dbg(f"modrinth version: {e}")
        if not urls:
            continue
        packs.append({
            "name": hit.get("title") or hit.get("slug", "shader"),
            "downloads": int(hit.get("downloads", 0)),
            "desc": (hit.get("description") or "")[:70],
            "urls": urls,
        })
    return packs


def build_shader_catalog():
    """Онлайн (Modrinth) → при неудаче офлайн-каталог. [(name, meta), ...]."""
    packs = fetch_modrinth_shaders()
    if packs:
        info(f"Modrinth: найдено {len(packs)} шейдер-паков.")
        return [(p["name"], p) for p in packs]
    warn("Modrinth API недоступен — включаю офлайн-каталог.")
    return [(p["name"], {"name": p["name"], "downloads": 0, "desc": p["desc"],
                         "urls": [p["url"]] + p["alt_urls"]})
            for p in OFFLINE_SHADERS]


# ─────────────────────────────────────────────────────────────────────
#  Валидация и установка zip
# ─────────────────────────────────────────────────────────────────────

def validate_shader_zip(path):
    """Проверяет что zip открывается и содержит файлы шейдеров (.fsh/.vsh/glsl)
    либо структуру папки пакета. True/False."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size < 1024:
        return False
    if not zipfile.is_zipfile(p):
        debug.dbg(f"validate: {p} не zip")
        return False
    try:
        with zipfile.ZipFile(p) as z:
            names = [n.lower() for n in z.namelist()]
            if not names:
                return False
            has_shader_files = any(n.endswith((".fsh", ".vsh", ".glsl", ".gsh"))
                                   for n in names)
            has_pack_meta = any("shader" in n and n.endswith(".zip") or
                                n.endswith("shaders/") or "/shaders/" in n
                                for n in names)
            return has_shader_files or has_pack_meta
    except (zipfile.BadZipFile, OSError) as e:
        debug.dbg(f"validate: {e}")
        return False


def install_shader_zip(zip_path, shaderpacks_dir):
    """Кладёт проверенный zip в shaderpacks/. Возвращает путь к файлу или None."""
    zip_path = Path(zip_path)
    if not validate_shader_zip(zip_path):
        err("Файл не похож на шейдер-пак (битый zip или не шейдеры).")
        return None
    try:
        shaderpacks_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        err(f"Не могу создать {shaderpacks_dir}: {e}")
        return None
    dest = shaderpacks_dir / zip_path.name
    try:
        shutil.copy2(zip_path, dest)
    except OSError as e:
        err(f"Копирование не удалось: {e}")
        return None
    return dest


def cmd_shaders():
    """Команда shaders / шейдеры — интерактивная установка шейдер-пака."""
    print(f"\n{BOLD}═══ УСТАНОВКА ШЕЙДЕРОВ ═══{RESET}")
    mc, version = pick_target_mc()
    if mc is None:
        err("Папка .minecraft не найдена.")
        hint("Сначала установи Minecraft (optifine / fo / legacy) или запусти игру.")
        return True
    vers = installed_mc_versions(mc)
    info(f"Игра: {CYAN}{mc}{RESET}")
    if version:
        info(f"Целевая версия: {CYAN}{version}{RESET}")
    elif vers:
        info(f"Установленные версии: {CYAN}{', '.join(vers[:5])}{RESET}")
    packs = build_shader_catalog()
    if not packs:
        err("Каталог пуст (ни сеть, ни офлайн-список не помогли).")
        return True
    print(f"\n{BOLD}Доступные шейдер-паки:{RESET}")
    for i, (name, meta) in enumerate(packs, 1):
        dl = f"  {meta['downloads']:,} загрузок".replace(",", " ") if meta.get("downloads") else ""
        print(f"  {CYAN}{i}{RESET}) {name}{dl}")
        if meta.get("desc"):
            print(f"      {meta['desc']}")
    print(f"  {CYAN}0{RESET}) Отмена")
    try:
        choice = input(f"{YELLOW}Номер пака: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return True
    if not choice.isdigit() or not (1 <= int(choice) <= len(packs)):
        warn("Отменено.")
        return True
    name, meta = packs[int(choice) - 1]
    urls = meta.get("urls") or []
    if not urls:
        err("Для этого пака нет ссылки.")
        return True
    # зеркала: прямая ссылка + github-прокси если URL с github releases
    mirrors = [("direct", urls[0])]
    gh = make_github_mirrors(urls[0])
    if gh:
        mirrors += gh
    for extra in urls[1:]:
        mirrors.append(("alt", extra))
    tmp = WINE_DIR / "shaders"
    tmp.mkdir(parents=True, exist_ok=True)
    fname = urls[0].split("/")[-1].split("?")[0] or f"{name}.zip"
    if not fname.lower().endswith(".zip"):
        fname += ".zip"
    dest_zip = tmp / fname
    info(f"Скачиваю '{name}'...")
    if not download_file(mirrors, dest_zip, name, min_size_mb=0, silent=False):
        err("Скачать не удалось.")
        return True
    shaderpacks = mc / "shaderpacks"
    installed = install_shader_zip(dest_zip, shaderpacks)
    if installed is None:
        try:
            dest_zip.unlink()
        except OSError:
            pass
        hint("Файл удалён как невалидный. Попробуй другой пак.")
        return True
    ok(f"Шейдер установлен: {installed}")
    hint("В игре: Настройки → Графика → Шейдеры → выбрать пакет → Применить.")
    hint("Нужен OptiFine или Iris (Fabulously Optimized уже содержит Iris).")
    return True
