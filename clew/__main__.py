# SPDX-License-Identifier: MIT
"""Module entry point: `python -m clew`.

Defers to `cli.main`. Exists so a caller can run the package via
`python -m clew ...` without needing a wrapper script.

@brief Module entry-point shim.
@version 1
"""

from .cli import main

if __name__ == "__main__":
    main()
