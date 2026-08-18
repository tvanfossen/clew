# SPDX-License-Identifier: MIT
"""Tests for the shared R2→JSON serializer.

ASSERTED DIRECTLY, on synthetic dataclasses rather than through a surface. Two modules
call `wire` (`mcp_server/tools_query.py`, `mcp_server/emptiness.py`), and testing it
only through them would pin whatever those two happen to pass rather than the rule
itself. `tests/wire_expect.py` carries a deliberately INDEPENDENT reimplementation for
the same reason — a test that reuses the code under test cannot see that code change.

The distinctions being pinned are all ones that were argued about and could
plausibly be "simplified" away later:

  * a row is a dict inside a LIST; the envelope is not a row;
  * `False` and `0` survive, because `crosses_thread: false` is a measurement;
  * a tuple becomes a list, because `json.loads` cannot return a tuple.

@brief Tests for clew.wire.
@version 2
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from clew import wire


## @brief A neighbour-shaped row: some fields populated, some empty by kind.
## @version 1
@dataclass(frozen=True)
class _Row:
    """Mirrors the real `CallEdge` split — a `call` row leaves the dataflow half
    empty, a `key` row the reverse.

    @brief Synthetic neighbour row.
    @version 1
    """

    name: str = "callee"
    ## `line_start`, not `rowid`. This field is only ever standing in for "an int field that
    ## carries a value", and `rowid` is now STRIPPED at the wire boundary (an opaque internal id
    ## published beside real line numbers produced a fabricated `file:2244` citation in a graded
    ## answer). Using a stripped field here would make three tests about pruning, falsy values and
    ## the rows helper fail for a reason that has nothing to do with any of them.
    line_start: int = 7
    strength: str | None = None
    crosses_thread: bool | None = None
    implementors: tuple[str, ...] = ()


## @brief A dataflow-shaped row carrying the enum fields whose 'unknown' means absent.
## @version 1
@dataclass(frozen=True)
class _KeyRow:
    """Mirrors the `key` half of a neighbour row. `dispatch_mode` and `edge_kind` are
    `TEXT NOT NULL DEFAULT 'unknown'` in the real schema, so they arrive as literals
    rather than nulls — which is the whole reason the elision rule needs a name list.
    `lock_kind` is the control: same `'unknown'` string, informative there.

    @brief Synthetic dataflow row.
    @version 1
    """

    name: str = "publish"
    dispatch_mode: str = "unknown"
    edge_kind: str = "unknown"
    lock_kind: str = "unknown"
    crosses_thread: bool | None = None


## @brief An envelope holding rows, like a Dossier.
## @version 1
@dataclass(frozen=True)
class _Envelope:
    """@brief Synthetic envelope with row lists and empty scalars.
    @version 1
    """

    subject: str = "fn"
    brief: str | None = None
    threads: tuple[str, ...] = ()
    callers: list[_Row] = field(default_factory=list)


## @brief The envelope keeps every key, even the empty ones.
## @return None.
## @version 1
def test_envelope_keys_all_survive() -> None:
    """A consumer reads the envelope key by key, so `threads: []` must be PRESENT to
    be read as "none". This is the distinction that broke when elision was applied
    universally, and the viewer/MCP field-parity test caught it."""
    out = wire.one(_Envelope())
    assert out is not None
    assert set(out) == {"subject", "brief", "threads", "callers"}
    assert out["brief"] is None
    assert out["threads"] == []
    assert out["callers"] == []


## @brief A row inside a list drops the fields carrying nothing.
## @return None.
## @version 1
def test_rows_inside_an_envelope_are_pruned() -> None:
    """The measured saving: 54% of a real call row's fields were null by kind."""
    out = wire.one(_Envelope(callers=[_Row()]))
    assert out is not None
    assert out["callers"] == [{"name": "callee", "line_start": 7}]


## @brief A false or zero value is kept, not treated as absent.
## @return None.
## @version 1
def test_false_and_zero_are_measurements_not_absences() -> None:
    """`crosses_thread: false` says "this edge stays on one thread", which is a
    different claim from the field being missing ("nobody looked"). Eliding falsy
    values instead of absent ones would silently turn the former into the latter."""
    out = wire.one(_Envelope(callers=[_Row(crosses_thread=False, line_start=0)]))
    assert out is not None
    row = out["callers"][0]
    assert row["crosses_thread"] is False
    assert row["line_start"] == 0
    assert "strength" not in row


