# 06: Editing Features: Implementation Recipes

Each recipe lists: **UX flow → core function(s) → command → edge cases → test**. Feature IDs match `01-product-spec.md`. All coordinates in core are unrotated PyMuPDF points (doc 03 §3).

---

## A. Annotations

### A1/A2: Text markup (highlight, underline, strike-out, squiggly)

**UX:** Select tool active → user drags across text → floating mini-toolbar appears (Highlight / Underline / Strike / Copy). Or HighlightTool active → drag directly creates highlight on release. Color chosen from toolbar swatch (defaults: yellow `(1, 0.92, 0.23)`, green, blue, pink, red).

**Core:**
```python
def quads_for_selection(page, a: Point, b: Point) -> list[Quad]:
    """One quad per line fragment covered by the selection, in reading order."""
    # 1. chars = flattened rawdict chars with (block, line, idx) ordering
    # 2. find start/end char indices nearest a and b; swap if reversed
    # 3. group selected chars by (block, line) → union of char bboxes per line → Quad(rect)
    # (for rotated/skewed text, build quads from char quads, not rects)

def add_text_markup(page, kind: str, quads: list[Quad], color, annot_id: str,
                    opacity=1.0, author="") -> None:
    fn = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
          "strikeout": page.add_strikeout_annot, "squiggly": page.add_squiggly_annot}[kind]
    a = fn(quads)
    a.set_colors(stroke=color); a.set_opacity(opacity); a.set_info(title=author)
    a.update()
    set_annot_id(page, a, annot_id)   # stable handle, see doc 02 §2.2
```
Pass **quads, not one big rect**; one big rect highlights the whitespace between lines.

**Command:** `AddAnnotCommand(page_index, factory_args)`: generates `annot_id` (UUID) once in `__init__`; `do` creates the annotation with that ID; `undo` deletes it by ID; redo recreates it with the **same** ID, so later commands that refer to it still work.

**Edge cases:** scanned pages with no text layer (offer OCR or rectangle highlight fallback = `Square` annot with fill and 0.3 opacity); multi-column layouts (reading order may jump: rely on block order, accept imperfection); vertical/rotated text; selection spanning pages (split into one command per page, wrapped in a macro: `stack.beginMacro("Highlight")`).

**Test:** create highlight on fixture text; reopen saved file; assert annot type "Highlight", quads count = line count, and `page.get_text("text", clip=annot.rect)` contains selected words.

### A3: Sticky note
**UX:** NoteTool → click → note icon placed + popup editor (QTextEdit in a small floating widget) opens → commit on focus-out or Ctrl+Enter.
**Core:** `page.add_text_annot(point, content, icon="Comment")` then `set_info(title=author)`, `set_colors(stroke=color)`, `update()`.
**Edit content later:** double-click → same editor → `ModifyAnnotCommand(annot_id, {"content": new})`.

### A4: Free text (typewriter)
**UX:** FreeTextTool → click (default box 200×24 pt) or drag box → inline editor (`QGraphicsTextItem` overlay at the box position, matching font size × zoom) → commit on click-away/Esc.
**Core:** `page.add_freetext_annot(rect, text, fontsize, fontname="helv", text_color=..., fill_color=None, rotate=page.rotation)`; after commit, auto-grow rect height to fit: measure line count via `pymupdf.get_text_length` per wrapped line, or just grow by line count × fontsize × 1.2.
**Edge cases:** non-Latin text: base-14 fonts lack glyphs. PyMuPDF FreeText supports limited fonts; for non-Latin text fall back to inserting page content text with an embedded font (C1) and warn. Rotated pages: pass `rotate=page.rotation` so it reads upright.

### A5: Shapes
**UX:** ShapeTool(kind) → drag. Shift constrains (square/circle/45° lines). Preview is a Qt item.
**Core:** `add_rect_annot`, `add_circle_annot`, `add_line_annot(p1, p2)` + `set_line_ends(..., PDF_ANNOT_LE_OPEN_ARROW)` for arrow, `set_border(width)`, `set_colors(stroke, fill)`, `update()`.
**Normalize rects:** `pymupdf.Rect(a, b).normalize()` so dragging up-left works.

### A6: Ink
**UX:** InkTool → press/move/release builds a stroke as a live `QGraphicsPathItem`. Strokes within 1.5 s and the same page combine into one Ink annot (optional; simpler: one annot per stroke).
**Core:** simplify points (RDP, ε≈0.5 pt), then `page.add_ink_annot([points])`, `set_border(width=2)`, `set_colors(stroke=color)`, `update()`.
**Edge:** stroke leaving the page → clip points to `page.rect` (in unrotated coords: clip to `page.mediabox`-relative rect after derotation).

