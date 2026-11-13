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
# parents[1] is two folders up from tests/fixtures: the project root.
RESOURCES_DIR = FIXTURES_DIR.parents[1] / "src" / "pdfeditor" / "resources"

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


def make_cropbox_offset(path: Path) -> None:
    """Two Letter pages whose visible area (CropBox) is smaller than the paper.

    The CropBox cuts 30 points off the left and right and 40 off the top
    (and 30 off the bottom). PyMuPDF measures everything from the top-left
    of the *visible* area, so the text written at (72, 90) is afterwards
    found at (72 - 30, 90 - 40) = (42, 50). The second page is also rotated
    90 degrees, to test cropping and rotation together.
    """
    doc = pymupdf.open()
    for rotation in (0, 90):
        page = add_letter_page(doc, ["Cropped page"])
        page.set_cropbox(pymupdf.Rect(30, 40, 582, 762))
        page.set_rotation(rotation)
    save_and_close(doc, path)


def make_page_labels(path: Path) -> None:
    """Eight pages labelled i, ii, iii, iv, 1, 2, 3, 4, like a book.

    Each rule says "from this page on, number like this": style "r" is
    lower-case roman numerals, "D" is ordinary digits.
    """
    doc = pymupdf.open()
    for index in range(8):
        add_letter_page(doc, [f"Page index {index}"])
    roman_front_matter = {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}
    numbered_body = {"startpage": 4, "prefix": "", "style": "D", "firstpagenum": 1}
    doc.set_page_labels([roman_front_matter, numbered_body])
    save_and_close(doc, path)


def make_not_a_pdf(path: Path) -> None:
    """A text file that only has a .pdf name. Opening it must fail politely."""
    path.write_bytes(b"This is not a PDF file.\n")


def make_broken_xref(source: Path, path: Path) -> None:
    """A copy of `source` whose table of contents pointer is wrong.

    A PDF ends with "startxref" and a number: the byte position of the
    "xref" table that lists where every object is. Pointing it past the end
    of the file forces MuPDF to rebuild the table by scanning the file. The
    file still opens, but `doc.is_repaired` is True.
    """
    data = source.read_bytes()
    keyword = b"startxref\n"
    number_start = data.rindex(keyword) + len(keyword)
    number_end = data.index(b"\n", number_start)
    path.write_bytes(data[:number_start] + b"99999" + data[number_end:])


# The passwords of encrypted_user_pw.pdf. They protect nothing: this is a
# test file whose passwords are meant to be public.
USER_PASSWORD = "test"
OWNER_PASSWORD = "owner"


def make_encrypted_user_pw(path: Path) -> None:
    """One page that needs the password "test" to open (AES-256).

    Unlike every other fixture this one is only written when it is missing.
    Encryption uses fresh random numbers on every save, so the bytes can
    never be the same twice, and rewriting the file each run would make git
    report a change that isn't one. Delete the file to regenerate it.
    """
    if path.exists():
        return
    doc = pymupdf.open()
    add_letter_page(doc, ["This page is password protected."])
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw=USER_PASSWORD,
        owner_pw=OWNER_PASSWORD,
    )
    doc.close()


def make_outline_nested(path: Path) -> None:
    """Six pages with an outline ("bookmarks") three levels deep.

    Each outline entry is [level, title, page number counted from 1]. The
    last entry has page -1: a bookmark that points nowhere, which real
    files contain after pages were deleted.
    """
    doc = pymupdf.open()
    for number in range(1, 7):
        add_letter_page(doc, [f"Outline page {number}"])
    doc.set_toc(
        [
            [1, "Chapter 1", 1],
            [2, "Section 1.1", 2],
            [3, "Detail 1.1.1", 3],
            [2, "Section 1.2", 4],
            [1, "Chapter 2", 5],
            [2, "Section 2.1", 6],
            [1, "Lost bookmark", -1],
        ]
    )
    save_and_close(doc, path)


