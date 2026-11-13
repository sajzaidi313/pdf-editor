"""PyMuPDF behavior: what set_rotation() changes and what it leaves alone.

Tests in this folder do not test our code. Each one pins down a PyMuPDF
behavior our code relies on (the ✅ facts in docs/04), so that a PyMuPDF
upgrade which changes the behavior fails a test instead of quietly breaking
the app.
"""

import pymupdf


def test_set_rotation_90_swaps_rect_but_keeps_mediabox():
    """docs/04 §2: rotating a 612x792 page makes page.rect 792x612."""
    with pymupdf.open() as doc:  # a new, empty PDF in memory
        page = doc.new_page(width=612, height=792)

        page.set_rotation(90)

        # page.rect describes the page as displayed, so it turns with it.
        assert (page.rect.width, page.rect.height) == (792, 612)
        # The MediaBox is the stored paper size and is not touched.
        assert (page.mediabox.width, page.mediabox.height) == (612, 792)
