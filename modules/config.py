"""Все константы и пути. Никакой логики — только данные."""
import os
import re
import json
from pathlib import Path

# ВАЖНО: modules.debug импортирует из этого модуля DEBUG_LOG/LOG_DIR,
# поэтому верхнеуровневый `from modules import debug` здесь вызвал бы
# циклический импорт. Локальный импорт внутри except — намеренный.
# NOTE: keep this comment in sync if the import layout changes (CI marker v2).


# Прокси-зеркала GitHub (порядок = приоритет).
# Базовые значения; пользователь может переопределить список зеркал в
# settings.json без правки кода (см. gh_proxies()).
_GH_PROXIES = [
    ("ghfast.top",   "https://ghfast.top/"),
    ("ghproxy.net",  "https://ghproxy.net/"),
    ("gh-proxy.com", "https://gh-proxy.com/"),
]

# Файл настроек известен здесь заранее (config не импортирует settings.py,
# но умеет читать из него безопасные user-overrides). Реальный путь —
# WINE_DIR/settings.json (см. ниже); на время чтения overrides используется
# угаданный HOME, а после определения HOME путь пересчитывается.
SETTINGS_FILE = Path.home() / "wine-portable" / "settings.json"


def _user_settings():
    """Кэш settings.json для user-overrides (обновляется при save_settings).

    Назначение: ротация прокси-ключей без правки кода — достаточно поменять
    "gh_proxies" или "log_keep_days" в ~/wine-portable/settings.json.
    Любая ошибка файла — тихий откат к дефолтам.
    """
    if not getattr(_user_settings, "_loaded", False):
        data = {}
        try:
            if SETTINGS_FILE.exists():
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = raw
        except Exception:
            data = {}
        _user_settings._data = data
        _user_settings._loaded = True
    return _user_settings._data


def reload_user_settings():
    """Сброс кэша overrides (вызывается из settings.save_settings)."""
    _user_settings._loaded = False


def gh_proxies():
    """Список GitHub-прокси с учётом overrides из settings.json.

    Формат override: ["https://proxy1/", ...] или
    [["имя", "https://proxy1/"], ...]. Пустой/битый список -> дефолт.
    """
    raw = _user_settings().get("gh_proxies")
    if not isinstance(raw, list) or not raw:
        return list(_GH_PROXIES)
    out = []
    for item in raw:
        if isinstance(item, str) and item.startswith("http"):
            m = re.match(r"https?://([^/]+)", item)
            out.append((m.group(1), item if item.endswith("/") else item + "/"))
        elif (isinstance(item, (list, tuple)) and len(item) == 2
              and all(isinstance(x, str) for x in item)):
            out.append((item[0], item[1]))
    return out or list(_GH_PROXIES)


# ---------- ПУТИ ----------


def _resolve_home():
    """Определяет домашнюю папку надёжным способом.

    Path.home() берёт переменную окружения HOME, которая может указывать
    на несуществующий путь (например, /nonexistent у системных пользователей).
    Сначала пробуем HOME из окружения, затем passwd-запись пользователя —
    в ход идёт только реально существующая директория.
    """
    env_home = Path.home()
    if env_home.is_dir():
        return env_home
    try:
        import pwd
        pw_dir = Path(pwd.getpwuid(os.getuid()).pw_dir)
        if pw_dir.is_dir():
            return pw_dir
    except Exception as e:
        # локальный импорт — иначе циклический импорт config <-> debug
        from modules import debug
        debug.dbg_exc(e, "config")
    return env_home


HOME = _resolve_home()
WINE_DIR = HOME / "wine-portable"
LOG_DIR = WINE_DIR / "logs"
DEBUG_LOG = LOG_DIR / "debug.log"

BIN_DIR = WINE_DIR / "bin"
GAMES_DIR = HOME / "games"
PRISM_DIR = HOME / "prism"
JAVA_DIR = HOME / "java"
SHORTCUTS_DIR = WINE_DIR / "shortcuts"
PREFIXES_DIR = WINE_DIR / "prefixes"
DEFAULT_PREFIX = WINE_DIR / "prefix"
WINE_PREFIX = DEFAULT_PREFIX              # backward-compat алиас

