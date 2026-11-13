# 10: Build Plan (milestones)

Each milestone is **shippable on its own**: the app runs, tests pass, and there's something new to try. Do them in order. Each has: goal · what you'll learn · tasks · done-when · a starter prompt for Claude Code.

Rough effort assumes a beginner working evenings with Claude Code: ~1–2 weeks per milestone early on, faster later.

**MVP = M0–M8 plus the signature task at the start of M9.** That's where every P0 feature in doc 01 is done; see the checkpoint after M8.

---

## M0: Project skeleton
**Learn:** venv, `pyproject.toml`, package layout, pytest, ruff, git basics.
**Tasks**
- Create repo layout from CLAUDE.md; `pyproject.toml` with deps `PySide6`, `pymupdf>=2.1,<2.2`; dev extras `pytest`, `pytest-qt`, `ruff`, `pyright`, `pypdf`. (Pin PySide6 to a range too, based on the version you install.)
- Tool settings in `pyproject.toml`, so the rules in CLAUDE.md are checked automatically:
  ```toml
  [tool.ruff.lint]
  select = ["E", "F", "I", "B", "UP", "ANN", "C901", "PLR0915"]
  ignore = ["ANN401"]                      # allow `Any` where it's genuinely needed
  [tool.ruff.lint.per-file-ignores]
  "tests/**" = ["ANN"]                     # no type hints required in tests
  [tool.ruff.lint.mccabe]
  max-complexity = 10                      # too many branches → split the function
  [tool.ruff.lint.pylint]
  max-statements = 30                      # roughly the "~40 lines" rule
  [tool.pyright]
  typeCheckingMode = "basic"
  ```
  If PyMuPDF's incomplete type info causes a flood of pyright errors, lower just those rules to warnings rather than switching pyright off.
- `tests/core/test_no_qt_in_core.py` (doc 08 §3, Architecture rules).
- `python -m pdfeditor` opens an empty `QMainWindow` titled "PDF Editor".
- `tests/fixtures/make_fixtures.py` generating `simple_text.pdf` and `rotated_pages.pdf`.
- One passing core test (open fixture, assert page count).
- First test in `tests/pymupdf_behavior/` (the rotation one from doc 08 §3).
- `.gitignore` (`.venv/`, `scratch/`, `__pycache__/`, `dist/`, `build/`).
- `.github/workflows/ci.yml`: `ruff check` + `pyright` + `pytest -m "not slow"` on Windows, macOS and Linux (doc 08 §7). Push to GitHub and see it go green once.

**Done when:** `pytest -q`, `ruff check` and `pyright` pass locally **and in CI**; window opens.
**Prompt:** *"Read CLAUDE.md. Set up milestone M0 from docs/10-build-plan.md. Explain each file you create in one or two sentences."*

---

## M1: Open & render (synchronous, simple)
**Learn:** PyMuPDF open/render, Pixmap → QImage, QGraphicsView/Scene/Item, scene coordinates.
**Tasks**
- `DocumentModel.open/close`, error types (doc 02 §7).
- File → Open dialog, drag-and-drop, CLI arg, File → Open Recent (max 10, `QSettings`) (V1).
- Password prompt with retry for encrypted files (S3; doc 09 §3, Opening).
- `PageView` with all pages stacked; render **synchronously on the UI thread**, visible pages only.
- Zoom in/out/fit width; Ctrl+wheel; status bar "Page X / N · 125%". Also 100% (Ctrl+0) and fit page (Ctrl+1), so that V3 is complete here as the MVP table below says.
- Page navigation: PgUp/PgDn, go-to-page box (with page labels, V12). Also Home/End, to complete V5.
- **Packaging smoke build:** a first `packaging/pdfeditor.spec` (PyInstaller, one-folder) and a `--self-test` flag: open a bundled fixture, render page 1 offscreen, exit with code 0. Build it once by hand on your machine, then add a build-only CI job that runs the built app with `--self-test` (doc 08 §7). PySide6 + PyMuPDF bundling problems show up here, while the app is still tiny.

