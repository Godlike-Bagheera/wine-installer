#!/usr/bin/env python3
"""Mock-тесты ядра скачивания (modules/download.py) — без сети и реального Wine.

Вся внешняя среда (urlopen, subprocess, shutil.which) подменена фейками:
* зеркало отдаёт байты через фейковый HTTP-ответ (io.BytesIO + headers);
* aria2c имитируется подменой get_aria2c_path/subprocess.run.

Покрыто: выбор зеркал по кэшу, Range-докачка, обработка 416/200,
детект обрезанного ответа, slow-mode, HTML-заглушки вместо бинарника,
HEAD-проверка, пороги download_file.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# fake-HOME: изоляция от реального ~/.wine-portable (см. tests/conftest.py)
os.environ["HOME"] = tempfile.mkdtemp(prefix="fakehome_dl_")
os.environ["WI_FAKE_HOME"] = "1"

from modules import state                                  # noqa: E402
from modules import download as dl                         # noqa: E402
from modules.config import CACHE_FILE                      # noqa: E402

fails = []


def check(name, cond):
    print(f"  {'OK ' if cond else 'FAIL'} {name}")
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix="dl_test_"))


class FakeResp(io.BytesIO):
    """Фейковый ответ urlopen: read() из BytesIO + status/headers/close."""

    def __init__(self, body=b"", status=200, length=None):
        super().__init__(body)
        self.status = status
        n = len(body) if length is None else length
        self.headers = {"Content-Length": str(n)}

    def close(self):
        pass


def install_fake_urlopen(handler):
    """handler(url, headers) -> FakeResp | Exception; пишет вызовы в log."""
    calls = []

    def fake_open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        hdrs = dict(req.headers) if hasattr(req, "headers") else {}
        calls.append((url, hdrs))
        result = handler(url, hdrs, len(calls))
        if isinstance(result, Exception):
            raise result
        return result

    dl.open_checked = fake_open
    return calls


def fresh_dest(name="file.jar", content=None):
    dest = tmp / name
    if dest.exists():
        dest.unlink()
    if content is not None:
        dest.write_bytes(content)
    return dest


def real_zip_bytes():
    """Настоящий zip > 1 КБ (порог download_file: max(min_size_mb*МБ, 1024))."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("index.json", "x" * 3000)
    return buf.getvalue()


# ── 1. Кэш зеркал: сортировка по сохранённой скорости, битый файл ──
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
CACHE_FILE.unlink(missing_ok=True)
mirrors = [("slow", "http://s/1"), ("fast", "http://f/1"), ("mid", "http://m/1")]
check("без кэша порядок сохраняется", [n for n, _ in dl.sort_mirrors_by_cache(mirrors)]
      == ["slow", "fast", "mid"])
dl.remember_mirror_speed("fast", 900)
dl.remember_mirror_speed("mid", 400)
order = [n for n, _ in dl.sort_mirrors_by_cache(mirrors)]
check("сортировка по убыванию скорости", order == ["fast", "mid", "slow"])
CACHE_FILE.write_text("{битый json", encoding="utf-8")
check("битый кэш не роняет (пустой)", dl.load_mirror_cache() == {})
check("битый кэш не ломает сортировку",
      [n for n, _ in dl.sort_mirrors_by_cache(mirrors)] == ["slow", "fast", "mid"])
CACHE_FILE.unlink(missing_ok=True)

# ── 2. try_download_manual: чистая закачка с нуля ──
ZIP = real_zip_bytes()
state.slow_mode_active = False
state.slow_mirror_count = 0
dest = fresh_dest("clean.jar")
install_fake_urlopen(lambda url, h, i: FakeResp(ZIP))
res = dl.try_download_manual("m1", "http://mirror/clean.jar", dest, silent=True)
check("успешная закачка → True", res is True)
check("файл на диске равен телу ответа", dest.read_bytes() == ZIP)

