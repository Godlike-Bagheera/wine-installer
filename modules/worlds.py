"""Сохранение/загрузка миров Minecraft на съёмный «Диск D».

Среда: RED OS в техникуме — после перезагрузки система откатывается,
поэтому миры хранятся на «Диске D»: папке (или смонтированном разделе)
на рабочем столе. Сетевые ресурсы (mnt и т.п.) часто только для чтения,
поэтому перед копированием проверяется возможность записи; при неудаче
предлагается выбрать другой путь вручную.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, BOLD, YELLOW, RESET
from modules.config import HOME, DESKTOP_DIRS
from modules.prefix import find_minecraft_dirs, _in_worlds_backup

# Имена «Диска D», которые встречаются в RED OS / Windows-сборках
_D_LABELS = {"диск d", "диск_d", "disc d", "disk d", "d", "локальный диск (d)",
             "local disk (d)", "new volume", "data"}
# Папки с мирами в разных директориях игры
_WORLD_DIRS = ("saves", "worlds")
_SKIP_DIRS = {"$recycle.bin", "system volume information", ".Trash-info",
              ".fseventsd", ".Spotlight-V100"}

DIM_ = "\033[2m"


def find_disk_d():
    """Ищет «Диск D» по типичным местам. Возвращает Path или None."""
    candidates = []

    def add(p):
        try:
            p = Path(p)
            if p.is_dir() and p not in candidates:
                candidates.append(p)
        except Exception as e:
            debug.dbg_exc(e, "worlds")
    # 1) Рабочий стол (рус/англ имена из config.DESKTOP_DIRS + варианты)
    for desk in DESKTOP_DIRS + [HOME / "РабочийСтол", HOME / "рабочий стол"]:
        if not desk.is_dir():
            continue
        add(desk / "Диск D")
        add(desk / "Диск_D")
        add(desk / "Disk D")
        add(desk / "D")
        try:
            for f in desk.iterdir():
                try:
                    if f.is_dir() and f.name.lower().strip() in _D_LABELS:
                        add(f)
                except OSError:
                    continue
        except OSError:
            pass

    # 2) Точки монтирования съёмных разделов: /media/<user>/<vol>,
    #    /run/media/<user>/<vol>, /mnt/<vol>. Кандидатом становится ТОЛЬКО
    #    том с жёсткой меткой D (_is_d_label) — раньше достаточно было
    #    подстроки «диск» в имени, из-за чего первым кандидатом мог стать
    #    любой съёмный том («Диск C», флешка «DISK_1», сетевой шар).
    for base in ("/media", "/run/media", "/mnt"):
        root = Path(base)
        if not root.is_dir():
            continue
        try:
            first = list(root.iterdir())
        except OSError:
            continue
        level2_dirs = []
        for entry in first:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            if _is_d_label(entry.name):
                add(entry)          # /mnt/D, /mnt/Диск D — том прямо здесь
            else:
                level2_dirs.append(entry)   # это <user>, спускаемся глубже
        for user_dir in level2_dirs:
            try:
                for vol in user_dir.iterdir():
                    try:
                        if not vol.is_dir():
                            continue
                        if _is_d_label(vol.name):
                            add(vol)
                    except OSError:
                        continue
            except OSError:
                continue

    # 3) Домашняя папка и подпапки рабочего стола (в т.ч. «Мой диск D» и т.п.)
    add(HOME / "Диск D")
    add(HOME / "disk_d")
    for desk in DESKTOP_DIRS:
        if not desk.is_dir():
            continue
        try:
            for f in desk.iterdir():
                try:
                    if not f.is_dir():
                        continue
                    n = f.name.lower().replace(" ", "").replace("_", "")
                    if ("дискd" in n or "diskd" in n or "discd" in n) and \
                       f.name.lower().strip() not in _D_LABELS:
                        add(f)
                except OSError:
                    continue
        except OSError:
            pass

    # Отбрасываем заведомо неподписанные сетевые шары вида mnt/... без метки D
    for c in candidates:
        if _can_write(c):
            return c
    # Никуда нельзя писать — вернём первый кандидат (пользователь сам разберётся)
    return candidates[0] if candidates else None


def _can_write(p):
    """Проверяет реальную возможность записи (для read-only шаров вернёт False)."""
    try:
        p = Path(p)
        if not p.is_dir():
            return False
        test = p / ".write_test.tmp"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        return True
    except OSError as e:
        debug.dbg(f"_can_write({p}): {e}")
        return False


def _is_d_label(name):
    """Жёсткая проверка «это Диск D»: точное имя из справочника или одиночная
    буква D. Подстроки вида 'диск' раньше ловили всё подряд — «Диск C»,
    сетевой «Диск D backup (read only)» и пр. (ложные срабатывания)."""
    n = name.lower().strip()
    return n in _D_LABELS or n == "d"


def choose_disk(auto=True):
    """Возвращает путь к Диску D или None. При ненайденном — ручной ввод."""
    d = find_disk_d()
    if d is not None:
        info(f"Найден Диск D: {CYAN}{d}{RESET}")
        if _can_write(d):
            return d
        warn("В этот Диск D нельзя записывать (read-only, например сетевой mnt).")
    elif auto:
        warn("Диск D на рабочем столе/в /media не найден.")
    try:
        manual = input(f"{YELLOW}Укажи путь к Диску D (Enter — отказаться): {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        return None
    if not manual:
        return None
    p = Path(manual).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        err(f"Не могу создать папку: {e}")
        return None
    if not _can_write(p):
        err(f"По пути {p} нет прав на запись.")
        return None
    return p


def get_saves_dirs():
    """Все папки с мирами во всех найденных .minecraft. [(Path, метка), ...].

    Каталоги, лежащие внутри папки-бэкапа «minecraft-worlds», отбрасываются
    (защита от самокопирования, когда Диск D расположен внутри HOME)."""
    result = []
    for mc in find_minecraft_dirs(limit=12):
        if _in_worlds_backup(mc):          # страховка: бэкап — не игровая папка
            debug.dbg(f"get_saves_dirs: пропускаю бэкап {mc}")
            continue
        for wd in _WORLD_DIRS:
            w = mc / wd
            try:
                if w.is_dir() and any(x.is_dir() for x in w.iterdir()):
                    result.append((w, str(mc)))
            except OSError:
                continue
    return result


def choose_saves_target(saves):
    """Выбирает целевую папку saves[] при загрузке миров.

    Если найдена одна папка — берётся она; если несколько лаунчеров —
    пользователь выбирает сам (раньше миры всегда попадали в saves[0],
    т.е. в первую попавшуюся игру)."""
    if len(saves) == 1:
        info(f"Целевая папка: {CYAN}{saves[0][0]}{RESET}")
        return saves[0][0]
    print(f"{BOLD}Найдено несколько папок с мирами. Куда загружать?{RESET}")
    for i, (w, label) in enumerate(saves, 1):
        print(f"  {i}) {CYAN}{w}{RESET}  ({label})")
    try:
        raw = input(f"{YELLOW}Выбор [1]: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        return None
    if not raw:
        idx = 0
    else:
        try:
            idx = int(raw) - 1
        except ValueError:
            warn("Не удалось разобрать число — беру вариант 1.")
            idx = 0
    if not 0 <= idx < len(saves):
        warn(f"Нет варианта {raw} — беру вариант 1.")
        idx = 0
    target = saves[idx][0]
    info(f"Целевая папка: {CYAN}{target}{RESET}")
    return target


def _is_world_dir(p):
    """Мир = папка с level.dat или region/."""
    try:
        return p.is_dir() and ((p / "level.dat").exists() or (p / "region").is_dir())
    except OSError:
        return False


def _iter_backup_snapshots(backup):
    """Снимки бэкапа по возрастанию «свежести»: сначала старые saves.bak-*,
    последний элемент — актуальный saves/. Детерминированный порядок
    (сортировка по mtime, затем по имени)."""
    snaps = []
    try:
        for inst in sorted(backup.iterdir(), key=lambda x: x.name.lower()):
            if not inst.is_dir():
                continue
            for d in inst.iterdir():
                try:
                    if not d.is_dir():
                        continue
                    dl = d.name.lower()
                    if dl == "saves" or dl.startswith("saves.bak-") or dl in _WORLD_DIRS:
                        snaps.append(d)
                except OSError:
                    continue
    except OSError:
        pass
    snaps.sort(key=lambda d: (d.stat().st_mtime, d.name))
    return snaps


def _collect_backup_worlds(backup):
    """Собирает миры из структуры бэкапа ЦЕЛЕВО (без rglob('*') по всему дереву):
    обходятся только <inst>/saves[.bak-*]/<world> и <inst>/worlds/<world>.

    Возвращает {путь_мира: имя_для_выгрузки}. Ни одна копия не теряется молча:
    при коллизии имён самый свежий снимок сохраняет исходное имя (пользователь
    получает ожидаемый 'New World' из актуального saves), а старые копии
    переименовываются с меткой инстанта/снимка:
    'New World [.minecraft-saves.bak-20240101-000000]'."""
    # 1) все кандидаты (защита от вложенности: datapack-области DIM-1/DIM1
    #    внутри уже принятого мира не считаются отдельными мирами)
    candidates = []
    for snap in _iter_backup_snapshots(backup):
        taken = [w for w, _ in candidates]
        try:
            entries = sorted(snap.iterdir(), key=lambda x: x.name)
        except OSError:
            continue
        for w in entries:
            try:
                if not _is_world_dir(w):
                    continue
                if any(prev in w.parents for prev in taken):
                    debug.dbg(f"пропущен вложенный мир (datapack-область): {w}")
                    continue
                candidates.append((w, snap))
            except OSError:
                continue
    # 2) имена для выгрузки: свежие снимки (saves/worlds) идут первыми и
    #    занимают базовое имя; старые saves.bak-* получают суффикс-метку
    def is_current(snap):
        return snap.name.lower() in _WORLD_DIRS
    ordered = ([c for c in candidates if is_current(c[1])] +
               [c for c in candidates if not is_current(c[1])])
    worlds = {}   # src_path -> display name
    used = set()  # уже занятые имена выгрузки
    for w, snap in ordered:
        base = w.name
        if base not in used:
            name = base
        else:
            inst_tag = snap.parent.name
            suffix = inst_tag if is_current(snap) else f"{inst_tag}-{snap.name}"
            name = f"{base} [{suffix}]"
            k = 2
            while name in used:
                name = f"{base} [{suffix}] #{k}"
                k += 1
            warn(f"Коллизия имён: '{base}' уже есть в более свежем снимке — "
                 f"выгружу эту копию как '{name}'")
        used.add(name)
        worlds[w] = name
    return worlds


def _list_worlds(saves_dir):
    """Мир = папка с level.dat (или с region/). Возвращает список имён."""
    worlds = []
    try:
        for f in saves_dir.iterdir():
            try:
                if not f.is_dir() or f.name.lower() in _SKIP_DIRS:
                    continue
                if (f / "level.dat").exists() or (f / "region").is_dir():
                    worlds.append(f.name)
            except OSError:
                continue
    except OSError:
        pass
    return worlds


def _copy_tree(src, dst, rel=""):
    """Копирует дерево с прогрессом по файлам; возвращает число файлов.

    Ошибки НЕ глотаем: любой сбой (нет прав, диск отвалился/переполнился)
    бросает OSError наверх — вызывающий код удаляет неполную копию, иначе
    полуобрезанный мир выглядел бы как успешное сохранение («теряем данные
    при сбоях копирования»).
    """
    count = 0
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if item.name.lower() in _SKIP_DIRS:
            continue
        target = dst / item.name
        if item.is_dir():
            count += _copy_tree(item, target, rel + "/" + item.name)
        else:
            try:
                shutil.copy2(item, target)
            except OSError as e:
                debug.dbg(f"copy fail {item}: {e}")
                raise OSError(f"сбой копирования {rel}/{item.name}: {e}") from e
            count += 1
            if count % 50 == 0:
                print(f"\r  {DIM_}{count} файлов...{RESET}", end="", flush=True)
    return count


def _copy_world(src, dst):
    """Копирует один мир атомарно: во временную папку рядом с целью, затем
    переименование. При сбое — временный огрызок удаляется, в целевой папке
    не остаётся половины мира (раньше частичное дерево оставалось «живым»
    и мешало повторной загрузке). Возвращает число файлов."""
    tmp = dst.parent / f".{dst.name}.tmp-{os.getpid()}"
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        n = _copy_tree(src, tmp)
        os.replace(str(tmp), str(dst))
        return n
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def cmd_save_worlds():
    """Копирует все миры из .minecraft/saves на Диск D."""
    print(f"\n{BOLD}═══ Сохранить миры → Диск D ═══{RESET}")
    saves = get_saves_dirs()
    if not saves:
        err("Миры не найдены: нет папки .minecraft/saves (или она пуста).")
        hint("Сначала создай мир в игре и выйди из него.")
        return
    disk = choose_disk()
    if disk is None:
        warn("Отменено.")
        return
    backup = disk / "minecraft-worlds"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    total = 0
    for saves_dir, mc_label in saves:
        # страховка: никогда не сохраняем бэкап сам в себя
        if _in_worlds_backup(saves_dir):
            debug.dbg(f"save_worlds: пропускаю источник-бэкап {saves_dir}")
            continue
        worlds = _list_worlds(saves_dir)
        if not worlds:
            continue
        info(f"Из {CYAN}{saves_dir}{RESET}: {len(worlds)} мир(ов)")
        inst_name = Path(mc_label).name.replace(" ", "_")
        dest_root = backup / inst_name / "saves"
        # Резервная копия старых миров на диске (одна на запуск)
        if dest_root.is_dir():
            old = backup / inst_name / f"saves.bak-{stamp}"
            try:
                dest_root.rename(old)
                info(f"Старые копии на диске сохранены: {old.name}")
            except OSError as e:
                debug.dbg_exc(e, "save_worlds/rename-old")
                warn("Не удалось отложить старые копии — перезаписываю.")
        for wname in worlds:
            src = saves_dir / wname
            dst = dest_root / wname
            info(f"  Копирую '{wname}'...")
            n = _copy_tree(src, dst)
            total += n
            ok(f"  '{wname}' → {dst} ({n} файлов)")
    if total == 0:
        warn("Ничего не скопировано (миры пустые?).")
        return
    ok(f"Готово: {total} файлов на диске → {backup}")
    hint("После перезагрузки системы введи: loadworlds")


def cmd_load_worlds():
    """Загружает миры с Диска D обратно в .minecraft/saves."""
    print(f"\n{BOLD}═══ Загрузить миры ← Диск D ═══{RESET}")
    disk = choose_disk()
    if disk is None:
        warn("Отменено.")
        return
    backup = disk / "minecraft-worlds"
    if not backup.is_dir():
        err(f"На диске нет папки {backup}. Сначала выполни saveworlds.")
        return
    # Собираем миры целевым обходом известной структуры бэкапа:
    # <inst>/saves[.bak-*]/<world> и <inst>/worlds/<world>.
    # Коллизии имён не теряются — копии переименовываются с меткой инстанта.
    found = _collect_backup_worlds(backup)
    if not found:
        err("На диске миры не найдены (нет level.dat/region).")
        return
    n_snaps = len({p.parent.name for p in found})
    info(f"Найдено миров: {len(found)} (из {n_snaps} снимков на диске)")
    saves = get_saves_dirs()
    target = None
    if saves:
        target = choose_saves_target(saves)
        if target is None:
            warn("Отменено.")
            return
    else:
        mc = None
        dirs = [d for d in find_minecraft_dirs(limit=12) if not _in_worlds_backup(d)]
        if dirs:
            mc = dirs[0]
        else:
            try:
                manual = input(f"{YELLOW}Папка .minecraft не найдена. Укажи путь (Enter — ~/.minecraft): {RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                return
            mc = Path(manual) if manual else HOME / ".minecraft"
        target = mc / "saves"
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            err(f"Не могу создать {target}: {e}")
            return
        info(f"Целевая папка: {CYAN}{target}{RESET}")
    total = 0
    loaded = 0
    for src, wname in sorted(found.items(), key=lambda kv: str(kv[0])):
        dst = target / wname
        if dst.exists():
            warn(f"  '{wname}' уже есть в игре — пропускаю (удали вручную для замены).")
            continue
        info(f"  Ставлю '{wname}'...")
        n = _copy_tree(src, dst)
        total += n
        loaded += 1
        ok(f"  '{wname}' → {dst} ({n} файлов)")
    if total == 0:
        warn("Нечего загружать (все миры уже на месте).")
        return
    ok(f"Готово: {loaded} мир(ов), {total} файлов загружено в {target}")
    hint("Запусти игру — миры появятся в списке.")


def cmd_worlds_menu():
    while True:
        print(f"\n{BOLD}═══════ МИРЫ (Диск D) ═══════{RESET}")
        saves = get_saves_dirs()
        nw = sum(len(_list_worlds(s)) for s, _ in saves)
        print(f"  В игре сейчас миров: {nw}")
        print(f"  {CYAN}1{RESET}) Сохранить миры на Диск D")
        print(f"  {CYAN}2{RESET}) Загрузить миры с Диска D")
        print(f"  {CYAN}3{RESET}) Показать, что лежит на Диске D")
        print(f"  {CYAN}0{RESET}) Назад")
        try:
            choice = input(f"{YELLOW}Выбор: {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if choice == "1":
            cmd_save_worlds()
        elif choice == "2":
            cmd_load_worlds()
        elif choice == "3":
            disk = choose_disk()
            if disk:
                backup = disk / "minecraft-worlds"
                if backup.is_dir():
                    # целевой обход известной структуры бэкапа (без rglob по всему дереву)
                    worlds = _collect_backup_worlds(backup)
                    if not worlds:
                        warn(f"В {backup} миры не найдены.")
                    for src, wname in sorted(worlds.items(), key=lambda kv: str(kv[0])):
                        inst = src.parent.name          # saves / saves.bak-... / worlds
                        tag = src.parent.parent.name    # имя инстанта
                        print(f"    {CYAN}{wname}{RESET}  {DIM_}[{tag}/{inst}]{RESET}")
                else:
                    warn(f"Папка {backup} пуста/отсутствует.")
        elif choice == "0":
            return
        else:
            warn("Неверный выбор")