**Done when:** a 100-page PDF scrolls acceptably; zoom works; bad files show a friendly error; the packaged build passes `--self-test` in CI.
**Prompt:** *"Implement M1. Keep rendering synchronous for now (we'll move it to a separate render process in M3). Use the scene-in-PDF-points + view transform approach from docs/05 §1. Add `core/geometry.py` with PagePlacement and unit tests for all four rotations."*

---

## M2: Thumbnails, search, text selection & copy
**Learn:** Qt model/view (`QAbstractListModel`), text extraction (`rawdict`), hit-testing.
**Tasks**
- Sidebar with thumbnails (click → navigate).
- Search bar: find all, highlight hits (overlay items), next/prev, count.
- Select tool: drag-select text, Ctrl+C copy; I-beam cursor over text.
- Outline (TOC) panel.

**Done when:** you can find a word in a long doc and copy a paragraph.

---

## M3: Background rendering & cache
**Learn:** processes vs threads (`multiprocessing`, queues), getting results back onto the Qt UI thread with a signal, LRU caches, why PyMuPDF can't be used from threads.
**Tasks**
- RenderScheduler + one render process with its own Document (doc 05 §3); kill-and-restart on timeout.
- `multiprocessing.freeze_support()` in `__main__.py` so packaged builds still work; extend `--self-test` to render through the render process, so CI catches a broken packaged build.
- LRU cache with byte budget; stale-image fallback; generation counters.
- HiDPI-correct rendering.
- Tiling for > 4096 px renders.
- First `@pytest.mark.slow` performance test (doc 08 §3, Performance) and the nightly CI job that runs it (doc 08 §7; deferred from M0).

**Done when:** a 500-page file opens instantly and scrolling never stutters; zooming to 800% stays responsive.

---

## M4: Command pattern, undo/redo, dirty state, Save
**Learn:** command pattern, `QUndoStack`, `QUndoView`, atomic file writes, incremental vs full save.
**Tasks**
- `core/commands/base.py` with `InverseCommand` + `SnapshotCommand` (doc 07 §3).
- `QtCommand` adapter, Edit menu Undo/Redo with labels ("Undo Rotate Page").
- History panel: a `QUndoView` on the undo stack in a sidebar tab (doc 07 §3, History panel). A few lines of code, and it shows you exactly what your commands are doing while you build the rest.
- First real commands: RotatePages (inverse), DeletePages (snapshot).
- Save / Save As per doc 07 §5; title `*`; unsaved-changes prompt.
- Tests: do/undo/redo round-trips; save failure leaves original intact.

**Done when:** rotate + delete pages, undo/redo them, save, reopen → correct.

---

## M5: Annotations I (highlight, note, free text) + selection
**Learn:** tool state pattern, mouse event → PDF coordinates, annotation APIs, appearance streams.
**Tasks**
- Tool system (`ui/tools/`), toolbar with tool buttons + shortcuts.
- HighlightTool / underline / strikeout with quads.
- NoteTool with popup editor; FreeTextTool with inline editor.
- SnapshotTool (V15): copy a region to the clipboard.
- Export comments to Markdown (A12).
- SelectTool: select existing annots, move (rect-based), delete, recolor.
- Annotation author name setting.

**Done when:** annotations made here look right and are editable in Acrobat/Chrome.

---

## M6: Page organization & merge/split
**Tasks**
- Thumbnail drag-reorder (ReorderPagesCommand), multi-select delete/rotate.
- Insert blank page, insert from file.
- Merge dialog (new file), Extract/Split dialog with range parser (+ heavy unit tests).
- TOC cleanup after deletes.

**Done when:** merge 3 PDFs with bookmarks, reorder, extract pages 2–4 to a new file.

---

## M7: Forms
**Tasks**
- Detect widgets; overlay editors per type; tab navigation.
- SetFieldValueCommand; appearance regeneration; read-only handling.
- XFA and JavaScript banners.

