# 04: PyMuPDF Reference (task → API, with gotchas)

Checked against **PyMuPDF 2.1** (the version on PyPI in November 2026). Import as `import pymupdf`. Colors are RGB tuples of floats 0–1. Geometry types: `pymupdf.Point`, `Rect`, `IRect`, `Quad`, `Matrix`. Every method name below was confirmed to exist in 2.1; behaviors marked ✅ were verified with a test script. Those scripts weren't kept, so each ✅ behavior the code relies on should get a test in `tests/pymupdf_behavior/` when you first depend on it (list in doc 08 §3). The project pins `pymupdf>=2.1,<2.2`; after any upgrade, run those tests and update this file.

> When unsure, write a throwaway script in `scratch/` and check. Don't guess.

> **Threads:** PyMuPDF does not support Python threads (wrong results or crashes, and it blocks the main thread). Use a separate process for background work; see doc 05 §3.1.

## 1. Open, inspect, close

```python
doc = pymupdf.open(path)                  # raises pymupdf.FileDataError / pymupdf.FileNotFoundError (§13)
doc = pymupdf.open(stream=data, filetype="pdf")   # from bytes
doc.is_pdf                                # False for XPS/EPUB/images/HTML/text; we only edit PDFs
doc.needs_pass                            # truthy → prompt for password. Read it ONCE, before authenticate() (trap below)
doc.authenticate(pw)                      # returns 0 on failure, >0 on success (2 = user password, 4 = owner password)
doc.is_encrypted, doc.permissions         # permission bitfield (pymupdf.PDF_PERM_*)
doc.is_repaired                           # True if MuPDF had to fix a broken file on open
doc.page_count
doc.metadata                              # dict: title, author, subject, keywords, creator, producer, ...
doc.get_toc(simple=False)                 # [[level, title, page_1based, dest_dict], ...]
doc.get_page_labels()                     # page label rules
page = doc[i]          # or doc.load_page(i), 0-based
page.get_label()                          # displayed label like "iv"; "" when the PDF defines no labels
doc.close()                               # a second close() raises ValueError
```

⚠️ ✅ **The `needs_pass` trap.** `doc.needs_pass` is not a harmless question: MuPDF answers it by trying an empty password, and a *wrong* password after the *right* one throws the decryption key away. So reading `needs_pass` after a successful `authenticate()` (or calling `authenticate()` again with a wrong password) silently breaks the document: no exception, but every page renders blank and `get_text()` returns nothing. Rule: read `needs_pass` once, right after `open()`; call `authenticate()` until it succeeds; then touch neither again. `DocumentModel` does this and exposes its own `needs_password` flag. `doc.is_encrypted` is safe to read at any time (it turns False after a successful `authenticate()`). (Tests: `tests/pymupdf_behavior/test_passwords.py::test_reading_needs_pass_after_unlocking_breaks_decryption`, `::test_wrong_password_after_the_right_one_breaks_decryption`. If they ever fail, the trap is fixed upstream and this warning can go.)

✅ Verified in 2.1, each with a test in `tests/pymupdf_behavior/`:
- Wrong `authenticate()` attempts *before* the right one do no harm, so a retry prompt can reuse one open `Document`. (`test_passwords.py::test_wrong_attempts_before_the_right_one_do_no_harm`)
- `authenticate()` returns 0 for a wrong password and a positive number for a right one; on an unprotected file it also returns a positive number. (`test_passwords.py::test_authenticate_returns_zero_when_wrong_and_positive_when_right`, `::test_authenticate_on_unprotected_file_reports_success`)
- A locked document answers `page_count`, but loading a page raises `ValueError("document closed or encrypted")`. (`test_passwords.py::test_locked_document_counts_pages_but_will_not_load_them`)
- **The file extension proves nothing.** MuPDF looks at the content: an HTML page or an image saved as `x.pdf` opens *without an error* as a 1-page document with `is_pdf == False`. Check `is_pdf` after every open. Content MuPDF recognizes as nothing at all (plain text, random bytes) raises `FileDataError`. (`test_open.py::test_html_saved_as_pdf_opens_but_is_not_a_pdf`, `::test_image_saved_as_pdf_opens_but_is_not_a_pdf`, `::test_garbage_file_raises_file_data_error`)
- A file whose `startxref` number is wrong still opens, with `is_repaired == True`. (`test_open.py::test_wrong_startxref_is_repaired_on_open`)
- `page.get_label()` returns each page's label, and `""` on every page when `doc.get_page_labels()` is `[]`. (`test_page_labels.py::test_get_label_returns_each_pages_label`, `::test_document_without_labels_gives_empty_strings_and_no_rules`)
- Not relied on, good to know: `doc.get_page_numbers("iii")` finds pages by label but is case-sensitive (`"III"` finds nothing), which is why `DocumentModel.find_page()` compares the labels itself.

