# 08: Testing Strategy

## 1. Pyramid

| Layer | Tool | Volume | What |
|---|---|---|---|
| PyMuPDF behavior tests | pytest | One per relied-on behavior | `tests/pymupdf_behavior/`: prove the library still does what doc 04 says (✅ items). Run first after any PyMuPDF upgrade |
| Core unit tests | pytest | Many (most tests live here) | Each core function on fixture PDFs; geometry math; range parser; commands do/undo/redo round-trips |
| Integration | pytest | Medium | Open → edit → save → reopen → assert; cross-check output with a second library (pypdf) |
| GUI smoke | pytest-qt (`qtbot`) | Few | Window opens a file, tool switching, a highlight via simulated mouse drag, undo shortcut |
| Visual regression | pytest + pixel diff | Few, P1 | Render pages to PNG, compare against golden images with tolerance |
| Manual | checklist (§6) | Each release | Open outputs in Acrobat / Chrome / Preview |

`tests/core` must run without a display (no Qt import). In CI for GUI tests on Linux: `QT_QPA_PLATFORM=offscreen`.

## 2. Fixtures (`tests/fixtures/`)

Generate most fixtures **with a script** (`tests/fixtures/make_fixtures.py`) using PyMuPDF so they're reproducible and license-free. Keep a few real-world files that are hard to synthesize.

