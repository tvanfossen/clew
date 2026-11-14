# SPDX-License-Identifier: MIT
"""The wire-key manifest: every field the dossier and search replies can carry, generated.

1.3.1, Track 1. semver covers the MCP wire keys (docs/OVERVIEW.md, "What semver covers"), and
until now that promise was prose: nothing listed the keys, so nothing could notice one change. The
manifest is GENERATED from the dataclasses the replies serialize, plus the envelope keys the
payload layer adds, and committed as `docs/wire-keys.json`. A test regenerates it and compares,
so a renamed or removed field fails the gate and has to be either reverted or shipped with a
`WIRE_VERSION` decision — the review a covered change needs, made unavoidable.

Regenerate after a deliberate change:

    .venv/bin/python -m clew.query.wire_manifest > docs/wire-keys.json

FIELD NAMES AND DECLARED TYPES, NOT VALUES. An added field shows as a diff and is additive; a
removed or renamed one is the break the version exists for.

@brief Generate the wire-key manifest from the reply dataclasses.
@version 1
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from typing import Any

from ..code_text import CodeHit
from . import models
from .export import WIRE_VERSION

## The reply roots: what `dossier` and each `search` corpus serialize.
_ROOTS: tuple[type, ...] = (
    models.SubjectDossier,
    models.SymbolHit,
    models.ProseHit,
    CodeHit,
    models.FileEntry,
    models.DirectoryInventory,
    models.LockInventory,
    models.ThreadInventory,
    models.KconfigSpace,
)

## Keys the payload layer adds on top of the dataclass fields (`clew.query.payload`,
## `clew.query.export`). Listed by hand because they are not fields of any dataclass; the
## manifest test pins this list too, so adding one here is the act of covering it.
ENVELOPE_KEYS: tuple[str, ...] = (
    "subject",
    "subject_kind",
    "also",
    "chain",
    "depth_note",
    "ambiguous",
    "gate_definitions",
    "gate_definitions_limited",
    "callers_note",
    "candidates_limited",
    "kconfig_found",
    "gates_shared",
    "found",
    "note",
    "kind",
    "count",
    "results",
    "matched",
    "provenance",
    "inventory",
    "doc_scope",
    "wire_version",
    ## 1.3.7, opt-in compact shape: a neighbour list's groups and the reply's shared values.
    "rows",
    "edge_defaults",
    ## 1.3.9, compact shape: `detail` dropped because the body excerpt already carries it.
    "detail_in_body",
    ## 1.3.10: an over-cap batch names the subjects it did not answer.
    "not_answered",
    "not_answered_means",
)


## @brief The dataclass names a field's declared type mentions.
## @param annotation The field's type, as a string or an object.
## @return Names that are dataclasses in `models` (or CodeHit).
## @version 1
## @dg_internal
def _referenced(annotation: Any) -> list[type]:
    """@brief Resolve referenced dataclasses by name. @return The classes."""
    found: list[type] = []
    for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(annotation)):
        cls = getattr(models, word, None) if word != "CodeHit" else CodeHit
        if isinstance(cls, type) and dataclasses.is_dataclass(cls) and cls not in found:
            found.append(cls)
    return found


## @brief Every field of every dataclass reachable from the reply roots.
## @return The manifest: version, envelope keys, and {class: {field: declared type}}.
## @version 1
## @req REQ-DDB-QUERY-014
def wire_manifest() -> dict[str, Any]:
    """BREADTH-FIRST FROM THE ROOTS, so a nested dataclass (a caller row, a gate row) is covered
    by being reachable, not by being remembered.

    @brief Build the manifest.
    @return The manifest dict.
    @version 1
    """
    types: dict[str, dict[str, str]] = {}
    queue = list(_ROOTS)
    while queue:
        cls = queue.pop(0)
        if cls.__name__ in types:
            continue
        fields = dataclasses.fields(cls)
        types[cls.__name__] = {f.name: str(f.type) for f in fields}
        for f in fields:
            queue.extend(c for c in _referenced(f.type) if c.__name__ not in types)
    return {
        "wire_version": WIRE_VERSION,
        "envelope_keys": sorted(ENVELOPE_KEYS),
        "types": dict(sorted(types.items())),
    }


if __name__ == "__main__":
    json.dump(wire_manifest(), sys.stdout, indent=1, sort_keys=False)
    sys.stdout.write("\n")
