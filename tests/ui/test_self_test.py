"""`--self-test`: the check the packaged app runs on itself (docs/08 §7)."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from pdfeditor import self_test
from pdfeditor.app import main, parse_arguments
from pdfeditor.self_test import SELF_TEST_PDF, has_ink, run_self_test


def test_the_self_test_pdf_ships_with_the_app():
    assert SELF_TEST_PDF.is_file()
    # It has to live inside the package folder, or the packaged app loses it.
    assert SELF_TEST_PDF.parent.name == "resources"
    assert SELF_TEST_PDF.parent.parent.name == "pdfeditor"


def test_self_test_passes(qtbot, capsys):
    # capsys is a built-in pytest fixture that captures what was printed.
    assert run_self_test() == 0
    assert "self-test OK" in capsys.readouterr().out


def test_self_test_fails_with_exit_code_1_when_the_pdf_is_missing(
    qtbot, capsys, monkeypatch, tmp_path
):
    monkeypatch.setattr(self_test, "SELF_TEST_PDF", tmp_path / "missing.pdf")

    assert run_self_test() == 1

    printed = capsys.readouterr()
    assert "self-test FAILED" in printed.out
    assert "PdfOpenError" in printed.err  # the reason is printed for the CI log


def test_command_line_flag_is_understood():
    assert parse_arguments(["--self-test"]).self_test is True
    assert parse_arguments([]).self_test is False
    assert parse_arguments(["a.pdf"]).file == Path("a.pdf")


def test_main_with_the_flag_runs_the_self_test_and_returns(qtbot, capsys):
    # No window, no event loop: main() must come straight back.
    assert main(["--self-test"]) == 0
    assert "self-test OK" in capsys.readouterr().out


def test_has_ink_tells_blank_from_drawn(qtbot):
    blank = QImage(40, 40, QImage.Format.Format_RGB888)
    blank.fill(Qt.GlobalColor.white)
    assert not has_ink(blank)

    drawn = blank.copy()
    drawn.setPixelColor(10, 10, Qt.GlobalColor.black)
    assert has_ink(drawn)