def make_scanned_no_text(path: Path) -> None:
    """One page that only holds a picture of text, like a scan.

    The words are visible but there is no text in the file: nothing to
    search, select or copy.
    """
    source = pymupdf.open()
    source_page = add_letter_page(source, ["This text is only a picture."])
    # Photograph just the strip that holds the line, in gray, at 72 dpi
    # (one pixel per point). A picture of the whole page would make the
    # fixture a hundred times larger.
    strip = pymupdf.Rect(60, 70, 300, 100)
    picture = source_page.get_pixmap(dpi=72, clip=strip, colorspace=pymupdf.csGRAY)
    source.close()
    doc = pymupdf.open()
    page = doc.new_page(width=LETTER_WIDTH, height=LETTER_HEIGHT)
    page.insert_image(strip, pixmap=picture)
    save_and_close(doc, path)


# The paragraph on page 1 of search_and_select.pdf. PyMuPDF wraps it into
# four lines inside PARAGRAPH_BOX; the tests rely on these exact lines:
#   "The quick brown fox jumps over the lazy"
#   "dog and then the very lazy dog sleeps for"
#   "a long while under the old oak tree near"
#   "the river bank."
PARAGRAPH = (
    "The quick brown fox jumps over the lazy dog and then the very lazy dog "
    "sleeps for a long while under the old oak tree near the river bank."
)
PARAGRAPH_BOX = pymupdf.Rect(72, 72, 300, 200)
HYPHEN_BOX = pymupdf.Rect(72, 220, 300, 300)


def make_search_and_select(path: Path) -> None:
    """Three pages for the search and text-selection tests.

    Page 1: a wrapped paragraph (one "lazy dog" is split over two lines), a
    word hyphenated at a line end ("exam-" / "ple") and the line
    "fox fox FOX". Page 2: two plain lines. Page 3: one line on a page
    rotated by 90 degrees.

    "lazy dog" appears 4 times (2 + 1 + 1), "fox" 4 times (all on page 1).
    """
    doc = pymupdf.open()
    page = doc.new_page(width=LETTER_WIDTH, height=LETTER_HEIGHT)
    # insert_textbox wraps the text inside the rectangle, which makes one
    # block of several lines, like a paragraph in a real document.
    page.insert_textbox(PARAGRAPH_BOX, PARAGRAPH, fontsize=FONT_SIZE)
    page.insert_textbox(
        HYPHEN_BOX, "This is an exam-\nple of hyphenation.", fontsize=FONT_SIZE
    )
    page.insert_text((LEFT_MARGIN, 330), "fox fox FOX", fontsize=FONT_SIZE)
    add_letter_page(
        doc, ["Second page: the lazy dog is back.", "Nothing else to see here."]
    )
    rotated = add_letter_page(doc, ["A lazy dog on a rotated page."])
    rotated.set_rotation(90)
    save_and_close(doc, path)


def make_self_test(path: Path) -> None:
    """The one-page PDF that ships inside the app for `--self-test`.

    It lives in the app's own resources folder, not in tests/, because the
    packaged app has to carry it along (see src/pdfeditor/self_test.py).
    """
    path.parent.mkdir(exist_ok=True)
    doc = pymupdf.open()
    lines = [
        "PDF Editor self-test",
        "If you can read this, opening and drawing a PDF works.",
    ]
    add_letter_page(doc, lines)
    save_and_close(doc, path)


def main() -> None:
    make_self_test(RESOURCES_DIR / "self_test.pdf")
    make_simple_text(FIXTURES_DIR / "simple_text.pdf")
    make_rotated_pages(FIXTURES_DIR / "rotated_pages.pdf")
    make_cropbox_offset(FIXTURES_DIR / "cropbox_offset.pdf")
    make_page_labels(FIXTURES_DIR / "page_labels.pdf")
    make_not_a_pdf(FIXTURES_DIR / "not_a_pdf.pdf")
    make_broken_xref(FIXTURES_DIR / "simple_text.pdf", FIXTURES_DIR / "broken_xref.pdf")
    make_encrypted_user_pw(FIXTURES_DIR / "encrypted_user_pw.pdf")
    make_outline_nested(FIXTURES_DIR / "outline_nested.pdf")
    make_scanned_no_text(FIXTURES_DIR / "scanned_no_text.pdf")
    make_search_and_select(FIXTURES_DIR / "search_and_select.pdf")
    print(f"Wrote fixtures to {FIXTURES_DIR} and {RESOURCES_DIR}")


# Only run main() when this file is started directly, not when imported.
if __name__ == "__main__":
    main()
