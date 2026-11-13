"""PDF logic with no user interface.

Hard rule: nothing in this package may import PySide6. Keeping Qt out means
the core can be tested without opening a window, and
`tests/core/test_no_qt_in_core.py` enforces it.
"""