## 2. Page geometry

```python
page.rect              # visible (CropBox-based) rect, ROTATED orientation, origin (0,0)
page.mediabox, page.cropbox, page.cropbox_position
page.rotation          # 0/90/180/270
page.set_rotation(90)  # absolute, not relative! new = (page.rotation + 90) % 360
page.rotation_matrix   # unrotated → rotated
page.derotation_matrix # rotated → unrotated
page.transformation_matrix  # PDF native (bottom-left) → PyMuPDF space; rarely needed
page.set_cropbox(rect)      # rect in unrotated MediaBox-relative coords
```
✅ Verified: after `set_rotation(90)` on a 612×792 page, `page.rect` = 792×612 while `mediabox` stays 612×792. (Test: `tests/pymupdf_behavior/test_rotation.py::test_set_rotation_90_swaps_rect_but_keeps_mediabox`)

✅ Verified, all in `tests/pymupdf_behavior/test_rotation.py`:
- `Point(72, 72) * page.rotation_matrix` is `Point(720, 72)` on that rotated page, and `derotation_matrix` undoes `rotation_matrix` at 0/90/180/270. (`::test_rotation_matrix_maps_unrotated_point_to_displayed_point`, `::test_derotation_matrix_undoes_rotation_matrix`)
- Text positions (`search_for`) are the same on a page at every rotation: they stay unrotated. (`::test_text_positions_stay_unrotated`)
- With a CropBox of `Rect(30, 40, 582, 762)`, `page.rect` is `Rect(0, 0, 552, 722)`, `cropbox_position` is `(30, 40)`, and text coordinates are measured from the CropBox corner. The two matrices need no extra offset. (`::test_page_rect_starts_at_zero_when_cropped`)

## 3. Rendering

```python
pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=rect_or_None, alpha=False, annots=True)
# also: dpi=150 instead of matrix
pix.width, pix.height, pix.stride, pix.n (3=RGB, 4=RGBA), pix.samples (bytes), pix.samples_mv (memoryview, no copy)
pix.save("out.png")    # export
```
Qt conversion (on the UI side, after the render process sends back the pixel bytes; `.copy()` so the QImage owns its memory):
```python
fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
```
✅ Verified (`tests/pymupdf_behavior/test_pixmap.py`): with `Matrix(z, z)` and `alpha=False` the pixmap is `page.rect` size × `z` (the *displayed*, rotated size), `pix.n == 3`, `pix.stride == 3 * pix.width`, the background is white. A Letter page at `z = 8` is 4896×6336 px = 93 MB, which is why `geometry.render_scale()` caps the size until tiling exists (M3).
- `clip` lets you render only a tile/region (essential for high zoom).
- `annots=False` renders page content without annotations (used when the UI draws an annotation being edited itself).
- Display list for repeated renders of the same page at different zooms: `dl = page.get_displaylist(); dl.get_pixmap(matrix=..., clip=...)`. Parse once, render many. Good for the render process.

## 4. Text extraction, search, selection

```python
page.get_text("text")                 # plain text
page.get_text("words")                # [(x0,y0,x1,y1, "word", block_no, line_no, word_no), ...]
page.get_text("dict")                 # blocks → lines → spans (font, size, color int, origin, bbox, flags)
page.get_text("rawdict")              # like dict but with per-character "chars" (bbox, origin, c)
page.get_text("dict", clip=rect)      # only inside rect
tp = page.get_textpage()              # reuse for multiple queries on one page (faster)
tp.extractSelection(pointa, pointb)   # text between two points, reading order (for copy)
page.search_for("needle", quads=True, textpage=tp)   # list of Quad (case-insensitive)
```
✅ `dict` span keys in 2.1: `size, flags, bidi, char_flags, font, color, alpha, ascender, descender, text, origin, bbox`.
- `color` is an int `0xRRGGBB` → convert: `((c>>16)&255)/255, ((c>>8)&255)/255, (c&255)/255`.
- `flags` bits: 1 superscript, 2 italic, 4 serif, 8 monospace, 16 bold.
- Search is case-insensitive, doesn't support regex. For regex: extract `words`/`rawdict`, regex over the joined text, map char indices back to char bboxes.
- Hyphenated line breaks and ligatures (ﬁ) affect matching; flags `pymupdf.TEXT_DEHYPHENATE`, `TEXT_PRESERVE_LIGATURES` control this.
- OCR (optional, needs Tesseract installed): `tp = page.get_textpage_ocr(language="eng", dpi=300, full=False)`.

