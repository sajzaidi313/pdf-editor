"""The sidebar: a panel beside the pages with a Thumbnails and an Outline tab.

A QDockWidget is a panel that sits at an edge of the main window. The user
can drag it to the other side or close it (View > Sidebar brings it back).
"""

from collections.abc import Sequence

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QDockWidget, QTabWidget, QTreeView, QWidget

from pdfeditor.core.document import DocumentModel, OutlineEntry
from pdfeditor.ui.thumbnails import ThumbnailModel, ThumbnailView

# Besides its text, an item in a Qt model can carry extra values, each
# stored under a numbered "role". Roles from UserRole upward are free for
# the app's own use; this one holds an outline entry's target page.
PAGE_ROLE = Qt.ItemDataRole.UserRole + 1

NO_OUTLINE_TEXT = "This document has no outline."
NO_TARGET_TOOLTIP = "This bookmark does not point to a page."


class OutlinePanel(QTreeView):
    """The PDF's outline (bookmarks) as a tree. A click asks for its page.

    Model/view again (see thumbnails.py), but with a ready-made model:
    QStandardItemModel stores a tree of QStandardItems, which is all an
    outline needs. A model of our own is only worth writing when the data
    is large or expensive, like the thumbnails.
    """

    page_requested = Signal(int)  # the 0-based index of the target page

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items = QStandardItemModel(self)
        self.setModel(self._items)
        self.setHeaderHidden(True)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.clicked.connect(self._request_page)
        self.activated.connect(self._request_page)  # Enter on the keyboard
        self.set_entries([])

    def set_entries(self, entries: Sequence[OutlineEntry]) -> None:
        """Rebuild the tree from a flat list of entries with levels."""
        self._items.clear()
        # The chain of entries the next one could sit inside: the last
        # level-1 entry, the last level-2 entry below it, and so on.
        open_levels: list[tuple[int, QStandardItem]] = []
        for entry in entries:
            item = _outline_item(entry)
            # Entries at the same or a deeper level than this one are
            # finished: nothing more goes inside them.
            while open_levels and open_levels[-1][0] >= entry.level:
                open_levels.pop()
            if open_levels:
                open_levels[-1][1].appendRow(item)
            else:
                self._items.appendRow(item)
            open_levels.append((entry.level, item))
        if not entries:
            note = QStandardItem(NO_OUTLINE_TEXT)
            note.setEnabled(False)
            self._items.appendRow(note)
        self.expandToDepth(0)  # show the entries directly below the top ones

    def _request_page(self, index: QModelIndex) -> None:
        page_index = index.data(PAGE_ROLE)
        if page_index is not None:
            self.page_requested.emit(page_index)


def _outline_item(entry: OutlineEntry) -> QStandardItem:
    item = QStandardItem(entry.title)
    item.setEditable(False)
    item.setData(entry.page_index, PAGE_ROLE)
    if entry.page_index is None:
        item.setEnabled(False)  # shown gray, cannot be clicked
        item.setToolTip(NO_TARGET_TOOLTIP)
    return item


class Sidebar(QDockWidget):
    """The dock with the thumbnails and the outline."""

    # Emitted when the user picks a page in either tab.
    page_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Sidebar", parent)
        self.setObjectName("sidebar")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        # Closable and movable, but not "floating" as a separate window.
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.thumbnail_model = ThumbnailModel(self)
        self.thumbnails = ThumbnailView(self)
        self.thumbnails.setModel(self.thumbnail_model)
        self.outline = OutlinePanel(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.thumbnails, "Thumbnails")
        self.tabs.addTab(self.outline, "Outline")
        self.setWidget(self.tabs)
        # A signal can be connected straight to another signal, which then
        # simply passes the news on.
        self.thumbnails.page_requested.connect(self.page_requested)
        self.outline.page_requested.connect(self.page_requested)

    def set_document(self, model: DocumentModel | None) -> None:
        """Show the thumbnails and outline of `model`, or nothing for None.

        Call set_document(None) before the model is closed (the
        thumbnails are drawn later, when they scroll into view).
        """
        self.thumbnail_model.set_document(model, self.devicePixelRatioF())
        self.outline.set_entries([] if model is None else model.outline())

    def set_current_page(self, page_index: int) -> None:
        """Mark the page the user is looking at in the thumbnails."""
        self.thumbnails.set_current_page(page_index)
