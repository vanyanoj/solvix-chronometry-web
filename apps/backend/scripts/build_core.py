"""Сборка компилируемого ядра (core/) в .so-бинарники.

Использование (из apps/backend):
    python scripts/build_core.py            # собрать .so рядом с исходниками
    python scripts/build_core.py --strip    # собрать и УДАЛИТЬ .py/.c исходники
                                            # (только для прод-сборки в Docker!)

Директивы:
    annotation_typing=False — аннотации не превращаются в жёсткие типы
                              (иначе defaultdict не проходит как dict и т.п.)
    docstrings=False        — докстринги не попадают в бинарник
                              (в них описаны алгоритмы — это утечка ноу-хау)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from Cython.Build import cythonize
from Cython.Compiler import Options
from setuptools import Extension
from setuptools.dist import Distribution

BACKEND = Path(__file__).resolve().parent.parent
CORE = BACKEND / "src" / "solvix_chronometry" / "core"

# __init__.py не компилируем — это маркеры пакетов без логики
MODULES = [
    p for p in CORE.rglob("*.py")
    if p.name != "__init__.py" and "__pycache__" not in p.parts
]

DIRECTIVES = {
    "language_level": "3",
    "annotation_typing": False,
}

# Докстринги не должны попадать в бинарник (в них описаны алгоритмы).
# В Cython это глобальная опция компилятора, не директива.
Options.docstrings = False


def build() -> None:
    extensions = [
        Extension(
            name=str(p.relative_to(BACKEND / "src")).removesuffix(".py").replace("/", "."),
            sources=[str(p)],
        )
        for p in MODULES
    ]
    ext_modules = cythonize(
        extensions,
        compiler_directives=DIRECTIVES,
        build_dir=str(BACKEND / "build" / "cython"),
    )
    dist = Distribution({"ext_modules": ext_modules})
    cmd = dist.get_command_obj("build_ext")
    cmd.inplace = False
    cmd.build_lib = str(BACKEND / "src")
    cmd.build_temp = str(BACKEND / "build" / "temp")
    dist.run_command("build_ext")
    print(f"\nbuilt {len(MODULES)} modules:")
    for so in sorted(CORE.rglob("*.so")):
        print(f"  {so.relative_to(BACKEND)}")


def strip_sources() -> None:
    """Удалить .py-исходники и .c-артефакты ядра. Только для прод-образа."""
    for p in MODULES:
        p.unlink(missing_ok=True)
    for c in CORE.rglob("*.c"):
        c.unlink(missing_ok=True)
    shutil.rmtree(BACKEND / "build", ignore_errors=True)
    for pyc in CORE.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)
    print("sources stripped (production build)")


if __name__ == "__main__":
    build()
    if "--strip" in sys.argv:
        strip_sources()