# ── 3. Докачка по Range: сервер отдаёт остаток (206) ──
half = len(ZIP) // 2
dest = fresh_dest("resume.jar", ZIP[:half])
calls = install_fake_urlopen(
    lambda url, h, i: FakeResp(ZIP[half:], status=206))
res = dl.try_download_manual("m2", "http://mirror/resume.jar", dest, silent=True)
check("докачка → True", res is True)
check("Range-заголовок отправлен", calls[0][1].get("Range") == f"bytes={half}-")
check("файл долит полностью", dest.read_bytes() == ZIP)

# ── 4. Сервер игнорирует Range и отвечает 200 целиком → без дублей ──
dest = fresh_dest("ignore200.jar", ZIP[:half])
install_fake_urlopen(lambda url, h, i: FakeResp(ZIP, status=200))
res = dl.try_download_manual("m3", "http://mirror/x.jar", dest, silent=True)
check("200 при частичном файле → True", res is True)
check("нет удвоения данных (wb-режим)", dest.read_bytes() == ZIP)

# ── 5. 416 Range Not Satisfiable → файл удалён, перезакачка с нуля ──
dest = fresh_dest("r416.jar", ZIP)   # полный файл на диске


def h416(url, hdrs, i):
    if i == 1:
        assert hdrs.get("Range"), "первый запрос должен быть с Range"
        raise urllib.error.HTTPError(url, 416, "Range Not Satisfiable", None, None)
    return FakeResp(ZIP)


calls = install_fake_urlopen(h416)
res = dl.try_download_manual("m4", "http://mirror/r416.jar", dest, silent=True)
check("416 → перезакачка успешна", res is True)
check("второй запрос без Range", "Range" not in calls[1][1])
check("содержимое корректно", dest.read_bytes() == ZIP)

# ── 6. Обрезанный ответ: меньше обещанного Content-Length → False ──
dest = fresh_dest("trunc.jar")
install_fake_urlopen(lambda url, h, i: FakeResp(b"PK\x03\x04" + b"x" * 5000,
                                                length=10 * 1024 * 1024))
res = dl.try_download_manual("m5", "http://mirror/trunc.jar", dest, silent=True)
check("обрубок ответа → False", res is False)
check("неполный файл остался для докачки", 0 < dest.stat().st_size < 10 * 1024 * 1024)

# ── 7. Ошибка соединения → False, исключение наружу не летит ──
dest = fresh_dest("conn.jar")
install_fake_urlopen(lambda url, h, i: OSError("connection refused"))
res = dl.try_download_manual("m6", "http://mirror/conn.jar", dest, silent=True)
check("нет соединения → False", res is False)

# ── 8. Slow-mode: медленное зеркало отвергается, счётчик растёт ──
# Эмулируем реальный сетевой поток: ChunkedResp отдаёт тело по чанкам, а
# read(n) сдвигает «виртуальные часы» (time.time в пространстве имён
# download-модуля) на +100 с — скорость получается ~1 КБ/с < MIN_SPEED_KB.
state.slow_mode_active = False
state.slow_mirror_count = 0


class ChunkedResp(io.RawIOBase):
    """Фейковый ответ, отдающий тело по чанкам; каждый read = +100 вирт. секунд."""

    def __init__(self, chunks, clock):
        self._chunks = list(chunks)
        self.status = 200
        self.headers = {"Content-Length": str(sum(len(c) for c in chunks))}
        self._clock = clock

    def readable(self):
        return True

    def readinto(self, b):
        self._clock[0] += 100.0     # тик виртуального времени на каждый read
        if not self._chunks:
            return 0
        data = self._chunks.pop(0)
        n = min(len(data), len(b))
        b[:n] = data[:n]
        if n < len(data):           # чанок крупнее буфера — дозируем
            self._chunks.insert(0, data[n:])
        return n

    def close(self):
        pass