## 5. Annotations

### Create
```python
a = page.add_highlight_annot(quads)       # also add_underline_annot, add_strikeout_annot, add_squiggly_annot
a = page.add_text_annot(point, "note text", icon="Note")   # sticky note
a = page.add_freetext_annot(rect, "text", fontsize=12, fontname="helv",
                            text_color=(0,0,0), fill_color=None, border_width=0, align=0)
a = page.add_rect_annot(rect); a = page.add_circle_annot(rect)
a = page.add_line_annot(p1, p2)
a = page.add_polyline_annot(points); a = page.add_polygon_annot(points)
a = page.add_ink_annot([[p, p, p, ...], [stroke2...]])   # list of strokes
a = page.add_stamp_annot(rect, stamp=0)
a = page.add_caret_annot(point)
```

### Style & finalize: ALWAYS call `update()` after changes
```python
a.set_colors(stroke=(1,0,0), fill=(1,1,0))   # highlight color is "stroke"
a.set_opacity(0.4)
a.set_border(width=2, dashes=[3, 2])
a.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)   # arrow
a.set_info(title="Jafer", content="comment text", subject="Review")   # title = author
a.set_flags(pymupdf.PDF_ANNOT_IS_PRINT)
a.set_rect(new_rect)          # move/resize (not for all types; ink/line/polygon: transform vertices)
a.update()                    # regenerate appearance stream; REQUIRED
```

### Read / find / delete
```python
for a in page.annots(): a.type  # (int, "Highlight"), a.rect, a.xref, a.info, a.colors, a.vertices, a.opacity
a = page.load_annot(annot_id)   # re-find by /NM unique name (our stable handle); also accepts an xref
a.info["id"]                    # the annotation's /NM value
doc.xref_set_key(a.xref, "NM", pymupdf.get_pdf_str(annot_id))   # set our own ID (set_info ignores "id")
page.delete_annot(a)
```
Gotchas:
- Iterating `page.annots()` while deleting → collect xrefs first, then delete.
- `annot.rect` for FreeText/Text is in unrotated coords; on rotated pages pass `rotate=page.rotation` to `add_freetext_annot` so text reads upright.
- `Text` annots (sticky notes) have a fixed icon size; `set_rect` only moves them.
- Ink stroke points come from mouse input: simplify (Ramer–Douglas–Peucker, epsilon ≈ 0.5 pt) before creating to avoid huge annotations.

## 6. Page operations

```python
doc.new_page(pno=-1, width=612, height=792)     # blank page (pno=-1 → append)
doc.delete_page(i); doc.delete_pages(from_page=a, to_page=b)   # or delete_pages([list])
doc.move_page(src, dest)                         # dest=-1 → to end
doc.copy_page(src, dest)                         # reference copy (shares content)
doc.fullcopy_page(src, dest)                     # independent copy
doc.select([2, 0, 1])                            # reorder/keep subset in one go
doc.insert_pdf(other_doc, from_page=0, to_page=-1, start_at=-1, links=True, annots=True, widgets=True)
page.show_pdf_page(rect, src_doc, src_pno)       # place another page as a "stamp" (n-up, overlays)
```
Gotchas:
- **`doc.select()` and `delete_pages` invalidate existing `Page` objects.** Reload pages after structural ops.
- Merging: `insert_pdf` copies TOC entries only if you rebuild TOC (`get_toc`/`set_toc`) yourself. Write a helper that offsets page numbers and concatenates TOCs.
- Merging docs with form fields that have **the same field names** merges their values. Rename fields on import if needed (`widget.field_name = f"{prefix}.{name}"; widget.update()`).
- ✅ `insert_pdf` **cannot run inside a journal operation** (raises "Can't undo/redo during an operation"). This affects the undo design (doc 07).

## 7. Adding content to the page (not annotations)

