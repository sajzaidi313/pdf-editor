"""The main application window: menus, toolbar, status bar, opening files."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QMimeData, QSettings, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
)
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QWidget

from pdfeditor.core.document import DocumentModel
from pdfeditor.core.errors import PdfOpenError
from pdfeditor.ui.dialogs import error_dialog, password_dialog
from pdfeditor.ui.page_view import PageView
from pdfeditor.ui.recent_files import RecentFiles
from pdfeditor.ui.toolbar import MainToolBar, page_box_text

WINDOW_TITLE = "PDF Editor"
MAX_PASSWORD_ATTEMPTS = 3
MESSAGE_MILLISECONDS = 8000  # how long a passing status-bar message stays


def status_text(page_index: int, page_count: int, zoom: float) -> str:
    """The status bar's text, for example "Page 3 / 120 · 125%"."""
    return f"Page {page_index + 1} / {page_count} · {round(zoom * 100)}%"


def first_local_file(mime_data: QMimeData) -> Path | None:
    """The first file in something dragged onto the window, if there is one.

    Dragged data can be many things (text, an image, a web link). Files
    arrive as a list of URLs like file:///C:/docs/a.pdf.
    """
    for url in mime_data.urls():
        if url.isLocalFile():
            return Path(url.toLocalFile())
    return None