### A7: Select / move / resize / delete annotations
**Hit-test:** iterate `page.annots()` in reverse (topmost last-drawn first), test `annot.rect.contains(pt)` (inflate small rects by 3 pt for usability). Exclude `Link` and `Widget` and `Popup` types from annotation selection.
**Selection overlay:** dashed rect + 8 handles (corners/edges) as Qt items, positioned via `PagePlacement.pdf_to_scene`.
**Move:** for `Square/Circle/FreeText/Stamp/Text`: `annot.set_rect(rect + delta)`. For `Ink/Line/Polygon/PolyLine`: vertices must be moved; simplest reliable way is **recreate**: read `annot.vertices`, `info`, `colors`, `border`, `opacity`, delete, re-add with transformed points (record as one command).
For text markup (Highlight etc.): **don't allow move** (it's tied to text); allow delete/recolor only.
**Resize:** Square/Circle/FreeText/Stamp via `set_rect`. Ink: scale vertices about the opposite corner (recreate).
**Command:** `MoveAnnotCommand(page, annot_id, old_rect_or_vertices, new_...)`. When moving by recreating (Ink/Line/Polygon), give the new annotation the same `annot_id`. Use `mergeWith` so arrow-key nudges merge into one undo step.
**Delete:** Delete key → `DeleteAnnotCommand` capturing a full property snapshot so undo can recreate it. Robust alternative: capture `doc.xref_object(xref)` + appearance stream and restore via low-level calls; complex. **Recommended:** snapshot-based undo for delete (doc 07 §3).

### A8/A9: Annotation list & properties
List model built from all pages' `annots()` (skip Link/Widget/Popup): columns page, type, author, content preview, modified date (`annot.info["modDate"]`). Properties edits → `ModifyAnnotCommand(annot_id, changes: dict)` mapping keys to setters (`color`→`set_colors`, `opacity`→`set_opacity`, `width`→`set_border`, `content`/`author`→`set_info`), then `update()`.

### A10: Flatten
`doc.bake(annots=True, widgets=False)` on the whole doc (no per-page option). Irreversible in the file sense; still undoable in-app via snapshot. Confirm dialog.

---

## P. Page organization

| Op | Core call | Undo approach |
|---|---|---|
| Rotate | `page.set_rotation((page.rotation + delta) % 360)` | inverse rotation (cheap) |
| Delete | `doc.delete_pages(sorted_indices)` | snapshot restore |
| Move/reorder | `doc.move_page(src, dest)` or `doc.select(new_order)` | inverse `select(inverse_order)` (cheap) or snapshot |
| Insert blank | `doc.new_page(pno=i, width=w, height=h)` (copy size of neighbor page) | delete page i |
| Insert from file | `doc.insert_pdf(src, start_at=i, links=True, annots=True)` | delete inserted range |
| Duplicate | `doc.fullcopy_page(i, i+1)` | delete page |
| Crop | `page.set_cropbox(rect)` | restore old cropbox |

**Reorder via thumbnails:** list widget emits the new order → `ReorderPagesCommand(old_order, new_order)` → `doc.select(new_order)`. Inverse: `inverse[new_order[k]] = k`, then `doc.select(inverse)`.

> ✅ Verified in 2.1: after `doc.select([3,2,1,0])` the outline is remapped correctly (bookmark "A" now points to page 4). After `delete_page`, bookmarks that pointed to the deleted page remain with page `-1` (dangling). After deletes, clean the TOC: `doc.set_toc([e for e in doc.get_toc(simple=False) if e[2] > 0])`, and keep that inside the same command so undo restores it.

**P5 Merge (dialog):** list of files (add/remove/reorder, show page counts, optional page ranges per file). Output to a *new* document:
```python
out = pymupdf.open()
toc = []
for path, ranges in items:
    src = pymupdf.open(path)  # handle passwords
    offset = out.page_count
    for (a, b) in ranges:
        out.insert_pdf(src, from_page=a, to_page=b, links=True, annots=True)
    toc += [[lvl, title, pg + offset, *rest] for lvl, title, pg, *rest in src.get_toc(simple=False)
            if in_ranges(pg - 1, ranges)]   # (page numbers in TOC are 1-based; remap if ranges skip pages)
    src.close()
out.set_toc(toc)
out.save(tmp, garbage=3, deflate=True); os.replace(tmp, dest)
```
Optional: add a top-level bookmark per source file (filename) and nest its TOC under it (level + 1).
Duplicate form field names across merged files collide → offer "rename fields with file prefix".

