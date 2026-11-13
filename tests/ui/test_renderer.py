"""render_page: a PDF page becomes a QImage of the right size with ink on it."""

from PySide6.QtGui import QColor, QImage

from pdfeditor.render.renderer import render_page, render_thumbnail

WHITE = QColor("white")


def has_ink(image: QImage, left: int, top: int, right: int, bottom: int) -> bool:
    """True when any pixel in the box is not white."""
    return any(
        image.pixelColor(x, y) != WHITE
        for x in range(left, right)
        for y in range(top, bottom)
    )


def test_image_size_is_page_size_times_scale(qtbot, model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    image = render_page(model.page(0), scale=1.0)
    doubled = render_page(model.page(0), scale=2.0)

    assert (image.width(), image.height()) == (612, 792)
    assert (doubled.width(), doubled.height()) == (1224, 1584)


def test_text_is_drawn_where_the_fixture_puts_it(qtbot, model, fixtures_dir):
    """README: "Lorem" covers about Rect(72, 77, 106, 94) on page index 0."""
    model.open(fixtures_dir / "simple_text.pdf")

    image = render_page(model.page(0), scale=1.0)

    assert has_ink(image, 72, 77, 106, 94)
    assert not has_ink(image, 300, 400, 340, 440)  # an empty part of the page
    assert image.pixelColor(0, 0) == WHITE


def test_rotated_page_is_drawn_rotated(qtbot, model, fixtures_dir):
    model.open(fixtures_dir / "rotated_pages.pdf")

    image = render_page(model.page(1), scale=1.0)  # the 90 degree page

    assert (image.width(), image.height()) == (792, 612)


def test_image_owns_its_pixels(qtbot, model, fixtures_dir):
    """The image must stay valid after the document is closed (the copy())."""
    model.open(fixtures_dir / "simple_text.pdf")
    image = render_page(model.page(0), scale=1.0)

    model.close()

    assert has_ink(image, 72, 77, 106, 94)


# --- thumbnails ---------------------------------------------------------------


def test_thumbnail_fits_the_box_it_is_given(qtbot, model, fixtures_dir):
    model.open(fixtures_dir / "rotated_pages.pdf")

    upright = render_thumbnail(model.page(0), 120, 180, device_pixel_ratio=1.0)
    on_its_side = render_thumbnail(model.page(1), 120, 180, device_pixel_ratio=1.0)

    assert (upright.width(), upright.height()) == (120, 156)
    assert (on_its_side.width(), on_its_side.height()) == (120, 93)


def test_thumbnail_for_a_hidpi_screen_has_more_pixels_and_says_so(
    qtbot, model, fixtures_dir
):
    model.open(fixtures_dir / "simple_text.pdf")

    image = render_thumbnail(model.page(0), 120, 180, device_pixel_ratio=2.0)

    assert image.width() == 240  # twice the pixels ...
    assert image.devicePixelRatio() == 2.0
    assert image.deviceIndependentSize().width() == 120  # ... same room on screen


def test_thumbnail_shows_the_page(qtbot, model, fixtures_dir):
    model.open(fixtures_dir / "simple_text.pdf")

    image = render_thumbnail(model.page(0), 120, 180, device_pixel_ratio=1.0)

    # "Lorem ipsum ..." sits about a tenth of the way down the page.
    assert has_ink(image, 10, 12, 60, 22)
    assert not has_ink(image, 10, 100, 110, 150)
