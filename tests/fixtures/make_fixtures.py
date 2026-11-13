"""Generate the sample PDFs ("fixtures") that the tests open.

Run it from the project root whenever a fixture needs to change:

    python tests/fixtures/make_fixtures.py

The PDFs are committed to git, so tests and CI never need to run this.
Building them with a script, instead of keeping hand-made files, means
anyone can see exactly what is inside each one. The same facts are written
down in README.md next to this script: update both together.
"""

from pathlib import Path

import pymupdf

FIXTURES_DIR = Path(__file__).parent

# US Letter paper in PDF points. 1 point = 1/72 inch, so 8.5 x 11 inches is:
LETTER_WIDTH = 612
LETTER_HEIGHT = 792

FONT_SIZE = 12
LEFT_MARGIN = 72  # one inch from the left edge
FIRST_BASELINE = 90  # y of the first line of text
LINE_SPACING = 30


def add_letter_page(doc: pymupdf.Document, lines: list[str]) -> pymupdf.Page:
    """Append a Letter page and write the lines of text onto it.

    insert_text() takes the start of the "baseline": the invisible line the
    letters sit on. PyMuPDF measures y downward from the top of the page, so
    the first line sits 90 points below the top edge.
    """
    page = doc.new_page(width=LETTER_WIDTH, height=LETTER_HEIGHT)
    for index, line in enumerate(lines):
        baseline_start = (LEFT_MARGIN, FIRST_BASELINE + index * LINE_SPACING)
        page.insert_text(baseline_start, line, fontsize=FONT_SIZE)
    return page


def save_and_close(doc: pymupdf.Document, path: Path) -> None:
    """Write the PDF so that running this script twice gives identical bytes.

    Normally every save stamps a fresh random ID into the file. Skipping
    that with no_new_id=True means git only shows a fixture as changed when
    its content really changed.
    """
    doc.save(path, no_new_id=True)
    doc.close()


def make_simple_text(path: Path) -> None:
    """Two Letter pages with known sentences at known positions."""
    doc = pymupdf.open()  # no arguments: a new, empty PDF in memory
    first_page_lines = [
        "Lorem ipsum dolor sit amet.",
        "The quick brown fox jumps over the lazy dog.",
    ]
    add_letter_page(doc, first_page_lines)
    add_letter_page(doc, ["This is the second page."])
    save_and_close(doc, path)


def make_rotated_pages(path: Path) -> None:
    """Four Letter pages rotated 0, 90, 180 and 270 degrees.

    Rotation in a PDF is only a display instruction (the page's /Rotate
    entry). The content keeps its unrotated coordinates, so the text is
    stored at the same place on all four pages; only how the page is shown
    differs.
    """
    doc = pymupdf.open()
    for rotation in (0, 90, 180, 270):
        page = add_letter_page(doc, [f"Rotation {rotation}"])
        page.set_rotation(rotation)
    save_and_close(doc, path)


def main() -> None:
    make_simple_text(FIXTURES_DIR / "simple_text.pdf")
    make_rotated_pages(FIXTURES_DIR / "rotated_pages.pdf")
    print(f"Wrote fixtures to {FIXTURES_DIR}")


# Only run main() when this file is started directly, not when imported.
if __name__ == "__main__":
    main()