slow_clock = [time.time()]
slow_body = [b"PK\x03\x04" + b"x" * (1024 * 1024)] * 3   # ~3 МБ потоком
# do_speed_check требует total > SPEED_CHECK_MIN_MB*МБ (в конфиге 50 МБ);
# чтобы не гонять десятки МБ в памяти, временно понижаем порог и подменяем
# time.time в пространстве имён download-модуля (имена импортированы через
# `from ... import`, поэтому патчим атрибуты модуля, а не стандартной библиотеки).
dl.SPEED_CHECK_MIN_MB = 1
dl.time = type("FakeTime", (), {
    "time": staticmethod(lambda: slow_clock[0]),
    "sleep": staticmethod(lambda _s: None),
})()
try:
    dest = fresh_dest("slow.jar")
    install_fake_urlopen(lambda url, h, i: ChunkedResp(slow_body, slow_clock))
    res = dl.try_download_manual("m7", "http://mirror/slow.jar", dest, silent=True)
    check("медленная закачка → False", res is False)
    check("slow_mirror_count увеличен", state.slow_mirror_count == 1)
    dest2 = fresh_dest("slow2.jar")
    install_fake_urlopen(lambda url, h, i: ChunkedResp(slow_body, slow_clock))
    dl.try_download_manual("m8", "http://mirror/slow2.jar", dest2, silent=True)
    check("после SLOW_MODE_AFTER включён slow-mode", state.slow_mode_active is True)
finally:
    from modules.config import SPEED_CHECK_MIN_MB as _SCM
    import time as _time_mod
    dl.SPEED_CHECK_MIN_MB = _SCM   # восстановление (НЕ del — будет NameError)
    dl.time = _time_mod
    state.slow_mode_active = False
    state.slow_mirror_count = 0

# ── 9. download_file: ранний выход для валидного кэша (сеть не трогается) ──
dest = fresh_dest("cached_ok.jar", ZIP)
calls = install_fake_urlopen(lambda url, h, i: FakeResp(b"should-not-be-used"))
res = dl.download_file([("m", "http://x/y.jar")], dest, "t", min_size_mb=0, silent=True)
check("валидный кэш → True без сети", res is True and not calls)
check("кэш не перезаписан", dest.read_bytes() == ZIP)

# ── 10. download_file: HTML-заглушка в кэше → перекачка с зеркал ──
dest = fresh_dest("cached_html.jar", b"<html>proxy blocked</html>" * 200)
install_fake_urlopen(lambda url, h, i: FakeResp(ZIP))
res = dl.download_file([("good", "http://mirror/good.jar")], dest, "t",
                       min_size_mb=0, silent=True)
check("битый кэш перекачан", res is True and dest.read_bytes() == ZIP)

# ── 11. download_file: зеркало отдаёт HTML вместо jar → False, мусор удалён ──
dest = fresh_dest("html_only.jar")
install_fake_urlopen(lambda url, h, i: FakeResp(b"<html><body>404</body></html>" * 300))
res = dl.download_file([("bad", "http://mirror/bad.jar")], dest, "t",
                       min_size_mb=0, silent=True)
check("HTML вместо бинарника → False", res is False)
check("мусорный файл удалён с диска", not dest.exists())

# ── 12. download_file: все зеркала недоступны → False ──
dest = fresh_dest("dead.jar")
install_fake_urlopen(lambda url, h, i: OSError("no route"))
res = dl.download_file([("a", "http://1/x.jar"), ("b", "http://2/x.jar")],
                       dest, "t", min_size_mb=0, silent=True)
check("все зеркала мертвы → False", res is False)

# ── 13. head_check: размеры/коды ──
dl.open_checked = lambda req, timeout=None: FakeResp(b"", length=123)
ok_, size = dl.head_check("http://m/f")
check("HEAD вернул размер", ok_ is True and size == 123)


def raise404(req, timeout=None):
    raise urllib.error.HTTPError(str(req.full_url), 404, "Not Found", None, None)


