"""The sidebar: the outline tree and how the dock is wired to the window.

outline_nested.pdf has six pages and this outline (tests/fixtures/README.md):

    Chapter 1            -> page 1
        Section 1.1      -> page 2
            Detail 1.1.1 -> page 3
        Section 1.2      -> page 4
    Chapter 2            -> page 5
        Section 2.1      -> page 6
    Lost bookmark        -> nowhere
"""

import pytest
from PySide6.QtCore import QModelIndex, Qt

from pdfeditor.core.document import OutlineEntry
from pdfeditor.ui.sidebar import NO_OUTLINE_TEXT, OutlinePanel


@pytest.fixture
def panel(qtbot) -> OutlinePanel:
    outline_panel = OutlinePanel()
    qtbot.addWidget(outline_panel)
    outline_panel.resize(250, 400)
    outline_panel.show()
    qtbot.waitExposed(outline_panel)
    return outline_panel


def titles_under(panel: OutlinePanel, parent: QModelIndex | None = None) -> list[str]:
    """The texts of the rows directly below `parent` (the top level for None)."""
    parent = parent or QModelIndex()
    model = panel.model()
    return [model.index(row, 0, parent).data() for row in range(model.rowCount(parent))]


def index_of(panel: OutlinePanel, *path: int) -> QModelIndex:
    """The row reached by going down the tree: index_of(panel, 0, 1) is the
    second child of the first top-level row."""
    index = QModelIndex()
    for row in path:
        index = panel.model().index(row, 0, index)
    return index


def click_row(qtbot, panel: OutlinePanel, index: QModelIndex) -> None:
    panel.scrollTo(index)
    spot = panel.visualRect(index).center()
    qtbot.mouseClick(panel.viewport(), Qt.MouseButton.LeftButton, pos=spot)


NESTED = [
    OutlineEntry(1, "Chapter 1", 0),
    OutlineEntry(2, "Section 1.1", 1),
    OutlineEntry(3, "Detail 1.1.1", 2),
    OutlineEntry(2, "Section 1.2", 3),
    OutlineEntry(1, "Chapter 2", 4),
    OutlineEntry(1, "Lost bookmark", None),
]


# --- the outline tree ---------------------------------------------------------------


def test_empty_outline_shows_a_note(panel):
    assert titles_under(panel) == [NO_OUTLINE_TEXT]
    note = index_of(panel, 0)
    assert not note.flags() & Qt.ItemFlag.ItemIsEnabled


def test_entries_are_nested_by_their_level(panel):
    panel.set_entries(NESTED)

    assert titles_under(panel) == ["Chapter 1", "Chapter 2", "Lost bookmark"]
    chapter_1 = index_of(panel, 0)
    assert titles_under(panel, chapter_1) == ["Section 1.1", "Section 1.2"]
    assert titles_under(panel, index_of(panel, 0, 0)) == ["Detail 1.1.1"]
    assert titles_under(panel, index_of(panel, 1)) == []


def test_a_level_that_skips_a_step_still_finds_a_parent(panel):
    # Badly made files jump from level 1 straight to level 3.
    panel.set_entries([OutlineEntry(1, "Top", 0), OutlineEntry(3, "Deep", 1)])

    assert titles_under(panel) == ["Top"]
    assert titles_under(panel, index_of(panel, 0)) == ["Deep"]


def test_setting_entries_again_replaces_the_old_ones(panel):
    panel.set_entries(NESTED)

    panel.set_entries([OutlineEntry(1, "Only one", 0)])

    assert titles_under(panel) == ["Only one"]


def test_clicking_an_entry_asks_for_its_page(qtbot, panel):
    panel.set_entries(NESTED)

    # waitSignal fails the test unless the signal arrives while the
    # indented code runs; `blocker.args` holds what the signal carried.
    with qtbot.waitSignal(panel.page_requested, timeout=1000) as blocker:
        click_row(qtbot, panel, index_of(panel, 1))  # "Chapter 2"

    assert blocker.args == [4]


def test_clicking_a_nested_entry_asks_for_its_page(qtbot, panel):
    panel.set_entries(NESTED)

    with qtbot.waitSignal(panel.page_requested, timeout=1000) as blocker:
        click_row(qtbot, panel, index_of(panel, 0, 1))  # "Section 1.2"

    assert blocker.args == [3]


def test_a_bookmark_without_target_cannot_be_followed(qtbot, panel):
    panel.set_entries(NESTED)
    lost = index_of(panel, 2)

    assert not lost.flags() & Qt.ItemFlag.ItemIsEnabled
    # assertNotEmitted fails the test if the signal does arrive.
    with qtbot.assertNotEmitted(panel.page_requested, wait=100):
        click_row(qtbot, panel, lost)


# --- the sidebar in the main window ---------------------------------------------------


def test_the_window_has_a_sidebar_with_two_tabs(window):
    tabs = window.sidebar.tabs

    assert window.sidebar.isVisible()
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Thumbnails",
        "Outline",
    ]


def test_opening_a_file_fills_the_outline(window, fixtures_dir):
    window.open_path(fixtures_dir / "outline_nested.pdf")

    outline = window.sidebar.outline
    assert titles_under(outline) == ["Chapter 1", "Chapter 2", "Lost bookmark"]


def test_a_file_without_outline_shows_the_note(window, fixtures_dir):
    window.open_path(fixtures_dir / "outline_nested.pdf")

    window.open_path(fixtures_dir / "simple_text.pdf")

    assert titles_under(window.sidebar.outline) == [NO_OUTLINE_TEXT]


def test_clicking_an_outline_entry_goes_to_its_page(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "outline_nested.pdf")
    outline = window.sidebar.outline
    window.sidebar.tabs.setCurrentWidget(outline)

    click_row(qtbot, outline, index_of(outline, 1))  # "Chapter 2" -> page 5

    assert window.view.current_page == 4


def test_the_sidebar_can_be_hidden_and_shown_from_the_view_menu(window):
    window.sidebar_action.trigger()
    assert not window.sidebar.isVisible()

    window.sidebar_action.trigger()
    assert window.sidebar.isVisible()


def test_the_outline_is_emptied_when_a_file_cannot_be_unlocked(
    window, fixtures_dir, password_prompt
):
    window.open_path(fixtures_dir / "outline_nested.pdf")
    password_prompt.answers = [None]  # the user cancels the password prompt

    window.open_path(fixtures_dir / "encrypted_user_pw.pdf")

    assert titles_under(window.sidebar.outline) == [NO_OUTLINE_TEXT]
    assert window.sidebar.thumbnail_model.rowCount() == 0
