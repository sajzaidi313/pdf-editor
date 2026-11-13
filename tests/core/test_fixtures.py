"""The sample PDFs open and contain what tests/fixtures/README.md says.

DocumentModel does not exist until milestone M1, so these tests talk to
PyMuPDF directly. They prove the install and the fixtures work.
"""

import pymupdf


# `fixtures_dir` is a pytest fixture from tests/conftest.py: pytest sees the
# parameter name and passes in the folder path.
def test_simple_text_has_two_pages(fixtures_dir):
    # `with` closes the document when the block ends, even if the assert fails.
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        assert doc.page_count == 2
        assert "Lorem ipsum" in doc[0].get_text()


def test_rotated_pages_has_one_page_per_rotation(fixtures_dir):
    with pymupdf.open(fixtures_dir / "rotated_pages.pdf") as doc:
        assert [page.rotation for page in doc] == [0, 90, 180, 270]
