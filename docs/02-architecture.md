# 02: Architecture

## 1. Big picture

```
┌──────────────────────────── UI layer (PySide6) ────────────────────────────┐
│ MainWindow ─ Toolbar ─ Sidebar(Thumbs/Outline/Annots/Search) ─ PropsPanel  │
│        │                                                                   │
│   PageView (QGraphicsView) ── PageItem × N ── OverlayItems (selection,     │
│        │                                     handles, search hits, tool    │
│        │                                     previews)                     │
│   ToolController ── active Tool (SelectTool, HighlightTool, InkTool, …)    │
└────────┬───────────────────────────────┬───────────────────────────────────┘
         │ creates Commands              │ requests renders
         ▼                               ▼
┌──────────────── QUndoStack ─────┐   ┌──────── Render layer ───────────────┐
│ Command.redo()/undo()           │   │ RenderScheduler → render process     │
│ (wraps core operations)         │   │ RenderJob(page, zoom, rect, gen)     │
└────────┬────────────────────────┘   │ RenderCache (LRU of QImages)         │
         ▼                            └────────▲────────────────────────────┘
┌──────────────── Core layer (no Qt) ─────────┐│ reads bytes snapshot
│ DocumentModel ── wraps pymupdf.Document     ││
│  ├ annotations.py  pages.py  forms.py       │┘
│  ├ redaction.py  text_edit.py  search.py    │
│  ├ geometry.py   save.py                    │
│  └ emits change events via callbacks        │
└─────────────────────────────────────────────┘
                     ▼
                PyMuPDF (MuPDF C library)
```

**Dependency direction is one-way:** `ui → commands → core → pymupdf`. Core never imports UI. Render reads from core (or from a byte snapshot) but never mutates.

## 2. Core layer

### 2.1 `DocumentModel`

The single owner of the open `pymupdf.Document`. Everything else asks it.

```python
# core/document.py (shape, not final code)
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable
import pymupdf

ChangeListener = Callable[["DocChange"], None]

@dataclass(frozen=True)
class ChangeKind(StrEnum):   # an Enum, so a typo like "annot" fails loudly instead of silently
    PAGES_CHANGED = "pages_changed"   # pages added/removed/reordered/rotated
    PAGE_CONTENT = "page_content"
    ANNOTS = "annots"
    FORMS = "forms"
    METADATA = "metadata"
    RELOADED = "reloaded"             # whole Document object replaced (snapshot undo/redo, reopen after save)

class DocChange:
    kind: ChangeKind
    pages: tuple[int, ...] = ()   # affected page indices (empty = all)

class DocumentModel:
    def __init__(self) -> None:
        self.doc: pymupdf.Document | None = None
        self.path: Path | None = None
        self.revision: int = 0            # bumps on every notify(); the render process's snapshot generation. Per-page cache invalidation uses page_rev (doc 05 §5)
        self._listeners: list[ChangeListener] = []

    # lifecycle
    def open(self, path: Path, password: str | None = None) -> None: ...
    def close(self) -> None: ...
    @property
    def is_dirty(self) -> bool: ...       # undo stack clean index + unsaved_outside_history flag, see doc 07 §6

    # observation
    def subscribe(self, fn: ChangeListener) -> None: ...
    def notify(self, change: DocChange) -> None:
        self.revision += 1
        for fn in self._listeners: fn(change)

    # convenience
    def page(self, index: int) -> pymupdf.Page: ...
    @property
    def page_count(self) -> int: ...
    def snapshot_bytes(self) -> bytes:    # for the render process and undo snapshots
        ...   # returns a cached doc.tobytes() if the doc hasn't changed since (doc 07 §3, Memory control)
```

Why callbacks and not Qt signals? Core must stay Qt-free. The UI wraps the callback in a small `QObject` adapter (`ui/doc_signals.py`) that re-emits as a Qt `Signal`, so widgets connect normally.

### 2.2 Feature modules

