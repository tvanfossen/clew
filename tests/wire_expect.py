# SPDX-License-Identifier: MIT
## @brief Independent reimplementation of the MCP wire transform, for tests to compare against.
## @version 1
"""What the MCP boundary is ALLOWED to do to an R2 payload, written out separately.

Two transforms are sanctioned at the JSON boundary and nowhere else:

  1. a tuple-valued field becomes a JSON array (JSON has no tuple; gh#8's
     `implementors` is one such field), and
  2. a ROW — a dict appearing inside a list — omits fields carrying no value,
     because a neighbour row's `call` and `key` variants populate disjoint halves
     of one dataclass and 54% of a measured call row's fields were null by kind.

Everything else is drift: no field may be added, renamed, re-valued, or dropped
from the ENVELOPE.

This module deliberately does NOT import `tools_query._prune_rows`. The parity
tests exist to catch the wire layer changing, and a test that reuses the code
under test to compute its own expectation moves both sides together and asserts
nothing. It is a second implementation on purpose; if the two disagree, one of
them is wrong and that is the finding.
"""

from __future__ import annotations

from typing import Any

## Names whose `'unknown'` means "not determined" and is therefore elided. Written out
## HERE independently rather than imported from `wire`, on the same reasoning as the rest
## of this module: a reference that imports the code under test moves with it.
##
## Both are `TEXT NOT NULL DEFAULT 'unknown'` columns, so they cannot be null and record
## "undetermined" as a literal. Without this, the wire kept two uninformative fields and
## elided `crosses_thread = NULL`, which is informative when known — exactly inverted.
UNKNOWN_MEANS_ABSENT = frozenset({"dispatch_mode", "edge_kind"})


## @brief True when a value carries nothing a consumer could read.
## @param name Field name, for the `'unknown'`-means-absent exceptions.
## @param value Any already-serialized value.
## @return True for None, an empty tuple/list/str, and a no-information 'unknown'.
## @version 2
def absent(name: str, value: Any) -> bool:
    """`False` and `0` are NOT absent. `crosses_thread: false` is a measurement —
    "this edge stays on one thread" — and is a different claim from the field not
    being there at all.

    `'unknown'` is elided only for the two named fields. `lock_kind` also has an
    `'unknown'` member and there it IS informative: "a lock whose type was not
    determined" differs from "no lock", so matching on the string alone would erase a
    real distinction.

    @brief Report whether a serialized value is absent rather than falsy.
    @return True when the value carries no information.
    @version 2
    """
    if value is None or (isinstance(value, tuple | list | str) and not value):
        return True
    return value == "unknown" and name in UNKNOWN_MEANS_ABSENT


## @brief The wire form of an R2 payload: tuples listed, row-level absences elided.
## @param obj Any structure produced by `dataclasses.asdict` over an R2 result.
## @return The structure as the MCP boundary is permitted to emit it.
## @version 1
def expected_wire(obj: Any) -> Any:
    """Recurses the envelope untouched (every key survives, absent or not) and
    prunes only dicts that appear as elements of a list.

    @brief Compute the sanctioned wire form of a payload.
    @return Transformed structure.
    @version 1
    """
    if isinstance(obj, dict):
        return {k: expected_wire(v) for k, v in obj.items()}
    if isinstance(obj, tuple | list):
        return [_expected_row(v) if isinstance(v, dict) else expected_wire(v) for v in obj]
    return obj


## @brief One row as the wire may emit it.
## @param row A dict that appeared as a list element.
## @return The row without its absent fields.
## @version 1
def _expected_row(row: dict[str, Any]) -> dict[str, Any]:
    """@brief Drop absent fields from a single row.
    @return Pruned row.
    @version 1
    """
    return {k: expected_wire(v) for k, v in row.items() if not absent(k, v)}
