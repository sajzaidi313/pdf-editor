# PDF Editor

A desktop PDF editor written in Python with PySide6 (Qt 6) and PyMuPDF.
It is a learning project, built one milestone at a time; the plan is in
`docs/10-build-plan.md`.

**Status:** M2 (view, find and copy). The app opens PDFs, including
password-protected ones, and shows all pages with zoom and page navigation.
A sidebar has page thumbnails and the outline (bookmarks). You can search
the text and select and copy it. Editing starts in later milestones.

## Setup (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

## Run

```
python -m pdfeditor
python -m pdfeditor tests\fixtures\simple_text.pdf
```

The second form opens a file straight away. You can also use File > Open,
File > Open Recent, or drag a PDF onto the window.

| Action | Keys |
|---|---|
| Open | Ctrl+O |
| Zoom in / out | Ctrl+= / Ctrl+-, or Ctrl + mouse wheel |
| 100% / fit page / fit width | Ctrl+0 / Ctrl+1 / Ctrl+2 |
| Next / previous page | PgDn / PgUp |
| First / last page | Home / End |
| Go to a page | type a page number or page label in the Page box, then Enter; or click a thumbnail or an outline entry in the sidebar |
| Show / hide the sidebar | F4 |
| Find | Ctrl+F, type, then Enter / Shift+Enter (or F3 / Shift+F3) for the next / previous match; Esc closes the find bar |
| Select text | drag across it; double-click a word; triple-click a line |
| Copy the selected text | Ctrl+C |

## Build a stand-alone app

```
pyinstaller packaging/pdfeditor.spec --noconfirm
dist\pdfeditor\pdfeditor.exe --self-test
```

The first command writes the app into `dist\pdfeditor\`; that folder runs on
a computer without Python. The second checks the build: it prints
`self-test OK` when the packaged app can open and draw a PDF.

## Develop

```
pytest -q                  # run the tests
ruff check src tests       # lint
ruff format src tests      # auto-format
pyright                    # type check
```

## License

AGPL-3.0, see `LICENSE`. The app uses PyMuPDF, which is AGPL-licensed; details
are in `docs/09-security-licensing-edge-cases.md`.