Each module is a set of **pure-ish functions** that take a `pymupdf.Document`/`Page` plus plain arguments and perform one operation. They do not know about undo. Commands call them.

```python
# core/annotations.py
def add_highlight(page: pymupdf.Page, quads: list[pymupdf.Quad],
                  color: tuple[float, float, float], annot_id: str) -> None:
    """Add a highlight annotation tagged with annot_id so it can be found again."""
```

Identify annotations by an **annotation ID** (`annot_id`): a UUID string that we write into the annotation's own `/NM` ("unique name") key. Don't hold Python `Annot` objects (they become invalid after page reloads), and don't use xrefs as annotation handles either:
- **Redo breaks xrefs.** Undoing an "add highlight" deletes the object; redoing it creates a *new* object with a *new* xref, so a later "change color" command that remembered the old xref fails.
- **Saving can renumber xrefs** (`garbage` ≥ 2).

`/NM` is data stored inside the annotation, so it survives both. The command that creates an annotation generates the UUID once (in its `__init__`) and reuses the **same** ID on every redo. Re-fetch with `page.load_annot(annot_id)` (it accepts a `/NM` name or an xref).

```python
# core/annotations.py
def set_annot_id(page: pymupdf.Page, annot: pymupdf.Annot, annot_id: str) -> None:
    """Store our stable ID in /NM. (set_info ignores id changes, so write the key directly.)"""
    page.parent.xref_set_key(annot.xref, "NM", pymupdf.get_pdf_str(annot_id))
```
> Verify in `scratch/` before relying on it: `load_annot(annot_id)` finds the annotation, `annot.update()` doesn't overwrite `/NM`, and the ID survives `save(garbage=3)` + reopen.

Annotations made by other apps may have no `/NM`, or a non-unique one. Hit-testing finds them by xref; the first command that edits one calls `set_annot_id` with a fresh UUID inside its `do()`, and from then on refers to it by ID.

Form widgets are different: they're never deleted and recreated by our commands, so `(page_index, xref)` is fine for them.

### 2.3 Geometry (`core/geometry.py`)

The only place that knows about page offsets, rotation, zoom and device pixel ratio. Pure math, no Qt.

```python
@dataclass(frozen=True)
class PagePlacement:
    page_index: int
    origin_x: float          # top-left of the page in scene units (PDF points)
    origin_y: float
    rotation_matrix: pymupdf.Matrix     # copied from page.rotation_matrix
    derotation_matrix: pymupdf.Matrix   # copied from page.derotation_matrix

    def scene_to_pdf(self, x: float, y: float) -> pymupdf.Point:
        """Scene point → unrotated PDF point (what core functions expect)."""
        shown = pymupdf.Point(x - self.origin_x, y - self.origin_y)
        return shown * self.derotation_matrix

    def pdf_to_scene(self, p: pymupdf.Point) -> tuple[float, float]:
        shown = p * self.rotation_matrix
        return shown.x + self.origin_x, shown.y + self.origin_y

def render_matrix(zoom: float, dpr: float) -> pymupdf.Matrix:
    s = zoom * dpr           # zoom 1.0 = 72 dpi; dpr = devicePixelRatio (2.0 on Retina)
    return pymupdf.Matrix(s, s)
```
The view's own zoom transform (scene ↔ viewport pixels) is handled by Qt (`view.mapToScene`), so geometry.py never needs the zoom except for choosing render resolution. Unit-test both directions for rotations 0/90/180/270 (doc 08).

Rotation is handled by PyMuPDF: `page.rect` and rendered pixmaps already reflect `/Rotate`; annotation and text coordinates are in **unrotated** space. Use `page.rotation_matrix` / `page.derotation_matrix` when converting. Full explanation: doc 03 §3.

## 3. Command layer (undo/redo)

Commands subclass `QUndoCommand` **in the UI package** (`ui/commands_qt.py`) and wrap a Qt-free `core.commands.Command`:

```python
# core/commands/base.py (Qt-free)
class Command(ABC):
    label: str
    @abstractmethod
    def do(self, model: DocumentModel) -> DocChange: ...
    @abstractmethod
    def undo(self, model: DocumentModel) -> DocChange: ...

# ui/commands_qt.py
class QtCommand(QUndoCommand):
    def __init__(self, cmd: Command, model: DocumentModel):
        super().__init__(cmd.label); self.cmd, self.model = cmd, model
    def redo(self): self.model.notify(self.cmd.do(self.model))
    def undo(self): self.model.notify(self.cmd.undo(self.model))
```

`QUndoStack.push()` calls `redo()` immediately; that's how every edit gets applied. Details and the undo strategy decision: doc 07.

**One notification per step.** `QtCommand` is the *only* place that calls `model.notify()` for edits: commands return a `DocChange`, and core helpers (including `DocumentModel.restore_snapshot`) never notify on their own. Otherwise listeners run twice per undo.

**What listeners do on `RELOADED`:** every `Page`/`Annot` object is invalid, so re-read page count and sizes and re-lay out the view, clear page renders from the cache, send the render process a new snapshot, and rebuild thumbnails, outline and the annotation list.

## 4. Render layer

- `RenderScheduler` receives requests `(page_index, zoom, clip_rect, priority)` from visible `PageItem`s.
- Jobs run in a separate **render process** (PyMuPDF does not support Python threads). The process keeps its **own** `pymupdf.Document` opened from the current byte snapshot (or the path if the doc is unmodified). When `model.revision` changes, it reloads lazily.
- Results come back as raw pixel bytes. A small listener on the UI side turns them into a `QImage` and delivers it to the UI thread via a signal.
- `RenderCache`: LRU keyed by `RenderKey(page_index, zoom_bucket, tile, page_rev)` with a memory budget (e.g. 300 MB). The key is defined once, in doc 05 §3; use that definition.
- Stale results (generation counter mismatch) are discarded.

Full details: doc 05.

## 5. UI layer

### 5.1 PageView / PageItem
- `PageView(QGraphicsView)` holds a `QGraphicsScene`. Pages are stacked vertically with a fixed gap (e.g. 12 pt, in scene units) and centered.
- **Scene units are PDF points in displayed (rotated) orientation**; zoom is applied with the view transform (`view.setTransform(QTransform.fromScale(z, z))`). This is the decision from doc 05 §1; don't mix in the alternative.
- `PageItem(QGraphicsItem)` paints the cached image for its page (scaled to its point-size rect), or a placeholder (white rect + spinner) while rendering. It knows its page index and its size in scene units (= `page.rect` width/height).
- Overlays (selection rectangles, handles, search hit highlights, in-progress ink strokes) are **child items** of the `PageItem`, so they move with the page.
- Annotations are **rendered into the page image** by MuPDF (`annots=True`) *except* the one currently being edited, which is hidden from the render (set it to hidden temporarily, or render with `annots=False` and draw annots as items; see doc 05 §6 for the trade-off).

### 5.2 Tools (state pattern)
```python
class Tool:                      # ui/tools/base.py
    cursor: Qt.CursorShape
    def on_press(self, ev: PageEvent) -> None: ...
    def on_move(self, ev: PageEvent) -> None: ...
    def on_release(self, ev: PageEvent) -> None: ...
    def on_key(self, ev: QKeyEvent) -> bool: ...
    def activate(self) -> None: ...
    def deactivate(self) -> None: ...

@dataclass
class PageEvent:
    page_index: int
    pdf_point: pymupdf.Point     # already converted, unrotated PDF space
    modifiers: Qt.KeyboardModifiers
    button: Qt.MouseButton
```
`PageView` converts every mouse event into a `PageEvent` (hit-testing which page is under the cursor) and forwards it to `ToolController.active_tool`. Tools never deal with scene coordinates. They produce `Command`s and push them.

