"""Установка шейдер-паков для Minecraft (Iris/OptiFine).

Логика:
  1. Смотрим, какая версия Minecraft установлена/запущена (versions/, .minecraft).
  2. Предлагаем популярные паки: живой каталог через Modrinth API
     (project "shaders", facets shader) + офлайн-каталог на случай отсутствия сети.
  3. Скачиваем выбранный .zip в папку shaderpacks/ с валидацией файла
     (настоящий zip, а не HTML-заглушка прокси).
"""
import json
import re
import zipfile
from pathlib import Path

from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, BOLD, YELLOW, RESET
from modules.config import HOME
from modules.download import download_file, _looks_binary
from modules.prefix import find_minecraft_dirs

MODRINTH_PROJECTS_API = "https://api.modrinth.com/v2/search"

# Офлайн-каталог популярных шейдер-паков: (slug, человекочитаемое имя, описание)
OFFLINE_SHADER_PACKS = [
    ("complementary-shaders", "Complementary Reimagined",
     "Сбалансированные шейдеры, хорошо дружат с OptiFine/Iris"),
    ("bsl-shaders", "BSL Shaders",
     "Мягкая картинка, средняя нагрузка на GPU"),
    ("seus-vibrant", "SEUS Vibrant",
     "Классика SEUS, яркая атмосфера"),
    ("chocapic13-shaders", "Chocapic13's Shaders",
     "Лёгкие шейдеры для слабых ПК"),
    ("nostalgia-shader", "Nostalgia Shader",
     "Ретро-стиль под старые версии MC"),
    ("silders-enhanced", "Sildur's Enhanced Default",
     "Минималистичные, почти без нагрузки"),
    ("rocks-shaders", "Rocks Shaders",
     "Очень лёгкие, для старых компьютеров"),
]


