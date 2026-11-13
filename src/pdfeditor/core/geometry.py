"""Geometry: where pages sit on the canvas, and PDF <-> screen conversion.

Three kinds of numbers meet in a PDF viewer, and mixing them up is the
classic source of bugs (docs/03 §3):

1. PDF points on the *unrotated* page. Origin at the page's top-left, y
   grows downward, 1 point = 1/72 inch. Everything in core/ uses these.
2. Scene coordinates. The "scene" is one tall imaginary sheet on which all
   pages are stacked top to bottom. It is also measured in points, but each
   page appears the way it is *displayed*: a page rotated by 90 degrees is
   lying on its side.
3. Screen pixels. How many pixels one point covers depends on the zoom and
   on the monitor.

This file is the only place that converts between them (CLAUDE.md, hard
rule 3). It is plain math and must not import Qt.
"""

import bisect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pymupdf

POINTS_PER_INCH = 72.0

# Vertical space between two pages, and the empty border around all of them.
# In points, so it grows and shrinks with the zoom like the pages do.
PAGE_GAP = 12.0

# The zoom levels that "zoom in" and "zoom out" step through (docs/05 §7).
# 1.0 means 100%.
ZOOM_STEPS = (
    0.25,
    0.33,
    0.5,
    0.67,
    0.75,
    0.9,
    1.0,
    1.1,
    1.25,
    1.5,
    1.75,
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    6.0,
    8.0,
)
MIN_ZOOM = ZOOM_STEPS[0]
MAX_ZOOM = ZOOM_STEPS[-1]

# The longest side, in pixels, a page image may have. A Letter page at 800%
# would be 93 MB of pixels; beyond this limit the image is stretched instead
# (slightly soft). Milestone M3 replaces this with tiles.
MAX_RENDER_PIXELS = 4096


# A dataclass writes __init__ (and more) from the list of fields.
# frozen=True makes instances read-only: a placement describes where a page
# is, and nobody should be able to move a page by accident.
@dataclass(frozen=True)
class PagePlacement:
    """Where one page sits in the scene, and how to convert points on it."""

    page_index: int
    origin_x: float  # top-left corner of the displayed page, in scene units
    origin_y: float
    width: float  # size as displayed (already rotated), in points
    height: float
    rotation_matrix: pymupdf.Matrix  # unrotated point -> displayed point
    derotation_matrix: pymupdf.Matrix  # displayed point -> unrotated point

    @property
    def bottom(self) -> float:
        """Scene y of the page's bottom edge."""
        return self.origin_y + self.height

    def scene_to_pdf(self, x: float, y: float) -> pymupdf.Point:
        """Scene point -> unrotated PDF point (what core functions expect)."""
        shown = pymupdf.Point(x - self.origin_x, y - self.origin_y)
        # Multiplying a Point by a Matrix applies the matrix to the point.
        return shown * self.derotation_matrix

    def pdf_to_page(self, point: pymupdf.Point) -> tuple[float, float]:
        """Unrotated PDF point -> point on the page as displayed, measured
        from the displayed page's own top-left corner."""
        shown = point * self.rotation_matrix
        return shown.x, shown.y

    def pdf_to_scene(self, point: pymupdf.Point) -> tuple[float, float]:
        """Unrotated PDF point -> scene point."""
        x, y = self.pdf_to_page(point)
        return x + self.origin_x, y + self.origin_y

    def quad_on_page(self, quad: pymupdf.Quad) -> list[tuple[float, float]]:
        """The corners of an unrotated quad on the page as displayed.

        They are listed going around the outline (upper-left, upper-right,
        lower-right, lower-left), so that joining them in order draws the
        shape. On a rotated page the result is rotated with it.
        """
        corners = (quad.ul, quad.ur, quad.lr, quad.ll)
        return [self.pdf_to_page(corner) for corner in corners]


def layout_pages(
    pages: Iterable[pymupdf.Page], gap: float = PAGE_GAP
) -> list[PagePlacement]:
    """Stack the pages top to bottom, each centered on the widest one.

    Only page sizes are read, nothing is drawn, so this is fast even for
    long documents.
    """
    # page.rect is the page as displayed: rotation and CropBox are already
    # applied and its top-left corner is (0, 0).
    shapes = [
        (
            page.rect.width,
            page.rect.height,
            page.rotation_matrix,
            page.derotation_matrix,
        )
        for page in pages
    ]
    widest = max((width for width, _, _, _ in shapes), default=0.0)
    placements: list[PagePlacement] = []
    y = 0.0
    for index, (width, height, rotation, derotation) in enumerate(shapes):
        placement = PagePlacement(
            page_index=index,
            origin_x=(widest - width) / 2,
            origin_y=y,
            width=width,
            height=height,
            # Copies: the placement must stay valid after the Page is gone.
            rotation_matrix=pymupdf.Matrix(rotation),
            derotation_matrix=pymupdf.Matrix(derotation),
        )
        placements.append(placement)
        y = placement.bottom + gap
    return placements


def content_size(placements: Sequence[PagePlacement]) -> tuple[float, float]:
    """Width and height of the area covered by all pages (no outer margin)."""
    if not placements:
        return 0.0, 0.0
    width = max(placement.width for placement in placements)
    return width, placements[-1].bottom