Tool list: `SelectTool` (text select + annotation select/move/resize), `HandTool`, `HighlightTool` (also underline/strike), `NoteTool`, `FreeTextTool`, `ShapeTool(kind)`, `InkTool`, `RedactTool`, `TextAddTool`, `ImageTool`, `SignatureTool`, `TextEditTool`, `FormFillTool` (default when clicking a widget).

### 5.3 Panels
- Thumbnails: `QListView` + custom model; renders at low zoom via the same scheduler with low priority. Supports drag-reorder (`InternalMove`) → emits `MovePagesCommand`.
- Outline: `QTreeView` from `doc.get_toc(simple=False)`.
- Annotations list: model rebuilt on `DocChange(kind="annots")`.
- Search: results list; runs in the background process (not a thread); streams results page by page.
- Properties: shows editable props for the current selection; edits produce `ModifyAnnotCommand` (merged via `QUndoCommand.mergeWith` for slider drags).

## 6. Data flow examples

**Highlighting text**
1. User drags with HighlightTool → tool asks `core.search/text` for chars under the drag (`page.get_text("rawdict")` or `page.get_textpage().extractSelection`; see doc 06 §A1), producing quads.
2. Tool shows a live preview overlay (no doc change yet).
3. On release → `push(AddHighlightCommand(page=3, quads=..., color=...))`.
4. `do()` calls `annotations.add_highlight` with the command's `annot_id` → returns `DocChange("annots", (3,))`.
5. Model notifies → render cache invalidates page 3 → PageItem requests re-render → annotations sidebar refreshes → window title shows `*`.

**Opening a file**
1. `File > Open` → dialog → `model.open(path)` (catch `pymupdf.FileDataError`, check `doc.needs_pass` → password dialog → `doc.authenticate(pw)`).
2. Check `doc.is_repaired` → if True, show non-blocking banner "File was damaged and repaired on open; save a copy."
3. Check XFA (doc 06 §F) → banner if present.
4. PageView builds PageItems using `page.rect` sizes only (cheap; no rendering yet).
5. Visible pages request renders.

## 7. Error-handling boundaries

| Where | What to do |
|---|---|
| Core functions | Raise specific exceptions (`PdfOpenError`, `EncryptedError`, `UnsupportedFeature`, `SaveError`). Never `print` + continue. |
| Commands `do()` | If core raises, the command must leave the doc unchanged (do the risky part first, or snapshot). Re-raise. |
| UI (slots, tool handlers) | `try/except` → `QMessageBox.warning` with a human message + "Details" containing traceback. Log to file. |
| Render process | Catch everything, send back `failed(page_index, message)`. If the process dies or times out, restart it. PageItem shows an error placeholder. |

Logging: `logging` module, rotating file in the user data dir (`QStandardPaths.AppDataLocation`), level INFO; DEBUG with `--debug` flag.

## 8. Settings & persistence

`QSettings` for: window geometry/state, recent files (max 10), default highlight color, author name for annotations, saved signatures (stored as PNG files in app data dir, paths in settings), last zoom mode.

## 9. Threading & process rules (summary)

1. Only the UI thread touches Qt widgets.
2. Only the UI thread touches the **main** `pymupdf.Document` held by `DocumentModel`. **No PyMuPDF calls on any other thread, ever**: PyMuPDF does not support Python threads.
3. Background PyMuPDF work (rendering, search) runs in a separate **process** with its own `Document` opened from bytes/path. `Page`, `Annot`, `TextPage` and `Document` objects can't cross a process boundary; don't try.
4. Only plain data crosses the boundary: requests as small tuples/dataclasses of numbers and strings; results as raw pixel bytes (+ width, height, stride) or lists of rects/strings. The UI side builds the `QImage` and `.copy()`s it so it owns its buffer.
5. A plain Python thread on the UI side *may* wait on the result queue and emit a Qt signal, as long as it never calls PyMuPDF or touches widgets.
