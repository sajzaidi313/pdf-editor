"""PyMuPDF behavior: what get_pixmap() returns (docs/04 §3).

render/renderer.py hands these numbers straight to QImage, which trusts
them blindly: a wrong width, height or stride means a garbled picture.
"""

import pymupdf
import pytest


@pytest.mark.parametrize("zoom", [1.0, 1.25, 2.0])
def test_pixmap_size_is_displayed_page_size_times_zoom(fixtures_dir, zoom):
    with pymupdf.open(fixtures_dir / "rotated_pages.pdf") as doc:
        page = doc[1]  # rotated 90 degrees: displayed as 792 x 612

        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)

        assert (pixmap.width, pixmap.height) == (round(792 * zoom), round(612 * zoom))


def test_pixmap_without_alpha_is_three_bytes_per_pixel(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        pixmap = doc[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)

    assert pixmap.n == 3  # red, green, blue; no transparency byte
    assert pixmap.stride == 3 * pixmap.width  # bytes per row, no padding
    assert len(pixmap.samples) == pixmap.stride * pixmap.height


def test_pixmap_background_is_white_and_text_is_dark(fixtures_dir):
    with pymupdf.open(fixtures_dir / "simple_text.pdf") as doc:
        pixmap = doc[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)

    assert pixmap.pixel(0, 0) == (255, 255, 255)
    # README: "Lorem" covers about Rect(72, 77, 106, 94).
    text_area = [pixmap.pixel(x, y) for x in range(72, 106) for y in range(77, 94)]
    assert any(sum(color) < 3 * 128 for color in text_area)
