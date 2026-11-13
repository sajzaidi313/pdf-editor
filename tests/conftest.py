"""Shared pytest fixtures. pytest loads conftest.py automatically.

The word "fixture" means two different things in this project:

- A *fixture PDF* is a sample file in tests/fixtures/.
- A *pytest fixture* is a function marked with @pytest.fixture. When a test
  has a parameter with the same name as that function, pytest calls the
  function and passes its result in. Tests get what they need by naming it,
  with no setup code of their own.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from pdfeditor.core.document import DocumentModel

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Folder that holds the sample PDFs."""
    return FIXTURES_DIR


@pytest.fixture
def model() -> Iterator[DocumentModel]:
    """An empty DocumentModel that is closed again when the test ends.

    A fixture that uses `yield` runs in two halves: everything before the
    yield prepares the test, everything after it cleans up, even when the
    test failed. Closing matters on Windows, where an open file cannot be
    deleted and pytest wants to remove its temporary folders.
    """
    document_model = DocumentModel()
    yield document_model
    document_model.close()
