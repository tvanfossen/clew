# SPDX-License-Identifier: MIT
"""Declared failure modes: a catalog entry's `failure_modes`, and the `@fails_when` ids tests name.

2.2 (owner Q/A 2026-11-25, the test-flowchart design pass). A requirement declares the ways it
can fail, each an id with a one-line meaning; a test names the modes it guards with
`@fails_when ID`. The ids are defined ONCE, in the catalog, so the index, the gate and the wiki's
flowchart read the same set.

ONE PARSER, TWO USERS: the index (`requirements.py`) and the gate (`clew.guard`) both read a
catalog entry through `modes_of`, so a shape one accepts the other cannot refuse.

@brief Parse declared failure modes and `@fails_when` references.
@version 1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

## The catalog field.
FIELD = "failure_modes"
## The tag a test names a mode with.
TAG = "fails_when"
## `@fails_when ID` / `\fails_when ID`; an id ends at whitespace or a markup boundary.
_REF = re.compile(r"[@\\]" + TAG + r"\s+([^\s<]+)")


## @brief One declared failure mode.
## @version 1
@dataclass(frozen=True)
class FailureMode:
    """@brief A mode's requirement, id and meaning. @version 1"""

    req_id: str
    mode_id: str
    meaning: str


## @brief The failure modes one catalog entry declares.
## @param req_id The entry's requirement id.
## @param fields The entry's fields, as the catalog holds them.
## @return The modes, in the catalog's order; empty when the entry declares none.
## @version 1
## @req REQ-DDB-SCHEMA-006
def modes_of(req_id: str, fields: dict[str, Any]) -> list[FailureMode]:
    """A MAPPING OF ID TO MEANING, nothing else: a list or a scalar is refused by name, because a
    shape read loosely is how a declared mode ends up silently matching nothing.

    @brief Declared modes.
    @return Modes.
    """
    declared = fields.get(FIELD)
    if declared is None:
        return []
    if not isinstance(declared, dict):
        raise ValueError(
            f"{req_id}: `{FIELD}` must be a mapping of mode id to meaning, "
            f"got {type(declared).__name__}"
        )
    return [FailureMode(req_id, str(mode), str(meaning)) for mode, meaning in declared.items()]


## @brief The failure-mode ids a documentation text names with `@fails_when`.
## @param text Doc text, or None.
## @return The ids, in order.
## @version 1
## @utility
def fails_when_ids(text: str | None) -> list[str]:
    """@brief Referenced ids. @return Ids."""
    return [m.rstrip(".,;:") for m in _REF.findall(text or "")]
