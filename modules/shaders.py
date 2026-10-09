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
import os
import json
import re
import shutil
import zipfile
import urllib.parse
import urllib.request
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


def _download_to_temp(url, fname):
    """Скачивает файл по URL в WINE_DIR/shaders. Возвращает Path или None."""
    tmp = WINE_DIR / "shaders"
    tmp.mkdir(parents=True, exist_ok=True)
    if not fname.lower().endswith(".zip"):
        fname += ".zip"
    dest_zip = tmp / fname
    mirrors = [("direct", url)]
    gh = make_github_mirrors(url)
    if gh:
        mirrors += gh
    if download_file(mirrors, dest_zip, fname, min_size_mb=0, silent=False):
        return dest_zip
    return None


def _install_from_url(name, url, shaderpacks_dir):
    """Скачивает zip по ссылке и устанавливает в shaderpacks/. True/False."""
    info(f"Скачиваю '{name}'...")
    fname = url.split("/")[-1].split("?")[0] or f"{name}.zip"
    dest_zip = _download_to_temp(url, fname)
    if dest_zip is None:
        err("Скачать не удалось.")
        return False
    installed = install_shader_zip(dest_zip, shaderpacks_dir)
    if installed is None:
        try:
            dest_zip.unlink()
        except OSError:
            pass
        hint("Файл удалён как невалидный. Попробуй другой пак.")
        return False
    ok(f"Шейдер установлен: {installed}")
    return True