**P6 Split/extract:** parse range strings `"1-3, 7, 10-"` → 0-based indices (validate, dedupe, keep order). Modes: extract selected pages to one file; split every N pages; split by top-level bookmarks. Implementation: `new = pymupdf.open(); new.insert_pdf(doc, from_page=a, to_page=b)` per range; save each.

Range parser is a pure function, so unit test it heavily: `"" → error`, `"0" → error`, `"5-3" → error or reversed?` (decide: error), `"3-" → 3..last`, `"-2" → 1..2`, whitespace, duplicates.

---

## F. Forms

### F1: Fill
- On open: `doc.is_form_pdf`; build `FieldIndex`: for each page, `[(w.xref, w.field_name, w.field_type, w.rect)]`.
- Render widgets via MuPDF (appearance streams). When the user clicks a widget (in any non-annotation tool, FormFillTool behavior): overlay a native editor at the widget rect:
  - Text → `QLineEdit` (or `QTextEdit` if multiline flag `field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE`), font size scaled by zoom; respect `text_maxlen`.
  - Checkbox → toggle immediately (no editor): `on_state()` vs `"Off"`.
  - Radio → set this widget's on state (others in group turn off automatically when `update()` is called on the widget; verify with fixture).
  - Combo/List → `QComboBox` with `choice_values`.
- Commit → `SetFieldValueCommand(page, xref, old_value, new_value)`: `w = page.load_widget(xref); w.field_value = v; w.update()`.
- Tab/Shift+Tab → next/prev widget in (page, y, x) order (true tab order `/Tabs` is rarely reliable).
- Read-only fields (`field_flags & 1`) → not editable, show tooltip.
- Comb fields, date formats, JavaScript calculations/validation: **not executed**. Show a one-time banner if the form has JS actions ("Calculated fields won't update automatically").

### F5: XFA
```python
def has_xfa(doc) -> bool:
    t, _ = doc.xref_get_key(doc.pdf_catalog(), "AcroForm/XFA")
    return t != "null"
```
If true: banner "This form uses Adobe XFA. It may not display or fill correctly here." If the document has XFA **and** no AcroForm widgets (dynamic XFA), editing forms is impossible; make that clear.

### F3: Create field (P2)
FieldTool → drag rect → dialog (name must be unique, type) → `page.add_widget(w)`.

---

## C. Content editing

### C1: Add text to page content
**UX:** TextAddTool → click → inline editor → commit.
**Core:**
```python
def add_page_text(page, point, text, fontsize, color, font: FontChoice) -> None:
    if font.is_base14:
        missing = [ch for ch in text if not base14_supports(ch)]   # Latin-1 check
        if missing: raise UnsupportedGlyphs(missing)
        page.insert_text(point, text, fontsize=fontsize, fontname=font.short, color=color)
    else:
        page.insert_font(fontname=font.alias, fontfile=font.path)   # bundled TTF, e.g. Noto Sans
        page.insert_text(point, text, fontsize=fontsize, fontname=font.alias, color=color)
```
Multi-line: `insert_textbox(rect, ...)` and check return value `< 0` = overflow → grow rect or warn.
Ship fonts: Noto Sans (+ Noto Sans CJK optional, large), DejaVu Sans Mono. Check license (OFL) in `resources/fonts/LICENSES`.
Undo: snapshot restore (content-stream insertion has no cheap inverse).

> Prefer a **FreeText annotation** (A4) when the user just wants to "type on the PDF"; it stays editable later. C1 is for permanent content. The UI should present "Text box (editable)" vs "Add text (permanent)" clearly; default to the annotation.

### C2: Insert image
ImageTool → file dialog → place at click with natural size capped to 50% of page width, keep aspect ratio → drag to adjust before commit (overlay item) → `page.insert_image(rect, filename=path, keep_proportion=True)`.
- Convert HEIC/WebP/etc. via Qt (`QImage` → PNG bytes) → `stream=bytes`.
- Large photos: downscale to ≤ 300 dpi at placed size before inserting (`QImage.scaled`) to avoid bloating the file.
- Undo: snapshot.

### C3: Visual signature
- Signature manager dialog: **Draw** (QWidget with mouse painting, smoothing), **Type** (name rendered in a script font to transparent PNG), **Import** (image; auto-remove white background by thresholding to alpha).
- Store as transparent PNGs in app data dir.
- Place: SignatureTool → click → positioned overlay → resize with handles → commit as either:
  - **Stamp annotation** with custom appearance (movable later), via `page.add_stamp_annot(rect, stamp=0)` then replace appearance? Complex. **Or**
  - **Page content image** via `insert_image(rect, stream=png_bytes)` (simple, permanent). **Recommended v1.**