**Done when:** a government-style AcroForm can be filled, saved and shows values in Chrome and Acrobat.

---

## M8: Redaction & sanitize (security milestone)
**Tasks**
- RedactTool (area + text selection), Search & Redact dialog with regex presets.
- Apply redactions with confirmation; forced secure save; undo stack clear notice.
- Sanitize dialog (`doc.scrub`).
- Attachments panel (V16): list + "Save as…" (sanitize can remove them, so build them together).
- The redaction tests in doc 08 §3 (with the non-vacuous byte check).

**Done when:** all redaction tests pass and redacted text is unrecoverable in every viewer.

---

## ✅ MVP checkpoint (after M8 + the signature task in M9)
Every P0 feature from doc 01 is built by here:

| Milestone | P0 features |
|---|---|
| M1 | V1 open (incl. recent files), V2 scroll, V3 zoom, V5 go to page, S3 password |
| M2 | V4 thumbnails, V6 search |
| M4 | S1 save, S2 unsaved prompt, P1 rotate, P2 delete |
| M5 | A1 highlight, A3 note, A4 free text, A7 select/move/delete |
| M6 | P3 reorder, P5 merge, P6 split/extract |
| M7 | F1 fill forms |
| M8 | R1 mark redaction, R3 apply redaction |
| M9 (first task) | C3 visual signature |

Before going on: run the manual release checklist (doc 08 §6), tag `v0.1.0`, and record a short demo GIF for the README. Everything after this is P1/P2.

---

## M9: Content: images, signatures, shapes, ink, add text
**Tasks**
- **First (P0, part of the MVP):** Signature manager (draw/type/import) + placement (C3).
- ImageTool.
- ShapeTool (rect/ellipse/line/arrow), InkTool with RDP simplification.
- Measure tool (A11): calibration + distance/perimeter/area, building on the line/polygon shapes.
- Add permanent text (C1) with bundled Noto Sans.
- Whiteout.

---

## M10: Edit existing text (C4)
**Tasks**
- TextEditTool with span hover outlines; replace_span recipe (doc 06 §C4); font mapping; overflow warning; pending-redaction guard.
- Test on `simple_text.pdf` and `subset_font_real.pdf`.

---

## M11: Polish & ship
**Tasks**
- Properties panel, annotation list, document properties dialog, password Save As, Optimize dialog, export PNG/JPG.
- Settings dialog, dark UI theme, icons, About + licenses dialog. (Recent files moved to M1.)
- Remember reading position per file (V13).
- Autosave/recovery, external-change detection.
- Packaging polish: app icon, version info, release build artifacts uploaded by CI (CI and the basic packaged build exist since M0/M1).
- README with screenshots + GIF demo (good for a portfolio).

---

## M12: Extras after v1 (P2)
**Tasks**
- Night reading mode (V14).
- OCR "make searchable" (T1), using the render/background process.
- Compare two versions (T2).

**Done when:** each has its tests from doc 08 § Extras and is documented in the README.

---

## Portfolio framing (for job applications)

What to highlight in the README / interviews:
- **Architecture:** Qt-free core with unit tests; command pattern undo with a measured trade-off (journal vs inverse vs snapshot, backed by your own experiments).
- **Concurrency:** rendering in a separate process (PyMuPDF can't use threads), timeout + restart for hostile files, cache with memory budget.
- **Correctness under hostile input:** atomic saves, verified redaction tests, fuzz-ish tests on broken files.
- **Measurements:** time-to-first-page and memory on a 500-page file before/after M3.

## Definition of done (every milestone)
- [ ] `pytest -q` green, `ruff check` and `pyright` clean
- [ ] New core code has tests; at least one round-trip (save → reopen) test for new edits
- [ ] No Qt imports in `core/` (the test checks this)
- [ ] All mutations go through commands
- [ ] Manually tried in the app; output opened in at least one other viewer
- [ ] CLAUDE.md / docs updated if a decision changed, plus one line in `docs/11-decisions.md`
