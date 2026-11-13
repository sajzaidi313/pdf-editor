"""GUI smoke test: the main window can be created and shown."""

from pdfeditor.ui.main_window import MainWindow


# `qtbot` is a pytest fixture provided by pytest-qt. Asking for it makes sure
# a QApplication exists, which Qt requires before any widget is created.
def test_main_window_opens_with_title(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)  # qtbot closes the window when the test ends

    window.show()

    assert window.isVisible()
    assert window.windowTitle() == "PDF Editor"
