"""Turn a PDF page into a picture Qt can paint.

PyMuPDF draws a page into a Pixmap: a block of raw pixel bytes. Qt's type
for a picture in memory is QImage. This file is the bridge between the two.

For now the drawing happens right here, on the UI thread, which is fine for
ordinary pages (a few milliseconds each). Milestone M3 moves the PyMuPDF
half into a separate process (render_process.py) so a slow page can never
freeze the window; this file then becomes the part that asks that process
for pixels.
"""

import pymupdf
from PySide6.QtGui import QImage

from pdfeditor.core import geometry


def render_page(page: pymupdf.Page, scale: float) -> QImage:
    """Draw `page` at `scale` image pixels per PDF point.

    Get the scale from geometry.render_scale(): it accounts for the zoom,
    the screen and the size limit.
    """
    # alpha=False: an opaque picture with a white background, 3 bytes per
    # pixel (red, green, blue). annots=True: draw annotations too.
    pixmap = page.get_pixmap(
        matrix=geometry.render_matrix(scale), alpha=False, annots=True
    )
    # "stride" is the number of bytes in one row of pixels.
    image = QImage(
        pixmap.samples,
        pixmap.width,
        pixmap.height,
        pixmap.stride,
        QImage.Format.Format_RGB888,
    )
    # A QImage built this way does not own its pixels: it only points into
    # pixmap.samples, which Python frees as soon as this function returns.
    # copy() gives the image its own memory. Without it the app shows
    # garbage or crashes.
    return image.copy()