## @brief An undetermined enum is absent, and a determined one is present.
## @return None.
## @version 1
def test_unknown_enums_are_elided_but_only_the_named_ones() -> None:
    """A REGRESSION TEST for an inversion this module itself introduced.

    `dispatch_mode` and `edge_kind` are `TEXT NOT NULL DEFAULT 'unknown'`, so unlike a
    nullable column they cannot BE null — the pipeline records "undetermined" as a
    literal string. Row elision therefore kept those two while dropping
    `crosses_thread = NULL`, which is informative when known. The result was exactly
    backwards: the two fields that say nothing were presented as measurements, and the
    one that would matter was presented as not-applicable, which the shared `rows`
    description tells a model to read as "the question does not apply".

    `lock_kind` is the control. It also has an `'unknown'` member and there it IS
    informative — "a lock whose type was not determined" is a different claim from "no
    lock" — so the rule is keyed on FIELD NAME, and matching the string alone would
    erase that."""
    row = {
        "name": "publish",
        "dispatch_mode": "unknown",
        "edge_kind": "unknown",
        "lock_kind": "unknown",
        "crosses_thread": False,
    }
    out = wire.one(_Envelope(callers=[]))
    assert out is not None  # envelope path still intact

    pruned = wire.rows([_KeyRow(**row)])[0]
    assert "dispatch_mode" not in pruned, "an undetermined dispatch_mode must not ship"
    assert "edge_kind" not in pruned, "an undetermined edge_kind must not ship"
    assert pruned["lock_kind"] == "unknown", (
        "lock_kind='unknown' is a measurement — a lock of undetermined type is not no lock"
    )
    assert pruned["crosses_thread"] is False, "a measured non-crossing must still ship"

    ## And a DETERMINED value of the same field must survive.
    determined = wire.rows([_KeyRow(**{**row, "dispatch_mode": "keyed"})])[0]
    assert determined["dispatch_mode"] == "keyed"


## @brief A tuple field becomes a JSON array so the round trip holds.
## @return None.
## @version 1
def test_tuples_become_lists() -> None:
    """R2's dataclasses are frozen, so a multi-valued field is a tuple; `json.loads`
    returns a list, so a tuple on the wire fails equality with its own round trip."""
    out = wire.one(_Envelope(callers=[_Row(implementors=("Derived::run", "Other::run"))]))
    assert out is not None
    assert out["callers"][0]["implementors"] == ["Derived::run", "Other::run"]
    assert json.loads(json.dumps(out)) == out


## @brief `rows` prunes each element; `one` per element would not.
## @return None.
## @version 1
def test_rows_helper_treats_its_items_as_rows() -> None:
    """The two entry points differ ONLY in whether the top level is a row, and calling
    the wrong one is a real mistake that the MCP parity test caught: `one` per element
    treats each as an envelope and prunes nothing."""
    assert wire.rows([_Row()]) == [{"name": "callee", "line_start": 7}]
    assert wire.one(_Row()) == {
        "name": "callee",
        "line_start": 7,
        "strength": None,
        "crosses_thread": None,
        "implementors": [],
    }


## @brief None in, None out.
## @return None.
## @version 1
def test_none_serializes_to_none() -> None:
    """Every MCP wrapper over an optional R2 result depends on this: a missing symbol
    is a null payload, not an exception and not an empty dict."""
    assert wire.one(None) is None


## @brief Internal database row ids must never reach a served payload.
## @return None.
## @version 1
def test_internal_row_ids_are_stripped_from_envelope_and_rows() -> None:
    """A GRADED ANSWER PUBLISHED ONE AS A SOURCE LOCATION. An index-arm run wrote
    `programs/ssl/ssl_pthread_server.c:2244` as a citation; the file is 484 lines and 2244 was a
    `rowid`. The answer even hedged "per index rowid", so the model half-knew and wrote it anyway —
    which makes this a payload-shape defect rather than a model slip.

    THE SHAPE IS WHY. `rowid` sat beside `line_start` and `line_end`, which ARE locations, and
    repeated inside every `callers`/`callees` row — 15 occurrences in one measured reply, each an
    integer next to a symbol name with no line number of its own. That is precisely the slot a
    reader fills with "line". Nothing on the tool surface accepts a rowid as input, so it bought
    nothing in exchange.

    BOTH LEVELS, which is what distinguishes this from elision. Elision is row-scoped because an
    envelope key must be present to read as "none"; a `rowid` misleads equally in either place.

    @brief `rowid` is absent from both the envelope and its rows.
    @return None.
    @version 1
    """

    ## THE FIXTURE MUST ACTUALLY CARRY A rowid, and the first version of this test did not — the
    ## shared `_Row` had been renamed to `line_start`, so `"rowid" not in row` was trivially true
    ## and emptying `_INTERNAL_ONLY` left the test GREEN. The mutation control caught it. A fixture
    ## that matches the detector rather than the world is this repo's standing failure.
    @dataclass(frozen=True)
    class _IdBearing:
        """@brief A row and envelope that really do carry an internal id. @version 1"""

        rowid: int = 99
        name: str = "callee"
        line_start: int = 7

    @dataclass(frozen=True)
    class _IdEnvelope:
        """@brief Envelope carrying an id of its own plus id-bearing rows. @version 1"""

        rowid: int = 42
        subject: str = "thing"
        callers: tuple[_IdBearing, ...] = (_IdBearing(),)

    out = wire.one(_IdEnvelope())
    assert out is not None
    assert "rowid" not in out, "an internal row id must not be served on the envelope"
    assert "rowid" not in out["callers"][0], "nor inside a neighbour row"
    ## A strip that emptied everything would satisfy both assertions above.
    assert out["subject"] == "thing", "stripping must not remove real envelope fields"
    assert out["callers"][0]["name"] == "callee", "nor real row fields"
    assert out["callers"][0]["line_start"] == 7, "a genuine int field must survive"
