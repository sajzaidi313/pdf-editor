"""Architecture rule: pdfeditor.core must never import PySide6 (Qt).

The same goes for the render process. Keeping Qt out lets the core be
tested without a window and lets the render process start quickly.

Why a subprocess? pytest-qt has already imported Qt into the process that
runs the tests, so looking at sys.modules here would always find PySide6.
Each check therefore starts a fresh Python, imports the modules there, and
prints which PySide6 modules ended up loaded.
"""

import subprocess
import sys

# Import every module under pdfeditor.core, plus the render process.
IMPORT_CORE = """
import importlib
import pkgutil

import pdfeditor.core

prefix = "pdfeditor.core."
for module_info in pkgutil.walk_packages(pdfeditor.core.__path__, prefix):
    importlib.import_module(module_info.name)

import pdfeditor.render.render_process
"""

IMPORT_UI = "import pdfeditor.ui.main_window"

# sys.modules is Python's table of every module imported so far.
PRINT_QT_MODULES = """
import sys

for name in sorted(sys.modules):
    if name.startswith("PySide6"):
        print(name)
"""


def qt_modules_loaded_by(import_code: str) -> list[str]:
    """Run import_code in a fresh Python and return the PySide6 modules loaded."""
    result = subprocess.run(
        [sys.executable, "-c", import_code + PRINT_QT_MODULES],
        capture_output=True,
        text=True,
    )
    # A non-zero return code means the imports themselves crashed.
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_core_and_render_process_do_not_import_qt():
    assert qt_modules_loaded_by(IMPORT_CORE) == []


def test_check_notices_a_qt_import():
    """Sanity check: the detector must be able to fail.

    The UI does import Qt. If this found nothing, the test above would be
    passing for the wrong reason.
    """
    assert "PySide6.QtWidgets" in qt_modules_loaded_by(IMPORT_UI)
