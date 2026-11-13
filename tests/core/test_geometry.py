"""Geometry: page layout, PDF <-> scene conversion at every rotation, zoom math.

rotated_pages.pdf has four Letter pages rotated 0, 90, 180 and 270 degrees
(page index x 90). Its text "Rotation N" is stored at the same unrotated
position on every page; see tests/fixtures/README.md.
"""

import pymupdf
import pytest

from pdfeditor.core import geometry
from pdfeditor.core.geometry import PAGE_GAP, PagePlacement

LETTER_WIDTH = 612
LETTER_HEIGHT = 792

# Comparing floats with == fails on tiny rounding differences, so the tests
# use pytest.approx. One thousandth of a point is far below anything visible.
TOLERANCE = 1e-3


def close_to(*numbers: float):
    return pytest.approx(numbers, abs=TOLERANCE)


@pytest.fixture
def rotated(model, fixtures_dir) -> list[PagePlacement]:
    """Placements of the four pages of rotated_pages.pdf."""
    model.open(fixtures_dir / "rotated_pages.pdf")
    return geometry.layout_pages(model.pages())


# --- layout -------------------------------------------------------------------


def test_layout_uses_the_displayed_page_size(rotated):
    sizes = [(placement.width, placement.height) for placement in rotated]

    # The 90 and 270 degree pages lie on their side.
    assert sizes == [(612, 792), (792, 612), (612, 792), (792, 612)]


def test_layout_stacks_pages_with_a_gap(rotated):
    tops = [placement.origin_y for placement in rotated]

    assert tops == [
        0,
        792 + PAGE_GAP,
        792 + 612 + 2 * PAGE_GAP,
        792 + 612 + 792 + 3 * PAGE_GAP,
    ]
    assert [placement.page_index for placement in rotated] == [0, 1, 2, 3]


def test_layout_centers_narrow_pages_on_the_widest(rotated):
    lefts = [placement.origin_x for placement in rotated]

    # The widest page is 792, so a 612 wide page is shifted by (792 - 612) / 2.
    assert lefts == [90, 0, 90, 0]


def test_content_size_spans_all_pages(rotated):
    width, height = geometry.content_size(rotated)

    assert width == 792
    assert height == 792 + 612 + 792 + 612 + 3 * PAGE_GAP


def test_layout_of_no_pages_is_empty():
    assert geometry.layout_pages([]) == []
    assert geometry.content_size([]) == (0.0, 0.0)


# --- PDF <-> scene conversion -------------------------------------------------


@pytest.mark.parametrize("page_index", [0, 1, 2, 3])
def test_round_trip_at_every_rotation(rotated, page_index):
    placement = rotated[page_index]
    for pdf_point in [(0, 0), (72, 90), (300.5, 400.25), (612, 792)]:
        scene_x, scene_y = placement.pdf_to_scene(pymupdf.Point(pdf_point))

        back = placement.scene_to_pdf(scene_x, scene_y)

        assert (back.x, back.y) == close_to(*pdf_point)


# Where the unrotated point (72, 90) appears on the displayed page, measured
# from the displayed page's own top-left corner. Worked out by hand:
#   90 degrees clockwise:  (x, y) -> (792 - y, x)
#   180 degrees:           (x, y) -> (612 - x, 792 - y)
#   270 degrees clockwise: (x, y) -> (y, 612 - x)
@pytest.mark.parametrize(
    ("page_index", "expected_on_page"),
    [(0, (72, 90)), (1, (702, 72)), (2, (540, 702)), (3, (90, 540))],
)
def test_pdf_point_lands_where_the_rotation_puts_it(
    rotated, page_index, expected_on_page
):
    placement = rotated[page_index]

    scene_x, scene_y = placement.pdf_to_scene(pymupdf.Point(72, 90))

    on_page = (scene_x - placement.origin_x, scene_y - placement.origin_y)
    assert on_page == close_to(*expected_on_page)


# A click on the displayed top-left corner of each page. On the 90 degree
# page that corner is the unrotated page's bottom-left corner, and so on.
@pytest.mark.parametrize(
    ("page_index", "unrotated_corner"),
    [
        (0, (0, 0)),
        (1, (0, LETTER_HEIGHT)),
        (2, (LETTER_WIDTH, LETTER_HEIGHT)),
        (3, (LETTER_WIDTH, 0)),
    ],
)
def test_click_on_displayed_top_left_maps_to_the_right_corner(
    rotated, page_index, unrotated_corner
):
    placement = rotated[page_index]

    point = placement.scene_to_pdf(placement.origin_x, placement.origin_y)

    assert (point.x, point.y) == close_to(*unrotated_corner)


@pytest.mark.parametrize("page_index", [0, 1, 2, 3])
def test_text_found_by_pymupdf_maps_inside_its_page(model, rotated, page_index):
    """End to end: a position PyMuPDF reports ends up on the right page."""
    placement = rotated[page_index]
    text_rect = model.page(page_index).search_for("Rotation")[0]

    scene_x, scene_y = placement.pdf_to_scene(text_rect.tl)  # tl = top-left

    assert placement.origin_x <= scene_x <= placement.origin_x + placement.width
    assert placement.origin_y <= scene_y <= placement.bottom


