"""Все константы и пути. Никакой логики — только данные."""
import os
from pathlib import Path


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
    except Exception:
        pass
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
SETTINGS_FILE = WINE_DIR / "settings.json"

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

# ---------- НАСТРОЙКИ ЗАГРУЗКИ ----------
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

# ---------- НОВЫЕ ФИЧИ (флаги) ----------
USE_PER_GAME_PREFIX = False
USE_DXVK_HUD = False
USE_MANGOHUD = False
USE_GAMESCOPE = False
USE_TTS_NOTIFY = False
LOG_KEEP_DAYS = 30

CURRENT_VERSION = "2.6"

DEFAULT_SETTINGS = {"quiet_mode": False, "use_gamemode": False, "debug_mode": False}

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


def make_github_mirrors(url):
    """Оборачивает ссылку github.com прокси-зеркалами (для плохих сетей).

    Прокси умеют отдавать ассеты GitHub Releases — поддерживаются оба
    формата ссылок:
      - github.com/.../releases/download/<tag>/<file>  (конкретный релиз);
      - github.com/.../releases/latest/download/<file> (последний релиз,
        используется в офлайн-каталоге шейдеров).
    Для api.github.com и прочих URL возвращают пустой список — качаем прямо.
    """
    if "github.com" not in url:
        return []
    if "/releases/download/" not in url and "/releases/latest/download/" not in url:
        return []
    return [
        ("ghfast.top",      f"https://ghfast.top/{url}"),
        ("ghproxy.net",     f"https://ghproxy.net/{url}"),
        ("gh-proxy.com",    f"https://gh-proxy.com/{url}"),
    ]


def make_dxvk_mirrors(version):
    fname = f"dxvk-{version.lstrip('v')}.tar.gz"
    base = f"https://github.com/doitsujin/dxvk/releases/download/{version}/{fname}"
    return [
        ("ghfast.top",       f"https://ghfast.top/{base}"),
        ("ghproxy.net",      f"https://ghproxy.net/{base}"),
        ("gh-proxy.com",     f"https://gh-proxy.com/{base}"),
        ("ghproxy.cc",       f"https://ghproxy.cc/{base}"),
        ("gh.llkk.cc",       f"https://gh.llkk.cc/{base}"),
        ("GitHub (прямой)",  base),
    ]


# ---------- КАТАЛОГ БЕСПЛАТНЫХ ИГР ----------
FREE_GAMES = [
    ("Cave Story",            "https://www.cavestory.org/downloads/cavestoryen.zip"),
    ("Doom (shareware)",      "https://distro.ibiblio.org/slitaz/sources/packages/d/doom1.wad"),
    ("OpenTTD (Windows)",     "https://cdn.openttd.org/openttd-releases/latest/openttd-windows.zip"),
    ("Wolfenstein 3D",        "https://distro.ibiblio.org/slitaz/sources/packages/w/wolf3d.zip"),
    ("SuperTux (Linux AppImage)", "https://github.com/SuperTux/supertux/releases/download/v0.6.3/SuperTux-v0.6.3-x86_64.AppImage"),
    ("Battle for Wesnoth",    "https://sourceforge.net/projects/wesnoth/files/latest/download"),
]
