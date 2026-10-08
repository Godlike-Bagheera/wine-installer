"""Prism, Legacy, Fabulously Optimized, OptiFine, Fabric."""
import os
import re
import ssl
import json
import shutil
import tarfile
import zipfile
import hashlib
import subprocess
import urllib.request
from pathlib import Path
from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, YELLOW, MAGENTA, BOLD, RESET
from modules.config import (
    WINE_DIR, PRISM_DIR, PRISM_URL, WINE_PREFIX,
    FO_GITHUB_API, OPTIFINE_PAGE, FABRIC_META, FABRIC_MAVEN,
    MOJANG_VERSION_MANIFEST, make_github_mirrors,
    LEGACY_JAR_MIRRORS, LEGACY_JAR_MIN_SIZE,
    SYSTEM_TRUSTSTORE_PATHS, SYSTEM_TRUSTSTORE_PASSWORD,
)
from modules.download import download_file
from modules.hash_utils import verify_sha512, copy_to_clipboard
from modules.java import find_java, install_portable_java, cmd_install_java
from modules.prefix import choose_minecraft_dir


def _http_get_json(url, timeout=30):
    """GET url -> распарсенный JSON (SSL-контекст как в остальном проекте)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "wine-installer/2.5"})
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════════════════════════════
#  JAVA TRUSTSTORE — русские CA (Минцифры) не в cacerts OpenJDK
# ═══════════════════════════════════════════════════════════════════

def _find_system_truststore():
    """Ищет системный Java-truststore с русскими CA."""
    for path_str in SYSTEM_TRUSTSTORE_PATHS:
        p = Path(path_str)
        try:
            if p.exists() and p.stat().st_size > 10_000:
                return str(p)
        except Exception:
            continue
    return None


def _java_env_with_truststore():
    """Копирует env и добавляет JAVA_TOOL_OPTIONS с системным truststore.

    JAVA_TOOL_OPTIONS подхватывается ВСЕМИ JVM, включая второй процесс,
    который Legacy Launcher запускает сам через BootstrapRestarter.
    Просто добавить -D... в командную строку недостаточно — внутренний
    процесс его не унаследует.

    Также задаём trustStorePassword: системный cacerts, который
    генерирует update-ca-trust, защищён паролем 'changeit'.
    """
    env = os.environ.copy()
    truststore = _find_system_truststore()
    if truststore:
        opts = [
            f"-Djavax.net.ssl.trustStore={truststore}",
            f"-Djavax.net.ssl.trustStorePassword={SYSTEM_TRUSTSTORE_PASSWORD}",
            "-Djavax.net.ssl.trustStoreType=JKS",
        ]
        existing = env.get("JAVA_TOOL_OPTIONS", "").strip()
        new_opts = " ".join(opts)
        if "javax.net.ssl.trustStore" not in existing:
            env["JAVA_TOOL_OPTIONS"] = (existing + " " + new_opts).strip()
        debug.dbg(f"JAVA_TOOL_OPTIONS={env['JAVA_TOOL_OPTIONS']}")
    else:
        warn("Системный Java-truststore не найден — SSL может падать")
        hint("Проверь /etc/pki/ca-trust/extracted/java/cacerts")
        hint("Если файла нет: sudo update-ca-trust")
    return env


# ═══════════════════════════════════════════════════════════════════
#  PRISM LAUNCHER
# ═══════════════════════════════════════════════════════════════════

def setup_prism():
    info(f"{BOLD}Установка Prism Launcher{RESET}")
    archive = WINE_DIR / "prism.tar.gz"
    if not download_file([("direct", PRISM_URL)], archive, "Prism Launcher", min_size_mb=3):
        err("Не удалось скачать Prism")
        return False
    PRISM_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(PRISM_DIR)
    except Exception as e:
        debug.dbg_exc(e, "setup_prism/extract")
        err(f"Распаковка: {e}")
        return False
    exe = None
    for root, dirs, files in os.walk(PRISM_DIR):
        for f in files:
            if f == "PrismLauncher" or f.startswith("PrismLauncher"):
                exe = Path(root) / f
                exe.chmod(0o755)
                break
        if exe:
            break
    if exe:
        ok(f"Prism: {exe}")
        hint(f"Запусти: {exe}")
        return True
    err("PrismLauncher не найден")
    return False


# ═══════════════════════════════════════════════════════════════════
#  LEGACY LAUNCHER
# ═══════════════════════════════════════════════════════════════════

def _find_legacy_installed():
    candidates = [
        WINE_PREFIX / "drive_c" / "users" / "stud" / "AppData" / "Local" / "Programs",
        WINE_PREFIX / "drive_c" / "users" / "stud" / "AppData" / "Roaming",
        WINE_PREFIX / "drive_c" / "Program Files",
        WINE_PREFIX / "drive_c" / "Program Files (x86)",
    ]
    for base in candidates:
        if not base.exists():
            continue
        try:
            for root, dirs, files in os.walk(base):
                for f in files:
                    if f.lower() == "legacylauncher.exe":
                        return Path(root) / f
        except Exception:
            pass
    return None


def _find_local_legacy_jar():
    """Ищет уже скачанный .jar в стандартных местах."""
    candidates = [
        WINE_DIR / "legacy-portable" / "LegacyLauncher.jar",
        WINE_DIR / "LegacyLauncher.jar",
        WINE_DIR / "legacy-portable" / "bootstrap.jar",
        WINE_DIR / "bootstrap.jar",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > LEGACY_JAR_MIN_SIZE:
            return p
    return None


def setup_legacy_portable():
    """Скачивает Legacy Launcher Portable .jar (если нужно) и запускает через Java.

    .exe-установщик Legacy Launcher падает в Wine 11 WOW64 с page fault
    (баг Wine, не наш). Portable .jar работает на чистой Java.

    ВАЖНО: на Red OS / RHEL русские CA (Минцифры) лежат в системном
    truststore, но не в cacerts OpenJDK. Передаём JAVA_TOOL_OPTIONS,
    чтобы внутренний JVM-процесс LL тоже доверял этим сертификатам.
    """
    info(f"{BOLD}Legacy Launcher Portable (.jar){RESET}")

    jar_dir = WINE_DIR / "legacy-portable"
    jar_dir.mkdir(parents=True, exist_ok=True)
    jar_path = jar_dir / "LegacyLauncher.jar"

    # 1. Уже скачан?
    existing = _find_local_legacy_jar()
    if existing:
        jar_path = existing
        ok(f"Portable .jar уже есть: {jar_path}")
    else:
        # 2. Скачиваем
        info("Скачиваю Legacy Launcher Portable...")
        if download_file(
            LEGACY_JAR_MIRRORS, jar_path,
            "Legacy Launcher Portable",
            min_size_mb=1, silent=False,
        ):
            ok(f"Скачано: {jar_path}")
        else:
            # 3. Фоллбэк — ручной путь
            err("Не удалось скачать Portable .jar автоматически")
            hint("Скачай вручную: https://dl.legacylauncher.ru/legacy/installer")
            hint(f"И положи в: {jar_dir}  (имя: LegacyLauncher.jar)")
            print()
            try:
                manual = input(f"{YELLOW}Путь к .jar (Enter — отмена): {RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return False
            if not manual:
                return False
            jar_path = Path(manual).expanduser()
            if not jar_path.exists():
                err(f"Файл не найден: {jar_path}")
                return False
            if jar_path.suffix.lower() != ".jar":
                warn(f"Это не .jar файл: {jar_path.suffix}")
                return False

    # 4. Java
    java_bin, java_home, java_status = find_java()
    if not java_bin:
        err("Java не найдена. Portable .jar требует Java.")
        hint("Установи: install-java")
        return False
    if java_home:
        ok(f"Java: {java_home}")
    else:
        warn(f"Java: {java_status}")

    # 5. Окружение с системным truststore
    env = _java_env_with_truststore()
    truststore = _find_system_truststore()
    if truststore:
        ok(f"SSL truststore: {truststore}")
    print()

    # 6. Запуск (несколько попыток — bootstrap-джары иногда падают с кодом 1
    #    при сетевом сбое на первой загрузке)
    MAX_LAUNCH_ATTEMPTS = 2
    rc = None
    for attempt in range(1, MAX_LAUNCH_ATTEMPTS + 1):
        info(f"Запускаю Legacy Launcher Portable... (попытка {attempt})")
        hint("Закрой окно лаунчера КРЕСТИКОМ когда закончишь")
        print()
        try:
            r = subprocess.run(
                [java_bin, "-jar", str(jar_path)],
                env=env, check=False,
            )
            rc = r.returncode
        except FileNotFoundError:
            debug.dbg(f"java_bin не найден: {java_bin}", "ERR")
            err(f"Путь к Java больше не существует: {java_bin}")
            hint("Проверь install-java или удали ~/java и поставь заново")
            return False
        except Exception as e:
            debug.dbg_exc(e, "setup_legacy_portable/run")
            err(f"Не запустить: {e}")
            return False

        if rc == 0:
            ok("Legacy Launcher завершён")
            return True

        warn(f"Java завершилась с кодом {rc}")
        if attempt < MAX_LAUNCH_ATTEMPTS:
            try:
                again = input(f"{YELLOW}Попробовать ещё раз? [Y/n]: {RESET}").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                break
            if again not in ("", "y", "yes", "д", "да"):
                break

    print()
    info("Если в логе выше 'PKIX path building failed':")
    hint("Сертификаты Минцифры не попали в Java-truststore.")
    hint("Проверь: ls -la /etc/pki/ca-trust/extracted/java/cacerts")
    hint("Если файла нет: sudo update-ca-trust")
    hint("Если файл есть, но пустой: поставь CA Минцифры (см. README)")
    hint("Альтернатива: используй Prism Launcher (команда `prism`)")
    print()
    return False


def setup_legacy():
    """Legacy Launcher.

    .exe-установщик на Wine 11 стабильно падает с page fault в WOW64
    (баг Wine, не наш). Если .exe-версии в префиксе нет — сразу идём в
    Portable .jar, не тратя время на скачивание и запуск установщика.

    Перед скачиванием проверяем окружение: без Java portable-вариант
    физически не запустится, поэтому предупреждаем сразу и предлагаем
    установить JDK — а не роняем скрипт ошибкой в момент запуска.
    """
    info(f"{BOLD}Legacy Launcher{RESET}")

    # 0. Окружение: Legacy Portable = чистая Java. Без неё дальше идти смысла нет.
    java_bin, java_home, java_status = find_java()
    if not java_bin:
        warn(f"Java: {java_status}. Legacy Launcher Portable работает на Java.")
        try:
            answer = input(f"{MAGENTA}Скачать портативную JDK 17 сейчас? [Y/n]: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return False
        if answer in ("", "y", "yes", "д", "да"):
            if not install_portable_java():
                err("JDK установить не удалось — Legacy Launcher без Java не запустить.")
                hint("Попробуй позже: install-java, затем снова legacy")
                return False
            java_bin, java_home, java_status = find_java()
        else:
            hint("Отменено. Установи Java командой install-java, затем повтори legacy")
            return False

    # 1. Уже установлен через .exe-установщик?
    found = _find_legacy_installed()
    if found:
        ok(f"Legacy Launcher уже установлен: {found}")
        return True

    warn("Wine-установщик Legacy Launcher известен крашем на Wine 11 (WOW64)")
    info("Использую Portable (.jar) — работает без Wine")
    print()
    return setup_legacy_portable()


# ═══════════════════════════════════════════════════════════════════
#  FABRIC / FABULOUSLY OPTIMIZED
# ═══════════════════════════════════════════════════════════════════

def download_fabric_installer():
    installers_dir = WINE_DIR / "fabric"
    installers_dir.mkdir(parents=True, exist_ok=True)
    dest = installers_dir / "fabric-installer.jar"
    if dest.exists() and dest.stat().st_size > 100 * 1024:
        return dest
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(FABRIC_META, headers={"User-Agent": "wine-installer/2.5"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            data = json.loads(r.read().decode())
        latest = data[0].get("version", "1.0.1")
    except Exception:
        latest = "1.0.1"
    url = f"{FABRIC_MAVEN}/{latest}/fabric-installer-{latest}.jar"
    info(f"Скачиваю Fabric installer {latest}...")
    if download_file([("direct", url)], dest, "Fabric installer", min_size_mb=0):
        return dest
    return None


def install_fabric_loader(game_dir, mc_version, loader_version, java_bin="java"):
    installer = download_fabric_installer()
    if not installer:
        err("Fabric installer не скачан")
        return False
    game_dir = Path(game_dir)
    # Fabric installer refuse работать, если launcher directory не существует —
    # раньше это давало "Launcher directory not found" и установка молча падала.
    try:
        (game_dir / "versions").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        debug.dbg_exc(e, "install_fabric_loader/mkdir")
        err(f"Не создать каталог игры {game_dir}: {e}")
        return False
    expected_json = game_dir / "versions" / f"fabric-loader-{loader_version}-{mc_version}" / f"fabric-loader-{loader_version}-{mc_version}.json"
    info(f"Устанавливаю Fabric {loader_version} для MC {mc_version} в {game_dir}...")
    try:
        r = subprocess.run(
            [java_bin, "-jar", str(installer), "client",
             "-dir", str(game_dir),
             "-mcversion", mc_version,
             "-loader", loader_version,
             "-noprofile"],
            check=False, timeout=600, capture_output=True, text=True,
        )
        if r.returncode != 0:
            err(f"Fabric installer код {r.returncode}")
            out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
            if out:
                print(out[-800:])
            return False
        if not expected_json.exists():
            err(f"Профиль версии не создан: {expected_json}")
            return False
        ok(f"Fabric {loader_version} установлен")
        return True
    except FileNotFoundError:
        err("Java не найдена (путь битый). Установи: install-java")
        return False
    except Exception as e:
        debug.dbg_exc(e, "install_fabric_loader")
        err(f"Fabric: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#  ДОБОРКА ВЕРСИИ: vanilla jar + merged profile + assets index
#  Без этого лаунчер видит профиль, но игра не стартует
#  ("сборки не знают куда встать / появляются ошибки").
# ═══════════════════════════════════════════════════════════════════

def finish_version_install(game_dir, mc_version, version_id):
    """Доводит установку до конца: скачивает client.jar Mojang,
    объединяет профиль загрузчика с манифестом Minecraft и кладёт
    assets-index. Всё — строго в <game_dir>/versions/."""
    game_dir = Path(game_dir)
    vdir = game_dir / "versions" / version_id
    prof_path = vdir / f"{version_id}.json"
    if not prof_path.exists():
        err(f"Профиль не найден: {prof_path}")
        return False
    try:
        manifest = _http_get_json(MOJANG_VERSION_MANIFEST)
        entry = next(v for v in manifest["versions"] if v["id"] == mc_version)
        vm = _http_get_json(entry["url"], timeout=60)
    except Exception as e:
        debug.dbg_exc(e, "finish_version/mojang")
        warn(f"Mojang meta недоступна: {e}")
        hint("Версия уже лежит в versions/ — лаунчер может докачать сам при запуске.")
        return True

    try:
        profile = json.loads(prof_path.read_text(encoding="utf-8"))
    except Exception as e:
        debug.dbg_exc(e, "finish_version/read_profile")
        return False

    # Уже доведено ранее?
    if profile.get("inheritsFrom") == mc_version and profile.get("mainClass"):
        ok("Версия уже доведена (merged-профиль)")
    else:
        merged = dict(vm)
        merged["id"] = version_id
        merged["inheritsFrom"] = mc_version
        merged["jar"] = mc_version
        merged["mainClass"] = profile.get("mainClass", vm.get("mainClass"))
        merged["type"] = profile.get("type", "release")
        libs = []
        for l in profile.get("libraries", []) + vm.get("libraries", []):
            l = dict(l)
            l.pop("downloaders", None)
            libs.append(l)
        merged["libraries"] = libs
        prof_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        ok("Профиль объединён с манифестом Minecraft")

    # vanilla client.jar -> versions/<mc>/<mc>.jar
    jar_path = game_dir / "versions" / mc_version / f"{mc_version}.jar"
    dl = vm.get("downloads", {}).get("client", {})
    url = dl.get("url") or dl.get("raw", {}).get("url")   # старые версии имеют raw/server
    sha1 = dl.get("sha1") or dl.get("raw", {}).get("sha1")
    if url:
        jar_path.parent.mkdir(parents=True, exist_ok=True)
        if jar_path.exists() and sha1 and _sha1(jar_path) == sha1:
            ok("client.jar уже на месте")
        else:
            info(f"Скачиваю Minecraft {mc_version} client.jar (~40 МБ)...")
            if download_file([("Mojang", url)], jar_path, "Minecraft client", min_size_mb=5):
                if sha1 and _sha1(jar_path) != sha1:
                    warn("SHA-1 client.jar не совпал — удаляю битый файл")
                    try:
                        jar_path.unlink()
                    except Exception:
                        pass
                else:
                    ok("client.jar скачан и проверен")
            else:
                warn("client.jar не скачан — лаунчер докачает сам")
    # assets index -> assets/indexes/<id>.json
    assets = vm.get("assetIndex", {})
    a_url, a_id = assets.get("url"), assets.get("id")
    if a_url and a_id:
        a_path = game_dir / "assets" / "indexes" / f"{a_id}.json"
        a_path.parent.mkdir(parents=True, exist_ok=True)
        if not a_path.exists():
            info("Скачиваю индекс ресурсов (assets)...")
            if download_file([("Mojang", a_url)], a_path, "Assets index", min_size_mb=0):
                ok("Assets index скачан")
            else:
                warn("Assets index не скачан — не критично")
    # launcher_profiles.json — без него Legacy/TLauncher считают папку «не игрой»
    lp = game_dir / "launcher_profiles.json"
    if not lp.exists():
        lp.write_text(json.dumps({"profiles": {}, "clientToken": ""}, indent=2), encoding="utf-8")
        ok("Создан launcher_profiles.json")
    return True


def unpack_mrpack_to_game(mrpack_path, game_dir, java_bin="java"):
    info(f"{BOLD}Распаковка .mrpack{RESET}")
    try:
        with zipfile.ZipFile(mrpack_path, "r") as z:
            names = z.namelist()
            index_name = "modrinth.index.json"
            if index_name not in names:
                err("modrinth.index.json не найден")
                return False
            manifest = json.loads(z.read(index_name).decode("utf-8"))
    except Exception as e:
        debug.dbg_exc(e, "unpack_mrpack/open")
        err(f"Открыть .mrpack: {e}")
        return False
    deps = manifest.get("dependencies", {})
    mc_version = deps.get("minecraft")
    loader_version = deps.get("fabric-loader") or deps.get("quilt-loader")
    if not mc_version:
        err("Не найдена версия Minecraft")
        return False
    info(f"MC {mc_version}, Fabric {loader_version or 'не указан'}")
    version_id = None
    if loader_version:
        version_id = f"fabric-loader-{loader_version}-{mc_version}"
        if not install_fabric_loader(game_dir, mc_version, loader_version, java_bin):
            warn("Fabric installer не сработал")
            version_id = None
    files = manifest.get("files", [])
    info(f"Скачиваю {len(files)} файлов модов...")
    downloaded = 0
    failed = 0
    for entry in files:
        path = entry.get("path", "")
        env = entry.get("env", {})
        if env.get("client") == "unsupported":
            continue
        dest = game_dir / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        hashes = entry.get("hashes", {})
        sha512 = hashes.get("sha512")
        if dest.exists() and sha512:
            ok_hash, _ = verify_sha512(dest, sha512)
            if ok_hash:
                downloaded += 1
                continue
        urls = entry.get("downloads", [])
        if not urls:
            failed += 1
            continue
        if download_file([("direct", urls[0])], dest, path.split("/")[-1], min_size_mb=0, silent=True):
            if sha512:
                ok_hash, actual = verify_sha512(dest, sha512)
                if not ok_hash:
                    warn(f"  Хеш не совпал: {path}")
                    failed += 1
                    continue
            downloaded += 1
        else:
            failed += 1
    ok(f"Модов: {downloaded}, ошибок: {failed}")
    try:
        with zipfile.ZipFile(mrpack_path, "r") as z:
            for prefix in ["overrides/", "client-overrides/"]:
                for name in z.namelist():
                    if name.startswith(prefix) and not name.endswith("/"):
                        rel = name[len(prefix):]
                        if not rel:
                            continue
                        target = game_dir / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(name) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        ok("Overrides распакованы")
    except Exception as e:
        debug.dbg_exc(e, "unpack_mrpack/overrides")
        warn(f"Overrides: {e}")
    if version_id:
        info("Доводим установку версии до конца (vanilla jar + профиль)...")
        finish_version_install(game_dir, mc_version, version_id)
    return True


def _fo_is_release(tag, name=""):
    """True, если тег/имя — чистый релиз (не alpha/beta/rc/dev/nightly)."""
    s = f"{tag} {name}".lower()
    return not re.search(r"alpha|beta|rc\d|[_\-.]rc|dev|nightly|snapshot|pre", s)


def _pick_fo_release():
    """Ищет последний RELEASE Fabulously Optimized на официальном GitHub.

    Возвращает dict: tag, version, mc_versions, url, name, direct_url.
    Только release-версии: prerelease=False, draft отброшен, плюс фильтр
    по имени тега (v14.1.0 годится, v15.0.0-alpha.5 / beta — нет).
    """
    releases = _http_get_json(f"{FO_GITHUB_API}?per_page=100", timeout=30)
    best = None
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        tag = r.get("tag_name", "")
        if not _fo_is_release(tag):
            continue
        asset = next((a for a in r.get("assets", [])
                      if a["name"].endswith(".mrpack") and _fo_is_release(a["name"])), None)
        if not asset:
            continue
        cand = {
            "tag": tag,
            "version": tag.lstrip("v"),
            "mc_versions": [],
            "url": asset["browser_download_url"],
            "name": asset["name"],
            "size": asset.get("size", 0),
        }
        # сортировка по числовой части тега — берём самый свежий релиз
        nums = [int(x) for x in re.findall(r"\d+", tag)]
        key = tuple(nums + [0] * (6 - len(nums)))
        cand["_key"] = key
        if best is None or key > best["_key"]:
            best = cand
    if not best:
        raise RuntimeError("На GitHub нет ни одной release-версии FO")
    best.pop("_key")
    return best


def setup_fabulously_optimized():
    info(f"{BOLD}Скачивание Fabulously Optimized{RESET}")
    hint("Источник: официальный GitHub (только RELEASE, без alpha/beta)")
    try:
        rel = _pick_fo_release()
    except Exception as e:
        debug.dbg_exc(e, "setup_fo/github")
        err(f"GitHub API: {e}")
        return False
    info(f"Release: {rel['tag']} ({rel['name']}, {rel['size'] // 1024} КБ)")
    dest = WINE_DIR / rel["name"]
    mirrors = [("GitHub (официально)", rel["url"])] + make_github_mirrors(rel["url"])
    if not download_file(mirrors, dest, "Fabulously Optimized", min_size_mb=0):
        err("Не удалось скачать .mrpack ни с одного зеркала")
        return False
    # проверка целостности по modrinth.index.json внутри архива
    try:
        with zipfile.ZipFile(dest, "r") as z:
            m = json.loads(z.read("modrinth.index.json").decode("utf-8"))
        deps = m.get("dependencies", {})
        if not deps.get("minecraft"):
            raise RuntimeError("нет версии minecraft в манифесте")
    except Exception as e:
        debug.dbg_exc(e, "setup_fo/validate")
        err(f"Скачанный файл повреждён: {e}")
        try:
            dest.unlink()
        except Exception:
            pass
        return False
    ok(f"Скачано: {dest}")

    # ── Куда ставить: ищем реальные .minecraft / game на системе ──
    found = choose_minecraft_dir(auto=True)
    if found is None:
        warn("Папка .minecraft (или game у Legacy) не найдена на системе.")
        print()
        info("Варианты:")
        hint("1. Запусти любой лаунчер (legacy / Prism) один раз — он создаст папку игры")
        hint("2. Укажи путь вручную")
        try:
            manual = input(f"{YELLOW}Путь к .minecraft (Enter — отказаться): {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            manual = ""
        if manual and Path(manual).expanduser().is_dir():
            found = Path(manual).expanduser()
        elif manual:
            err("Такой папки нет")
        else:
            hint(f"Скачанный .mrpack лежит тут: {dest}")
            hint("Распакуешь позже сам или повтори `fo` после запуска лаунчера.")
            return True
    game_dir = Path(found)
    (game_dir / "versions").mkdir(parents=True, exist_ok=True)
    ok(f"Директория игры: {game_dir}")

    java_bin, java_home, java_status = find_java()
    if not java_bin:
        warn("Java не найдена. Fabric installer требует Java.")
        hint("Установи: install-java (пункт 6 этого меню)")
        hint(f".mrpack уже скачан: {dest}")
        return True
    info(f"Java: {java_bin}")
    unpack_mrpack_to_game(dest, game_dir, java_bin)
    hint("Готово! Версия Fabric появится в лаунчере")
    return True


# ═══════════════════════════════════════════════════════════════════
#  OPTIFINE
# ═══════════════════════════════════════════════════════════════════

def _optifine_versions_from_html(html):
    """[(mc_ver, opti_ver), ...] в порядке страницы (свежие сверху)."""
    out = []
    seen = set()
    for m in re.finditer(r'OptiFine_(\d+\.\d+(?:\.\d+)?)_HD_U_([A-Z]\w+)\.jar', html):
        key = (m.group(1), m.group(2))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def setup_optifine():
    info(f"{BOLD}Скачивание OptiFine{RESET}")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(OPTIFINE_PAGE, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        debug.dbg_exc(e, "setup_optifine/page")
        err(f"Страница: {e}")
        return False
    versions = _optifine_versions_from_html(html)
    if not versions:
        err("На странице OptiFine не найдено ни одной версии")
        hint("Возможно, сайт отдал заглушку/антибот. Попробуй позже.")
        return False

    # ── Куда ставить: ищем реальные .minecraft / game на системе ──
    found = choose_minecraft_dir(auto=True)
    if found is None:
        warn("Папка .minecraft (или game у Legacy) не найдена на системе.")
        try:
            manual = input(f"{YELLOW}Путь к .minecraft (Enter — отказаться): {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            manual = ""
        if manual and Path(manual).expanduser().is_dir():
            found = Path(manual).expanduser()
        else:
            if manual:
                err("Такой папки нет")
            hint("Запусти сначала любой лаунчер — он создаст папку игры.")
            return False
    game_dir = Path(found)
    ok(f"Директория игры: {game_dir}")

    # ── Подбор версии под уже установленные в games/versions ──
    installed = []
    vdir = game_dir / "versions"
    if vdir.is_dir():
        installed = sorted((d.name for d in vdir.iterdir() if d.is_dir()), reverse=True)
    mc_in_installed = []
    for name in installed:
        for m in re.finditer(r"(\d+\.\d+(?:\.\d+)?)", name):
            if m.group(1) not in mc_in_installed:
                mc_in_installed.append(m.group(1))
    pick = None
    for mc_ver, opti_ver in versions:              # свежие релизы OptiFine сверху
        if mc_ver in mc_in_installed:
            pick = (mc_ver, opti_ver)
            break
    if pick:
        info(f"Подобрал версию под установленную в игре: MC {pick[0]}")
    else:
        pick = versions[0]
        if installed:
            warn("Точного совпадения с версиями в games/versions нет — беру свежий OptiFine")
        info(f"MC {pick[0]}, OptiFine HD U {pick[1]}")
        try:
            ans = input(f"{YELLOW}Сменить версию? [y/N]: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            ans = "n"
        if ans in ("y", "д", "да"):
            print("Доступные (первые 15):")
            shown = versions[:15]
            for i, (mv, ov) in enumerate(shown, 1):
                print(f"  {CYAN}{i}{RESET}) MC {mv}, HD U {ov}")
            try:
                c = int(input("Номер: ").strip()) - 1
                if 0 <= c < len(shown):
                    pick = shown[c]
            except (ValueError, IndexError, KeyboardInterrupt, EOFError):
                pass
    mc_ver, opti_ver = pick
    fname = f"OptiFine_{mc_ver}_HD_U_{opti_ver}.jar"
    url = f"http://optifine.net/adloadx?f={fname}"
    dest = WINE_DIR / fname
    if not download_file([("direct", url)], dest, "OptiFine", min_size_mb=0):
        err("Не удалось скачать")
        return False
    # скачанный "jar" с adloadx иногда оказывается HTML-заглушкой
    head = b""
    try:
        with open(dest, "rb") as f:
            head = f.read(4)
    except Exception:
        pass
    if head != b"PK\x03\x04":
        err("Скачался не JAR (похоже на страницу-заглушку optifine.net)")
        hint("Открой браузером https://optifine.net/downloads, скачай вручную,")
        hint(f"положи файл в {WINE_DIR} и повтори команду — файл уже будет там.")
        try:
            dest.unlink()
        except Exception:
            pass
        return False
    ok(f"Скачано: {dest}")
    java_bin, java_home, java_status = find_java()
    if not java_home:
        warn(f"Java: {java_status}")
        hint("Для OptiFine installer нужна Java с GUI (AWT).")
        try:
            answer = input(f"{MAGENTA}Скачать портативную JDK 17? [Y/n]: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            answer = "n"
        if answer in ("", "y", "yes", "д", "да"):
            if not install_portable_java():
                return False
            java_bin, java_home, java_status = find_java()
        if not java_home:
            err("Java с GUI так и не найдена")
            return False
    if java_bin is None:
        err("Java не найдена")
        return False
    ok(f"Java: {java_home or java_bin} ({java_status})")
    game_path = str(game_dir)
    clipboard_ok = copy_to_clipboard(game_path)
    info("Запускаю установщик OptiFine...")
    print()
    print(f"{BOLD}В поле 'Folder' вставь путь:{RESET}")
    print(f"  {CYAN}{game_path}{RESET}")
    if clipboard_ok:
        ok("Путь уже в буфере обмена (Ctrl+V в поле Folder)")
    else:
        hint("Выдели и скопируй вручную")
    print()
    try:
        subprocess.run([java_bin, "-jar", str(dest)], check=False)
    except FileNotFoundError:
        err("Не запустить: битый путь к Java. Установи заново: install-java")
        return False
    except Exception as e:
        debug.dbg_exc(e, "setup_optifine/run")
        err(f"Не запустить: {e}")
        return False

    # ── Проверяем результат и добираем недостающее ──
    of_vdir = game_dir / "versions" / f"OptiFine_{mc_ver}"
    of_json = game_dir / "versions" / f"OptiFine_{mc_ver}_HD_U_{opti_ver}" / \
        f"OptiFine_{mc_ver}_HD_U_{opti_ver}.json"
    created = [p for p in (of_vdir, of_json) if p.exists()]
    # установщик мог создать профиль с другим именем — ищем любой новый OptiFine json
    if not created:
        cand = list((game_dir / "versions").glob("OptiFine*/*.json")) if (game_dir / "versions").is_dir() else []
        if cand:
            created = cand
    if created:
        prof_path = Path(created[-1]) if isinstance(created[-1], Path) else None
        ok(f"OptiFine установлен: {prof_path.parent.name if prof_path else 'профиль создан'}")
        version_id = prof_path.stem if prof_path else f"OptiFine_{mc_ver}_HD_U_{opti_ver}"
        finish_version_install(game_dir, mc_ver, version_id)
        hint("Готово! Выбери эту версию в лаунчере")
    else:
        warn("Похоже, установка в окне OptiFine не завершилась (профиль не создан).")
        hint("Запусти установщик ещё раз и в поле Folder вставь путь выше;")
        hint("кнопка Install должна сказать 'OptiFine is installed successfully'.")
    return True


# ═══════════════════════════════════════════════════════════════════
#  МЕНЮ
# ═══════════════════════════════════════════════════════════════════

def cmd_minecraft():
    while True:
        print(f"\n{BOLD}═══════ MINECRAFT ═══════{RESET}")
        print(f"  {CYAN}1{RESET}) Prism Launcher (Linux)")
        print(f"  {CYAN}2{RESET}) Legacy Launcher (Portable .jar)")
        print(f"  {CYAN}3{RESET}) Fabulously Optimized (скачать + распаковать)")
        print(f"  {CYAN}4{RESET}) OptiFine (скачать + установить)")
        print(f"  {CYAN}5{RESET}) Показать пути")
        print(f"  {CYAN}6{RESET}) Установить Java (для OptiFine)")
        print(f"  {CYAN}0{RESET}) Назад")
        try:
            choice = input(f"{YELLOW}Выбор: {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if choice == "1":
            setup_prism()
        elif choice == "2":
            setup_legacy()
        elif choice == "3":
            setup_fabulously_optimized()
        elif choice == "4":
            setup_optifine()
        elif choice == "5":
            from modules.prefix import show_minecraft_paths
            show_minecraft_paths()
        elif choice == "6":
            cmd_install_java()
        elif choice == "0":
            return
        else:
            warn("Неверный выбор")
