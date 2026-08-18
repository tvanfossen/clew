# SPDX-License-Identifier: MIT
"""ONE serializer from an R2 dataclass to JSON.

A LEAF ON PURPOSE, and not owned by MCP. This module imports nothing from the package,
and the rule it enforces is authored by `query/models.py` rather than by any surface:
one dataclass serves both neighbour variants, so a field can be empty BY KIND. MCP is
today's only consumer — through `mcp_server/tools_query.py` and `mcp_server/emptiness.py`
— but it consumes the rule, it does not define it, so filing this under `mcp_server/`
would name the wrong owner.

Two transforms, both LOSSLESS, for every consumer:

  1. **A tuple field becomes a JSON array.** R2's dataclasses are frozen, so a
     multi-valued field is a tuple (gh#8's `implementors`); `json.loads` returns a
     list, so a tuple fails the round-trip contract.
  2. **A ROW omits fields carrying no value.** A `call` row's `strength`/`key_name`/
     `edge_kind`/`dispatch_mode`/`edge_triggered`/`crosses_thread`/`to_thread` are
     empty BY KIND. NULL AND ABSENT SAY DIFFERENT THINGS — null reads as "measured,
     found nothing", absent as "does not apply here" — and the tool descriptions
     promise that distinction. Measured on eight random real symbols: **54% of a call
     row's fields were null**; eliding took the mean row 292 B → 135 B and the mean
     dossier 2,209 B → 1,275 B.

Elision is NOT confined to the surface that asks for it. It was written that way first
and rejected: the reasoning had been borrowed from `RESPONSE_BUDGET_BYTES`, where
confinement is right because that cap is LOSSY. Elision drops nothing, so a second
payload shape bought only the cost of per-surface field access.

  * A **row** is a dict inside a LIST. Its absent fields go.
  * The **envelope** keeps every key — a consumer reads it key by key, so
    `requirements: []` must be present to read as "none".
  * `False`/`0` are never elided: `crosses_thread: false` is a measurement.

@brief The single R2-dataclass-to-JSON serializer.
@version 2
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

## Fields whose registered `'unknown'` member means "not determined", spelled out by
## NAME rather than matched on the string.
##
## These columns are `TEXT NOT NULL DEFAULT 'unknown'`, so unlike a nullable field they
## can never BE null — the pipeline records "undetermined" as a literal. That put the
## wire exactly backwards: `crosses_thread = NULL` (a possible thread crossing nobody
## could determine) was elided and read as "does not apply", while
## `dispatch_mode = 'unknown'` and `edge_kind = 'unknown'` were kept and read as
## measurements. The two uninformative fields were presented as facts and the
## informative one as inapplicable.
##
## Eliding them here restores one rule: a field is present only when it says something.
## Both view surfaces already discarded these two by hand
## (`k.dispatch_mode !== "unknown" ? … : null`), so this moves an existing convention to
## the one place it belongs instead of leaving it duplicated in two JavaScript files.
##
## Matched by field name, NOT by the string: `lock_kind` also has an `'unknown'` member
## and there it is informative — "a lock whose type was not determined" is a different
## claim from "no lock". A blanket string rule would erase that.
_UNKNOWN_MEANS_ABSENT = frozenset({"dispatch_mode", "edge_kind"})


## @brief True when a value carries nothing a consumer could read.
## @param name The field's name, for the `'unknown'`-means-absent exceptions.
## @param value Any already-serialized value.
## @return True for None, an empty tuple/list/str, and a no-information 'unknown'.
## @version 2
## @dg_internal
def _absent(name: str, value: Any) -> bool:
    """`False` and `0` are NOT absent — `crosses_thread: false` is a measurement.

    @brief Report whether a value is absent rather than merely falsy.
    @return True when the value carries no information.
    @version 2
    """
    if value is None or (isinstance(value, tuple | list | str) and not value):
        return True
    return value == "unknown" and name in _UNKNOWN_MEANS_ABSENT


## @brief `asdict` dict_factory that turns tuple-valued fields into lists.
## @param pairs (field name, already-recursed value) pairs for one dataclass.
## @return Plain dict with every tuple value converted to a list.
## @version 1
## @dg_internal
def _listed(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """@brief Convert tuple fields to lists while serializing a dataclass.
    @return JSON-safe dict for one dataclass.
    @version 1
    """
    return {name: list(value) if isinstance(value, tuple) else value for name, value in pairs}


## @brief One row with its absent fields removed, recursing into nested rows.
## @param row A dict that appeared as an element of a list.
## @return The row without None/empty-sequence fields.
## @version 3
## @dg_internal
def _pruned_row(row: dict[str, Any]) -> dict[str, Any]:
    """Split out from `_prune_rows` to name the rule: this is what "a row" means on
    the wire.

    @brief Remove absent fields and internal-only keys from a single row.
    @return Pruned row.
    @version 4
    """
    return {
        k: _prune_rows(v) for k, v in row.items() if k not in _INTERNAL_ONLY and not _absent(k, v)
    }


## INTERNAL DATABASE ROW IDS, STRIPPED AT THE BOUNDARY (gh#1's sibling defect). `rowid` is an
## opaque integer published beside `line_start` and `line_end`, which ARE locations, and it repeats
## inside every `callers`/`callees` row — 15 occurrences in one measured dossier reply, each one an
## integer beside a symbol name that has no line number of its own. That is exactly the slot a
## reader fills with "line".
##
## IT PRODUCED A FABRICATED CITATION IN A GRADED ANSWER. An index-arm run published
## `programs/ssl/ssl_pthread_server.c:2244` as a source location; the file is 484 lines and 2244
## was a rowid. The answer even hedged "per index rowid", so the model half-knew and wrote it
## anyway — which makes this a payload-shape defect, not a model slip.
##
## NOTHING ACCEPTS ONE AS INPUT. `dossier` takes a `subject` name and `qualified` for
## disambiguation; there is no rowid-keyed call anywhere on the surface. `models.py` described it
## as riding along "as a convenience for re-lookup" — a re-lookup that does not exist.
##
## STRIPPED HERE, NOT REMOVED FROM THE DATACLASSES. The Python API is a separate contract and
## internal code joins on these ids; this is the one boundary every served payload crosses.
_INTERNAL_ONLY = frozenset({"rowid"})


## @brief Prune absent fields from ROWS (dicts inside a list), leaving the envelope whole.
## @param obj Any already-serialized wire structure.
## @return The same structure with each list-of-dicts row pruned.
## @version 2
## @dg_internal
def _prune_rows(obj: Any) -> Any:
    """Row elision throughout, plus internal-only keys dropped at EVERY level — a `rowid` is
    equally misleading on an envelope and inside a row, so unlike elision it is not row-scoped.

    @brief Apply row-level elision and strip internal-only keys.
    @return Structure with rows pruned, internal ids gone, and the envelope intact.
    @version 3
    """
    if isinstance(obj, dict):
        return {k: _prune_rows(v) for k, v in obj.items() if k not in _INTERNAL_ONLY}
    if isinstance(obj, list):
        return [_pruned_row(v) if isinstance(v, dict) else _prune_rows(v) for v in obj]
    return obj


## @brief Serialize one R2 dataclass (an ENVELOPE) to its JSON wire form.
## @param obj Dataclass instance, or None.
## @return dict for a dataclass, None when obj is None.
## @version 1
## @req REQ-DDB-QUERY-001
def one(obj: Any) -> dict[str, Any] | None:
    """The object itself is treated as an envelope — every one of its own keys
    survives — while rows nested inside it are pruned.

    @brief Wire form of a single dataclass result.
    @return Serialized dict, or None.
    @version 1
    """
    return None if obj is None else _prune_rows(asdict(obj, dict_factory=_listed))


## @brief Drop named ENVELOPE keys that carry nothing, in place.
## @param payload A serialized envelope, or None.
## @param keys The envelope keys eligible for elision.
## @return The same payload, with the absent named keys removed.
## @version 1
## @req REQ-DDB-QUERY-001
def prune_absent_keys(
    payload: dict[str, Any] | None, keys: tuple[str, ...]
) -> dict[str, Any] | None:
    """`one()` deliberately keeps every key of the envelope itself, because a consumer
    reading a known shape should not have to ask whether a field it always saw is
    missing this time. That guarantee is worth keeping for the fields that had it — so
    elision is OPT-IN and NAMED, never blanket.

    Applied to fields added later, whose absence is the common case and whose presence
    is the news: a dossier for a function that opens no critical section should not
    spend a key saying so on every call.

    Uses the same `_absent` rule as row pruning, so `false` and `0` survive — a
    `truncated: false` inside a body excerpt is a measurement, and an added field whose
    value is `0` is an answer.

    @brief Elide the named absent keys from one envelope.
    @return The payload, mutated.
    @version 1
    """
    if payload is None:
        return None
    for key in keys:
        if key in payload and _absent(key, payload[key]):
            del payload[key]
    return payload


## @brief Serialize an iterable of R2 dataclasses as ROWS.
## @param items Iterable of dataclass instances.
## @return List of pruned row dicts.
## @version 1
## @req REQ-DDB-QUERY-001
def rows(items: Any) -> list[dict[str, Any]]:
    """These ARE rows — they are about to sit in a list — so each one is pruned.
    Calling `one` per element instead would treat each as an envelope and prune
    nothing, which is the mistake the parity test caught.

    @brief Wire form of a list of dataclass results.
    @return List of row dicts.
    @version 1
    """
    return [_pruned_row(asdict(i, dict_factory=_listed)) for i in items]
