# CLAUDE.md: PDF Editor (project root context)

Read this file at the start of every session. It is the entry point. Detailed context lives in `docs/`; open the file that matches the task before writing code.

## Current status (update at the end of every session)

- **Milestone:** M0 (project skeleton) done; M1 (open & render) not started
- **Done so far:** context docs; M0: `pyproject.toml`, empty "PDF Editor" window, 2 fixture PDFs, 6 tests, CI green on Windows/macOS/Linux with Python 3.11 and 3.14
- **Next step:** start M1 from `docs/10-build-plan.md`
- **Known issues / open questions:** none
- **Last updated:** 2026-11-12

## What we are building

A **desktop PDF editor** written in Python. It opens existing PDFs, renders them accurately, and lets the user:

1. View and navigate (zoom, scroll, thumbnails, search, outline/bookmarks)
2. Annotate (highlight, underline, strike-out, sticky notes, free text, shapes, ink/freehand)
3. Organize pages (reorder, rotate, delete, insert, extract, merge PDFs, split)
4. Fill and create form fields (AcroForm)
5. Add content (text boxes, images, a visual signature stamp)
6. Redact **securely** (content is actually removed, not just covered)
7. Edit existing text in a limited, honest way (see `docs/06-editing-features.md`, "Text editing")
8. Save safely (incremental save, "Save As", optimize/compress, password-protect)

The developer (Jafer) is a **Python beginner** building this to learn. Optimize for:
- **Readable code over clever code.** Short functions, clear names, type hints, docstrings that explain *why*.
- **Small, testable steps.** Every milestone in `docs/10-build-plan.md` must run on its own.
- **Explaining as you go.** When introducing a new concept (Qt signals, PDF coordinate spaces, the command pattern), add a 2–4 line comment or tell the developer in chat what it is and why it's used. Don't dump a finished app; build feature by feature.

## Tech stack (decided, don't swap without asking)

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Developer's language |
| GUI | **PySide6** (Qt 6, LGPL) | Mature desktop toolkit, `QGraphicsView` suits page canvases, has `QUndoStack` |
| PDF engine | **PyMuPDF** (`import pymupdf`), pinned `pymupdf>=2.1,<2.2` | Fast MuPDF rendering + annotations, redaction, forms, page ops in one library. Upgrade deliberately: bump the pin, run `tests/pymupdf_behavior`, update doc 04 |
| Optional OCR | Tesseract via PyMuPDF's `get_textpage_ocr` | Later milestone only |
| Packaging | PyInstaller | Single-folder app for Windows/macOS |
| Tests | pytest + pytest-qt | Unit tests for the core, a few GUI smoke tests |
| Lint/format | ruff (lint + format) | One tool, fast |
| Type check | pyright (basic mode) | Catches wrong types and typos in attribute names before you run the app |

**Licensing note:** PyMuPDF is AGPL-3.0 (or a commercial license from Artifex). That's fine for a personal or portfolio project whose source is public. If the app is ever *distributed closed-source or sold*, it needs a commercial license or a swap to permissive libraries (pypdfium2 for rendering + pikepdf/pypdf for editing). See `docs/09-security-licensing-edge-cases.md`.

Use the modern import name: `import pymupdf` (not `import fitz`, which is the legacy alias).

## Repository layout

```
pdf-editor/
├── CLAUDE.md                  ← this file
├── LICENSE                    ← AGPL-3.0 (see docs/09 §2)
├── pyproject.toml
├── README.md
├── .github/workflows/ci.yml   ← lint + tests on Windows/macOS/Linux (docs/08 §7)
├── docs/                      ← context files (read before coding)
├── packaging/
│   └── pdfeditor.spec         ← PyInstaller build
├── scratch/                   ← throwaway experiment scripts (git-ignored)
├── src/pdfeditor/
│   ├── __main__.py            ← `python -m pdfeditor`
│   ├── app.py                 ← QApplication setup, main window creation
│   ├── core/                  ← NO Qt imports allowed in here
│   │   ├── document.py        ← DocumentModel: wraps pymupdf.Document
│   │   ├── geometry.py        ← PDF ↔ screen coordinate conversion
│   │   ├── errors.py          ← PdfOpenError, EncryptedError, UnsupportedFeature, SaveError, …
│   │   ├── commands/          ← one file per undoable command family
│   │   │   └── base.py        ← Command, InverseCommand, SnapshotCommand (docs/07 §3)
│   │   ├── annotations.py
│   │   ├── pages.py           ← reorder/rotate/delete/insert/merge/split
│   │   ├── forms.py
│   │   ├── redaction.py
│   │   ├── text_edit.py
│   │   ├── search.py
│   │   ├── links.py           ← is_safe_link() and link helpers (docs/05 §9)
│   │   └── save.py
│   ├── render/
│   │   ├── render_process.py  ← runs in a separate process: page → raw pixels (PyMuPDF only, no Qt)
│   │   ├── renderer.py        ← UI-side client: sends requests, turns pixels into QImage
│   │   └── cache.py           ← LRU cache of rendered pages/tiles
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── commands_qt.py     ← QtCommand: wraps a core Command in a QUndoCommand
│   │   ├── doc_signals.py     ← re-emits DocumentModel callbacks as Qt signals
│   │   ├── page_view.py       ← QGraphicsView canvas
│   │   ├── page_item.py       ← one QGraphicsItem per page
│   │   ├── thumbnails.py
│   │   ├── sidebar.py         ← outline, annotations list, search results
│   │   ├── toolbar.py
│   │   ├── tools/             ← one class per interaction tool (select, highlight, ink, …)
│   │   └── dialogs/
│   └── resources/             ← icons, .qss stylesheet, fonts/ (+ their license texts)
└── tests/
    ├── fixtures/              ← sample PDFs (see docs/08-testing.md)
    │   ├── make_fixtures.py   ← generates most fixture PDFs
    │   └── README.md          ← what each fixture contains
    ├── pymupdf_behavior/      ← small tests proving each PyMuPDF behavior the code relies on (the ✅ facts in docs/04)
    ├── core/
    └── ui/
```

