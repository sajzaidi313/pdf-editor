"""Shared pytest fixtures. pytest loads conftest.py automatically.

The word "fixture" means two different things in this project:

- A *fixture PDF* is a sample file in tests/fixtures/.
- A *pytest fixture* is a function marked with @pytest.fixture. When a test
  has a parameter with the same name as that function, pytest calls the
  function and passes its result in. Tests get what they need by naming it,
  with no setup code of their own.
"""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Folder that holds the sample PDFs."""
    return FIXTURES_DIR