class MainWindow(QMainWindow):
    """Top-level window of the app.

    QMainWindow is Qt's ready-made window with places for a menu bar,
    toolbars, a status bar and one central widget. The central widget is
    the PageView; this class connects it to the menus and owns the
    "open a file" steps: errors, the password prompt, the recent list.
    """

    def __init__(
        self, settings: QSettings | None = None, parent: QWidget | None = None
    ) -> None:
        # super().__init__ runs QMainWindow's own setup first. Forgetting it
        # is a classic Qt mistake that crashes as soon as the window is used.
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1000, 700)
        self.model = DocumentModel()
        # QSettings() with no arguments is the app's normal settings store.
        # Tests pass their own so they never touch the real one.
        self.recent_files = RecentFiles(
            settings if settings is not None else QSettings()
        )
        self.view = PageView(self)
        self.setCentralWidget(self.view)
        self.setAcceptDrops(True)  # allow files to be dragged onto the window
        self._create_actions()
        self._create_menus()
        self._create_toolbar_and_status_bar()
        # When the view says the zoom or page changed, refresh the texts.
        self.view.zoom_changed.connect(self._refresh_page_display)
        self.view.current_page_changed.connect(self._refresh_page_display)
        self._refresh_after_document_change()
        self.view.setFocus()

    # --- building the window --------------------------------------------------

    def _new_action(
        self,
        text: str,
        on_triggered: Callable[[], object],
        *shortcuts: str | QKeySequence.StandardKey,
    ) -> QAction:
        """Make a QAction: one command with a text, shortcuts and a function.

        The "&" in a text marks the letter that Alt underlines in menus.
        """
        action = QAction(text, self)
        action.setShortcuts([QKeySequence(shortcut) for shortcut in shortcuts])
        # The `triggered` signal passes along a True/False "checked" value
        # that these commands have no use for; the lambda drops it.
        action.triggered.connect(lambda _checked=False: on_triggered())
        return action

    def _create_actions(self) -> None:
        view = self.view
        # StandardKey picks the usual shortcut of each system: Open is
        # Ctrl+O on Windows and Cmd+O on a Mac.
        keys = QKeySequence.StandardKey
        new = self._new_action
        self.open_action = new("&Open…", self.choose_file, keys.Open)
        self.exit_action = new("E&xit", self.close, keys.Quit)
        # Ctrl+= as well, because "+" needs Shift on most keyboards.
        self.zoom_in_action = new("Zoom &In", view.zoom_in, keys.ZoomIn, "Ctrl+=")
        self.zoom_out_action = new("Zoom &Out", view.zoom_out, keys.ZoomOut)
        self.actual_size_action = new("&Actual Size", view.actual_size, "Ctrl+0")
        self.fit_width_action = new("Fit &Width", view.fit_width, "Ctrl+2")
        self.fit_page_action = new("Fit &Page", view.fit_page, "Ctrl+1")
        self.next_page_action = new("&Next Page", view.next_page, "PgDown")
        self.previous_page_action = new("P&revious Page", view.previous_page, "PgUp")
        self.first_page_action = new(
            "&First Page", view.first_page, "Home", "Ctrl+Home"
        )
        self.last_page_action = new("&Last Page", view.last_page, "End", "Ctrl+End")
        self._zoom_actions = [
            self.zoom_in_action,
            self.zoom_out_action,
            self.actual_size_action,
            self.fit_width_action,
            self.fit_page_action,
        ]
        self._page_actions = [
            self.next_page_action,
            self.previous_page_action,
            self.first_page_action,
            self.last_page_action,
        ]

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.open_action)
        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._recent_menu.setToolTipsVisible(True)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions(self._zoom_actions)
        view_menu.addSeparator()
        view_menu.addActions(self._page_actions)
        self._rebuild_recent_menu()

    def _create_toolbar_and_status_bar(self) -> None:
        zoom_buttons = [
            self.zoom_out_action,
            self.zoom_in_action,
            self.fit_width_action,
        ]
        self.toolbar = MainToolBar(self.open_action, zoom_buttons, self)
        self.addToolBar(self.toolbar)
        self.toolbar.page_box.page_entered.connect(self._go_to_typed_page)
        # A "permanent" widget sits at the right end of the status bar and
        # is not covered by passing messages.
        self._status_label = QLabel(self)
        self.statusBar().addPermanentWidget(self._status_label)

    # --- opening files --------------------------------------------------------

    def choose_file(self) -> None:
        """File > Open: let the user pick a PDF, then open it."""
        current = self.model.path
        start_folder = "" if current is None else str(current.parent)
        file_name, _chosen_filter = QFileDialog.getOpenFileName(
            self, "Open PDF", start_folder, "PDF files (*.pdf);;All files (*)"
        )
        if file_name:  # an empty string means the dialog was cancelled
            self.open_path(Path(file_name))

    def open_path(self, path: Path) -> bool:
        """Open the PDF at `path` and show it. Returns True when it worked.

        Every way of opening a file ends up here: the Open dialog, the
        recent list, drag and drop and the command line. A file that
        cannot be opened gets an error dialog, and the document that was
        open before stays open.
        """
        try:
            self.model.open(path)
        except PdfOpenError as error:
            self._report_open_error(path, error)
            return False
        # The model has switched to the new file, so the old pages on the
        # canvas belong to a document that no longer exists.
        self.view.set_document(None)
        if self.model.needs_password and not self._ask_until_unlocked(path):
            self.model.close()
            self._refresh_after_document_change()
            return False
        self.view.set_document(self.model)
        self.recent_files.add(path)
        self._rebuild_recent_menu()
        self._refresh_after_document_change()
        if self.model.was_repaired:
            self.statusBar().showMessage(
                "This file was damaged. It has been repaired for viewing.",
                MESSAGE_MILLISECONDS,
            )
        return True

    def _ask_until_unlocked(self, path: Path) -> bool:
        """Ask for the password, three times at most. True when unlocked."""
        wrong_before = False
        for _attempt in range(MAX_PASSWORD_ATTEMPTS):
            password = password_dialog.ask_password(self, path.name, wrong_before)
            if password is None:  # the user pressed Cancel
                return False
            if self.model.authenticate(password):
                return True
            wrong_before = True
        error_dialog.show_error(
            self,
            "File not opened",
            f'The password for "{path.name}" was wrong {MAX_PASSWORD_ATTEMPTS} times, '
            "so the file was not opened.",
        )
        return False

    def _report_open_error(self, path: Path, error: PdfOpenError) -> None:
        if not path.exists():
            # A recent file that was deleted or moved: stop offering it.
            self.recent_files.remove(path)
            self._rebuild_recent_menu()
        error_dialog.show_error(
            self, "Cannot open file", str(error), error_dialog.error_details(error)
        )

    # --- the recent files menu ------------------------------------------------

    def _rebuild_recent_menu(self) -> None:
        menu = self._recent_menu
        menu.clear()
        paths = self.recent_files.paths()
        for number, path in enumerate(paths, start=1):
            # "&&" shows a real "&"; a single one would mark a shortcut letter.
            name = path.name.replace("&", "&&")
            action = menu.addAction(f"&{number}  {name}")
            action.setToolTip(str(path))
            # `chosen=path` freezes the path for this menu entry. Without
            # it every entry would open the last path of the loop.
            action.triggered.connect(
                lambda _checked=False, chosen=path: self.open_path(chosen)
            )
        menu.addSeparator()
        clear_action = menu.addAction("&Clear Recent Files")
        clear_action.triggered.connect(
            lambda _checked=False: self._clear_recent_files()
        )
        menu.setEnabled(bool(paths))

    def _clear_recent_files(self) -> None:
        self.recent_files.clear()
        self._rebuild_recent_menu()

    # --- keeping the texts up to date -----------------------------------------

    def _refresh_after_document_change(self) -> None:
        """Update everything that depends on whether a document is shown."""
        shown = self.view.page_count > 0
        for action in self._zoom_actions + self._page_actions:
            action.setEnabled(shown)
        self.toolbar.page_box.setEnabled(shown)
        title = WINDOW_TITLE
        if shown and self.model.path is not None:
            title = f"{self.model.path.name} - {WINDOW_TITLE}"
        self.setWindowTitle(title)
        self._refresh_page_display()

    def _refresh_page_display(self, _new_value: object = None) -> None:
        """Show the current page and zoom in the status bar and page box.

        Connected to the view's signals, which pass the new zoom or page
        along; this method reads the current state itself, so it ignores
        that value.
        """
        if self.view.page_count == 0:
            self._status_label.setText("")
            self.toolbar.page_box.setText("")
            return
        self._status_label.setText(
            status_text(self.view.current_page, self.model.page_count, self.view.zoom)
        )
        self.toolbar.page_box.setText(self._page_box_text())

    def _page_box_text(self) -> str:
        index = self.view.current_page
        return page_box_text(index, self.model.page_count, self.model.page_label(index))

    def _go_to_typed_page(self, text: str) -> None:
        """Called when the user presses Enter in the page box."""
        if text != self._page_box_text():  # unchanged text: nothing to do
            index = self.model.find_page(text)
            if index is None:
                self.statusBar().showMessage(
                    f'There is no page "{text.strip()}" in this document.',
                    MESSAGE_MILLISECONDS,
                )
                self._refresh_page_display()
                self.toolbar.page_box.selectAll()
                return
            self.view.go_to_page(index)
        self.view.setFocus()  # so PgUp/PgDn work again right away
        self._refresh_page_display()

    # --- events Qt sends ------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Something is being dragged over the window: say whether we take it."""
        if first_local_file(event.mimeData()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """A file was dropped on the window: open it."""
        path = first_local_file(event.mimeData())
        if path is None:
            return
        event.acceptProposedAction()
        # Open it a moment later, not inside this event. The program the
        # file was dragged from (Explorer, say) waits until the drop is
        # handled, and an error dialog here would freeze it meanwhile.
        QTimer.singleShot(0, lambda: self.open_path(path))

    def closeEvent(self, event: QCloseEvent) -> None:
        """The window is closing: let go of the file."""
        self.view.set_document(None)
        self.model.close()
        super().closeEvent(event)
