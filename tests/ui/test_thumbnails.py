"""Thumbnails: the model that draws them on demand, and the list that shows them.

page_labels.pdf has eight Letter pages labelled i, ii, iii, iv, 1, 2, 3, 4.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QModelIndex, QSize, Qt

from pdfeditor.ui import thumbnails
from pdfeditor.ui.thumbnails import ThumbnailModel, ThumbnailView, thumbnail_size

ROLE = Qt.ItemDataRole


@pytest.fixture
def thumbnail_model(qtbot, model) -> Iterator[ThumbnailModel]:
    """An empty ThumbnailModel that lets go of the document afterwards."""
    list_model = ThumbnailModel()
    yield list_model
    # Before the `model` fixture closes the document (see conftest.py).
    list_model.set_document(None)


@pytest.fixture
def eight_thumbnails(thumbnail_model, model, fixtures_dir) -> ThumbnailModel:
    model.open(fixtures_dir / "page_labels.pdf")
    thumbnail_model.set_document(model)
    return thumbnail_model


@pytest.fixture
def thumbnail_view(qtbot, eight_thumbnails) -> ThumbnailView:
    """A shown list of the eight thumbnails, too short to show them all."""
    view = ThumbnailView()
    qtbot.addWidget(view)
    view.setModel(eight_thumbnails)
    view.resize(200, 380)
    view.show()
    qtbot.waitExposed(view)
    return view


def wait_until_drawn(qtbot, list_model: ThumbnailModel, rows: set[int]) -> None:
    # waitUntil calls the function again and again until it returns True,
    # and fails the test if that takes longer than the timeout.
    qtbot.waitUntil(lambda: rows <= list_model.drawn_rows(), timeout=3000)


# --- sizes ---------------------------------------------------------------------------


def test_an_upright_page_is_limited_by_the_width():
    # 792 x (120 / 612) = 155.3, rounded up like PyMuPDF does for pictures.
    assert thumbnail_size(612, 792) == QSize(120, 156)


def test_a_page_on_its_side_is_wide_and_flat():
    assert thumbnail_size(792, 612) == QSize(120, 93)


def test_a_very_tall_page_is_limited_by_the_height():
    assert thumbnail_size(100, 2000) == QSize(9, 180)


def test_the_reserved_size_matches_the_picture_for_every_fixture_page(
    qtbot, thumbnail_model, model, fixtures_dir
):
    for name in ("rotated_pages.pdf", "cropbox_offset.pdf", "simple_text.pdf"):
        model.open(fixtures_dir / name)
        thumbnail_model.set_document(model)
        rows = set(range(model.page_count))
        blanks = [
            thumbnail_model.index(row, 0).data(ROLE.DecorationRole) for row in rows
        ]
        wait_until_drawn(qtbot, thumbnail_model, rows)

        drawn = [
            thumbnail_model.index(row, 0).data(ROLE.DecorationRole) for row in rows
        ]

        assert [picture.size() for picture in drawn] == [
            picture.size() for picture in blanks
        ], name
        thumbnail_model.set_document(None)


# --- the model -----------------------------------------------------------------------


def test_empty_model_has_no_rows(thumbnail_model):
    assert thumbnail_model.rowCount() == 0


def test_one_row_per_page(eight_thumbnails):
    assert eight_thumbnails.rowCount() == 8
    # A list has no rows *inside* a row.
    assert eight_thumbnails.rowCount(eight_thumbnails.index(0, 0)) == 0


def test_rows_are_named_by_page_label(eight_thumbnails):
    names = [eight_thumbnails.index(row, 0).data(ROLE.DisplayRole) for row in range(8)]

    assert names == ["i", "ii", "iii", "iv", "1", "2", "3", "4"]


def test_rows_of_a_file_without_labels_are_numbered(
    thumbnail_model, model, fixtures_dir
):
    model.open(fixtures_dir / "simple_text.pdf")
    thumbnail_model.set_document(model)

    names = [thumbnail_model.index(row, 0).data(ROLE.DisplayRole) for row in range(2)]

    assert names == ["1", "2"]
    assert thumbnail_model.index(1, 0).data(ROLE.ToolTipRole) == "Page 2"


def test_row_size_leaves_room_for_picture_label_and_padding(eight_thumbnails):
    size = eight_thumbnails.index(0, 0).data(ROLE.SizeHintRole)

    padding = 2 * thumbnails.ITEM_PADDING
    assert size == QSize(120 + padding, 156 + thumbnails.LABEL_HEIGHT + padding)


def test_rows_on_their_side_are_less_tall(thumbnail_model, model, fixtures_dir):
    model.open(fixtures_dir / "rotated_pages.pdf")  # rotated 0, 90, 180, 270
    thumbnail_model.set_document(model)

    heights = [
        thumbnail_model.index(row, 0).data(ROLE.SizeHintRole).height()
        for row in range(4)
    ]

    assert heights[0] == heights[2] > heights[1] == heights[3]


def test_an_invalid_index_has_no_data(eight_thumbnails):
    assert eight_thumbnails.data(QModelIndex(), ROLE.DisplayRole) is None
    # A role this model does not serve.
    assert eight_thumbnails.index(0, 0).data(ROLE.FontRole) is None


def test_a_picture_is_blank_at_first_and_drawn_a_moment_later(qtbot, eight_thumbnails):
    index = eight_thumbnails.index(2, 0)

    blank = index.data(ROLE.DecorationRole)

    assert eight_thumbnails.drawn_rows() == set()  # nothing drawn yet ...
    assert blank.size() == QSize(120, 156)  # ... but the right size already
    wait_until_drawn(qtbot, eight_thumbnails, {2})
    drawn = index.data(ROLE.DecorationRole)
    assert drawn.size() == blank.size()
    # The blank one is all white apart from its border; the drawn one has ink.
    assert drawn.toImage() != blank.toImage()


def test_the_view_is_told_when_a_picture_is_ready(qtbot, eight_thumbnails):
    with qtbot.waitSignal(eight_thumbnails.dataChanged, timeout=3000) as blocker:
        eight_thumbnails.index(5, 0).data(ROLE.DecorationRole)

    top_left, bottom_right, roles = blocker.args
    assert (top_left.row(), bottom_right.row()) == (5, 5)
    assert roles == [ROLE.DecorationRole]


def test_only_pictures_that_were_asked_for_are_drawn(qtbot, eight_thumbnails):
    eight_thumbnails.index(0, 0).data(ROLE.DecorationRole)
    eight_thumbnails.index(7, 0).data(ROLE.DecorationRole)

    wait_until_drawn(qtbot, eight_thumbnails, {0, 7})
    qtbot.wait(50)  # give it the chance to draw more, wrongly

    assert eight_thumbnails.drawn_rows() == {0, 7}


def test_old_requests_are_dropped_when_too_many_wait(
    qtbot, eight_thumbnails, monkeypatch
):
    monkeypatch.setattr(thumbnails, "MAX_WAITING", 3)

    for row in range(8):  # as if the list was scrolled quickly past all rows
        eight_thumbnails.index(row, 0).data(ROLE.DecorationRole)

    wait_until_drawn(qtbot, eight_thumbnails, {5, 6, 7})
    qtbot.wait(50)
    assert eight_thumbnails.drawn_rows() == {5, 6, 7}  # the three newest requests


def test_only_so_many_pictures_are_kept(qtbot, eight_thumbnails, monkeypatch):
    monkeypatch.setattr(thumbnails, "MAX_CACHED_THUMBNAILS", 2)

    for row in (0, 1, 2):
        eight_thumbnails.index(row, 0).data(ROLE.DecorationRole)
        wait_until_drawn(qtbot, eight_thumbnails, {row})

    assert eight_thumbnails.drawn_rows() == {1, 2}  # the oldest, row 0, was dropped


def test_another_document_starts_from_nothing(qtbot, eight_thumbnails, model):
    eight_thumbnails.index(0, 0).data(ROLE.DecorationRole)
    wait_until_drawn(qtbot, eight_thumbnails, {0})

    eight_thumbnails.set_document(None)

    assert eight_thumbnails.rowCount() == 0
    assert eight_thumbnails.drawn_rows() == set()


def test_requests_for_a_closed_document_are_forgotten(qtbot, eight_thumbnails):
    eight_thumbnails.index(0, 0).data(ROLE.DecorationRole)

    eight_thumbnails.set_document(None)  # before the timer could draw row 0
    qtbot.wait(50)

    assert eight_thumbnails.drawn_rows() == set()


# --- the list ------------------------------------------------------------------------


def test_the_list_draws_the_thumbnails_it_shows_and_no_others(qtbot, thumbnail_view):
    list_model = thumbnail_view.model()

    wait_until_drawn(qtbot, list_model, {0, 1})
    qtbot.wait(50)

    # A 380 pixel high list shows the first two or three of eight rows.
    assert list_model.drawn_rows() <= {0, 1, 2}


def test_clicking_a_thumbnail_asks_for_its_page(qtbot, thumbnail_view):
    index = thumbnail_view.model().index(1, 0)
    spot = thumbnail_view.visualRect(index).center()

    with qtbot.waitSignal(thumbnail_view.page_requested, timeout=1000) as blocker:
        qtbot.mouseClick(thumbnail_view.viewport(), Qt.MouseButton.LeftButton, pos=spot)

    assert blocker.args == [1]


def test_set_current_page_marks_the_row_and_scrolls_to_it(qtbot, thumbnail_view):
    thumbnail_view.set_current_page(7)

    index = thumbnail_view.model().index(7, 0)
    assert thumbnail_view.currentIndex() == index
    assert thumbnail_view.selectionModel().isSelected(index)
    # The last row is now inside the visible part of the list.
    assert thumbnail_view.viewport().rect().intersects(thumbnail_view.visualRect(index))


def test_marking_the_current_page_does_not_ask_for_a_page(qtbot, thumbnail_view):
    with qtbot.assertNotEmitted(thumbnail_view.page_requested, wait=50):
        thumbnail_view.set_current_page(3)


def test_a_page_that_does_not_exist_is_ignored(thumbnail_view):
    thumbnail_view.set_current_page(2)

    thumbnail_view.set_current_page(99)

    assert thumbnail_view.currentIndex().row() == 2


# --- in the main window ---------------------------------------------------------------


def test_opening_a_file_fills_the_thumbnails(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")

    list_model = window.sidebar.thumbnail_model
    assert list_model.rowCount() == 8
    assert window.sidebar.thumbnails.currentIndex().row() == 0
    wait_until_drawn(qtbot, list_model, {0})


def test_clicking_a_thumbnail_goes_to_that_page(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")
    thumbnail_list = window.sidebar.thumbnails
    spot = thumbnail_list.visualRect(thumbnail_list.model().index(2, 0)).center()

    qtbot.mouseClick(thumbnail_list.viewport(), Qt.MouseButton.LeftButton, pos=spot)

    assert window.view.current_page == 2


def test_the_current_thumbnail_follows_the_page_view(window, fixtures_dir):
    window.open_path(fixtures_dir / "page_labels.pdf")

    window.view.go_to_page(6)

    assert window.sidebar.thumbnails.currentIndex().row() == 6


def test_closing_the_window_while_thumbnails_wait_is_harmless(
    qtbot, window, fixtures_dir
):
    window.open_path(fixtures_dir / "page_labels.pdf")

    window.close()  # thumbnails are still waiting to be drawn
    qtbot.wait(50)

    assert window.sidebar.thumbnail_model.rowCount() == 0
