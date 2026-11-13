"""The "Open Recent" list, remembered between runs of the app.

QSettings is Qt's small key-value store for user preferences. It saves to
the place each system expects (the registry on Windows, a .plist file on
macOS, a config file on Linux), so the app never has to choose a location.

Only file paths are stored here. Passwords never are (docs/09 §1).
"""

from pathlib import Path

from PySide6.QtCore import QSettings

MAX_RECENT_FILES = 10
SETTINGS_KEY = "recent_files"


class RecentFiles:
    """The most recently opened files, newest first, at most ten."""

    def __init__(self, settings: QSettings) -> None:
        # The settings object is passed in, instead of created here, so
        # tests can hand over a throwaway file and leave the real
        # settings alone.
        self._settings = settings

    def paths(self) -> list[Path]:
        """The remembered files, newest first."""
        stored = self._settings.value(SETTINGS_KEY, [])
        # QSettings hands a list with one entry back as a bare string, and
        # an empty list as None or "". Tidy all of that into a list.
        if isinstance(stored, str):
            stored = [stored] if stored else []
        if not isinstance(stored, list):
            return []
        return [Path(text) for text in stored if isinstance(text, str) and text]

    def add(self, path: Path) -> None:
        """Put `path` at the top of the list (moving it there if present)."""
        # resolve() makes the path absolute, so the same file opened as
        # "a.pdf" and as "C:\docs\a.pdf" is listed only once.
        path = path.resolve()
        others = [other for other in self.paths() if other != path]
        self._save([path, *others][:MAX_RECENT_FILES])

    def remove(self, path: Path) -> None:
        """Drop `path` from the list (for a file that no longer exists)."""
        path = path.resolve()
        self._save([other for other in self.paths() if other != path])

    def clear(self) -> None:
        self._save([])

    def _save(self, paths: list[Path]) -> None:
        self._settings.setValue(SETTINGS_KEY, [str(path) for path in paths])