HISTORY_FILE = WINE_DIR / "history.json"
CACHE_FILE = WINE_DIR / ".mirror_cache"
# SETTINGS_FILE уже был объявлен в начале файла (для user-overrides) —
# пересчитываем на надёжный HOME и сбрасываем кэш, чтобы overrides
# перечитались с правильного пути.
SETTINGS_FILE = WINE_DIR / "settings.json"
reload_user_settings()

WINE_BIN = WINE_DIR / "wine.AppImage"
RUNEXE = WINE_DIR / "runexe"
DXVK_DIR = WINE_DIR / "dxvk"
WINETRICKS_BIN = BIN_DIR / "winetricks"
ARIA2C_BIN = BIN_DIR / "aria2c"

DESKTOP_DIRS = [HOME / "Рабочий стол", HOME / "Desktop"]

# Приоритетные папки для поиска .exe.
PRIORITY_DIRS = [
    HOME / "Загрузки", HOME / "Downloads",
    HOME / "Рабочий стол", HOME / "Desktop",
    HOME / "games", HOME / "Игры",
    WINE_PREFIX / "drive_c",
]

EXCLUDE_DIRS = {
    ".wine", ".wine-appimage-stable", "wine-portable", ".cache", ".local", ".config",
    ".mozilla", ".thunderbird", ".steam", ".var", ".npm",
    ".cargo", ".rustup", ".dotnet", ".gradle", ".m2",
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "snap", "flatpak", "Trash", ".Trash", ".Trash-1000",
    ".thumbnails", "target", "build", "dist",
}

SUPPORTED_EXT = (".exe", ".lnk", ".msi")

# ---------- НАСТРОЙКИ ЗАГРУЗКИ / ПОВЕДЕНИЯ (runtime-флаги) ----------
# Дефолты; реальные значения берёт settings.apply_settings() из
# settings.json (DEFAULT_SETTINGS ниже), а носителями в рантайме служат
# флаги modules/state.py. Константы здесь — только стартовые значения.
MIN_SPEED_KB = 30
SPEED_TEST_SECONDS = 10
CONNECT_TIMEOUT = 60
SPEED_CHECK_MIN_MB = 50
SLOW_MODE_AFTER = 2

AUTO_FIX = True
MAX_RETRIES = 3
OK_RUN_SECONDS = 60
CRASH_SHOW_LOG_SECONDS = 25

MIN_WINETRICKS_SIZE = 100 * 1024
MIN_ARIA2C_SIZE = 500 * 1024

DXVK_OVERRIDES = "d3d11,dxgi,d3d9,d3d10core=n,b"

USE_PER_GAME_PREFIX = False
USE_DXVK_HUD = False
USE_MANGOHUD = False
USE_GAMESCOPE = False
USE_TTS_NOTIFY = False
LOG_KEEP_DAYS = 30

CURRENT_VERSION = "2.6"

# Все пользовательские опции — отсюда; меню `settings` и state.* их читают.
DEFAULT_SETTINGS = {
    "quiet_mode": False,
    "use_gamemode": False,
    "debug_mode": False,
    "use_dxvk_hud": False,
    "use_mangohud": False,
    "use_gamescope": False,
    "use_tts_notify": False,
    "use_per_game_prefix": False,
    "log_keep_days": 30,
}

# ---------- КОМАНДЫ ----------
EXPECTED_COMMANDS = [
    "help", "exit", "minecraft", "download", "fonts", "steamfix",
    "gamemode", "history", "log", "quiet", "reset", "dxvk",
    "desktop", "vulkan", "settings", "bin", "verify", "update",
    "debug", "debugreport", "install-java",
    "fo", "optifine", "prism", "legacy",
    "export", "gpu-temp", "freegames",
    "worlds", "saveworlds", "loadworlds",
    "gamestatus", "stopgame", "waitgame", "games", "shaders",
    "fo-autofix",
]

# ---------- SYSTEM TRUSTSTORE ДЛЯ JAVA ----------
# Java использует свой cacerts в $JAVA_HOME/lib/security/, и русские
# корневые сертификаты (Минцифры) туда не попадают. Системные CA лежат
# в /etc/pki/... (RHEL-семейство) или /etc/ssl/... (Debian-семейство).
# Перебираем по порядку — берём первый существующий и достаточно большой.
SYSTEM_TRUSTSTORE_PATHS = [
    "/etc/pki/ca-trust/extracted/java/cacerts",   # Red OS / RHEL / Fedora
    "/etc/ssl/certs/java/cacerts",                # Debian / Ubuntu / Arch
    "/var/lib/ca-certificates/java-cacerts",      # openSUSE
    "/usr/lib/jvm/java-17-openjdk/lib/security/cacerts",
    "/usr/lib/jvm/java-11-openjdk/lib/security/cacerts",
    "/usr/lib/jvm/java-8-openjdk/lib/security/cacerts",
]

