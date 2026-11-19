# SPDX-License-Identifier: MIT
"""A Sphinx domain that puts every symbol section in the site's objects.inv (P5, S8; 2.0.0).

OWNER-APPROVED 2026-11-17 (standards research, S8). `objects.inv` is what intersphinx,
`sphobjinv` and documentation search tools read to turn a name into a URL; the site's held only
`std:doc` and `std:label`, so no tool could resolve a function to its section. The symbol pages
are raw HTML (`symbols.symbol_pages`), so there is no directive to hang an object on: the build
writes `_clew_objects.json` beside the sources and this domain reports its rows.

ONE OBJECT PER SECTION, named `<file>::<name>`, which is unique. The BARE NAME is added only where
one file defines it: a bare `helper` defined in two files would resolve to whichever was listed
first, which is a wrong link presented as a right one.

@brief The `clew` Sphinx domain: symbol sections as inventory objects.
@version 1
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sphinx.domains import Domain, ObjType

## The file the build writes into the Sphinx source directory.
OBJECTS_FILE = "_clew_objects.json"


## @brief The `clew` domain: objects only, read from the build's list.
## @version 1
class ClewDomain(Domain):
    """@brief Symbol sections as inventory objects.
    @version 1
    """

    name = "clew"
    label = "clew"
    object_types = {"function": ObjType("function", "func")}

    ## @brief Every inventory object: (name, display name, type, page, anchor, priority).
    ## @return The objects.
    ## @version 1
    ## @req REQ-DDB-WIKI-025
    def get_objects(self) -> Any:
        """PRIORITY 1, Sphinx's "important" (the default for an object an index should list);
        a bare alias is priority 2, "unimportant", so a search ranks the qualified form first.

        @brief Yield objects.
        @return Objects.
        """
        rows = _rows(Path(self.env.srcdir) / OBJECTS_FILE)
        once = Counter(r["name"] for r in rows)
        for r in rows:
            yield (f"{r['file']}::{r['name']}", r["name"], "function", r["page"], r["anchor"], 1)
            if once[r["name"]] == 1:
                yield (r["name"], r["name"], "function", r["page"], r["anchor"], 2)

    ## @brief Nothing to forget: the objects are the build's list, not parsed state.
    ## @param docname A document being re-read.
    ## @return None.
    ## @version 1
    ## @utility
    def clear_doc(self, docname: str) -> None:
        """@brief No per-document state. @return None."""


## @brief The build's object rows, or none when it wrote no list.
## @param path The list.
## @return Rows.
## @version 1
## @utility
def _rows(path: Path) -> list[dict[str, str]]:
    """@brief Read the list. @return Rows."""
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")))


## @brief Register the domain.
## @param app The Sphinx application.
## @return Extension metadata.
## @version 1
## @req REQ-DDB-WIKI-025
def setup(app: Any) -> dict[str, Any]:
    """@brief Sphinx entry point. @return Metadata."""
    app.add_domain(ClewDomain)
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}