| Fixture | Purpose | How |
|---|---|---|
| `simple_text.pdf` | 2 pages Letter, known sentences with known positions | generated |
| `multi_column.pdf` | reading-order tests | generated (`insert_textbox` in two rects) |
| `rotated_pages.pdf` | pages with /Rotate 90, 180, 270 + text | generated + `set_rotation` |
| `cropbox_offset.pdf` | CropBox ≠ MediaBox, non-zero origin | generated + `set_cropbox` |
| `a4_and_letter_mixed.pdf` | mixed sizes for layout & merge | generated |
| `with_annotations.pdf` | one of each annot type, authored by "Other App" | generated |
| `form_acro.pdf` | text, checkbox (on state "Yes"), radio group (3), combo, list, read-only field, multiline | generated with `add_widget` |
| `form_xfa.pdf` | XFA detection | small real sample (check license) or craft by setting `AcroForm/XFA` key via `xref_set_key` |
| `encrypted_user_pw.pdf` | password "test" | generated: `save(encryption=AES_256, user_pw="test", owner_pw="owner")`; written only when missing, because encrypted output is never byte-identical twice |
| `page_labels.pdf` | page labels i–iv then 1–4 (go-to-page box, V12) | generated + `set_page_labels` |
| `owner_only_restricted.pdf` | opens without pw, no-modify permission | generated |
| `secret_for_redaction.pdf` | text "SECRET-4471", an image containing a known region, vector line under secret, a table border rectangle that crosses the redaction area | generated |
| `outline_nested.pdf` | 3-level TOC | generated + `set_toc` |
| `links.pdf` | internal GoTo + URI links | generated + `insert_link` |
| `subset_font_real.pdf` | real file with subset embedded fonts (for text-edit font fallback) | export from a word processor |
| `scanned_no_text.pdf` | image-only page | generated: insert a PNG of text |
| `large_500_pages.pdf` | performance | generated on demand in a perf test (don't commit) |
| `broken_xref.pdf` | repair path (`is_repaired`) | take `simple_text.pdf` bytes and corrupt the xref offset |
| `not_a_pdf.pdf` | error path | one fixed line of text (not random bytes, so the file is the same on every run) |
| `cjk_text.pdf` | non-Latin extraction/search | generated with a bundled CJK font if shipped |

Add `tests/fixtures/README.md` describing each file and its expected facts (e.g. "page 1 contains the word 'Lorem' at approx (72, 90)").

## 3. Key test cases (must exist)

### PyMuPDF behavior (`tests/pymupdf_behavior/`)
Add each one when code first relies on it:
- `set_rotation(90)` on a 612×792 page → `page.rect` is 792×612, `mediabox` unchanged.
- `tobytes()` → reopen keeps annotation xrefs; `save(garbage=2)` → reopen renumbers them.
- Non-incremental `save()` to the open file's own path raises.
- `doc.select([3,2,1,0])` remaps the outline; `delete_page` leaves `-1` outline entries.
- Inserted text is stored hex-encoded (why the redaction byte check needs the hex form).
- `apply_redactions()` removes the text from `get_text()`.
- `load_annot(annot_id)` finds an annotation by `/NM`; `annot.update()` keeps `/NM`; `/NM` survives `save(garbage=3)` (doc 02 §2.2).
- Full `save()` without `encryption=` writes an unencrypted file (doc 07 §5.4).

### Geometry
- Round-trip `scene_to_pdf(pdf_to_scene(p)) == p` for rotations 0/90/180/270 and cropbox offsets (use `pytest.approx`).
- Click in displayed top-left of a 90°-rotated page maps to the correct unrotated corner.

### Annotations
- Add each type → save → reopen → type, rect (≈), color, author preserved.
- Highlight across two lines → 2 quads.
- Stable IDs: add highlight → recolor → undo, undo → redo, redo → the highlight has the same `annot_id` and the new color.
- `annot_id` survives `save(garbage=3)` + reopen (`load_annot(annot_id)` still finds it).
- Editing an annotation from another app that has no `/NM` assigns one, and later commands find it by that ID.
- Modify color → `annot.colors["stroke"]` updated and appearance regenerated (render page, sample a pixel inside the highlight, assert hue changed).
- Delete annotation made by another app.

### Undo/redo (property-based style)
For each command type: `state0 = doc.tobytes()`, `do`, `undo`, assert semantic equality with state0 (compare page count, per-page text, annot list with (type, rect rounded, colors), field values). Byte equality is too strict. Then `redo` and compare with the post-do state.
Random sequence test: apply 30 random commands from a pool on `simple_text.pdf`, undo all, compare to original; redo all, compare to final.

### Pages
- Reorder → text order of pages matches new order; outline still points to correct pages.
- Delete page → TOC has no `-1` entries (cleanup applied).
- Merge two files → page count sum, bookmarks offset correctly, links still work (`get_links()` targets).
- Range parser: table-driven tests incl. invalid inputs.

### Forms
- Fill each field type → save → reopen with PyMuPDF **and** pypdf (`PdfReader(...).get_fields()`) → values match.
- Checkbox uses its actual on-state name ("Yes"), not hard-coded "On".
- Read-only field rejects edit at core level (raise).

### Redaction (security-critical)
```python
SECRET = "SECRET-4471"
SECRET_HEX = SECRET.encode().hex().encode()   # PyMuPDF writes inserted text as hex strings <5345...>

def raw_contains_secret(path) -> bool:
    raw = path.read_bytes().lower()
    return SECRET.encode().lower() in raw or SECRET_HEX in raw

def test_redaction_removes_text(tmp_path):
    src = tmp_path / "src.pdf"
    pymupdf.open(FIX / "secret_for_redaction.pdf").save(src, expand=True)
    assert raw_contains_secret(src)              # sanity check: the byte check below isn't vacuous

    doc = pymupdf.open(src)
    page = doc[0]
    for q in page.search_for(SECRET, quads=True):
        page.add_redact_annot(q)
    page.apply_redactions()
    out = tmp_path / "out.pdf"
    doc.save(out, garbage=3, deflate=False, expand=True)   # uncompressed for byte search
    assert SECRET not in pymupdf.open(out)[0].get_text()
    assert not raw_contains_secret(out)
    assert "SECRET" not in pypdf.PdfReader(out).pages[0].extract_text()  # second opinion
```
✅ Verified: PyMuPDF stores inserted text hex-encoded, so a plain `b"SECRET-4471" in bytes` check is *always* False and proves nothing. The sanity assertion catches that. After redaction + `garbage=3`, both literal and hex forms are gone.
- Image under redaction: pixels in region are blank after apply (render & sample).
- Line art: by default the line fully under the secret is gone but the crossing table border survives (check with `page.get_drawings()`); with "remove touching" on, the border is gone too.
- Text-edit (C4) refuses when other pending redactions exist on the page.
- Text-edit (C4) → Save: a full save was used (not incremental), and the old span text is not in the raw bytes (same plain + hex check as above).
- Secure save path is forced after apply (model flag) and undo stack cleared.

### Saving
- Save → reopen → identical page count/text.
- Incremental save path used when allowed (file size grows modestly; check `doc.can_save_incrementally()` branch via mock-free fixture).
- Simulated failure: monkeypatch `os.replace` to raise → original file bytes unchanged, temp cleaned or reported.
- Trimming undo history while there are unsaved changes keeps the document dirty (`is_dirty` True, quit prompt still shown); after Save it becomes clean.
- Encrypted doc full save keeps encryption when chosen (reopen needs password).
- Encrypted doc → snapshot command → undo → Save: the saved file is still encrypted (the model, not `doc.is_encrypted`, decides).
- `owner_only_restricted.pdf` → full save → reopened file has the same `permissions`.
- Autosave writes no recovery file for an encrypted doc; after ApplyRedactions, the recovery file passes the raw-bytes secret check (§ Redaction).
- Save As switches model path.

### Extras
- Page labels: `page_labels.pdf` (labels i–iv then 1–4) → go-to "iii" (or "III") lands on page index 2; go-to "3" finds the page *labelled* 3 (index 6), because a label wins; go-to "5" matches no label and so means the fifth page (index 4).
- Export comments: highlight a known sentence in `simple_text.pdf` + add a note → Markdown contains the sentence, the note text and the right page number.
- Measure: `core/measure.py` table tests (distance, perimeter, area of known shapes; calibration by known length).
- Night mode: normal and inverted renders of the same page get different cache keys; a white pixel renders black when inverted.
- Attachments: fixture with one embedded file → listed with correct name/size; saved bytes equal the original.
- OCR (slow, skipped when Tesseract isn't installed): `scanned_no_text.pdf` → after OCR, `search_for` finds a known word; the rendered page looks the same as before (pixel compare with tolerance).
- Compare: same file vs itself → no differences; vs a copy with one changed word → one changed region on the right page.

### Links
- `is_safe_link`: table-driven test. Allowed: `https://x.com`, `HTTP://X.COM`, `mailto:a@b.c`. Refused: `file:///C:/Windows/System32/calc.exe`, `javascript:alert(1)`, `  JavaScript:alert(1)`, `smb://host/share`, `../evil.exe`, empty string.

### Architecture rules
- `tests/core/test_no_qt_in_core.py`: in a fresh subprocess (`subprocess.run([sys.executable, "-c", ...])`), import every module under `pdfeditor.core` (use `pkgutil.walk_packages`) plus `pdfeditor.render.render_process`, then assert no name in `sys.modules` starts with `PySide6`. A subprocess is needed because pytest-qt has already imported Qt in the test process.

### Errors
- `not_a_pdf.pdf` → `PdfOpenError` with friendly message. Same for a missing file, a 0-byte file, a folder, and an HTML page saved as `.pdf` (which PyMuPDF opens without complaint; doc 04 §1).
- A failed open leaves the previously open document untouched.
- `broken_xref.pdf` → opens, `is_repaired` True → model exposes `was_repaired`.
- Wrong password → `model.authenticate()` returns False → retry flow (core returns status, not exception). Asking for a page while still locked raises `EncryptedError`.
- After unlocking, further `authenticate()` / `needs_password` calls on the model leave the document readable (guards the `needs_pass` trap, doc 04 §1).

### Performance (marked `@pytest.mark.slow`)
- Open `large_500_pages.pdf` + render page 1 at zoom 1.0 in < 1.5 s (the spec's target, doc 01 §4). CI machines vary, so log the timing every run and treat a failure as "investigate", not as flaky.
- Search across 500 pages completes and streams results (first result < 300 ms).

## 4. GUI tests (pytest-qt)

```python
def test_highlight_by_drag(qtbot, main_window_with(simple_text)):
    w = main_window_with
    w.tools.activate("highlight")
    start, end = w.view.scene_point_for(page=0, pdf_point=(72, 90)), ...(page=0, pdf_point=(300, 90))
    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=w.view.mapFromScene(start))
    qtbot.mouseMove(w.view.viewport(), pos=w.view.mapFromScene(end))
    qtbot.mouseRelease(w.view.viewport(), Qt.LeftButton, pos=w.view.mapFromScene(end))
    assert any(a.type[1] == "Highlight" for a in w.model.page(0).annots())
    qtbot.keyClick(w, Qt.Key_Z, Qt.ControlModifier)
    assert not list(w.model.page(0).annots())
```
Provide a test helper on PageView: `scene_point_for(page, pdf_point)` using `PagePlacement`.

## 5. Cross-viewer fidelity

Automate what's possible:
- Validate output structure with `qpdf --check out.pdf` (install qpdf in CI) → must report no errors.
- Re-open with pypdf to make sure a second, independent parser accepts the file.

## 6. Manual release checklist

- [ ] Open the outputs of: annotate-all-types, fill-form, merge, redact, password-save in **Adobe Acrobat Reader**, **Chrome**, **Firefox**, **macOS Preview** (if available), **Edge**.
- [ ] Annotations movable/editable in Acrobat; author name shows.
- [ ] Form values visible without clicking into fields (appearance streams OK).
- [ ] Redacted text not selectable/searchable in any viewer.
- [ ] Rotated page annotations display upright.
- [ ] 4K/Retina screen: text crisp at 100%, 200%.
- [ ] Large file scroll feels smooth; no freeze on open.
- [ ] Unsaved-changes prompt on quit.

## 7. CI

GitHub Actions matrix: ubuntu-latest + windows-latest + macos-latest, Python 3.11/3.14 (the oldest supported version and the one used for development). Steps: install → `ruff check` → `pyright` → `pytest -m "not slow"` (with `QT_QPA_PLATFORM=offscreen` on Linux, plus the Qt system libraries installed with `apt-get`). Cache pip. Set this up in **M0**, not at the end.

**Nightly slow-test job (from M3):** add a scheduled job that runs `pytest -m slow` together with the first slow test. Don't add it earlier: a pytest run that selects zero tests exits with an error.

**Packaging smoke job (from M1):** build with PyInstaller (one-folder), then run the built app with `--self-test` (opens a bundled fixture, renders page 1 offscreen, exits 0; from M3 it renders through the render process). It catches the classic packaging failures early: missing Qt plugins, missing MuPDF files, and a missing `multiprocessing.freeze_support()`.