# Пароль системного cacerts от update-ca-trust
SYSTEM_TRUSTSTORE_PASSWORD = "changeit"

# ---------- ЗЕРКАЛА ----------
WINE_MIRRORS = [
    ("ghfast.top",       "https://ghfast.top/https://github.com/mmtrt/WINE_AppImage/releases/download/continuous-stable/wine-stable_11.0-x86_64.AppImage"),
    ("ghproxy.net",      "https://ghproxy.net/https://github.com/mmtrt/WINE_AppImage/releases/download/continuous-stable/wine-stable_11.0-x86_64.AppImage"),
    ("gh-proxy.com",     "https://gh-proxy.com/https://github.com/mmtrt/WINE_AppImage/releases/download/continuous-stable/wine-stable_11.0-x86_64.AppImage"),
    ("ghproxy.cc",       "https://ghproxy.cc/https://github.com/mmtrt/WINE_AppImage/releases/download/continuous-stable/wine-stable_11.0-x86_64.AppImage"),
    ("gh.llkk.cc",       "https://gh.llkk.cc/https://github.com/mmtrt/WINE_AppImage/releases/download/continuous-stable/wine-stable_11.0-x86_64.AppImage"),
    ("GitHub (прямой)",  "https://github.com/mmtrt/WINE_AppImage/releases/download/continuous-stable/wine-stable_11.0-x86_64.AppImage"),
]

DXVK_VERSIONS = ["v2.4.1", "v2.3.1", "v2.4", "v2.3"]

WINETRICKS_MIRRORS = [
    ("ghfast.top",                "https://ghfast.top/https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"),
    ("ghproxy.net",               "https://ghproxy.net/https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"),
    ("gh-proxy.com",              "https://gh-proxy.com/https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"),
    ("gh.llkk.cc",                "https://gh.llkk.cc/https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"),
    ("raw.githubusercontent.com", "https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"),
]

ARIA2C_MIRRORS = [
    ("ghfast.top",       "https://ghfast.top/https://github.com/P3TERX/aria2-builder/releases/download/1.35.0_2020.09.04/aria2-1.35.0-static-linux-amd64.tar.gz"),
    ("ghproxy.net",      "https://ghproxy.net/https://github.com/P3TERX/aria2-builder/releases/download/1.35.0_2020.09.04/aria2-1.35.0-static-linux-amd64.tar.gz"),
    ("gh-proxy.com",     "https://gh-proxy.com/https://github.com/P3TERX/aria2-builder/releases/download/1.35.0_2020.09.04/aria2-1.35.0-static-linux-amd64.tar.gz"),
    ("gh.llkk.cc",       "https://gh.llkk.cc/https://github.com/P3TERX/aria2-builder/releases/download/1.35.0_2020.09.04/aria2-1.35.0-static-linux-amd64.tar.gz"),
    ("GitHub (P3TERX)",  "https://github.com/P3TERX/aria2-builder/releases/download/1.35.0_2020.09.04/aria2-1.35.0-static-linux-amd64.tar.gz"),
]

JDK_MIRRORS = [
    ("ghfast.top",       "https://ghfast.top/https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_linux_hotspot_17.0.13_11.tar.gz"),
    ("ghproxy.net",      "https://ghproxy.net/https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_linux_hotspot_17.0.13_11.tar.gz"),
    ("gh-proxy.com",     "https://gh-proxy.com/https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_linux_hotspot_17.0.13_11.tar.gz"),
    ("gh.llkk.cc",       "https://gh.llkk.cc/https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_linux_hotspot_17.0.13_11.tar.gz"),
    ("GitHub (прямой)",  "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_linux_hotspot_17.0.13_11.tar.gz"),
]

PRISM_URL = "https://github.com/PrismLauncher/PrismLauncher/releases/download/11.0.3/PrismLauncher-Linux-Qt6-Portable-11.0.3.tar.gz"

