"""Сохранение/загрузка миров Minecraft на съёмный «Диск D».

Среда: RED OS в техникуме — после перезагрузки система откатывается,
поэтому миры хранятся на «Диске D»: папке (или смонтированном разделе)
на рабочем столе. Сетевые ресурсы (mnt и т.п.) часто только для чтения,
поэтому перед копированием проверяется возможность записи; при неудаче
предлагается выбрать другой путь вручную.
"""
import shutil
from datetime import datetime
from pathlib import Path

from modules import debug
from modules.colors import ok, info, warn, err, hint, CYAN, BOLD, YELLOW, RESET
from modules.config import HOME, DESKTOP_DIRS
from modules.prefix import find_minecraft_dirs

# Имена «Диска D», которые встречаются в RED OS / Windows-сборках
# ВАЖНО: варианты с кириллической «Д» («диск д», «диск_д») обязательны —
# путь пользователя может быть, например, «Рабочий стол/Диск Д».
_D_LABELS = {"диск d", "диск_d", "диск д", "диск_д", "disc d", "disk d",
             "d", "локальный диск (d)", "local disk (d)", "new volume", "data"}
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
        except Exception:
            pass

    # 1) Рабочий стол (рус/англ имена из config.DESKTOP_DIRS + варианты)
    for desk in DESKTOP_DIRS + [HOME / "РабочийСтол", HOME / "рабочий стол"]:
        if not desk.is_dir():
            continue
        add(desk / "Диск D")
        add(desk / "Диск Д")   # кириллическая «Д» — как у пользователя в RED OS
        add(desk / "Диск_D")
        add(desk / "Диск_Д")
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

    # 2) Точки монтирования съёмных разделов
    for base in ("/media", "/run/media", "/mnt"):
        root = Path(base)
        if not root.is_dir():
            continue
        try:
            first = list(root.iterdir())
        except OSError:
            continue
        for user_dir in first:
            try:
                if not user_dir.is_dir():
                    continue
                for vol in user_dir.iterdir():
                    try:
                        if not vol.is_dir():
                            continue
                        name_low = vol.name.lower().strip()
                        if name_low in _D_LABELS or "диск" in name_low or name_low == "d":
                            add(vol)
                    except OSError:
                        continue
            except OSError:
                continue

    # 3) Домашняя папка
    add(HOME / "Диск D")
    add(HOME / "Диск Д")   # кириллическая «Д»
    add(HOME / "disk_d")

    # Избегаем read-only сетевых папок (mnt и т.п.): сначала проверяем запись.
    writable = [c for c in candidates if _can_write(c)]
    if writable:
        return writable[0]
    # Никуда нельзя писать — вернём первый кандидат (пользователь сам разберётся)
    return candidates[0] if candidates else None


def _can_write(p):
    """Проверяет реальную возможность записи (для read-only шаров вернёт False)."""
    try:
        p = Path(p)
        test = p / ".write_test.tmp"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        return True
    except OSError as e:
        debug.dbg(f"_can_write({p}): {e}")
        return False


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
    """Все папки с мирами во всех найденных .minecraft. [(Path, метка), ...]."""
    result = []
    for mc in find_minecraft_dirs(limit=12):
        for wd in _WORLD_DIRS:
            w = mc / wd
            try:
                if w.is_dir() and any(x.is_dir() for x in w.iterdir()):
                    result.append((w, str(mc)))
            except OSError:
                continue
    return result


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
    """Копирует дерево с прогрессом по файлам; возвращает число файлов."""
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
                warn(f"Пропущен файл: {rel}/{item.name} ({e})")
                continue
            count += 1
            if count % 50 == 0:
                print(f"\r  {DIM_}{count} файлов...{RESET}", end="", flush=True)
    return count


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
        worlds = _list_worlds(saves_dir)
        if not worlds:
            continue
        info(f"Из {CYAN}{saves_dir}{RESET}: {len(worlds)} мир(ов)")
        dest_root = backup / Path(mc_label).name.replace(" ", "_") / "saves"
        # Резервная копия старых миров на диске (одна на запуск)
        if dest_root.is_dir():
            old = backup / Path(mc_label).name.replace(" ", "_") / f"saves.bak-{stamp}"
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
    # Собираем миры со всех подпапок backups (только верхний уровень мира,
    # внутрь уже найденного мира не ныряем)
    found = {}  # world_name -> src_path
    for sub in backup.rglob("*"):
        try:
            if not sub.is_dir():
                continue
            if not ((sub / "level.dat").exists() or (sub / "region").is_dir()):
                continue
            if any(sub.is_relative_to(w) for w in found.values()):
                continue
            found[sub.name] = sub
        except OSError:
            continue
    if not found:
        err("На диске миры не найдены (нет level.dat/region).")
        return
    saves = get_saves_dirs()
    if saves:
        target = saves[0][0]
    else:
        mc = None
        dirs = find_minecraft_dirs(limit=12)
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
    for wname, src in sorted(found.items()):
        dst = target / wname
        if dst.exists():
            warn(f"  '{wname}' уже есть в игре — пропускаю (удали вручную для замены).")
            continue
        info(f"  Ставлю '{wname}'...")
        n = _copy_tree(src, dst)
        total += n
        ok(f"  '{wname}' → {dst} ({n} файлов)")
    if total == 0:
        warn("Нечего загружать (все миры уже на месте).")
        return
    ok(f"Готово: {total} файлов загружено в {target}")
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
                    for w in sorted({p.name for p in backup.rglob("*")
                                     if p.is_dir() and (p / "level.dat").exists()}):
                        print(f"    {CYAN}{w}{RESET}")
                else:
                    warn(f"Папка {backup} пуста/отсутствует.")
        elif choice == "0":
            return
        else:
            warn("Неверный выбор")