def visible_pages(
    placements: Sequence[PagePlacement], top: float, bottom: float
) -> range:
    """Indexes of the pages that overlap the scene strip from `top` to `bottom`.

    Pages are sorted by y, so there is no need to look at all of them:
    `bisect` does a binary search (halve the list, pick the half that can
    contain the answer, repeat). 1,000 pages take about 10 steps.
    """
    # First page whose bottom edge is below the strip's top...
    first = bisect.bisect_right(placements, top, key=lambda p: p.bottom)
    # ...up to, but not including, the first page that starts below the strip.
    end = bisect.bisect_left(placements, bottom, key=lambda p: p.origin_y)
    return range(first, max(first, end))


def page_at(placements: Sequence[PagePlacement], x: float, y: float) -> int | None:
    """Index of the page that covers the scene point (x, y), or None when
    the point is in a gap between pages or beside them."""
    # The first page whose bottom edge lies below the point is the only
    # one that can contain it.
    index = bisect.bisect_right(placements, y, key=lambda p: p.bottom)
    if index == len(placements):
        return None
    placement = placements[index]
    inside = (
        placement.origin_y <= y
        and placement.origin_x <= x <= placement.origin_x + placement.width
    )
    return index if inside else None


def most_visible_page(
    placements: Sequence[PagePlacement], top: float, bottom: float
) -> int:
    """The page the user is "on": the one with the largest share of itself
    inside the strip from `top` to `bottom`. Ties go to the earlier page.

    Example: three small pages fit in the window at once. All are 100%
    visible, so the first of them is the current page. That keeps "go to
    page 5" honest: page 5 lands at the top and is reported as current.
    """
    if not placements:
        return 0
    candidates = visible_pages(placements, top, bottom)
    if len(candidates) == 0:
        # The strip lies in a gap or outside the pages: take the nearest page.
        return min(candidates.start, len(placements) - 1)
    best_index = candidates.start
    best_share = -1.0
    for index in candidates:
        placement = placements[index]
        overlap = min(bottom, placement.bottom) - max(top, placement.origin_y)
        share = overlap / placement.height if placement.height > 0 else 0.0
        if share > best_share + 1e-9:  # strictly better, ignoring float dust
            best_index, best_share = index, share
    return best_index


# --- zoom ---------------------------------------------------------------------
# "zoom" is the number the user sees: 1.0 = 100% = the page appears at its
# real paper size, like in other PDF viewers. "scale" is pixels per point.
# A monitor that Windows treats as 96 dots per inch needs 96/72 = 1.33
# pixels for each point at 100%.


def view_scale(zoom: float, logical_dpi: float) -> float:
    """Screen pixels per PDF point at this zoom on a screen of `logical_dpi`."""
    return zoom * logical_dpi / POINTS_PER_INCH


def zoom_to_fit(
    available_pixels: float, length_points: float, logical_dpi: float
) -> float:
    """The zoom at which `length_points` exactly fills `available_pixels`."""
    if length_points <= 0 or available_pixels <= 0:
        return 1.0
    scale = available_pixels / length_points
    return clamp_zoom(scale * POINTS_PER_INCH / logical_dpi)


def clamp_zoom(zoom: float) -> float:
    """Keep a zoom inside the allowed range (25% to 800%)."""
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


def next_zoom_step(zoom: float) -> float:
    """The next larger entry of ZOOM_STEPS, or the largest one."""
    for step in ZOOM_STEPS:
        if step > zoom + 1e-6:
            return step
    return MAX_ZOOM


def previous_zoom_step(zoom: float) -> float:
    """The next smaller entry of ZOOM_STEPS, or the smallest one."""
    for step in reversed(ZOOM_STEPS):
        if step < zoom - 1e-6:
            return step
    return MIN_ZOOM


# --- rendering ----------------------------------------------------------------


def render_scale(
    scale: float, device_pixel_ratio: float, page_width: float, page_height: float
) -> float:
    """Image pixels per PDF point to render a page with.

    `scale` is view_scale(). On a HiDPI ("Retina") screen one logical pixel
    is made of several physical ones; `device_pixel_ratio` says how many
    (1.0 on an ordinary monitor, 2.0 on Retina), and the image needs that
    many more pixels to look sharp. The result is capped so the image's
    longer side stays within MAX_RENDER_PIXELS.
    """
    wanted = scale * device_pixel_ratio
    longest_side = max(page_width, page_height)
    if longest_side * wanted > MAX_RENDER_PIXELS:
        return MAX_RENDER_PIXELS / longest_side
    return wanted


def fit_scale(
    width: float, height: float, max_width: float, max_height: float
) -> float:
    """The largest scale at which a width x height page fits inside a box
    of max_width x max_height. Used for thumbnails: an ordinary page is
    limited by the box's width, a very tall one by its height."""
    if width <= 0 or height <= 0:
        return 1.0
    return min(max_width / width, max_height / height)


def render_matrix(scale: float) -> pymupdf.Matrix:
    """The matrix PyMuPDF needs to draw a page at `scale` pixels per point."""
    return pymupdf.Matrix(scale, scale)
