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

"Current page" for the status bar = page whose area covers the viewport center line.

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
- 100% means 72 dpi × dpr; some apps use 96 dpi as "actual size". Pick 100% = physical size on screen ≈ `zoom = logicalDpiX / 72`. Document the choice.

## 8. Text selection & hit-testing

- On page load (lazily, first interaction), extract `page.get_text("rawdict")` → flat list of chars with bboxes and (block, line) indexes; cache per page_rev.
- Selection by drag: find char nearest to press point and to current point; select all chars between them in reading order (block→line→char order). Draw selection as merged per-line rectangles (one `QGraphicsPathItem`).
- Copy: `tp.extractSelection(pa, pb)` or join selected chars (insert `\n` between lines).
- Double-click: select word (`get_text("words")`); triple-click: line.
- Cursor: I-beam over text (check if point within any char/line bbox; use a coarse grid index for speed), arrow elsewhere, pointer over links/widgets.

## 9. Links

`page.get_links()` → list of dicts with `kind` (`LINK_GOTO`, `LINK_URI`, `LINK_NAMED`...), `from` rect, `page`, `uri`. In Select/Hand tool, hovering shows pointing-hand cursor and tooltip; click navigates (internal) or asks confirmation before opening URI with `QDesktopServices.openUrl` (never open silently).

**Only open safe schemes:** `http`, `https`, `mailto`. Anything else (`file:`, `javascript:`, `smb:`, custom app schemes, or a relative path) is shown in the tooltip but **not opened**: "This link type isn't opened for safety." A `file://` link handed to `openUrl` can launch a program on the user's machine. Check with a small core function (`is_safe_link(uri) -> bool` in `core/`, no Qt) so it's unit-testable, and compare the scheme case-insensitively after stripping whitespace (`" JavaScript:..."` must be caught).

## 10. Thumbnails

- Render at fixed width (e.g. 120 logical px) using the same scheduler with LOW priority; cache in the thumbnail tier.
- `QListView` in `IconMode`, `setFlow(TopToBottom)`, `setDragDropMode(InternalMove)`, multi-selection.
- Lazy: model returns a placeholder icon until rendered; `dataChanged` when ready.

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
