"""Entry point for `python -m pdfeditor`.

Python runs this file when a package is started with `-m`. It is tiny on
purpose: the real startup code lives in app.py, where tests can import it.
"""

import sys

from pdfeditor.app import main

# `__name__` is "__main__" only when this file is run, not when it is imported.
if __name__ == "__main__":
    # sys.exit hands main()'s return value to the operating system as the
    # program's exit code (0 means "finished without errors").
    sys.exit(main())
