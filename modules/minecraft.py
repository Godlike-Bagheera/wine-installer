"""Prism, Legacy, Fabulously Optimized, OptiFine, Fabric."""
import os
import re
import ssl
import json
import shutil
import tarfile
import zipfile
import subprocess
import urllib.request
from pathlib import Path
from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, YELLOW, MAGENTA, BOLD, RESET
from modules.config import (
    WINE_DIR, PRISM_DIR, PRISM_URL, WINE_BIN, WINE_PREFIX,
    MODRINTH_FO_API, OPTIFINE_PAGE, FABRIC_META, FABRIC_MAVEN,
    LEGACY_MIRRORS, LEGACY_JAR_MIRRORS, LEGACY_JAR_MIN_SIZE,
    SYSTEM_TRUSTSTORE_PATHS, SYSTEM_TRUSTSTORE_PASSWORD,
)
from modules.download import download_file
from modules.hash_utils import verify_sha512, copy_to_clipboard
from modules.java import find_java, install_portable_java, cmd_install_java
from modules.prefix import get_minecraft_game_path, ensure_prefix, get_wine_env


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
            hint("Скачай вручную: https://llaun.ch/jar")
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

    # 6. Запуск
    info("Запускаю Legacy Launcher Portable...")
    hint("Закрой окно лаунчера КРЕСТИКОМ когда закончишь")
    print()
    try:
        r = subprocess.run(
            [java_bin, "-jar", str(jar_path)],
            env=env, check=False,
        )
    except Exception as e:
        debug.dbg_exc(e, "setup_legacy_portable/run")
        err(f"Не запустить: {e}")
        return False
    if r.returncode != 0:
        warn(f"Java завершилась с кодом {r.returncode}")
        print()
        info("Если в логе выше 'PKIX path building failed':")
        hint("Сертификаты Минцифры не попали в Java-truststore.")
        hint("Проверь: ls -la /etc/pki/ca-trust/extracted/java/cacerts")
        hint("Если файла нет: sudo update-ca-trust")
        hint("Если файл есть, но пустой: поставь CA Минцифры (см. README)")
        hint("Альтернатива: используй Prism Launcher (команда `prism`)")
        print()
    else:
        ok("Legacy Launcher завершён")
    return True


def setup_legacy():
    """Legacy Launcher.

    .exe-установщик на Wine 11 стабильно падает с page fault в WOW64
    (баг Wine, не наш). Если .exe-версии в префиксе нет — сразу идём в
    Portable .jar, не тратя время на скачивание и запуск установщика.
    """
    info(f"{BOLD}Legacy Launcher{RESET}")

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
    info(f"Устанавливаю Fabric {loader_version} для MC {mc_version}...")
    try:
        r = subprocess.run(
            [java_bin, "-jar", str(installer), "client",
             "-dir", str(game_dir),
             "-mcversion", mc_version,
             "-loader", loader_version,
             "-noprofile"],
            check=False, timeout=300, capture_output=True, text=True,
        )
        if r.returncode == 0:
            ok(f"Fabric {loader_version} установлен")
            return True
        err(f"Fabric installer код {r.returncode}")
        if r.stdout:
            print(r.stdout[-500:])
        if r.stderr:
            print(r.stderr[-500:])
        return False
    except Exception as e:
        debug.dbg_exc(e, "install_fabric_loader")
        err(f"Fabric: {e}")
        return False


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
    if loader_version:
        if not install_fabric_loader(game_dir, mc_version, loader_version, java_bin):
            warn("Fabric installer не сработал")
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
    return True


def setup_fabulously_optimized():
    info(f"{BOLD}Скачивание Fabulously Optimized{RESET}")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(MODRINTH_FO_API, headers={"User-Agent": "wine-installer/2.5"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            versions = json.loads(r.read().decode())
    except Exception as e:
        debug.dbg_exc(e, "setup_fo/api")
        err(f"Modrinth API: {e}")
        return False
    latest = None
    for v in versions:
        if v.get("version_type") == "release":
            latest = v
            break
    if not latest:
        err("Release-версия не найдена")
        return False
    mrpack_url = mrpack_name = mrpack_sha512 = None
    for f in latest.get("files", []):
        if f["filename"].endswith(".mrpack"):
            mrpack_url = f["url"]
            mrpack_name = f["filename"]
            mrpack_sha512 = f.get("hashes", {}).get("sha512")
            break
    if not mrpack_url or not mrpack_name:
        err(".mrpack не найден")
        return False
    info(f"Версия {latest['version_number']} для MC {', '.join(latest.get('game_versions', ['?']))}")
    dest = WINE_DIR / mrpack_name
    if not download_file([("direct", mrpack_url)], dest, "Fabulously Optimized", min_size_mb=0):
        return False
    if mrpack_sha512:
        info("Проверяю контрольную сумму...")
        ok_hash, actual = verify_sha512(dest, mrpack_sha512)
        if ok_hash:
            ok("Хеш совпал")
        else:
            err("Хеш НЕ совпал!")
            hint("Файл повреждён. Удали и скачай заново.")
            return False
    ok(f"Скачано: {dest}")

    game_dir = Path(get_minecraft_game_path())
    if not game_dir.exists():
        warn("Папка game не найдена — Legacy Launcher ещё не создал структуру.")
        print()
        info("Что нужно сделать:")
        hint("1. Запусти Legacy Launcher (команда `legacy`)")
        hint("2. В окне лаунчера выбери версию MC и нажми Установить")
        hint("3. Дождись создания папки game/")
        hint("4. Закрой лаунчер КРЕСТИКОМ (не Ctrl+C)")
        hint("5. Вернись сюда и повтори `fo` или `minecraft → 3`")
        print()
        hint(f"Скачанный .mrpack лежит тут: {dest}")
        return True

    print(f"{BOLD}Куда распаковать?{RESET}")
    print(f"  {CYAN}1{RESET}) В Legacy Launcher (game/)")
    print(f"  {CYAN}2{RESET}) Только скачать, распакую сам")
    try:
        choice = input(f"{YELLOW}Выбор [1]: {RESET}").strip() or "1"
    except (KeyboardInterrupt, EOFError):
        return True
    if choice == "1":
        java_bin, java_home, _ = find_java()
        if not java_bin:
            warn("Java не найдена. Fabric installer требует Java.")
            hint("Установи: install-java")
            return True
        unpack_mrpack_to_game(dest, game_dir, java_bin)
        hint("Готово! Версия Fabric появится в Legacy Launcher")
    else:
        hint("Файл лежит: " + str(dest))
    return True


# ═══════════════════════════════════════════════════════════════════
#  OPTIFINE
# ═══════════════════════════════════════════════════════════════════

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
    match = re.search(r'OptiFine_(\d+\.\d+(?:\.\d+)?)_HD_U_([A-Z]\d+)\.jar', html)
    if not match:
        err("Версия OptiFine не найдена")
        return False
    mc_ver = match.group(1)
    opti_ver = match.group(2)
    fname = f"OptiFine_{mc_ver}_HD_U_{opti_ver}.jar"
    url = f"http://optifine.net/adloadx?f={fname}"
    info(f"MC {mc_ver}, OptiFine HD U {opti_ver}")
    dest = WINE_DIR / fname
    if not download_file([("direct", url)], dest, "OptiFine", min_size_mb=0):
        err("Не удалось скачать")
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
    game_path = get_minecraft_game_path()
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
    except Exception as e:
        debug.dbg_exc(e, "setup_optifine/run")
        err(f"Не запустить: {e}")
        return False
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