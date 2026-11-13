"""`--self-test`: check that this copy of the app can open and draw a PDF.

Why it exists: the app is shipped as a folder built by PyInstaller, which
has to find and copy every library the program needs. When it misses one
(a Qt plugin, a MuPDF file, our own data files) the app works from source
but the packaged copy does not. CI therefore builds the package and runs it
with --self-test; exit code 0 means the bundle is complete (docs/08 §7).

The test opens a small PDF that ships with the app, draws its first page in
memory (no window appears) and checks that something was actually drawn.
It uses no dialogs and no settings, so it cannot hang or leave traces.
"""

import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from pdfeditor.core.document import DocumentModel
from pdfeditor.render.renderer import render_page
from pdfeditor.ui.page_view import PageView

# The PDF sits next to this file: in src/pdfeditor/resources/ when running
# from source, and in the same relative place inside the packaged app
# (packaging/pdfeditor.spec copies the folder there).
SELF_TEST_PDF = Path(__file__).parent / "resources" / "self_test.pdf"
EXPECTED_TEXT = "PDF Editor self-test"


def run_self_test() -> int:
    """Run the check. Returns the exit code: 0 = all good, 1 = something broke."""
    try:
        check_app_works()
    except Exception:
        # Catching everything is right here, and only here: whatever went
        # wrong, the job is to report it and exit with a failure code.
        traceback.print_exc()
        print("self-test FAILED")
        return 1
    print("self-test OK")
    return 0


def check_app_works() -> None:
    """Open the bundled PDF and draw its first page; raise if anything is off."""
    # Widgets need a QApplication. Keep a reference so it stays alive.
    _app = QApplication.instance() or QApplication(sys.argv[:1])
    model = DocumentModel()
    model.open(SELF_TEST_PDF)
    try:
        page = model.page(0)
        if EXPECTED_TEXT not in page.get_text():
            raise RuntimeError("The self-test PDF does not contain the expected text.")
        if not has_ink(render_page(page, scale=1.0)):
            raise RuntimeError("Page 1 of the self-test PDF was drawn blank.")
        # The same path the real window takes: lay out and draw in a view.
        view = PageView()
        view.set_document(model)
        if view.rendered_pages() != {0}:
            raise RuntimeError("The page view did not draw page 1.")
        view.set_document(None)
    finally:
        # `finally` runs whether or not an error happened above.
        model.close()


def has_ink(image: QImage) -> bool:
    """True when the picture is not just blank white paper."""
    white = QColor("white").rgb()
    # Looking at every second pixel is plenty to find text.
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            if image.pixel(x, y) != white:
                return True
    return False
