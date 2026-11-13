"""The Open Recent list: its rules, its storage, and its menu in the window."""

from pathlib import Path

from PySide6.QtCore import QSettings

from pdfeditor.ui.recent_files import MAX_RECENT_FILES, RecentFiles


def names(recent: RecentFiles) -> list[str]:
    return [path.name for path in recent.paths()]


# --- the list itself ------------------------------------------------------------


def test_starts_empty(settings):
    assert RecentFiles(settings).paths() == []


def test_newest_file_comes_first(settings, tmp_path):
    recent = RecentFiles(settings)

    recent.add(tmp_path / "a.pdf")
    recent.add(tmp_path / "b.pdf")

    assert names(recent) == ["b.pdf", "a.pdf"]


def test_opening_a_file_again_moves_it_to_the_top(settings, tmp_path):
    recent = RecentFiles(settings)
    recent.add(tmp_path / "a.pdf")
    recent.add(tmp_path / "b.pdf")

    recent.add(tmp_path / "a.pdf")

    assert names(recent) == ["a.pdf", "b.pdf"]  # no duplicate


def test_keeps_at_most_ten_files(settings, tmp_path):
    recent = RecentFiles(settings)

    for number in range(15):
        recent.add(tmp_path / f"file{number}.pdf")

    assert len(recent.paths()) == MAX_RECENT_FILES == 10
    assert names(recent)[0] == "file14.pdf"  # the newest
    assert names(recent)[-1] == "file5.pdf"  # the oldest that still fits


def test_paths_are_stored_absolute(settings):
    recent = RecentFiles(settings)

    recent.add(Path("relative.pdf"))

    assert recent.paths()[0].is_absolute()


def test_remove_and_clear(settings, tmp_path):
    recent = RecentFiles(settings)
    recent.add(tmp_path / "a.pdf")
    recent.add(tmp_path / "b.pdf")

    recent.remove(tmp_path / "a.pdf")
    assert names(recent) == ["b.pdf"]

    recent.clear()
    assert recent.paths() == []


def test_list_survives_a_restart(tmp_path):
    """Two QSettings objects on the same file act like two runs of the app."""
    settings_file = str(tmp_path / "settings.ini")
    first_run = QSettings(settings_file, QSettings.Format.IniFormat)
    RecentFiles(first_run).add(tmp_path / "only.pdf")
    first_run.sync()  # write to disk now, as happens when the app quits

    second_run = QSettings(settings_file, QSettings.Format.IniFormat)

    # One entry is the tricky case: QSettings returns it as a plain string.
    assert names(RecentFiles(second_run)) == ["only.pdf"]


def test_two_entries_survive_a_restart(tmp_path):
    settings_file = str(tmp_path / "settings.ini")
    first_run = QSettings(settings_file, QSettings.Format.IniFormat)
    RecentFiles(first_run).add(tmp_path / "a.pdf")
    RecentFiles(first_run).add(tmp_path / "b.pdf")
    first_run.sync()

    second_run = QSettings(settings_file, QSettings.Format.IniFormat)

    assert names(RecentFiles(second_run)) == ["b.pdf", "a.pdf"]


# --- in the window --------------------------------------------------------------


def recent_menu_texts(window) -> list[str]:
    return [action.text() for action in window._recent_menu.actions() if action.text()]


def test_recent_menu_is_disabled_when_empty(window):
    assert not window._recent_menu.isEnabled()


def test_opened_files_appear_in_the_recent_menu(window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")
    window.open_path(fixtures_dir / "rotated_pages.pdf")

    assert window._recent_menu.isEnabled()
    assert recent_menu_texts(window) == [
        "&1  rotated_pages.pdf",
        "&2  simple_text.pdf",
        "&Clear Recent Files",
    ]


def test_choosing_a_recent_file_opens_it(window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")
    window.open_path(fixtures_dir / "rotated_pages.pdf")

    window._recent_menu.actions()[1].trigger()  # the second entry

    assert window.windowTitle() == "simple_text.pdf - PDF Editor"
    assert recent_menu_texts(window)[0] == "&1  simple_text.pdf"


def test_clear_recent_files_empties_the_menu(window, fixtures_dir):
    window.open_path(fixtures_dir / "simple_text.pdf")

    window._recent_menu.actions()[-1].trigger()  # "Clear Recent Files"

    assert window.recent_files.paths() == []
    assert not window._recent_menu.isEnabled()


def test_bad_files_are_not_remembered(window, fixtures_dir):
    window.open_path(fixtures_dir / "not_a_pdf.pdf")

    assert window.recent_files.paths() == []


def test_recent_file_that_vanished_is_dropped_from_the_list(
    window, shown_errors, fixtures_dir, tmp_path
):
    vanished = tmp_path / "vanished.pdf"
    vanished.write_bytes((fixtures_dir / "simple_text.pdf").read_bytes())
    window.open_path(vanished)
    window.open_path(fixtures_dir / "rotated_pages.pdf")  # lets go of vanished.pdf
    vanished.unlink()  # delete it behind the app's back

    window._recent_menu.actions()[1].trigger()

    assert "was not found" in shown_errors[0][1]
    assert names(window.recent_files) == ["rotated_pages.pdf"]


def test_ampersand_in_a_file_name_is_shown_literally(window, fixtures_dir, tmp_path):
    odd_name = tmp_path / "Q&A.pdf"
    odd_name.write_bytes((fixtures_dir / "simple_text.pdf").read_bytes())

    window.open_path(odd_name)

    assert recent_menu_texts(window)[0] == "&1  Q&&A.pdf"