@pytest.mark.parametrize("page_index", [0, 1])
def test_round_trip_with_cropbox_offset(model, fixtures_dir, page_index):
    """cropbox_offset.pdf: the visible area starts at (30, 40) on the paper.

    PyMuPDF already measures from the visible area's corner, so the same
    two matrices work; page 1 is cropped *and* rotated by 90 degrees.
    """
    model.open(fixtures_dir / "cropbox_offset.pdf")
    placement = geometry.layout_pages(model.pages())[page_index]
    text_corner = model.page(page_index).search_for("Cropped")[0].tl

    scene_x, scene_y = placement.pdf_to_scene(text_corner)
    back = placement.scene_to_pdf(scene_x, scene_y)

    assert (back.x, back.y) == close_to(text_corner.x, text_corner.y)
    assert text_corner.x == pytest.approx(72 - 30, abs=0.5)  # shifted by the crop
    assert placement.origin_x <= scene_x <= placement.origin_x + placement.width
    assert placement.origin_y <= scene_y <= placement.bottom


def test_cropped_page_is_laid_out_at_its_visible_size(model, fixtures_dir):
    model.open(fixtures_dir / "cropbox_offset.pdf")

    first, second = geometry.layout_pages(model.pages())

    assert (first.width, first.height) == (552, 722)
    assert (second.width, second.height) == (722, 552)  # rotated 90 degrees


def test_placement_cannot_be_changed(rotated):
    # frozen=True on the dataclass: assigning to a field raises.
    with pytest.raises(AttributeError):
        rotated[0].origin_y = 5  # pyright: ignore[reportAttributeAccessIssue]


# --- which pages are visible --------------------------------------------------
# Page tops in rotated_pages.pdf: 0, 804, 1428, 2232. Bottoms: 792, 1416, 2220, 2844.


def test_visible_pages_inside_one_page(rotated):
    assert list(geometry.visible_pages(rotated, 100, 700)) == [0]


def test_visible_pages_across_a_page_break(rotated):
    assert list(geometry.visible_pages(rotated, 700, 900)) == [0, 1]


def test_visible_pages_spanning_everything(rotated):
    assert list(geometry.visible_pages(rotated, -50, 5000)) == [0, 1, 2, 3]


def test_visible_pages_in_the_gap_between_pages_is_empty(rotated):
    assert list(geometry.visible_pages(rotated, 794, 802)) == []


def test_visible_pages_below_the_last_page_is_empty(rotated):
    assert list(geometry.visible_pages(rotated, 3000, 3500)) == []


def test_most_visible_page_prefers_the_larger_share(rotated):
    # 50 points of page 0 (6% of it), 546 points of page 1 (89% of it).
    assert geometry.most_visible_page(rotated, 742, 1350) == 1


def test_most_visible_page_with_several_whole_pages_is_the_first(rotated):
    assert geometry.most_visible_page(rotated, 800, 2300) == 1


def test_most_visible_page_outside_the_pages_is_the_nearest(rotated):
    assert geometry.most_visible_page(rotated, -100, -50) == 0
    assert geometry.most_visible_page(rotated, 794, 802) == 1
    assert geometry.most_visible_page(rotated, 3000, 3500) == 3


def test_most_visible_page_without_pages_is_zero():
    assert geometry.most_visible_page([], 0, 100) == 0


# --- zoom ---------------------------------------------------------------------


def test_100_percent_is_real_paper_size():
    # At 96 dots per inch one inch (72 points) must cover 96 pixels.
    assert geometry.view_scale(1.0, logical_dpi=96) * 72 == pytest.approx(96)
    assert geometry.view_scale(2.0, logical_dpi=96) == pytest.approx(2 * 96 / 72)
    assert geometry.view_scale(1.0, logical_dpi=72) == pytest.approx(1.0)


def test_zoom_to_fit_fills_the_available_pixels():
    zoom = geometry.zoom_to_fit(available_pixels=816, length_points=612, logical_dpi=96)

    assert zoom == pytest.approx(1.0)
    assert geometry.view_scale(zoom, 96) * 612 == pytest.approx(816)


def test_zoom_to_fit_stays_inside_the_allowed_range():
    assert geometry.zoom_to_fit(10, 612, 96) == geometry.MIN_ZOOM
    assert geometry.zoom_to_fit(100_000, 612, 96) == geometry.MAX_ZOOM
    assert geometry.zoom_to_fit(800, 0, 96) == 1.0  # nothing to fit


def test_zoom_steps_go_up_and_down():
    assert geometry.next_zoom_step(1.0) == 1.1
    assert geometry.previous_zoom_step(1.0) == 0.9
    # From a zoom between two steps (after "fit width", say).
    assert geometry.next_zoom_step(1.3) == 1.5
    assert geometry.previous_zoom_step(1.3) == 1.25


def test_zoom_steps_stop_at_the_ends():
    assert geometry.next_zoom_step(8.0) == 8.0
    assert geometry.previous_zoom_step(0.25) == 0.25
    assert geometry.clamp_zoom(20) == 8.0
    assert geometry.clamp_zoom(0.01) == 0.25


# --- rendering ----------------------------------------------------------------


def test_render_scale_multiplies_by_the_device_pixel_ratio():
    assert geometry.render_scale(1.5, 1.0, 612, 792) == 1.5
    assert geometry.render_scale(1.5, 2.0, 612, 792) == 3.0


def test_render_scale_is_capped_for_huge_images():
    scale = geometry.render_scale(8 * 96 / 72, 1.0, 612, 792)

    assert 792 * scale == pytest.approx(geometry.MAX_RENDER_PIXELS)


def test_render_matrix_scales_both_directions_equally():
    matrix = geometry.render_matrix(2.0)

    assert (matrix.a, matrix.d) == (2.0, 2.0)
    assert (matrix.b, matrix.c, matrix.e, matrix.f) == (0, 0, 0, 0)