## Hard rules

1. **`core/` must never import PySide6.** Core works on PDF coordinates and plain Python types so it can be unit-tested without a GUI. The UI translates mouse events into core calls. (Enforced by `tests/core/test_no_qt_in_core.py`; the same goes for `render/render_process.py`.)
2. **Every document mutation goes through a Command** pushed onto the undo stack. No UI code calls `page.add_highlight_annot(...)` directly. See `docs/07-undo-redo-and-saving.md`.
3. **Coordinates:** core functions take and return **PDF user-space points in PyMuPDF's convention** (origin top-left of the *unrotated* page, y grows downward, 1 unit = 1/72 inch). Conversion to screen pixels happens only in `core/geometry.py`, and the UI calls it. Never mix the two. See `docs/03-pdf-fundamentals.md` §Coordinates.
4. **Never block the UI thread** with rendering or search on large docs. PyMuPDF **does not support Python threads** (it can crash, and its calls block the UI thread anyway), so background PyMuPDF work runs in a separate **process** (`multiprocessing`), never in a `QThread`/`QThreadPool`. The render process opens its own `pymupdf.Document` (from the path or bytes); only plain data (numbers, strings, bytes) crosses the process boundary. See `docs/05-viewer-and-rendering.md` §3.
5. **Never silently overwrite the user's original file in a destructive way.** Save writes to a temp file in the same folder, then atomically replaces (`os.replace`). Incremental save is allowed in place.
6. **Redaction must remove content**, never just draw a black box. Always `apply_redactions()` and verify with text extraction in tests.
7. **Fail loudly in dev, gracefully for users.** Catch exceptions at UI boundaries and show a dialog. Never swallow exceptions in core.
8. Keep functions under ~40 lines; split if longer. Type-hint all public functions. (ruff flags overly long/complex functions and missing type hints; pyright checks the hints.)

## Commands

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pdfeditor [optional/path/to/file.pdf]       # run
pytest -q                                              # all tests
pytest tests/core -q                                   # fast, no GUI
ruff check src tests && ruff format src tests          # lint + format
pyright                                                # type check
pyinstaller packaging/pdfeditor.spec                   # build app
```

## Which doc to read for which task

| Task | Read |
|---|---|
| What features, what "done" means | `docs/01-product-spec.md` |
| Where code goes, how layers talk | `docs/02-architecture.md` |
| Anything touching coordinates, fonts, objects, "why can't I just edit text" | `docs/03-pdf-fundamentals.md` |
| Which PyMuPDF call does X, plus gotchas | `docs/04-pymupdf-reference.md` |
| Canvas, zoom, scrolling, render process, caching | `docs/05-viewer-and-rendering.md` |
| Implementing a specific editing feature | `docs/06-editing-features.md` |
| Undo/redo, dirty state, saving, autosave | `docs/07-undo-redo-and-saving.md` |
| Writing tests, sample files | `docs/08-testing.md` |
| Malformed/encrypted/huge files, security, licensing | `docs/09-security-licensing-edge-cases.md` |
| What to build next | `docs/10-build-plan.md` |
| Why something is designed the way it is; recording a new or changed decision | `docs/11-decisions.md` |

## Working style for Claude Code in this repo

- Before a feature: state the plan in 3–6 bullets, name the files you'll touch, then implement.
- After a feature: run `pytest -q` and `ruff check`, then tell the developer how to try it by hand.
- At the end of a session: update **Current status** at the top of this file (keep it to ~5 lines; history lives in git).
- When a PyMuPDF behavior is uncertain, write a 10-line throwaway script in `scratch/` to confirm it rather than guessing. (`scratch/` is git-ignored.) Once the code relies on that behavior, turn the script into a test in `tests/pymupdf_behavior/` (one small test per behavior, named after what it proves) and mark the line in docs/04 with ✅ and the test name. That way a PyMuPDF upgrade that changes the behavior fails a test instead of breaking the app quietly.
- Prefer adding a test fixture PDF over mocking PyMuPDF.
