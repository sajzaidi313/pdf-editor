# 11: Decisions Log

One line per decision: **what** was decided, **why**, and **where** the details live. Add a line whenever a decision is made or changed; never delete old lines. If a decision is reversed, add a new line that says so and points back to the old one.

Why keep this: the other docs say what the design *is*; this file says *why it changed*, which is what you'll be asked about in an interview and what you'll have forgotten in three months.

| Date | Decision | Why | Details |
|---|---|---|---|
| 2026-11 | GUI: PySide6 (Qt 6) | Mature, LGPL, `QGraphicsView` and `QUndoStack` built in | CLAUDE.md, tech stack |
| 2026-11 | PDF engine: PyMuPDF, project licensed AGPL-3.0 | One library for rendering, annotations, redaction, forms, page ops; AGPL is fine for a public portfolio project | doc 09 §2 |
| 2026-11 | Undo: hybrid command pattern (inverse where cheap, whole-document snapshot otherwise), not MuPDF's journal | Journal fails for `insert_pdf` and needs every mutation wrapped | doc 07 §2–3 |
| 2026-11 | Scene units = PDF points; zoom = view transform | Instant zoom feedback; layout never changes on zoom | doc 05 §1 |
| 2026-11 | Text editing limited to "replace one span", no reflow | PDFs have no layout engine; honest scope | doc 03 §7, doc 06 C4 |
| 2026-11-12 | Background rendering in a separate process, not threads | PyMuPDF doesn't support Python threads; a process can also be killed on timeout | doc 05 §3.1 |
| 2026-11-12 | Annotations identified by a UUID in `/NM`, not by xref | Redo recreates objects with new xrefs; renumbering saves change xrefs | doc 02 §2.2 |
| 2026-11-12 | Dirty = undo stack not clean **or** `unsaved_outside_history` | `QUndoStack.clear()` marks the stack clean | doc 07 §6 |
| 2026-11-12 | Full saves re-apply encryption; no autosave for encrypted docs | Full saves and `tobytes()` produce decrypted output | doc 07 §5.4, §7 |
| 2026-11-12 | Redaction removes only line art fully covered by default | `REMOVE_IF_TOUCHED` can erase whole table grids | doc 06 R3 |
| 2026-11-12 | Text replacement (C4) forces a full save | Incremental saves keep the old text in earlier revisions | doc 06 C4 |
| 2026-11-12 | Consecutive undo snapshots share bytes; spill-to-disk only if needed | A 50 MB doc costs ~100 MB per snapshot command | doc 07 §3 |
| 2026-11-12 | Links open only for `http`/`https`/`mailto` | `file:` links can launch programs | doc 05 §9 |
| 2026-11-12 | PyMuPDF pinned to `>=2.1,<2.2`; relied-on behaviors get tests | Verified facts must survive upgrades | doc 08 §3 |
| 2026-11-12 | Added V12, V13, V15, V16, A12 (P1) and V14, T1, T2 (P2); Measure tool A11 raised to P1. Stamps considered and left out | Cheap reading/study wins; engineering use (measure, compare) fits the target users | doc 01 §3, doc 06 §X |
| 2026-11-12 | PySide6 pinned to `>=6.12,<6.13` | Same "upgrade deliberately" policy as the PyMuPDF pin; 6.12.0 was current when M0 was built | `pyproject.toml` |
| 2026-11-12 | CI tests Python 3.11 and 3.14 (doc 08 first said 3.11/3.12) | Oldest supported version plus the one used for development, so CI covers what actually runs locally | doc 08 §7 |
| 2026-11-12 | CI runs pyright from M0; the nightly slow-test job waits until M3 | "Definition of done" requires pyright clean; a pytest run that selects zero tests fails, and there are no slow tests before M3 | doc 08 §7, doc 10 M0/M3 |
| 2026-11-12 | Fixture PDFs are committed, generated with `no_new_id=True`, and marked `binary` in `.gitattributes` | CI needs them without a build step; identical bytes on every regeneration keep git diffs honest; git on Windows would otherwise convert line endings inside small PDFs | `tests/fixtures/README.md` |
| 2026-11-12 | `render/render_process.py` exists as an empty placeholder from M0 | The no-Qt test can check it from day one instead of being edited in M3 | doc 08 §3, Architecture rules |
| 2026-11-12 | Build backend: setuptools; type checker installed as `pyright[nodejs]` | Most common default; the extra bundles Node.js so pyright's first run doesn't download it | `pyproject.toml` |
| 2026-11-12 | M1: a password-protected file opens "locked"; `model.authenticate()` returns True/False; `EncryptedError` only when pages are asked for while locked. The model reads `doc.needs_pass` once and never again | A wrong password is a normal event, not a failure. Reading `needs_pass` (or a wrong `authenticate()`) after the right password silently breaks decryption in PyMuPDF 2.1 | doc 04 §1, doc 02 §2.1 and §7 |
| 2026-11-12 | M1: `DocumentModel.open()` rejects anything where `doc.is_pdf` is false, and a failed open keeps the current document | MuPDF opens HTML and images saved as `.pdf` without an error; an error should never cost the user the document they were reading | doc 04 §1, doc 09 §3 |
| 2026-11-12 | M1 limitation: a locked file replaces the open document before the password is known, so cancelling the prompt leaves an empty window | Keeps `open()` one simple step; revisit in M4 together with the unsaved-changes prompt | doc 09 §3 |
| 2026-11-12 | 100% zoom = real paper size: view scale = zoom × logical DPI / 72 (doc 02 used to say zoom 1.0 = 72 dpi) | Matches Acrobat and browsers; at 72 dpi a page looks 25% too small on a standard Windows screen | doc 05 §7, doc 02 §2.3 |
| 2026-11-12 | Current page = the page with the largest visible share of itself, ties to the earlier page. Reverses "the page under the viewport's center line" | With several whole pages in view, "go to page 5" showed page 5 at the top but reported page 6 | doc 05 §2 |
| 2026-11-12 | Page box: a page label wins (ignoring upper/lower case), then the text is tried as a page number | Readers type what is printed on the page; the box shows "iii (3 of 8)" so both numbers stay visible | doc 08 §3 Extras, `core/document.py` |
| 2026-11-12 | M1 also builds fit page (Ctrl+1), 100% (Ctrl+0) and Home/End, which the M1 task list had left out | The MVP table says V3 and V5 are complete at M1, and no later milestone picks these up | doc 10 M1, doc 01 §5 |
| 2026-11-12 | Until tiling (M3), page images are capped at 4096 px on the longer side; the real device pixel ratio is passed to the renderer from M1 on | A Letter page at 800% is 93 MB; the cap also protects against huge pages. Passing the ratio is one argument, and M3 keeps the cache and tiling parts of HiDPI | doc 05 §7, `core/geometry.py` |
| 2026-11-12 | `--self-test` uses its own PDF in `src/pdfeditor/resources/`, generated by `make_fixtures.py`, and touches no window, dialog or setting | Files under `tests/` are not part of the app; a dialog would hang CI; the user's recent-files list must not change | `self_test.py`, doc 08 §7 |
| 2026-11-12 | First packaged build: PyInstaller one-folder with a console; `pyinstaller` lives in the `dev` extra; CI builds and self-tests it on all three systems with Python 3.14 | A console shows the self-test's output and tracebacks in CI logs; M11 switches to a windowed app. One install command stays enough for a beginner | `packaging/pdfeditor.spec`, `.github/workflows/ci.yml` |
| 2026-11-12 | `encrypted_user_pw.pdf` is written only when missing (exception to the byte-identical fixtures rule above) | AES-256 uses fresh random values on every save, so its bytes can never repeat | `tests/fixtures/README.md` |
| 2026-11-12 | Dropped files are handled by the main window (the page view refuses drops) and opened just after the drop event | One place for every way of opening a file; an error dialog inside the drop event would freeze the program the file was dragged from | `ui/main_window.py` |
| 2026-11-12 | Left out of M1 on purpose: a log file, an error placeholder for a page that fails to render, the owner-restrictions banner | No milestone lists the log file yet (suggest M11); the placeholder belongs to the render process (M3); the banner needs editing to exist (M4) | doc 02 §7, doc 09 §3 |
