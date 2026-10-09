#!/usr/bin/env python3
"""Интеграционные проверки ключевых фиксов (без сети, локально)."""
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HOME", tempfile.mkdtemp(prefix="fakehome_"))

from modules.download import _looks_binary, download_file          # noqa: E402
from modules.hash_utils import verify_sha1, verify_sha512          # noqa: E402
from modules.config import make_github_mirrors                     # noqa: E402
import modules.minecraft as mc                                     # noqa: E402

fails = []


def check(name, cond):
    print(f"  {'OK ' if cond else 'FAIL'} {name}")
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix="fo_test_"))

# ── 1. _looks_binary: HTML-заглушка с расширением .jar/mrpack/gz ──
bad_jar = tmp / "fabric-installer.jar"
bad_jar.write_bytes(b"<html><body>proxy block</body></html>" * 100)
check("HTML под видом .jar отклоняется", not _looks_binary(bad_jar))

real_zip = tmp / "good.mrpack"
with zipfile.ZipFile(real_zip, "w") as z:
    z.writestr("modrinth.index.json", "{}")
check("настоящий zip/.mrpack принимается", _looks_binary(real_zip))

gz = tmp / "x.tar.gz"
gz.write_bytes(b"\x1f\x8b\x08\x00rest")
check("gzip принимается", _looks_binary(gz))
txt = tmp / "script.sh"
txt.write_text("#!/bin/sh\necho hi")
check(".sh не фальсифицируется проверкой", _looks_binary(txt))

# ── 2. download_file: битый кэш перекачивается, а не считается валидным ──
dest = tmp / "cached.jar"
dest.write_bytes(b"<!DOCTYPE html>not a jar " * 500)   # >1КБ, но HTML
res = download_file([("test-mirror", "http://127.0.0.1:9/none")], dest, "t", min_size_mb=0, silent=True)
check("битый кэш не принят как успешная закачка", res is False)

# ── 3. make_github_mirrors: api.github.com не оборачивается прокси ──
m = make_github_mirrors("https://api.github.com/repos/x/releases")
check("для API нет зеркал-прокси", m == [])
m2 = make_github_mirrors("https://github.com/a/b/releases/download/v1/f.zip")
check("для release-ассета зеркала есть", len(m2) == 3 and all("ghfast" in u or "ghproxy" in u or "gh-proxy" in u for _, u in m2))

# ── 4. sha1/sha512 утилиты ──
h = tmp / "hashme.bin"
h.write_bytes(b"abc")
ok1, actual1 = verify_sha1(h, "a9993e364706816aba3e25717850c26c9cd0d89d")
check("verify_sha1 совпал", ok1)
ok512, _ = verify_sha512(h, "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f")
check("verify_sha512 совпал", ok512)
ok_bad, _ = verify_sha1(h, "00" * 20)
check("неверный sha1 отклонён", not ok_bad)

# ── 5. патч overrides из zip (главный баг: файлы НЕ распаковывались) ──
game = tmp / ".minecraft"
(game / "versions").mkdir(parents=True)
zip_path = tmp / "FO_v14.1.0_for_1.21.5.zip"
with zipfile.ZipFile(zip_path, "w") as z:
    z.writestr("modlist.html", '<a href="https://example.cf/mods/download/1/sodium.jar">s</a>')
    z.writestr("overrides/", "")                                    # dir-entry
    z.writestr("overrides/config/sodium-options.json", '{"a":1}')   # файл!
    z.writestr("overrides/config/fabric_loader_dependencies.json",
               json.dumps({"overrides": {"java": {"net.fabricmc.fabric-loader": "0.16.9"}}}))
    z.writestr("manifest.json", json.dumps({"manifestVersion": "2", "minecraftVersion": "1.21.5"}))

# перехватываем сеть: install_fabric_profile/finish_version_install не дёрнем без сети —
# они вызываются только при loader_version; сделаем их заглушками
called = {}
mc.install_fabric_profile = lambda gd, mcv, lv: called.update(profile=(mcv, lv)) or True
mc.finish_version_install = lambda gd, mcv, vid: called.update(finish=(mcv, vid)) or True

res = mc.unpack_fo_zip_to_game(zip_path, game, "14.1.0")
check("zip-путь установки FO вернул успех", res is True)
check("override-ФАЙЛ распакован в config/",
      (game / "config" / "sodium-options.json").exists())
mods = list((game / "mods").glob("*.jar")) if (game / "mods").is_dir() else []
check("папка mods создана (модалити распознаны)", (game / "mods").is_dir())
check("Fabric-профиль затребован с версиями из zip",
      called.get("profile") == ("1.21.5", "0.16.9"))
check("finish_version_install вызван",
      called.get("finish") == ("1.21.5", "fabric-loader-0.16.9-1.21.5"))

# ── 6. фильтр релизов FO ──
check("v14.1.0 — релиз", mc._fo_is_release("v14.1.0", "FabulouslyOptimized-14.1.0.mrpack"))
check("alpha отбраковывается", not mc._fo_is_release("v15.0.0-alpha.5"))
check("beta отбраковывается", not mc._fo_is_release("v15.0.0-beta.2"))
check("rc отбраковывается", not mc._fo_is_release("v14.2.0-rc1"))

print()
if fails:
    print(f"ПРОВАЛОВ: {len(fails)} -> {fails}")
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
shutil.rmtree(tmp, ignore_errors=True)