# ─────────────────────────────────────────────────────────────
# Legacy Launcher — .exe-установщик.
# Официальная ссылка есть, но .exe всё равно падает в Wine 11 (WOW64).
# Реально используется Portable .jar.
# ─────────────────────────────────────────────────────────────
LEGACY_MIRRORS = [
    ("legacylauncher.ru (официальный)",
     "https://dl.legacylauncher.ru/legacy/installer"),
    ("GitHub (gradenGnostic)",
     "https://github.com/gradenGnostic/LegacyLauncher/releases/download/v3.5.0/LegacyLauncher.Setup.3.5.0.exe"),
    ("ghfast.top",
     "https://ghfast.top/https://github.com/gradenGnostic/LegacyLauncher/releases/download/v3.5.0/LegacyLauncher.Setup.3.5.0.exe"),
    ("ghproxy.net",
     "https://ghproxy.net/https://github.com/gradenGnostic/LegacyLauncher/releases/download/v3.5.0/LegacyLauncher.Setup.3.5.0.exe"),
    ("gh-proxy.com",
     "https://gh-proxy.com/https://github.com/gradenGnostic/LegacyLauncher/releases/download/v3.5.0/LegacyLauncher.Setup.3.5.0.exe"),
    ("Archive.org",
     "https://archive.org/download/legacy-launcher-for-minecraft/LegacyLauncher_Installer_legacy.exe"),
]

LEGACY_URL = LEGACY_MIRRORS[0][1]

# ─────────────────────────────────────────────────────────────
# Legacy Launcher Portable (.jar) — автоскачивание.
# ─────────────────────────────────────────────────────────────
LEGACY_JAR_MIRRORS = [
    # Официальная прямая ссылка скачивания с сайта Legacy Launcher
    # (отдаёт Portable .jar, поддерживает Range — можно докачивать).
    ("dl.legacylauncher.ru (официальный installer)",
     "https://dl.legacylauncher.ru/legacy/installer"),
    ("go.legacylauncher.ru (официальный)", "https://go.legacylauncher.ru/jar"),
    ("llaun.ch (официальный)",           "https://llaun.ch/jar"),
    ("dl.llaun.ch (прямой)",             "https://dl.llaun.ch/legacy/bootstrap"),
    ("lln4.cc",                          "https://lln4.cc/jar"),
]
LEGACY_JAR_MIN_SIZE = 1 * 1024 * 1024   # реальный .jar ~ 2-5 МБ

# ─────────────────────────────────────────────────────────────
# Wine Mono — НЕ используется (Wine сам предлагает установку).
# ─────────────────────────────────────────────────────────────
WINE_MONO_PATH = Path.home() / ".cache" / "wine" / "wine-mono-9.0.0-x86.msi"
WINE_MONO_MIN_SIZE = 50 * 1024 * 1024

WINE_MONO_MIRRORS = [
    ("GitHub (wine-mono)",
     "https://github.com/wine-mono/wine-mono/releases/download/wine-mono-9.0.0/wine-mono-9.0.0-x86.msi"),
    ("ghfast.top",
     "https://ghfast.top/https://github.com/wine-mono/wine-mono/releases/download/wine-mono-9.0.0/wine-mono-9.0.0-x86.msi"),
    ("WineHQ (прямой)",
     "https://dl.winehq.org/wine/wine-mono/9.0.0/wine-mono-9.0.0-x86.msi"),
]

# Fabulously Optimized — официальный источник: GitHub Releases.
# Скачиваются ТОЛЬКО release-версии (не alpha/beta/rc): фильтруем по
# prerelease=False и additional фильтрами в именах тегов/файлов.
FO_GITHUB_API = "https://api.github.com/repos/Fabulously-Optimized/fabulously-optimized/releases"
FO_MODRINTH_API = "https://api.modrinth.com/v2/project/fabulously-optimized/version"
OPTIFINE_PAGE = "https://optifine.net/downloads"
FABRIC_META = "https://meta.fabricmc.net/v2/versions/installer"
FABRIC_MAVEN = "https://maven.fabricmc.net/net/fabricmc/fabric-installer"

# Fabric meta API — профили версий (для установки БЕЗ Java, если installer
# недоступен) и maven-репозиторий библиотек.
FABRIC_META_API = "https://meta.fabricmc.net/v2"
MAVEN_FABRIC = "https://maven.fabricmc.net/"
MAVEN_CENTRAL = "https://repo1.maven.org/maven2/"