```python
page.insert_text(point, "text", fontsize=11, fontname="helv", color=(0,0,0), rotate=0)  # point = baseline start
rc = page.insert_textbox(rect, "long text", fontsize=11, fontname="helv", align=pymupdf.TEXT_ALIGN_LEFT)
# rc < 0 → text did not fit (overflow amount)
page.insert_htmlbox(rect, "<b>Rich</b> text", css="* {font-family: sans-serif;}")   # wraps, supports styling
page.insert_font(fontname="noto", fontfile="resources/fonts/NotoSans-Regular.ttf")    # then fontname="noto"
page.insert_image(rect, filename="sig.png", keep_proportion=True, overlay=True)     # or stream=bytes / pixmap=
shape = page.new_shape(); shape.draw_rect(r); shape.finish(color=(0,0,0), fill=(1,1,1)); shape.commit()
page.draw_rect(rect, color=None, fill=(1,1,1))   # quick whiteout
```
Measuring text:
```python
pymupdf.get_text_length("text", fontname="helv", fontsize=12)   # base-14 width in points
font = pymupdf.Font(fontfile="...ttf"); font.text_length("text", fontsize=12)
font.has_glyph(ord("Z"))     # returns glyph index; 0 → glyph missing
```
Base-14 short names: `helv`, `heit` (Helvetica-Oblique), `hebo`, `hebi`, `tiro` (Times), `tiit`, `tibo`, `tibi`, `cour`, `coit`, `cobo`, `cobi`, `symb`, `zadb`.

## 8. Redaction

```python
page.add_redact_annot(rect_or_quad, text=None, fill=(0,0,0), cross_out=True)   # marks only
page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,      # 2 (default): blank covered pixels
                      graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,   # 1 (default); TOUCHED=2 can wipe whole table grids
                      text=pymupdf.PDF_REDACT_TEXT_REMOVE)          # 0 (default)
```
✅ Verified: after apply, `get_text()` no longer contains the redacted string.
Constants: images `NONE=0, REMOVE=1, PIXELS=2, REMOVE_UNLESS_INVISIBLE=3`; graphics `NONE=0, REMOVE_IF_COVERED=1, REMOVE_IF_TOUCHED=2`; text `REMOVE=0, NONE=1, REMOVE_INVISIBLE=2`.

Gotchas:
- **`apply_redactions()` applies ALL pending redact annots on that page**, not just one. Any feature that uses redaction internally (text edit, C4) must handle pending user redactions on the same page (doc 06 §C4).
- `fill=False` → no box drawn after removal (used for text replacement).
- Text removal is per **character**: a char is removed if its bbox overlaps the redaction rect enough. Use the exact span/char bboxes.
- After redacting, do a **full save with `garbage=3` or higher**, not incremental, so old objects are dropped from the file.
- `doc.scrub(...)` removes metadata, JS, embedded files, hidden text, links, etc. (sanitize feature R4). Signature in 2.1: `scrub(attached_files, clean_pages, embedded_files, hidden_text, javascript, metadata, redactions, redact_images, remove_links, reset_fields, reset_responses, thumbnails, xml_metadata)`, all default True except `redact_images=0`.

## 9. Forms (widgets)

```python
doc.is_form_pdf                    # truthy (field count) if AcroForm fields exist
for w in page.widgets():
    w.field_name, w.field_type, w.field_type_string   # "Text", "CheckBox", "RadioButton", "ComboBox", "ListBox", "Button", "Signature"
    w.field_value, w.rect, w.field_flags, w.choice_values, w.button_states(), w.on_state()
    w.text_font, w.text_fontsize, w.text_maxlen, w.xref
w.field_value = "Jafer"; w.update()                   # text
w.field_value = w.on_state(); w.update()              # check a checkbox / select radio (on_state may be "Yes", "On", "1", ...)
w.field_value = "Off"; w.update()                     # uncheck
page.load_widget(xref)
# create:
w = pymupdf.Widget(); w.field_name="name"; w.field_type=pymupdf.PDF_WIDGET_TYPE_TEXT
w.rect = pymupdf.Rect(72,72,300,100); w.text_fontsize = 11; page.add_widget(w)
page.delete_widget(w)
```
- XFA detection: `doc.xref_get_key(doc.pdf_catalog(), "AcroForm/XFA")` → `('null','null')` if absent.
- Flatten form/annots: `doc.bake(annots=True, widgets=True)` (irreversible; do it on a copy).
- Widget JavaScript (`w.script*`) is stored but never executed by us. Calculated fields won't auto-update; document this.

