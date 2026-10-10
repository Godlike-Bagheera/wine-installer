"""Инфраструктура: тесты можно запускать И как скрипты (python tests/test_x.py,
так делает CI), И через pytest (pytest / pytest tests/).

Как это работает:
* Каждый test_*.py — standalone-скрипт: код верхнего уровня печатает
  результаты проверок и вызывает sys.exit(1) при провале. Обычный сбор
  pytest таких файлов ломается ещё на стадии collection: модуль
  импортируется целиком, его side-effects и sys.exit срабатывают внутри
  collection. Поэтому хук pytest_pycollect_makemodule возвращает None для
  наших скриптов — стандартный Python-сборщик (Module/Package) их не
  импортирует ни при `pytest`, ни при `pytest tests/test_x.py`
  (initpath-аргументы тоже проходят через этот хук).
* Вместо этого здесь определён явный wrapper-тест test_standalone_scripts,
  который параметризует все файлы tests/test_*.py и выполняет каждый из них
  отдельным subprocess'ом (интерпретатором текущего pytest-процесса).
  Код возврата транслируется в успех/провал теста, вывод показывается при
  падении. Скрипты при этом НЕ импортируются в процесс pytest.
* Изоляция HOME: os.environ["HOME"] подменяется свежей temp-папкой сразу
  при импорте conftest (до любых других плагинов/импортов), а
  WI_FAKE_HOME=1 запрещает config._resolve_home() фолбэк на passwd-дом
  (/root): иначе под root при недоступном fake-HOME фолбек вернул бы
  реальный /root и тесты начали бы трогать ~/.minecraft настоящего
  пользователя (FileExistsError на /root/.minecraft).
"""
import glob
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"

# --- изоляция fake-HOME ДО импорта любых модулей приложения -----------------
FAKE_HOME = Path(tempfile.mkdtemp(prefix="fakehome_conftest_"))
os.environ["HOME"] = str(FAKE_HOME)
os.environ["WI_FAKE_HOME"] = "1"


def _discover_scripts():
    """Все standalone-скрипты tests/test_*.py (список не хардкодится)."""
    return sorted(glob.glob(str(TESTS_DIR / "test_*.py")))


def pytest_collect_file(file_path, parent):
    """Отключает сбор standalone-скриптов стандартным Python-сборщиком.

    Хук firstresult: возвращаем Collection — наш скрипт собран как узел,
    который при expand ничего не даёт (файл НЕ импортируется; импорт =
    выполнение скрипта + sys.exit -> INTERNALERROR на стадии collection).
    Для остальных файлов возвращаем None — поведение по умолчанию задаёт
    core-хук. Работает и для `pytest`, и для `pytest tests/`, и для явного
    `pytest tests/test_x.py`: initpath-аргументы тоже проходят через этот
    хук. Реальный запуск скриптов делает wrapper test_standalone_scripts.

    Именно pytest_collect_file, а НЕ pytest_pycollect_makemodule: в
    pytest 9.x модули отдаются плагином из site-packages (makemodule),
    который обходится мимо conftest-хука makemodule, и его Module-ноды
    подавляют pytest_collect_file на уровне Package. pytest_collect_file
    вызывается для каждого файла до создания любого модульного узла,
    поэтому перехватывает сбор надёжно.
    """
    path = Path(str(file_path))
    if path.parent == TESTS_DIR and path.name.startswith("test_") \
            and path.suffix == ".py":
        return _ScriptPlaceholder.from_parent(parent, path=path)
    return None


class _ScriptPlaceholder(pytest.Item):
    """Заглушка сбора: не импортирует standalone-скрипт, детей не имеет.

    Это Item (а не Collector): узлы-Collector'ы без детей pytest вырезает
    из дерева сборки ещё до отчёта, и `pytest tests/` показывал бы
    "no tests collected" вместо 0 items с ошибкой. Запускать сам скрипт
    он не должен (импорт = sys.exit внутри процесса pytest); запуск
    делает wrapper test_standalone_scripts.
    """

    def __init__(self, *, name=None, path=None, parent=None, **kwargs):
        if name is None:
            name = Path(str(path)).name
        super().__init__(name=name, path=path, parent=parent, **kwargs)

    def runtest(self):
        # Реального выполнения здесь нет: скрипт гоняет test_standalone_scripts.
        pass

    def repr_failure(self, excinfo):
        return "standalone-скрипт запускается через test_standalone_scripts"

    def reportinfo(self):
        return self.path, None, self.path.name


@pytest.mark.parametrize("script_path", _discover_scripts())
def test_standalone_scripts(script_path):
    """Каждый tests/test_*.py выполняется как отдельный скрипт."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, script_path],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=300,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        pytest.fail(f"{Path(script_path).name}: код возврата {proc.returncode}\n"
                    f"--- вывод скрипта ---\n{output}")
