"""Find: the find bar, and the controller that searches page by page.

search_and_select.pdf has three pages; "lazy dog" occurs four times: twice
on page 1 (one of them split over two lines), once on page 2 and once on
the rotated page 3.
"""

import pytest
from PySide6.QtCore import Qt

from pdfeditor.ui import find_bar as find_bar_module
from pdfeditor.ui.find_bar import FindBar, find_status
from pdfeditor.ui.overlays import OverlayLayer


@pytest.fixture
def bar(qtbot) -> FindBar:
    """A find bar on its own, opened."""
    find_bar = FindBar()
    qtbot.addWidget(find_bar)
    find_bar.open_bar()
    qtbot.waitExposed(find_bar)
    return find_bar


@pytest.fixture
def searched(qtbot, window, fixtures_dir):
    """A window showing search_and_select.pdf. Call it with a text to
    search for that text and wait until every page has been searched."""
    window.open_path(fixtures_dir / "search_and_select.pdf")

    def search_for(needle: str):
        with qtbot.waitSignal(window.finder.finished, timeout=3000):
            window.finder.start(needle)
        return window

    return search_for


# --- the status text ----------------------------------------------------------------


def test_find_status_texts():
    assert find_status(3, 17, searching=False) == "3 of 17"
    assert find_status(3, 17, searching=True) == "3 of 17…"
    assert find_status(0, 0, searching=True) == "Searching…"
    assert find_status(0, 0, searching=False) == "No matches"


# --- the find bar ---------------------------------------------------------------------


def test_the_bar_is_hidden_until_opened(qtbot):
    find_bar = FindBar()
    qtbot.addWidget(find_bar)

    assert find_bar.isHidden()


def test_typing_asks_for_a_search_once_the_user_pauses(qtbot, bar):
    with qtbot.waitSignal(bar.search_requested, timeout=2000) as blocker:
        qtbot.keyClicks(bar.box, "lazy")

    assert blocker.args == ["lazy"]  # one search for the word, not four


def test_typing_does_not_search_before_the_pause(qtbot, bar):
    assert find_bar_module.SEARCH_DELAY_MS >= 200

    with qtbot.assertNotEmitted(bar.search_requested, wait=50):
        qtbot.keyClicks(bar.box, "lazy")


def test_enter_right_after_typing_searches_at_once(qtbot, bar):
    qtbot.keyClicks(bar.box, "lazy")

    with qtbot.waitSignal(bar.search_requested, timeout=100) as blocker:
        qtbot.keyClick(bar.box, Qt.Key.Key_Return)

    assert blocker.args == ["lazy"]


def test_enter_asks_for_the_next_hit_and_shift_enter_for_the_previous(qtbot, bar):
    with qtbot.waitSignal(bar.next_requested, timeout=100):
        qtbot.keyClick(bar.box, Qt.Key.Key_Return)

    with qtbot.waitSignal(bar.previous_requested, timeout=100):
        qtbot.keyClick(bar.box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)


def test_the_buttons_ask_for_next_and_previous(qtbot, bar):
    with qtbot.waitSignal(bar.next_requested, timeout=100):
        bar.next_action.trigger()
    with qtbot.waitSignal(bar.previous_requested, timeout=100):
        bar.previous_action.trigger()


def test_escape_closes_the_bar(qtbot, bar):
    with qtbot.waitSignal(bar.closed, timeout=100):
        qtbot.keyClick(bar.box, Qt.Key.Key_Escape)

    assert bar.isHidden()


def test_closing_cancels_a_search_that_was_about_to_start(qtbot, bar):
    qtbot.keyClicks(bar.box, "lazy")

    with qtbot.assertNotEmitted(bar.search_requested, wait=400):
        bar.close_action.trigger()


def test_status_can_be_set_and_read_back(bar):
    bar.set_status("3 of 17")

    assert bar.status() == "3 of 17"


# --- searching a document -------------------------------------------------------


def test_search_finds_every_hit_in_the_document(searched):
    window = searched("lazy dog")

    assert len(window.finder.results) == 4
    assert not window.finder.is_searching
    assert window.find_bar.status() == "1 of 4"


def test_hits_are_marked_on_their_pages(searched):
    window = searched("lazy dog")

    assert window.view.overlay_pages(OverlayLayer.SEARCH_HITS) == {0, 1, 2}
    # Page 1 has two hits; the split one needs two shapes.
    assert window.view.overlay(OverlayLayer.SEARCH_HITS, 0).shape_count == 3
    assert window.view.overlay(OverlayLayer.SEARCH_HITS, 1).shape_count == 1


def test_the_first_hit_becomes_the_current_one(searched):
    window = searched("lazy dog")

    assert window.finder.current == window.finder.results.on_page(0)[0]
    assert window.view.overlay_pages(OverlayLayer.CURRENT_HIT) == {0}
    assert window.view.overlay(OverlayLayer.CURRENT_HIT, 0).shape_count == 2


def test_next_steps_through_the_hits_and_wraps_around(searched):
    window = searched("lazy dog")
    seen = [window.find_bar.status()]

    for _ in range(4):
        window.finder.find_next()
        seen.append(window.find_bar.status())

    assert seen == ["1 of 4", "2 of 4", "3 of 4", "4 of 4", "1 of 4"]


def test_previous_from_the_first_hit_goes_to_the_last(searched):
    window = searched("lazy dog")

    window.finder.find_previous()

    assert window.find_bar.status() == "4 of 4"
    assert window.finder.current.page_index == 2
    assert window.view.overlay_pages(OverlayLayer.CURRENT_HIT) == {2}


