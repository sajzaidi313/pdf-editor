"""PyMuPDF behavior: reading characters with get_text("rawdict") (docs/04 §4).

core/text.py is built on these facts.
"""

import pymupdf
import pytest

from pdfeditor.core.text import EXTRACT_FLAGS, read_rawdict


def first_line(page: pymupdf.Page, flags: int = EXTRACT_FLAGS) -> dict:
    return read_rawdict(page, flags)["blocks"][0]["lines"][0]


def test_rawdict_nests_blocks_lines_spans_and_characters(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        raw = read_rawdict(doc[0], EXTRACT_FLAGS)

    block = raw["blocks"][0]
    line = block["lines"][0]
    characters = [char for span in line["spans"] for char in span["chars"]]
    assert block["type"] == 0  # 0 = text
    assert "".join(char["c"] for char in characters) == "Lorem ipsum dolor sit amet."
    # Every character is a single letter with a box of four numbers.
    assert all(len(char["c"]) == 1 for char in characters)
    assert all(len(char["bbox"]) == 4 for char in characters)
    assert len(line["bbox"]) == 4


def test_spaces_are_characters_with_a_box_too(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        line = first_line(doc[0])

    characters = [char for span in line["spans"] for char in span["chars"]]
    space = characters[5]  # between "Lorem" and "ipsum"
    assert space["c"] == " "
    assert space["bbox"][2] > space["bbox"][0]  # it has a width


def test_character_boxes_stay_unrotated(fixtures_dir):
    with pymupdf.open(fixtures_dir / "rotated_pages.pdf") as doc:
        boxes = [first_line(page)["spans"][0]["chars"][0]["bbox"] for page in doc]

    # "Rotation N" starts at the same spot on all four pages.
    for box in boxes[1:]:
        assert box == pytest.approx(boxes[0])
    assert boxes[0][0] == pytest.approx(72)


def test_character_boxes_are_measured_from_the_cropbox_corner(fixtures_dir):
    with pymupdf.open(fixtures_dir / "cropbox_offset.pdf") as doc:
        boxes = [first_line(page)["spans"][0]["chars"][0]["bbox"] for page in doc]

    # Written at x = 72 on the paper; the CropBox cuts 30 off the left.
    assert boxes[0][0] == pytest.approx(42)
    assert boxes[1] == pytest.approx(boxes[0])  # the rotated page agrees


def test_lines_of_a_wrapped_paragraph_share_one_block(fixtures_dir):
    with pymupdf.open(fixtures_dir / "search_and_select.pdf") as doc:
        blocks = read_rawdict(doc[0], EXTRACT_FLAGS)["blocks"]

    assert [len(block["lines"]) for block in blocks] == [4, 2, 1]
    assert [block["number"] for block in blocks] == [0, 1, 2]


def test_line_direction_is_1_0_for_ordinary_text_and_differs_for_sideways_text():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Ordinary", fontsize=12)
    page.insert_text((300, 300), "Sideways", fontsize=12, rotate=90)
    lines = [
        line
        for block in read_rawdict(page, EXTRACT_FLAGS)["blocks"]
        for line in block["lines"]
    ]
    doc.close()

    assert lines[0]["dir"] == (1.0, 0.0)
    assert lines[1]["dir"] == pytest.approx((0.0, -1.0))  # reads bottom to top


def test_a_scanned_page_has_an_image_block_unless_images_are_switched_off(
    fixtures_dir,
):
    with pymupdf.open(fixtures_dir / "scanned_no_text.pdf") as doc:
        default_blocks = read_rawdict(doc[0], pymupdf.TEXTFLAGS_RAWDICT)["blocks"]
        our_blocks = read_rawdict(doc[0], EXTRACT_FLAGS)["blocks"]

    assert [block["type"] for block in default_blocks] == [1]  # 1 = image
    assert our_blocks == []


def test_the_default_rawdict_flags_keep_ligatures_and_images():
    # EXTRACT_FLAGS switches these two off; that only means something as
    # long as PyMuPDF's default has them on.
    assert pymupdf.TEXTFLAGS_RAWDICT & pymupdf.TEXT_PRESERVE_LIGATURES
    assert pymupdf.TEXTFLAGS_RAWDICT & pymupdf.TEXT_PRESERVE_IMAGES
    assert not EXTRACT_FLAGS & pymupdf.TEXT_PRESERVE_LIGATURES
    assert not EXTRACT_FLAGS & pymupdf.TEXT_PRESERVE_IMAGES