dl.open_checked = raise404
ok_, _ = dl.head_check("http://m/f")
check("HEAD 404 → зеркало бракуется", ok_ is False)


def raise405(req, timeout=None):
    raise urllib.error.HTTPError(str(req.full_url), 405, "Method Not Allowed", None, None)


dl.open_checked = raise405
ok_, _ = dl.head_check("http://m/f")
check("HEAD 405 → принимается (метод не поддержан)", ok_ is True)

# ── 14. aria2c-путь: PATH или локальный ARIA2C_BIN (which внутри функции
# импортирует shutil из sys.modules — подменяем именно его атрибут which) ──
real_which = shutil.which
shutil.which = lambda name: "/bin/aria2c" if name == "aria2c" else real_which(name)
check("which(aria2c) используется", dl.get_aria2c_path() == "/bin/aria2c")
local = tmp / "aria2c-local"
local.write_text("#!/bin/sh\n")
local.chmod(0o755)
cfg_orig = dl.ARIA2C_BIN
dl.ARIA2C_BIN = local
shutil.which = lambda name: None
check("локальный бинарь приоритетнее PATH", dl.get_aria2c_path() == str(local))
dl.ARIA2C_BIN = cfg_orig
shutil.which = real_which

# ── 15. download_with_aria2: успех/мало байт/нет бинаря ──
dest = fresh_dest("aria.jar")
real_run = dl.subprocess.run


class FakeProc:
    """Подмена subprocess.run: пишет тело в dest и возвращает returncode."""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def run(self, cmd, check=False, **kw):
        self.calls.append(cmd)
        # dest собираем из аргументов вызова (-d каталог, -o имя), как это
        # делает настоящий aria2c; сигнатура обязана принимать check=True —
        # download_with_aria2 передаёт его keyword-аргументом
        p = Path(cmd[cmd.index("-d") + 1]) / cmd[cmd.index("-o") + 1]
        p.write_bytes(self.body)
        return type("R", (), {"returncode": 0})()


fp = FakeProc(b"x" * (2 * 1024 * 1024))     # > 1 МБ — aria2c-проверка проходит
fp_small = FakeProc(b"x" * 1024)            # слишком маленький (< 1 МБ)
dl.subprocess.run = fp.run
dl.get_aria2c_path = lambda: "/bin/aria2c"
check("aria2c успех → True", dl.download_with_aria2("http://m/a", dest, silent=True) is True)
dl.subprocess.run = fp_small.run
check("aria2c мелкий файл → False",
      dl.download_with_aria2("http://m/a", dest, silent=True) is False)
dl.get_aria2c_path = lambda: None
check("нет aria2c → None (откат на manual)",
      dl.download_with_aria2("http://m/a", dest, silent=True) is None)
dl.subprocess.run = real_run

# ── 16. download_file: aria2c-ветка с HEAD-фильтром битого зеркала ──
real_get_aria2c = dl.get_aria2c_path     # сохранаем для отката после секций 15-16
dl.get_aria2c_path = lambda: "/bin/aria2c"
dest = fresh_dest("aria_flow.jar")
orig_head = dl.head_check
dl.head_check = lambda url, timeout=15: (False, 0)
install_fake_urlopen(lambda url, h, i: FakeResp(ZIP))
orig_aria = dl.download_with_aria2
dl.download_with_aria2 = lambda url, d, silent=False: (_ for _ in ()).throw(
    AssertionError("aria2c не должен вызываться при провале HEAD"))
try:
    res = dl.download_file([("broken-head", "http://mirror/x.jar")], dest, "t",
                           min_size_mb=0, silent=True)
    check("HEAD-отказ пропускает aria2c, спасает manual", res is True)
finally:
    dl.head_check = orig_head
    dl.download_with_aria2 = orig_aria
    dl.get_aria2c_path = real_get_aria2c

print()
if fails:
    print(f"ПРОВАЛОВ: {len(fails)} -> {fails}")
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
shutil.rmtree(tmp, ignore_errors=True)
