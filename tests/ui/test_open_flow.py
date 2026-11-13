"""Opening files through the window: errors, passwords, drag and drop.

`shown_errors` and `password_prompt` (tests/ui/conftest.py) stand in for the
two dialogs and record what the user would have seen.
"""

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from pdfeditor.app import parse_arguments

# --- files that cannot be opened ------------------------------------------------


def test_bad_file_shows_a_friendly_error(window, shown_errors, fixtures_dir):
    assert window.open_path(fixtures_dir / "not_a_pdf.pdf") is False

    assert len(shown_errors) == 1
    title, message = shown_errors[0]
    assert title == "Cannot open file"
    assert "not_a_pdf.pdf" in message
    assert "not a valid PDF" in message
    assert "Traceback" not in message  # technical text belongs in the details
    assert window.windowTitle() == "PDF Editor"
    assert window.view.page_count == 0


def test_bad_file_leaves_the_open_document_alone(window, shown_errors, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")

    window.open_path(fixtures_dir / "not_a_pdf.pdf")

    assert len(shown_errors) == 1
    assert window.windowTitle() == "simple_text.pdf - PDF Editor"
    assert window.view.page_count == 2
    assert "Lorem ipsum" in window.model.page(0).get_text()


def test_missing_file_shows_an_error(window, shown_errors, tmp_path):
    window.open_path(tmp_path / "gone.pdf")

    assert "was not found" in shown_errors[0][1]


def test_error_details_include_the_technical_cause(fixtures_dir):
    from pdfeditor.core.document import DocumentModel
    from pdfeditor.core.errors import PdfOpenError
    from pdfeditor.ui.dialogs.error_dialog import error_details

    try:
        DocumentModel().open(fixtures_dir / "not_a_pdf.pdf")
    except PdfOpenError as error:
        details = error_details(error)

    assert "PdfOpenError" in details
    assert "FileDataError" in details  # PyMuPDF's original error


# --- passwords ------------------------------------------------------------------


def test_right_password_opens_the_file(window, password_prompt, fixtures_dir):
    password_prompt.answers = ["test"]

    assert window.open_path(fixtures_dir / "encrypted_user_pw.pdf") is True

    assert window.view.page_count == 1
    assert window.windowTitle() == "encrypted_user_pw.pdf - PDF Editor"
    assert password_prompt.wrong_before_flags == [False]


def test_wrong_password_asks_again(window, password_prompt, fixtures_dir):
    password_prompt.answers = ["nope", "test"]

    assert window.open_path(fixtures_dir / "encrypted_user_pw.pdf") is True

    # The second prompt tells the user that the first try was wrong.
    assert password_prompt.wrong_before_flags == [False, True]
    assert window.view.page_count == 1


def test_cancelling_the_password_prompt_opens_nothing(
    window, password_prompt, shown_errors, fixtures_dir
):
    password_prompt.answers = [None]  # None = the user pressed Cancel

    assert window.open_path(fixtures_dir / "encrypted_user_pw.pdf") is False

    assert not window.model.is_open
    assert window.view.page_count == 0
    assert window.windowTitle() == "PDF Editor"
    assert shown_errors == []  # cancelling is not an error


def test_three_wrong_passwords_give_up(
    window, password_prompt, shown_errors, fixtures_dir
):
    password_prompt.answers = ["a", "b", "c", "test"]

    assert window.open_path(fixtures_dir / "encrypted_user_pw.pdf") is False

    assert password_prompt.answers == ["test"]  # the fourth was never asked for
    assert password_prompt.wrong_before_flags == [False, True, True]
    assert "wrong 3 times" in shown_errors[0][1]
    assert not window.model.is_open


def test_locked_file_is_not_added_to_recent_files(
    window, password_prompt, fixtures_dir
):
    password_prompt.answers = [None]

    window.open_path(fixtures_dir / "encrypted_user_pw.pdf")

    assert window.recent_files.paths() == []


# --- drag and drop --------------------------------------------------------------


def dragged_file(path) -> QMimeData:
    """What Qt hands over when a file is dragged from a file manager."""
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(path))])
    return mime_data


def drop_on(window, mime_data: QMimeData) -> QDropEvent:
    event = QDropEvent(
        QPointF(50, 50),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    return event


def test_dragging_a_file_over_the_window_is_accepted(window, fixtures_dir):
    mime_data = dragged_file(fixtures_dir / "simple_text.pdf")
    event = QDragEnterEvent(
        QPointF(50, 50),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    event.ignore()  # start from "not accepted" so the test proves something

    window.dragEnterEvent(event)

    assert event.isAccepted()


def test_dragging_text_over_the_window_is_ignored(window):
    mime_data = QMimeData()
    mime_data.setText("just some text")
    event = QDragEnterEvent(
        QPointF(50, 50),
        Qt.DropAction.CopyAction,
        mime_data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    event.ignore()

    window.dragEnterEvent(event)

    assert not event.isAccepted()


def test_dropping_a_file_opens_it(qtbot, window, fixtures_dir):
    mime_data = dragged_file(fixtures_dir / "rotated_pages.pdf")

    drop_on(window, mime_data)

    # The window opens the file a moment after the drop, so wait for it.
    qtbot.waitUntil(lambda: window.view.page_count == 4, timeout=2000)
    assert window.windowTitle() == "rotated_pages.pdf - PDF Editor"


def test_dropping_a_bad_file_shows_the_error(qtbot, window, shown_errors, fixtures_dir):
    drop_on(window, dragged_file(fixtures_dir / "not_a_pdf.pdf"))

    qtbot.waitUntil(lambda: len(shown_errors) == 1, timeout=2000)
    assert window.view.page_count == 0


def test_the_canvas_leaves_drops_to_the_window(window):
    # If the page view accepted drops itself, the window would never see them.
    assert not window.view.acceptDrops()
    assert not window.view.viewport().acceptDrops()
    assert window.acceptDrops()


# --- the command line -----------------------------------------------------------


def test_command_line_file_argument():
    options = parse_arguments(["some folder/report.pdf"])

    assert options.file.name == "report.pdf"


def test_command_line_without_arguments():
    assert parse_arguments([]).file is None