## 10. Saving

✅ Signature (2.1): `save(filename, garbage=0, clean=0, deflate=0, deflate_images=0, deflate_fonts=0, incremental=0, ascii=0, expand=0, linear=0, no_new_id=0, appearance=0, pretty=0, encryption=1, permissions=4095, owner_pw=None, user_pw=None, preserve_metadata=1, use_objstms=0, compression_effort=0, raise_on_repair=False, reproducible=False)`

```python
doc.can_save_incrementally()       # False after some ops (e.g. repaired file, decrypt change)
doc.save(doc.name, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)    # fast in-place save
doc.save(tmp_path, garbage=3, deflate=True, use_objstms=1)                   # full rewrite (Save As / after redaction)
doc.ez_save(tmp_path)                                                        # shortcut: garbage=3, deflate=True
doc.save(tmp, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u",
         permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY)
doc.tobytes(garbage=0)                                                       # bytes in memory (snapshots)
doc.subset_fonts()                 # shrink embedded fonts before saving
doc.rewrite_images(dpi_threshold=150, dpi_target=120, quality=75)            # compress images (S5)
doc.is_dirty
```
Gotchas:
- ✅ **Saving non-incrementally to the currently open file's own path raises** "save to original must be incremental". Write to a temp file, close/reopen strategy, then `os.replace` (doc 07 §5).
- Incremental save with encryption changes is not allowed; use full save.
- `garbage=4` can be slow on big files; use 3 for normal Save As, 4 for "Optimize".

## 11. Undo journal (built into MuPDF)

```python
doc.journal_enable()
doc.journal_start_op("Add highlight"); ...edits...; doc.journal_stop_op()
doc.journal_undo(); doc.journal_redo(); doc.journal_can_do(); doc.journal_position()
```
✅ Verified behavior in 2.1:
- Once enabled, **every** mutation must happen inside `start_op/stop_op`, or MuPDF raises "Can't add a journal fragment absent an operation" (even `new_page`).
- Works for: annotations, delete_page, move_page, set_rotation, redactions.
- **Fails for `insert_pdf`** (merge/insert-from-file).
- Undo past the start raises `FzErrorArgument` ("Already at start of history"); guard with `journal_can_do()`.

Decision on whether to use it: doc 07.

## 12. Low-level object access (debugging, advanced)

```python
doc.xref_length()                 # number of objects
doc.xref_object(xref)             # PDF source of object as string
doc.xref_get_key(xref, "Key/Sub") # ('type', 'value')
doc.xref_set_key(xref, "Key", "value-as-pdf-syntax")
doc.xref_stream(xref)             # decompressed stream bytes
page.read_contents()              # page content stream bytes
page.clean_contents()             # normalize content stream (sometimes needed before edits)
page.wrap_contents()              # wrap in q/Q so our insertions aren't affected by unbalanced state
```
`wrap_contents()` matters: some PDFs leave the graphics state transformed at the end of their content stream, which makes text/images you insert appear mirrored or offset. PyMuPDF usually handles this; if insertions land in the wrong place, call `page.wrap_contents()` first.

## 13. Common error types

| Exception | When |
|---|---|
| `pymupdf.FileDataError` | Not a PDF / unrecoverably broken (but see §1: HTML and images open without error) |
| `pymupdf.EmptyFileError` | 0-byte file. A subclass of `FileDataError` ✅ (`test_open.py::test_empty_file_raises_empty_file_error`) |
| `pymupdf.FileNotFoundError` | Bad path. ✅ **PyMuPDF's own class** (a `RuntimeError`), *not* Python's built-in `FileNotFoundError`: `except FileNotFoundError:` does not catch it (`test_open.py::test_missing_file_raises_pymupdfs_own_file_not_found_error`) |
| `ValueError` | Bad arguments (e.g. page out of range, bad rect) |
| `RuntimeError` | Generic MuPDF errors (journal misuse, save-to-original) |
| `pymupdf.mupdf.FzErrorArgument` | Journal undo past start, etc. |

MuPDF also prints warnings to stderr for recoverable issues; capture with `pymupdf.TOOLS.mupdf_warnings()` and `pymupdf.TOOLS.reset_mupdf_warnings()` to show them in a debug panel.
