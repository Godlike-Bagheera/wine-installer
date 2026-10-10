"""Сеть: единый SSL-контекст и безопасная распаковка архивов.

CERT_NONE здесь — осознанный компромисс: Red OS кладёт корневые сертификаты
Минцифры, которые не совпадают с цепочками GitHub/Mojang, и строгая проверка
ломает скачивание в школьной сети. Раньше такой контекст копировался 6 раз
по модулям; теперь он ОДИН (minecraft/shaders/download/winetricks берут его
отсюда). Ответственность за целостность содержимого держат SHA-хеши
(modules.hash_utils) и сигнатуры файлов (download._looks_binary).
"""
import os
import ssl
import tarfile
import zipfile
from pathlib import Path


def ssl_ctx():
    """Единый SSL-контекст проекта (см. docstring модуля)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ─────────────────────────────────────────────────────────────────────
#  Безопасная распаковка (защита от path traversal / zip-slip)
# ─────────────────────────────────────────────────────────────────────

def _safe_target(dest_dir, member_name):
    """Путь внутри dest_dir для имени из архива или None, если имя опасное.

    Отсекается: абсолютные пути, '..', выход за пределы dest_dir
    (в т.ч. через симлинки-предки), Windows-префиксы вида C:/path.
    """
    name = str(member_name).replace("\\", "/")
    if not name or name.startswith("/") or ":" in name.split("/")[0]:
        return None
    parts = []
    for seg in name.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            return None
        parts.append(seg)
    if not parts:
        return None
    dest_root = os.path.realpath(str(dest_dir))
    target = os.path.realpath(os.path.join(dest_root, *parts))
    if target != dest_root and not target.startswith(dest_root + os.sep):
        return None
    return target


def safe_extract_tar(archive, dest_dir):
    """tar.extractall с фильтрацией опасных имён (работает на Python 3.9+)."""
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers()
                   if _safe_target(dest_dir, m.name) is not None]
        try:
            # Python 3.12+: встроенный фильтр data (на 3.9 TypeError — тихо мимо)
            tar.extractall(dest_dir, members=members, filter="data")
        except TypeError:
            tar.extractall(dest_dir, members=members)


def safe_extract_zip(archive, dest_dir):
    """zipfile.extractall с фильтрацией опасных имён (zip-slip)."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = _safe_target(dest, info.filename)
            if target is None:
                continue
            z.extract(info, dest)
