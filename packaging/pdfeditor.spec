# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build recipe ("spec file"). Build from the project root with:
#
#     pyinstaller packaging/pdfeditor.spec --noconfirm
#
# What PyInstaller does: it follows every `import` starting from our entry
# script, collects all of those modules plus the Python interpreter and the
# native libraries they need (Qt, MuPDF), and writes them into one folder,
# dist/pdfeditor/. That folder runs on a computer with no Python installed.
# Check a fresh build with:
#
#     dist/pdfeditor/pdfeditor --self-test        (Windows: dist\pdfeditor\pdfeditor.exe)
#
# A spec file is Python, but PyInstaller runs it with a few names already
# defined: Analysis, PYZ, EXE, COLLECT and SPECPATH (this file's folder).
# That is why editors mark those names as "undefined" here.
#
# This is a "one-folder" build on purpose (not one single .exe): it starts
# faster, and Qt's LGPL license wants the Qt libraries to stay separate,
# replaceable files (docs/09 §2).

from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent
SOURCE_DIR = PROJECT_ROOT / "src"
PACKAGE_DIR = SOURCE_DIR / "pdfeditor"

analysis = Analysis(
    # The entry script: what `python -m pdfeditor` runs.
    [str(PACKAGE_DIR / "__main__.py")],
    # Where to look for our own package when following imports.
    pathex=[str(SOURCE_DIR)],
    # Data files are not found by following imports, so they are listed:
    # (file or folder on disk, folder inside the app). The self-test PDF
    # must end up at pdfeditor/resources/, next to self_test.py.
    datas=[(str(PACKAGE_DIR / "resources"), "pdfeditor/resources")],
    hiddenimports=[],
    # Never needed at run time; leaving them out keeps the folder smaller.
    excludes=["pytest", "pytestqt", "ruff", "pyright", "pypdf", "tkinter"],
)

# The collected pure-Python modules, packed into one archive.
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    exclude_binaries=True,  # one-folder mode: libraries go next to the exe
    name="pdfeditor",
    # console=True keeps a terminal window attached, so printed text and
    # error tracebacks are visible, in CI logs too. Milestone M11 switches
    # to a windowed app without a console.
    console=True,
)

# Gather the executable and everything it needs into dist/pdfeditor/.
COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="pdfeditor",
)