def cmd_publish_shader():
    """Команда «опубликовать» — публикация своего шейдер-пака на GitHub.

    Публикация идёт через GitHub API (нужен токен с правом repo). Если у
    пользователя нет токена, вместо ошибки показываем понятную инструкцию,
    как опубликовать пак вручную через веб-интерфейс (Create repository →
    Upload files → Releases → Draft new release → Attach binaries → Publish).
    Именно отсутствие токена обычно и даёт сообщение вида
    «нет контента для отправки» / 401 Bad credentials.
    """
    import urllib.error

    print(f"\n{BOLD}═══ ПУБЛИКАЦИЯ ШЕЙДЕР-ПАКА НА GITHUB ═══{RESET}")

    # 1. Какой файл публикуем?
    packs = sorted((WINE_DIR / "shaders").glob("*.zip")) \
        if (WINE_DIR / "shaders").is_dir() else []
    src = None
    if packs:
        print("Недавние скачанные паки:")
        for i, p in enumerate(packs, 1):
            print(f"  {CYAN}{i}{RESET}) {p.name} "
                  f"({p.stat().st_size // 1024} КБ)")
        print(f"  {CYAN}0{RESET}) Свой путь к .zip")
        try:
            choice = input(f"{YELLOW}Номер: {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return True
        if choice.isdigit() and 1 <= int(choice) <= len(packs):
            src = packs[int(choice) - 1]
    if src is None:
        try:
            path_in = input(f"{YELLOW}Путь к .zip шейдер-пака: {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return True
        src = Path(path_in).expanduser() if path_in else None
    if src is None or not src.is_file():
        err(f"Файл не найден: {src}")
        return True
    if not validate_shader_zip(src):
        warn("Файл не похож на шейдер-пак (битый zip или не шейдеры).")
        try:
            go = input("Продолжить всё равно? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return True
        if go not in ("y", "yes", "д", "да"):
            warn("Отменено.")
            return True

    # 2. Ищем токен GitHub: env → gh CLI → ~/.gitconfig credential helper
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    token_src = "переменная окружения"
    if not token:
        try:
            r = subprocess.run(["gh", "auth", "token"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                token, token_src = r.stdout.strip(), "gh CLI"
        except (OSError, subprocess.SubprocessError):
            pass
    if not token:
        try:
            r = subprocess.run(
                ["git", "credential-fill"],
                input="protocol=https\nhost=github.com\n\n",
                capture_output=True, text=True, timeout=10)
            for line in (r.stdout or "").splitlines():
                if line.startswith("password="):
                    token, token_src = line[len("password="):], "git-credential"
                    break
        except (OSError, subprocess.SubprocessError):
            pass

    # 3. Токена нет — НЕ падаем с «нет контента для отправки», а объясняем
    if not token:
        warn("Не найден токен GitHub — публиковать нечем "
             "(«нет контента для отправки»).")
        hint("Вариант А (через браузер, без токена): github.com → New repository "
             "→ загрузи " + src.name + " → Actions/Releases → Draft new release "
             "→ Attach Binaries → Publish release.")
        hint("Вариант Б (автоматом): создай токен на "
             "github.com/settings/tokens (право repo), затем:")
        hint("    export GITHUB_TOKEN=ТВОЙ_ТОКЕН  и повтори «опубликовать»")
        hint("    (или установи gh CLI: https://cli.github.com/, `gh auth login`)")
        return True

    # 4. Логин владельца токена
    info(f"Токен найден ({token_src}), проверяю доступ...")
    try:
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}",
                     "User-Agent": "wine-installer/2.5"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            login = json.loads(resp.read()).get("login")
    except urllib.error.HTTPError as e:
        err(f"GitHub API: {e.code} — токен недействителен или истёк.")
        hint("Обнови токен: github.com/settings/tokens (право repo, срок ~30 дней)")
        return True
    except Exception as e:
        debug.dbg_exc(e, "publish/user")
        err(f"Нет связи с api.github.com: {e}")
        return True
    if not login:
        err("Не удалось определить владельца токена.")
        return True

    # 5. Репозиторий (имя по умолчанию — из имени файла)
    default_repo = re.sub(r"[^A-Za-z0-9._-]", "-", src.stem)[:60] or "shader-pack"
    try:
        repo_name = input(f"{YELLOW}Имя репозитория [{default_repo}]: {RESET}").strip() \
            or default_repo
    except (KeyboardInterrupt, EOFError):
        print()
        return True
    tag = f"{src.stem}-v1.0".replace(" ", "-")

    def _api(method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        rq = urllib.request.Request(
            f"https://api.github.com{path}", data=data, method=method,
            headers={"Authorization": f"token {token}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "wine-installer/2.5"})
        with urllib.request.urlopen(rq, timeout=30) as resp:
            body = resp.read()
            return json.loads(body) if body else {}

    # 5a. Создать репозиторий (если ещё нет)
    try:
        _api("POST", "/user/repos",
             {"name": repo_name, "public": True, "auto_init": True})
        ok(f"Создан репозиторий: {CYAN}github.com/{login}/{repo_name}{RESET}")
    except urllib.error.HTTPError as e:
        if e.code == 422:  # уже существует
            info(f"Репозиторий {login}/{repo_name} уже есть — дополняю.")
        elif e.code in (401, 403):
            err(f"GitHub API: {e.code} — у токена нет прав на создание репо "
                "(нужно право repo).")
            return True
        else:
            err(f"GitHub API: {e.code} {e.reason}")
            return True
    except Exception as e:
        debug.dbg_exc(e, "publish/create-repo")
        err(f"Ошибка сети при создании репозитория: {e}")
        return True

    # 5b. Загрузить zip в main (PUT /contents/<path>)
    import base64
    try:
        content_b64 = base64.b64encode(src.read_bytes()).decode()
        check_api = lambda: _api(  # noqa: E731
            "GET", f"/repos/{login}/{repo_name}/contents/{src.name}?ref=main")
        params = {"message": f"Add {src.name}", "content": content_b64,
                  "branch": "main"}
        try:
            params["sha"] = check_api().get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        except Exception:
            pass
        _api("PUT", f"/repos/{login}/{repo_name}/contents/{src.name}", params)
        ok(f"Файл загружен: {src.name}")
    except urllib.error.HTTPError as e:
        err(f"GitHub API: {e.code} — файл не загружен.")
        return True
    except Exception as e:
        debug.dbg_exc(e, "publish/upload")
        err(f"Ошибка загрузки файла: {e}")
        return True

    # 5c. Release с ассетом
    try:
        rel = _api("POST", f"/repos/{login}/{repo_name}/releases",
                   {"tag_name": tag, "name": f"{src.stem} v1.0",
                    "body": f"Shader pack {src.name}, published via Wine Installer.",
                    "draft": False, "prerelease": False})
        upload_url = (rel.get("upload_url") or "").split("{")[0]
        if upload_url:
            rq = urllib.request.Request(
                f"{upload_url}?name={urllib.parse.quote(src.name)}",
                data=src.read_bytes(), method="POST",
                headers={"Authorization": f"token {token}",
                         "Content-Type": "application/zip",
                         "User-Agent": "wine-installer/2.5"})
            with urllib.request.urlopen(rq, timeout=120) as resp:
                asset = json.loads(resp.read() or b"{}")
            dl = asset.get("browser_download_url", "")
            ok("Релиз опубликован!")
            hint(f"Страница: https://github.com/{login}/{repo_name}/releases/tag/{tag}")
            if dl:
                hint(f"Прямая ссылка: {dl}")
                hint("Эту ссылку другие игроки могут вставить в «shaders <URL>» "
                     "или скачать через download.")
        else:
            warn("Release создан, но upload_url пуст — приложи файл вручную.")
    except urllib.error.HTTPError as e:
        err(f"GitHub API: {e.code} — релиз не создан "
            "(файл в репозитории остался).")
        hint(f"Доделай вручную: github.com/{login}/{repo_name}/releases/new")
    except Exception as e:
        debug.dbg_exc(e, "publish/release")
        err(f"Ошибка создания релиза: {e}")
    return True


def cmd_shaders(arg=""):
    """Команда shaders / шейдеры — интерактивная установка шейдер-пака.

    Аргументы:
      shaders            — каталог (Modrinth + офлайн-список);
      shaders publish    — опубликовать свой пак на GitHub;
      shaders <URL>      — установить пак по прямой ссылке (.zip).
    """
    arg = (arg or "").strip()
    if arg.lower() in ("publish", "опубликовать", "pub"):
        return cmd_publish_shader()
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
    # Прямая ссылка: shaders https://.../MyShaders.zip
    if arg.lower().startswith(("http://", "https://")):
        _install_from_url(Path(arg.split("?")[0].split("/")[-1]).stem or "shader",
                          arg, mc / "shaderpacks")
        hint("В игре: Настройки → Графика → Шейдеры → выбрать пакет → Применить.")
        return True
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
    shaderpacks = mc / "shaderpacks"
    # пробуем все ссылки пака (прямая + github-зеркала подставляются внутри)
    ok_installed = False
    for url in urls:
        if _install_from_url(name, url, shaderpacks):
            ok_installed = True
            break
    if not ok_installed:
        return True
    hint("В игре: Настройки → Графика → Шейдеры → выбрать пакет → Применить.")
    hint("Нужен OptiFine или Iris (Fabulously Optimized уже содержит Iris).")
    return True
