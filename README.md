# PDF Editor

A desktop PDF editor written in Python with PySide6 (Qt 6) and PyMuPDF.
It is a learning project, built one milestone at a time; the plan is in
`docs/10-build-plan.md`.

**Status:** M0 (project skeleton). The app opens an empty window.

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
```

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