def test_stepping_to_a_hit_brings_its_page_into_view(searched):
    window = searched("lazy dog")
    assert window.view.current_page == 0

    window.finder.find_next()  # the second hit is still on page 1
    window.finder.find_next()  # the third is on page 2

    assert window.view.current_page == 1


def test_the_search_starts_at_the_page_being_looked_at(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "search_and_select.pdf")
    window.view.go_to_page(1)

    with qtbot.waitSignal(window.finder.finished, timeout=3000):
        window.finder.start("lazy dog")

    # The hit on page 2 is the third in the document, and the first shown.
    assert window.finder.current.page_index == 1
    assert window.find_bar.status() == "3 of 4"


def test_upper_and_lower_case_do_not_matter(searched):
    window = searched("LAZY DOG")

    assert len(window.finder.results) == 4


def test_text_that_does_not_occur(searched):
    window = searched("unicorn")

    assert len(window.finder.results) == 0
    assert window.finder.current is None
    assert window.find_bar.status() == "No matches"
    assert window.view.overlay_pages(OverlayLayer.SEARCH_HITS) == set()


def test_next_without_hits_does_nothing(searched):
    window = searched("unicorn")

    window.finder.find_next()
    window.finder.find_previous()

    assert window.find_bar.status() == "No matches"


def test_an_empty_search_clears_everything(searched):
    window = searched("lazy dog")

    window.finder.start("   ")

    assert len(window.finder.results) == 0
    assert window.find_bar.status() == ""
    assert window.view.overlay_pages(OverlayLayer.SEARCH_HITS) == set()
    assert window.view.overlay_pages(OverlayLayer.CURRENT_HIT) == set()


def test_a_new_search_replaces_the_old_one(searched):
    window = searched("lazy dog")

    window = searched("hyphenation")

    assert len(window.finder.results) == 1
    assert window.view.overlay_pages(OverlayLayer.SEARCH_HITS) == {0}


def test_the_window_stays_responsive_while_searching(qtbot, window, fixtures_dir):
    """The search does one page at a time, so right after start() only
    the first page has been searched at most."""
    window.open_path(fixtures_dir / "search_and_select.pdf")

    window.finder.start("lazy dog")

    assert window.finder.is_searching
    assert len(window.finder.results) == 0  # nothing happened inside start()
    with qtbot.waitSignal(window.finder.finished, timeout=3000):
        pass
    assert len(window.finder.results) == 4


# --- the find bar in the main window --------------------------------------------


def test_find_commands_need_a_document(window, fixtures_dir):
    assert not window.find_action.isEnabled()
    assert not window.find_next_action.isEnabled()

    window.open_path(fixtures_dir / "simple_text.pdf")

    assert window.find_action.isEnabled()
    assert window.find_previous_action.isEnabled()


def test_the_find_command_opens_the_bar(window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")
    assert window.find_bar.isHidden()

    window.find_action.trigger()

    assert window.find_bar.isVisible()


def test_typing_in_the_bar_searches_the_document(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "search_and_select.pdf")
    window.find_action.trigger()

    with qtbot.waitSignal(window.finder.finished, timeout=3000):
        qtbot.keyClicks(window.find_bar.box, "fox")
        qtbot.keyClick(window.find_bar.box, Qt.Key.Key_Return)

    assert window.find_bar.status() == "1 of 4"


def test_closing_the_bar_removes_the_marks(searched):
    window = searched("lazy dog")
    window.find_bar.open_bar()

    window.find_bar.close_bar()

    assert len(window.finder.results) == 0
    assert window.view.overlay_pages(OverlayLayer.SEARCH_HITS) == set()
    assert window.view.overlay_pages(OverlayLayer.CURRENT_HIT) == set()


def test_escape_closes_the_bar_even_when_the_pages_have_the_focus(
    qtbot, window, fixtures_dir
):
    window.open_path(fixtures_dir / "simple_text.pdf")
    window.find_action.trigger()
    window.view.setFocus()  # as if the user had clicked on a page

    qtbot.keyClick(window.view, Qt.Key.Key_Escape)

    assert window.find_bar.isHidden()


def test_opening_another_file_searches_it_for_the_same_text(
    qtbot, window, fixtures_dir
):
    window.open_path(fixtures_dir / "search_and_select.pdf")
    window.find_action.trigger()
    window.find_bar.box.setText("lazy dog")
    with qtbot.waitSignal(window.finder.finished, timeout=3000):
        window.finder.start("lazy dog")

    with qtbot.waitSignal(window.finder.finished, timeout=3000):
        window.open_path(fixtures_dir / "simple_text.pdf")

    # simple_text.pdf has "lazy dog" once, on its first page.
    assert window.find_bar.status() == "1 of 1"
    assert window.view.overlay_pages(OverlayLayer.SEARCH_HITS) == {0}


def test_opening_another_file_with_the_bar_closed_forgets_the_search(
    searched, fixtures_dir
):
    window = searched("lazy dog")

    window.open_path(fixtures_dir / "simple_text.pdf")

    assert len(window.finder.results) == 0
    assert not window.finder.is_searching


def test_find_next_after_a_new_file_searches_for_the_text_in_the_box(
    qtbot, window, fixtures_dir
):
    window.open_path(fixtures_dir / "simple_text.pdf")
    window.find_bar.box.setText("quick")  # typed earlier; the bar is closed now

    with qtbot.waitSignal(window.finder.finished, timeout=3000):
        window.find_next_action.trigger()

    assert len(window.finder.results) == 1


def test_closing_the_window_during_a_search_is_harmless(qtbot, window, fixtures_dir):
    window.open_path(fixtures_dir / "search_and_select.pdf")
    window.finder.start("lazy dog")

    window.close()  # the search has not looked at a single page yet
    qtbot.wait(50)

    assert not window.finder.is_searching
    assert len(window.finder.results) == 0
