# 05: Viewer & Rendering

Goal: smooth scrolling and zooming on 1,000-page documents, crisp text at any zoom, and no UI freezes.

## 1. Scene layout

- One `QGraphicsScene`; one `PageItem` per page, stacked vertically.
- **Decision: scene units = PDF points** (in the page's displayed, rotated orientation), and zoom is the view transform: `view.setTransform(QTransform.fromScale(z, z))`. The scene layout never changes when zooming.
  - Why: zoom is instant. Qt scales the old image right away (a bit blurry), and a sharp render replaces it shortly after (§2 debounce).
  - `PageItem.paint()` draws its image into its point-size rect; Qt does the scaling. The image's pixel size comes from `render_matrix(zoom, dpr)` (doc 02 §2.3).
  - Rejected alternative: scene units = pixels at the current zoom, re-laying out the scene on every zoom change. Don't mix the two.
- Layout: `y = sum(previous page heights) + gap * index`, all in points (so the gap scales with zoom, which is normal); x centers each page within `max_width`. Precompute page sizes once from `page.rect` (cheap: no rendering), store in a list; recompute only on page ops/rotation.
- Background: `view.setBackgroundBrush(QColor("#525659"))` (the familiar viewer gray). Page items draw a 1px border + soft shadow (`QGraphicsDropShadowEffect` is slow with many items; paint a cheap offset dark rect instead).

## 2. What to render (visibility)

On scroll/zoom/resize:
1. Compute visible scene rect: `view.mapToScene(view.viewport().rect()).boundingRect()`.
2. Find intersecting pages by binary search over the precomputed y-offsets (O(log n)).
3. Request renders for visible pages (priority HIGH) and ±2 neighbor pages (priority LOW, prefetch).
4. Cancel/deprioritize pending jobs for pages no longer near the viewport.
5. Debounce: during continuous zooming (Ctrl+wheel), wait ~120 ms after the last zoom event before requesting sharp renders; show scaled cached images meanwhile.

"Current page" for the status bar = the page with the largest share of itself inside the viewport; ties go to the earlier page (`geometry.most_visible_page`). The first idea, "the page under the viewport's center line", was dropped in M1: when several whole pages fit in the window (50% zoom in a maximized window), "go to page 5" put page 5 at the top but reported page 6.

## 3. Render pipeline

```
PageItem.needs_render(zoom) ──► RenderScheduler.request(RenderKey, priority)
                                     │ dedupe identical pending keys
                                     │ drop if cache hit
                                     ▼
                  request queue ──► render process (multiprocessing)
                                     │ own Document → page.get_pixmap(...)
                                     │ sends back (key, w, h, stride, pixel bytes, generation)
                                     ▼
        result listener → QImage(...).copy() → signal finished(key, QImage, generation)
                                     │ discard if generation stale
                                     ▼
                         RenderCache.put(key, image) → PageItem.update()
```

```python
@dataclass(frozen=True)
class RenderKey:
    page_index: int
    zoom_bucket: float        # zoom rounded to e.g. 2 decimals, × device pixel ratio
    tile: tuple[int, int] | None   # (col, row) when tiling, else None
    inverted: bool = False    # night reading mode (V14): inverted renders are cached separately
    page_rev: int             # per-page revision counter (bumped when that page changes)
```

### 3.1 Render process (why not threads)
PyMuPDF does **not** support Python threads: running it on several threads can give wrong results or crash Python, and its calls block the UI thread anyway. So background rendering runs in a **separate process**. PyMuPDF's docs include a Qt + `multiprocessing` recipe to start from.
- Start it with `multiprocessing.get_context("spawn")` (behaves the same on Windows, macOS and Linux). Call `multiprocessing.freeze_support()` first thing in `__main__.py`, or the PyInstaller build will relaunch the whole app instead of the render process.
- The process keeps one `(doc_generation, pymupdf.Document)`. When the main doc changes, the model publishes a new **bytes snapshot** (`doc.tobytes()`) with a new generation number; the process re-opens from bytes when its generation is stale. For an unmodified doc it opens from the file path instead (send the password too for encrypted files; never log it).
- Snapshot cost: `tobytes()` on a large doc can take 100s of ms, and sending it to the process is another copy. Only snapshot when a render is actually needed after a change, and coalesce (one snapshot per batch of edits). Use `model.snapshot_bytes()`, which reuses the snapshot an undo command just took when the doc hasn't changed since (doc 07 §3).
- Timeouts: if a job runs longer than ~10 s (hostile or enormous page), terminate the process, start a fresh one, and show a "page too complex to render" placeholder. This is only possible with a process; a stuck thread can't be killed.
- Start with **one** render process. A small pool (2–3) is an optimization for later, after measuring.
- Pixel transfer: send `pix.samples` (bytes) plus width/height/stride. Tiling (§4) keeps each message small. If profiling shows the copy matters, switch to `multiprocessing.shared_memory` later.
- **Start simple:** milestone 1 renders synchronously on the UI thread with no extra process at all; move to the render process in milestone 3 when it's measurably needed. Don't over-engineer day one.

### 3.2 Pixels → QImage
In the render process (no Qt here):
```python
pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False, annots=True)
result = (key, pix.width, pix.height, pix.stride, pix.samples, generation)   # plain data only
```
On the UI side:
```python
key, w, h, stride, samples, generation = result
img = QImage(samples, w, h, stride, QImage.Format.Format_RGB888).copy()
img.setDevicePixelRatio(dpr)   # so Qt draws it at logical size on HiDPI screens
```
Always `.copy()`: otherwise the QImage points into `samples`, which Python frees when the variable goes away → crashes/garbage.

### 3.3 HiDPI
`s = zoom * dpr` where `dpr = view.devicePixelRatioF()`. Paint with `painter.drawImage(target_rect_logical, img)`. Without this, text looks blurry on Retina/4K screens.

## 4. Tiling for high zoom

A US Letter page at 800% on a 2× display is 612×8×2 ≈ 9,800 px wide → ~380 MB RGB. Never render whole pages that large.
- If rendered page size > ~4096 px in either dimension, switch that page to **tile mode**: 512×512 px tiles, render only tiles intersecting the viewport (`clip=` in PDF coords = tile rect / s).
- Paint a low-res whole-page image underneath as a fallback while tiles load.
- Use `page.get_displaylist()` in the render process and cache the display list per page so each tile doesn't re-parse the content stream.

## 5. Cache

- LRU (`collections.OrderedDict`) with a **byte budget** (`img.sizeInBytes()`), default 300 MB, configurable.
- Keep two tiers: thumbnails (small, rarely evicted) and page renders.
- On page change (`DocChange` listing pages), bump those pages' `page_rev`; old keys simply miss and age out.
- On `DocChange` with an empty `pages` tuple (= all pages), `ChangeKind.PAGES_CHANGED` (delete/move/insert/rotate) or `ChangeKind.RELOADED`: clear all page renders and reset every `page_rev`. Simplest correct option; keep nothing.
- `RenderKey` (§3) is the only cache key definition; doc 02 refers to it.
- Hold the last good image per page outside the LRU ("stale image") so a changed page shows the old render until the new one arrives, avoiding white flashes.

## 6. Drawing annotations: baked vs live items

Option A (**recommended for v1**): Let MuPDF render annotations into the page image (`annots=True`). Selection handles and the in-progress tool preview are Qt overlay items. When the user drags/resizes an annotation, show a translucent Qt preview rectangle; on release, push the command → re-render. Simple and pixel-accurate.

Option B: render with `annots=False` and draw every annotation as a `QGraphicsItem`. Smooth dragging, but you must reimplement how every annotation type looks, and it will never match MuPDF exactly. Only consider for Ink live drawing (the in-progress stroke is a `QGraphicsPathItem` until release).

Hybrid used for editing: while one annotation is being moved, temporarily set it hidden (`a.set_flags(a.flags | pymupdf.PDF_ANNOT_IS_HIDDEN)`, outside the undo history, restored after) and render it as an overlay pixmap from `annot.get_pixmap(matrix)`. Only do this if Option A's preview feels inadequate.

## 7. Zoom behavior

- Zoom steps: 25, 33, 50, 67, 75, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400, 500, 600, 800 %.
- Ctrl+wheel and pinch (`QNativeGestureEvent` on macOS trackpads) zoom anchored at cursor: `view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)`.
- Fit width: `zoom = (viewport_width - margins) / max_page_width_pt`. Fit page: min of width/height fits for current page. Recompute on window resize when in a fit mode.
- **Decision (M1): 100% = real paper size**, like Acrobat and browsers. The view transform is `geometry.view_scale(zoom, logicalDpiX) = zoom × logicalDpiX / 72` pixels per point (1.33 at 100% on a standard 96-dpi Windows screen). "Zoom" everywhere in the UI means this user-facing number; "scale" means pixels per point.
- Fit modes stay on until the user picks a zoom: the view recomputes them on resize. The vertical scroll bar is always shown so the usable width can't flip-flop.
- Until tiling exists (M3, §4), `geometry.render_scale` caps a page image at 4096 px on its longer side; above roughly 500% the page is a stretched image and looks slightly soft.

## 8. Text selection & hit-testing

Built in M2 (`core/text.py`, `ui/tools/select_tool.py`):

- **One text model for everything.** `extract_page_text(page)` reads `rawdict` into a `PageText`: the page's lines, each with its text, one box per character, its block number and its direction. Selection, copy *and* search (`core/search.py`) all work on it, so they can never disagree about where the text is.
- **Offsets.** A position in the text is an offset: the number of characters before it, counted over the whole page (the gap in front of a character, like a text cursor). A selection is a range `(start, end)`.
- **Reading and caching:** lazily, on the first interaction with a page. `DocumentModel.page_text(i)` remembers the last 8 pages and forgets all of them when another file opens. (From M4 on the cache must also be dropped when a page changes: key it by `page_rev`.)
- **Drag:** `offset_at(point)` for the press point and for the current point; the range between them is the selection. The line is chosen first (a line level with the pointer wins over a nearer line above or below, so dragging beside a short last line selects it to its end), then the gap within the line, measured along the line's direction.
- **Drawing:** `quads_in_range()` gives one quad per line, shown as a `QuadOverlay` (a child item of the `PageItem`, layer `SELECTION`; see `ui/overlays.py`). Overlays are painted with the "multiply" blend, like a highlighter pen, so the text under them stays black.
- **Copy:** `text_in_range()` joins the selected characters, with `\n` between lines. Deliberately *not* `tp.extractSelection()`: two methods could copy something other than what is highlighted.
- **Double-click** selects the word (`word_range_at`: letters, digits, `_` and apostrophes), **triple-click** the line (`line_range_at`). Qt has no triple-click event; `PageView` counts a press shortly after a double-click on the same spot as the third click.
- **Cursor:** I-beam when the point is on a line's box (give or take 2 pt), arrow elsewhere. Needs mouse tracking on the view's viewport. Later: pointer over links/widgets.
- **Limits (M2):** a selection stays within one page; no auto-scroll while dragging; right-to-left and vertical scripts are selected in the order MuPDF reports them.
- A page without text (a scan) shows a status-bar message when the user tries to select on it.

## 9. Links

`page.get_links()` → list of dicts with `kind` (`LINK_GOTO`, `LINK_URI`, `LINK_NAMED`...), `from` rect, `page`, `uri`. In Select/Hand tool, hovering shows pointing-hand cursor and tooltip; click navigates (internal) or asks confirmation before opening URI with `QDesktopServices.openUrl` (never open silently).

**Only open safe schemes:** `http`, `https`, `mailto`. Anything else (`file:`, `javascript:`, `smb:`, custom app schemes, or a relative path) is shown in the tooltip but **not opened**: "This link type isn't opened for safety." A `file://` link handed to `openUrl` can launch a program on the user's machine. Check with a small core function (`is_safe_link(uri) -> bool` in `core/`, no Qt) so it's unit-testable, and compare the scheme case-insensitively after stripping whitespace (`" JavaScript:..."` must be caught).

## 10. Thumbnails

Built in M2 (`ui/thumbnails.py`):

- A thumbnail fits a box of 120 × 180 logical px: an ordinary page is 120 wide, a very tall one is limited by the height (`geometry.fit_scale`).
- Model/view/delegate: `ThumbnailModel` (a `QAbstractListModel`) knows the pages, `ThumbnailView` (a `QListView`) scrolls them, `ThumbnailDelegate` paints one row (picture centered, page label below, a soft tint behind the current page).
- Lazy: the view only asks for the rows on screen. The model answers with blank paper of the right size, queues the row, draws one thumbnail per turn of the event loop (newest request first) and emits `dataChanged` when it is ready. At most 40 requests wait and 400 pictures are kept.
- The model also answers `SizeHintRole`, so laying out the list never needs a picture.
- The current page's row is selected and scrolled into view; a click (or Enter) asks the page view to go there.

Still to come: drawing through the render scheduler with LOW priority and the thumbnail cache tier (M3); multi-selection and drag to reorder with `setDragDropMode(InternalMove)` (M6, needs the page commands).

## 11. Performance checklist

- [ ] Never call `get_pixmap` for off-screen pages.
- [ ] No PyMuPDF calls anywhere except the UI thread (main doc) and the render process.
- [ ] Never `tobytes()` on every keystroke; coalesce.
- [ ] Use `TextPage`/display list reuse per page.
- [ ] `QGraphicsView.setViewportUpdateMode(SmartViewportUpdate)`; `setOptimizationFlag(DontSavePainterState)`.
- [ ] `PageItem.boundingRect()` constant per zoom; avoid recomputation in `paint()`.
- [ ] Profile with `python -X importtime` (startup) and `cProfile` / `py-spy` (runtime). Target first paint < 1 s.

## 12. Printing (P2)

`QPrinter` + `QPainter`: for each page, render at printer DPI (cap at 300) with `get_pixmap(dpi=...)` and draw scaled to `printer.pageRect`. Respect rotation (landscape pages). Render print pages in the render process (PyMuPDF can't run on threads) with a progress dialog for large docs.