- UI wording: "Add signature image". Never claim it's a legally binding/digital signature.

### C4: Edit existing text (replace span)
**UX:** TextEditTool → hover highlights spans (outline from `get_text("dict")` span bboxes) → click span → inline editor pre-filled with span text, styled approximately (size × zoom) → Enter commits.

**Core recipe (✅ prototyped and working on a Helvetica span over a colored background):**
```python
def replace_span(page, span: dict, new_text: str, font: FontChoice) -> ReplaceResult:
    # 0) guard: page must have no OTHER pending redact annots (apply_redactions hits all of them)
    pending = [a for a in page.annots() if a.type[1] == "Redact"]
    if pending: raise PendingRedactionsError(page.number)
    # 1) remove only text glyphs under the span bbox, keep images & vector graphics
    page.add_redact_annot(span["bbox"], fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    # 2) re-insert at the original baseline with closest font & color
    c = span["color"]; rgb = ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255
    page.insert_text(span["origin"], new_text, fontsize=span["size"], fontname=font.alias, color=rgb)
    # 3) report overflow so UI can warn
    new_w = width_of(new_text, font, span["size"]); old_w = span["bbox"][2] - span["bbox"][0]
    return ReplaceResult(overflow=max(0.0, new_w - old_w))
```
Font matching (`span["font"]` like `ABCDEF+Arial-BoldMT`): strip subset prefix; map family + bold/italic flags → base-14 (`Arial`/`Helvetica` → `helv`/`hebo`; `Times*` → `tiro`/`tibo`; `Courier*` → `cour`) or bundled Noto Sans/Serif/Mono. Trying to reuse the embedded subset font is unreliable (missing glyphs); skip it.

**Force a full save afterwards:** the command sets `model.requires_full_save = True`. Replacing a span is a redaction underneath. An incremental save would keep the *old* text in an earlier revision inside the file, so someone who "fixed" an invoice amount would still be shipping the original number. A normal full save (`garbage=1`) is enough to drop it; this doesn't need the secure save, so undo history is kept.

Limitations to state in UI: one line at a time; no reflow; font may differ slightly; characters overlapping the span bbox from adjacent lines with tight leading might get removed (shrink bbox vertically by 15% of size to reduce risk; test on fixture).

If pending redactions exist on the page: ask "Apply pending redactions on this page first?" or block the edit.

### C5: Whiteout
`page.draw_rect(rect, color=None, fill=(1,1,1), overlay=True)`. Label: "Cover with white (content still exists underneath, so use Redact to remove it)".

---

## R. Redaction

### R1: Mark
RedactTool → drag rect (or select text → "Mark for redaction" uses quads) → `page.add_redact_annot(quad_or_rect, fill=(0,0,0), cross_out=True)` → visible as outlined red box, still reversible. Command: AddAnnot (cheap undo by `annot_id`).

### R2: Search & redact
Dialog: text term or preset patterns:
```python
PATTERNS = {
  "Email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
  "US phone": r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
  "US SSN": r"\b\d{3}-\d{2}-\d{4}\b",
  "Credit card (basic)": r"\b(?:\d[ -]?){13,19}\b",
}
```
Regex flow: per page, `get_text("rawdict")` → build page string + parallel list of char bboxes → `re.finditer` → for each match, union char bboxes per line → quads. Plain term flow: `page.search_for(term, quads=True)`. Show results list with checkboxes and page thumbnails; "Mark selected" → one macro command.

### R3: Apply
Confirmation dialog: "Redaction permanently removes the marked content. After applying, the file must be saved as a full copy. Continue?" with one checkbox, **off** by default: "Also remove lines and shapes that touch the marked areas (may erase table borders)". →
```python
graphics = (pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED if remove_touching_graphics
            else pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)
for page in doc:
    if any(a.type[1] == "Redact" for a in page.annots()):
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=graphics,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
```
Why `REMOVE_IF_COVERED` by default: with `REMOVE_IF_TOUCHED`, redacting one cell of a table can erase the *whole* table's border lines, because a grid is often drawn as one shape that touches every cell. Lines fully inside the box are removed either way.
Then set a model flag `requires_full_save = True` so the next Save does a full rewrite with `garbage=3`+ (doc 07 §5). Undo: snapshot.

Also offer (checkbox, default on) "Remove metadata and hidden content" → `doc.scrub(...)` with sensible flags.

