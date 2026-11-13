"""PyMuPDF behavior: what set_rotation() changes and what it leaves alone.

Tests in this folder do not test our code. Each one pins down a PyMuPDF
behavior our code relies on (the ✅ facts in docs/04), so that a PyMuPDF
upgrade which changes the behavior fails a test instead of quietly breaking
the app.
"""

import pymupdf
import pytest


def test_set_rotation_90_swaps_rect_but_keeps_mediabox():
    """docs/04 §2: rotating a 612x792 page makes page.rect 792x612."""
    with pymupdf.open() as doc:  # a new, empty PDF in memory
        page = doc.new_page(width=612, height=792)

        page.set_rotation(90)

        # page.rect describes the page as displayed, so it turns with it.
        assert (page.rect.width, page.rect.height) == (792, 612)
        # The MediaBox is the stored paper size and is not touched.
        assert (page.mediabox.width, page.mediabox.height) == (612, 792)


def test_rotation_matrix_maps_unrotated_point_to_displayed_point():
    """docs/03 §3.2: on a 612x792 page rotated 90, (72, 72) is shown at (720, 72)."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.set_rotation(90)

        shown = pymupdf.Point(72, 72) * page.rotation_matrix

        assert (shown.x, shown.y) == pytest.approx((720, 72))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_derotation_matrix_undoes_rotation_matrix(rotation):
    """docs/04 §2: core/geometry.py converts clicks with these two matrices."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.set_rotation(rotation)
        point = pymupdf.Point(100, 250)

        back = point * page.rotation_matrix * page.derotation_matrix

        assert (back.x, back.y) == pytest.approx((100, 250), abs=1e-3)


def test_text_positions_stay_unrotated(fixtures_dir):
    """docs/03 §3.2: search results ignore /Rotate; only the display turns."""
    with pymupdf.open(fixtures_dir / "rotated_pages.pdf") as doc:
        corners = [page.search_for("Rotation")[0].tl for page in doc]

    # The same top-left corner on all four pages, whatever their rotation.
    for corner in corners:
        assert (corner.x, corner.y) == pytest.approx((corners[0].x, corners[0].y))


def test_page_rect_starts_at_zero_when_cropped(fixtures_dir):
    """docs/03 §3.3: page.rect is the visible area moved to (0, 0); text
    coordinates are measured from that corner, not from the paper's."""
    with pymupdf.open(fixtures_dir / "cropbox_offset.pdf") as doc:
        page = doc[0]

        assert page.rect == pymupdf.Rect(0, 0, 552, 722)
        assert page.cropbox_position == pymupdf.Point(30, 40)
        # Written at x = 72 on the paper, found at 72 - 30 in the visible area.
        assert page.search_for("Cropped")[0].x0 == pytest.approx(42, abs=0.5)