# Mojang — списки версий и клиентские jar'ы (для доведения версии до конца,
# чтобы лаунчер видел установленный модпак целиком).
MOJANG_VERSION_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
MOJANG_RESOURCES = "https://resources.download.minecraft.net/"


def _gh_mirror_list(base_url, direct_name="GitHub (прямой)"):
    """base_url + прокси-зеркала из gh_proxies() (+ прямой адрес в конце)."""
    return gh_proxies() + [(direct_name, base_url)]


def make_github_mirrors(url):
    """Оборачивает ссылку github.com прокси-зеркалами (для плохих сетей).

    Прокси умеют отдавать ассеты GitHub Releases — поддерживаются все
    форматы ссылок:
      - github.com/<owner>/<repo>/releases/download/<tag>/<file>
        (конкретный релиз);
      - github.com/<owner>/<repo>/releases/latest/download/<file>
        (последний релиз, используется в офлайн-каталоге шейдеров);
      - ghuser.io/<owner>/<repo>@<tag>/<file> — сокращённые ссылки
        (встречаются в конфигах модпаков);
      - адреса с портом (github.com:8080/...) и редирект-пути
        (/releases/latest/..., /releases/tag/...).
    Для api.github.com и прочих URL возвращают пустой список — качаем прямо.
    """
    # Сокращённая форма ghuser/repo@tag/file — свои зеркала.
    canonical = _short_github_form(url)
    if canonical:
        return [(name, f"{prefix}{canonical}") for name, prefix in gh_proxies()]

    if "github.com" not in url:
        return []
    # Только API — прокси не нужны (и ломают запрос), качаем прямо.
    no_scheme = re.sub(r"^\w+://", "", url).lower()
    if no_scheme.startswith("api.github.com") or "://api.github.com" in url.lower():
        return []
    # Раньше путь вырезался жадным регэкспом «(.+?)/releases», из-за чего
    # адреса с портом (github.com:8080/owner/repo/releases/...) давали битые
    # зеркала (owner/repo:8080). Теперь host и path разделяются явно, а
    # owner/repo берётся non-greedily до '/releases'.
    m = re.search(r"github\.com(?::\d+)?/(.+?)/releases(/.*)?$", url)
    if not m:
        return []
    # Редиректы /releases/latest и /releases/tag/<t> — прямой download-ассет
    # неизвестен; оборачиваем ссылку целиком (прокси следуют редиректам).
    return [(name, f"{prefix}{url}") for name, prefix in gh_proxies()]


def _short_github_form(url):
    """Сокращённая форма ghuser/repo@tag/file (gh.io, github.io, git.io).

    Встречается в конфигах модпаков; раньше не поддерживалась вовсе.
    Возвращает канонический URL releases/download или None.
    """
    m = re.search(r"(?:^|[/:.])g(?:h|it)\.io/(?:github\.(?:io|com)/)?"
                  r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)@([^/?#]+)/([^?#]+)", url)
    if not m:
        m = re.search(r"github\.(?:io|com)/([A-Za-z0-9_.-]+)/"
                      r"([A-Za-z0-9_.-]+)@([^/?#]+)/([^?#]+)", url)
    if not m:
        return None
    owner, repo, tag, asset = m.groups()
    return (f"https://github.com/{owner}/{repo}"
            f"/releases/download/{tag}/{asset}")


def make_dxvk_mirrors(version):
    fname = f"dxvk-{version.lstrip('v')}.tar.gz"
    base = f"https://github.com/doitsujin/dxvk/releases/download/{version}/{fname}"
    return _gh_mirror_list(base)


# ---------- КАТАЛОГ БЕСПЛАТНЫХ ИГР ----------
FREE_GAMES = [
    ("Cave Story",            "https://www.cavestory.org/downloads/cavestoryen.zip"),
    ("Doom (shareware)",      "https://distro.ibiblio.org/slitaz/sources/packages/d/doom1.wad"),
    ("OpenTTD (Windows)",     "https://cdn.openttd.org/openttd-releases/latest/openttd-windows.zip"),
    ("Wolfenstein 3D",        "https://distro.ibiblio.org/slitaz/sources/packages/w/wolf3d.zip"),
    ("SuperTux (Linux AppImage)", "https://github.com/SuperTux/supertux/releases/download/v0.6.3/SuperTux-v0.6.3-x86_64.AppImage"),
    ("Battle for Wesnoth",    "https://sourceforge.net/projects/wesnoth/files/latest/download"),
]