def detect_mc_version():
    """Пытается определить установленную/последнюю версию Minecraft.

    Смотрит versions/ во всех найденных .minecraft (в т.ч. профили вида
    fabric-loader-X-Y, FO_версия) и возвращает самую свежую MC-версию."""
    best = None
    best_key = None

    def ver_key(v):
        parts = []
        for chunk in v.replace("-", ".").split("."):
            digits = "".join(c for c in chunk if c.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    for mc_dir in find_minecraft_dirs(limit=12):
        versions = mc_dir / "versions"
        try:
            if not versions.is_dir():
                continue
            for entry in versions.iterdir():
                name = entry.name
                # Имена профилей содержат MC-версию: 1.21.5, fabric-loader-0.16.9-1.21.5, FO 14.1.0 for 1.21.5
                m = re.search(r"(?<![\d.])(1\.\d+(?:\.\d+)?)(?![\d.])", name)
                if not m:
                    continue
                v = m.group(1)
                k = ver_key(v)
                if best_key is None or k > best_key:
                    best, best_key = v, k
        except OSError:
            continue
    return best


def get_shaderpacks_dir(auto=True):
    """Папка shaderpacks: первая найденная .minecraft (+ создаём при необходимости)."""
    dirs = find_minecraft_dirs(limit=12)
    if not dirs:
        if not auto:
            return None
        try:
            manual = input(f"{YELLOW}Папка .minecraft не найдена. Укажи путь (Enter — ~/.minecraft): {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            return None
        mc = Path(manual) if manual else HOME / ".minecraft"
        dirs = [mc]
    target = dirs[0] / "shaderpacks"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        err(f"Не могу создать {target}: {e}")
        return None
    return target


def _modrinth_search(query="shaders", limit=12):
    """Живой поиск популярных шейдер-паков на Modrinth. Возвращает [(slug, title, downloads)]."""
    params = (
        f"?query={query}"
        "&limit=" + str(limit)
        "&facets=[[\"project_type:mod\",\"categories:shaders\"]]"
        "&index=downloads"
    )
    url = MODRINTH_PROJECTS_API + params
    try:
        data = json.loads(url_open_text(url))
    except Exception as e:
        debug.dbg(f"modrinth search fail: {e}")
        return []
    result = []
    for hit in data.get("hits", []):
        slug = hit.get("slug") or ""
        title = hit.get("title") or slug
        downloads = hit.get("downloads", 0)
        if slug:
            result.append((slug, title, downloads))
    return result


def url_open_text(url, timeout=15):
    """GET текста по URL (отдельно, чтобы можно было подменить в тестах)."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "wine-portable-launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def list_available_packs():
    """Список паков: сначала из Modrinth (если сеть есть), затем офлайн-каталог."""
    packs = []
    seen = set()
    online = _modrinth_search()
    for slug, title, _dl in online:
        if slug not in seen:
            seen.add(slug)
            packs.append((slug, title, "(Modrinth)"))
    for slug, title, desc in OFFLINE_SHADER_PACKS:
        if slug not in seen:
            seen.add(slug)
            packs.append((slug, title, desc))
    return packs


def _latest_file_from_modrinth(slug):
    """Возвращает (url, filename) последней загрузки проекта-шейдера или (None, None)."""
    url = f"https://api.modrinth.com/v2/project/{slug}/version"
    try:
        data = json.loads(url_open_text(url))
    except Exception as e:
        debug.dbg(f"modrinth versions fail ({slug}): {e}")
        return None, None
    for ver in data:  # API отдаёт версии от новых к старым
        files = ver.get("files") or []
        for f in files:
            u = f.get("url", "")
            name = f.get("filename", "")
            if u.endswith(".zip") or name.endswith(".zip"):
                return u, (name or f"{slug}.zip")
    return None, None


def validate_shader_zip(path):
    """True, если файл выглядит как настоящий zip-архив (а не HTML-заглушка)."""
    p = Path(path)
    if not p.is_file():
        return False
    if not _looks_binary(p):
        return False
    try:
        with zipfile.ZipFile(p, "r") as z:
            bad = z.testzip()
        return bad is None
    except (zipfile.BadZipFile, OSError) as e:
        debug.dbg(f"validate_shader_zip({p}): {e}")
        return False


def install_shader_pack(slug, title=None, dest_dir=None):
    """Скачивает последнюю версию пака с Modrinth и кладёт zip в shaderpacks/.

    Возвращает Path к установленному файлу или None."""
    sp_dir = Path(dest_dir) if dest_dir else get_shaderpacks_dir()
    if sp_dir is None:
        return None
    label = title or slug
    url, fname = _latest_file_from_modrinth(slug)
    if not url:
        err(f"Не нашёл zip-файл у пака «{label}» на Modrinth.")
        hint("Попробуй другой пак из списка или скачай zip вручную и положи в shaderpacks/.")
        return None
    dest = sp_dir / fname
    info(f"Скачиваю «{label}»...")
    mirrors = [("Modrinth", url)]
    ok_dl = download_file(mirrors, dest, fname, min_size_mb=0, silent=False)
    if not ok_dl:
        err("Скачивание не удалось.")
        return None
    if not validate_shader_zip(dest):
        try:
            dest.unlink()
        except OSError:
            pass
        err("Файл не прошёл проверку (не zip или битый). Удалил его.")
        return None
    ok(f"Шейдер установлен: {CYAN}{dest}{RESET}")
    hint("В игре: Настройки → Графика → Шейдеры → выбрать пакет.")
    return dest


def cmd_shaders():
    """Меню установки шейдеров."""
    print(f"\n{BOLD}═══════ ШЕЙДЕРЫ ═══════{RESET}")
    ver = detect_mc_version()
    if ver:
        info(f"Обнаружена версия Minecraft: {CYAN}{ver}{RESET}")
    else:
        warn("Версия Minecraft не определена — шейдеры всё равно можно поставить.")
    sp_dir = get_shaderpacks_dir(auto=False)
    if sp_dir and sp_dir.is_dir():
        installed = sorted(p.name for p in sp_dir.glob("*.zip"))
        if installed:
            info(f"Уже установлено: {', '.join(installed)}")
    packs = list_available_packs()
    if not packs:
        err("Список паков пуст (нет сети и офлайн-каталог не загрузился?).")
        return
    print(f"\n{BOLD}Доступные шейдер-паки:{RESET}")
    for i, (slug, title, desc) in enumerate(packs, 1):
        print(f"  {CYAN}{i:2d}{RESET}) {title}  {desc}")
    print(f"  {CYAN}0{RESET}) Отмена")
    try:
        choice = input(f"{YELLOW}Номер пака: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return
    if choice in ("", "0"):
        return
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(packs)):
            err("Неверный номер")
            return
    except ValueError:
        err("Не число")
        return
    slug, title, _desc = packs[idx]
    install_shader_pack(slug, title=title)