**Verification test (must exist):** use the test in **doc 08 § Redaction** exactly as written. Don't write a simpler byte check like `b"secret" not in Path(out).read_bytes()`: PyMuPDF stores inserted text hex-encoded (and streams are usually compressed), so that check passes even when the secret is still in the file. Doc 08's version saves with `expand=True`, checks both the plain and hex forms, and first asserts the secret *is* found before redaction, so the check can't pass by accident.

### R4: Sanitize
Dialog with checkboxes mapped 1:1 to `doc.scrub` parameters. Always followed by full save.

---

## S. Other document-level features

- **Search (V6):** the background process (not a thread) iterates pages, `page.search_for(term, quads=True)`, emits results per page; UI highlights quads as overlay items (not annotations). Cancel on new search.
- **Properties (S9):** read/write `doc.metadata` → `doc.set_metadata({...})`. Command with old/new dict (cheap undo).
- **Export images (S6):** `page.get_pixmap(dpi=d).save(path)`; for JPG use `pix.save(path, jpg_quality=85)` (✅ parameter exists in 2.1).
- **Optimize (S5):** dialog: image target DPI, quality; run on a *copy*: `doc.rewrite_images(dpi_threshold=..., dpi_target=..., quality=...)`, `doc.subset_fonts()`, `save(garbage=4, deflate=True, use_objstms=1)`; show size before/after; let user keep or discard.
- **Password (S4):** Save As dialog option → `encryption=PDF_ENCRYPT_AES_256`, user/owner pw, permission checkboxes.

---

## X. Extras (V12–V16, A11–A12, T1–T2)

API names marked † aren't in doc 04's verified list yet: check them in `scratch/` first, then add a behavior test (CLAUDE.md working style).

- **Page labels (V12):** `page.get_label()` for display; to go to a typed label, `doc.get_page_numbers(label)`† (falls back to treating input as a number).
- **Reading position (V13):** `QSettings` key `positions/<sha1 of absolute path>` → `{page, zoom_mode, zoom}`. Keep the 100 most recent; clear them with File → Recent → Clear (doc 09 §4). Store a hash, not the path itself, under `positions/`.
- **Night mode (V14):** in the render process, after `get_pixmap`, call `pix.invert_irect()`† before sending pixels. `RenderKey.inverted` keeps normal and inverted images apart in the cache. Images and photos get inverted too; that's expected.
- **Snapshot tool (V15):** a `SnapshotTool` (drag a box, like the redact tool, but no command because nothing changes). Request the clip through the render scheduler at HIGH priority with `clip=` the box in PDF coords; on result, `QGuiApplication.clipboard().setImage(img)`.
- **Attachments (V16):** document-level files via `doc.embfile_names()`†, `doc.embfile_info(name)`†, `doc.embfile_get(name)`† (bytes); per-annotation files via `annot.get_file()`† on `FileAttachment` annots. "Save as…" writes the bytes with a file dialog; never open or execute them.
- **Measure (A11):**
  - Calibration: ratio entry ("1 in = 10 ft") or draw a line over a known dimension and type its real length → `units_per_point`, kept in the model per page for the session.
  - Distance = `Line` annot; perimeter = `PolyLine`; area = `Polygon` (shoelace formula on the vertices). Each gets its value written into the annot's content ("12.5 ft"), so other viewers show it.
  - The math is pure functions in `core/measure.py` with unit tests (known squares/triangles, rotated pages).
- **Export comments (A12):** for text markup annots, get the covered text per quad: `page.get_text("text", clip=quad.rect)` for each quad in `annot.vertices` (4 points per quad), joined; for notes/free text use `annot.info["content"]`. Write Markdown grouped by page (`## Page 3`, then `> highlighted text` + note + author). Pure function in core taking a `Document`, returning a string; the UI only picks the file path.
- **OCR (T1):** in the background process, per page: `tp = page.get_textpage_ocr(dpi=300, full=True)`†, then `page.get_text("dict", textpage=tp)` → for each span insert invisible text at its origin: `page.insert_text(origin, text, fontsize=size, fontname="helv", render_mode=3)`†. The page keeps its original image; only a hidden text layer is added. Return the modified pages as bytes; on the UI thread apply as one `SnapshotCommand`. Detect Tesseract first (catch the error from `get_textpage_ocr`) and show an install hint.
- **Compare (T2):** open the second file read-only. For each page pair: render both at the same DPI in the render process, compute a per-pixel difference (add `numpy` as a dependency for this), group changed pixels into boxes, draw them as overlay items. Text diff: `difflib` over `page.get_text("words")` lists. Pages added/removed: compare page counts and match by text similarity if they differ (keep v1 simple: compare page N with page N, and say so in the UI).
