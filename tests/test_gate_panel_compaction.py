# SPDX-License-Identifier: MIT
"""154 GATE ROWS CARRYING 31 FILES' WORTH OF INFORMATION.

**MEASURED on the rebuilt mbedtls index.** `dossier("MBEDTLS_THREADING_C")` serves 154 gate rows
at **39,884 bytes**, and across all 154 rows:

    macro          1 distinct value   (MBEDTLS_THREADING_C)
    symbol         1 distinct value   (MBEDTLS_THREADING_C)
    form           1 distinct value   (if_expr)
    default_state  1 distinct value   (off)
    default_site   1 distinct value   (include/mbedtls/mbedtls_config.h:3787)
    file_path     31 distinct values

Five of six fields are byte-identical on every row. The panel repeats ~185 bytes of invariant
text 154 times.

**WHY BYTES HERE ARE WORTH MORE THAN THEY LOOK.** `cache_read` is 98% of all tokens this harness
spends — 3,470,671 against 62,559 output for the `index_only` arm — because every byte served
sits in the context and is re-read on each subsequent turn. A 40 KB reply at turn 3 of 20 costs
roughly 800 KB of `cache_read` on its own. Across the grid, gate panels are 11.8% of all
`dossier` reply bytes (`gates` 5.9%, `gated_by` 2.8%, `gate_definitions` 2.0%,
`gate_definitions_limited` 1.1%).

**NOTHING IS REMOVED, WHICH IS THE WHOLE POINT.** A cost win that drops evidence trades one axis
for the other, and the standing rule here is that a gain on one axis is only a gain if the other
holds. An invariant field is hoisted to the panel, so every value a reader could have read off a
row is still in the reply — once instead of 154 times. A field that VARIES across rows is never
hoisted.

**THE WIRE ONLY.** `KconfigGate` keeps every field, so the library API and the tests that read
`gates[0].default_state` are untouched. Same placement as the `found`/`kconfig_found`
reconciliation, for the same reason: the dataclass is right and the serialization was wasteful.

@brief Invariant gate fields are stated once, not per row.
@version 1
"""

from __future__ import annotations

import json

import pytest

from clew.mcp_server.tools_query import _compact_gate_panel


##
# @brief A gate row as the wire carries it.
# @version 1
def _row(path: str, line: int, **over: object) -> dict:
    row = {
        "symbol": "MBEDTLS_THREADING_C",
        "macro": "MBEDTLS_THREADING_C",
        "form": "if_expr",
        "file_path": path,
        "line": line,
        "end_line": line + 4,
        "origin": "undeclared",
        "default_state": "off",
        "default_site": "include/mbedtls/mbedtls_config.h:3787",
    }
    row.update(over)
    return row


## @brief An invariant field is stated once and dropped from the rows.
## @version 1
def test_invariant_fields_are_hoisted_off_the_rows() -> None:
    """RED BEFORE THE FIX: every row repeats five identical fields.

    Asserted on BOTH halves — the value is present at the panel level AND absent from the rows —
    because hoisting without dropping saves nothing and dropping without hoisting loses the
    value.
    """
    payload = {"gates": [_row("a.c", 10), _row("b.c", 20), _row("c.c", 30)]}

    out = _compact_gate_panel(payload)

    shared = out["gates_shared"]
    assert shared["macro"] == "MBEDTLS_THREADING_C"
    assert shared["default_state"] == "off"
    assert shared["default_site"] == "include/mbedtls/mbedtls_config.h:3787"
    for row in out["gates"]:
        for k in ("macro", "symbol", "form", "default_state", "default_site"):
            assert k not in row, f"{k} is invariant and must not repeat on every row: {row}"
        assert row["file_path"] and row["line"], "what VARIES must stay on the row"


## @brief A field that varies is never hoisted.
## @version 1
def test_a_varying_field_stays_on_the_rows() -> None:
    """THE BOUND, AND THE ONLY WAY THIS CAN LOSE INFORMATION. Two gate sites of one symbol can
    genuinely disagree — a macro `#define`d in one profile and `#undef`ed in another — and
    hoisting the majority value would state as settled a thing the index reports as varying.
    """
    payload = {"gates": [_row("a.c", 10), _row("b.c", 20, default_state="on")]}

    out = _compact_gate_panel(payload)

    assert "default_state" not in out.get("gates_shared", {}), (
        "a field with two values must not be hoisted to one"
    )
    assert {r.get("default_state") for r in out["gates"]} == {"off", "on"}, (
        "both values must survive on their own rows"
    )
    ## The fields that ARE invariant here still hoist — compaction is per field, not all-or-none.
    assert out["gates_shared"]["macro"] == "MBEDTLS_THREADING_C"


## @brief The saving is large and is asserted as a saving.
## @version 1
def test_the_panel_gets_materially_smaller() -> None:
    """A COMPACTION THAT DOES NOT COMPACT IS A SHAPE CHANGE FOR NOTHING. The measured panel is
    154 rows; at that size the invariant text is most of the payload, so the test asserts a
    floor on the saving rather than merely that the keys moved.
    """
    rows = [_row(f"library/f{i}.c", i * 10) for i in range(154)]
    before = len(json.dumps({"gates": rows}))

    after = len(json.dumps(_compact_gate_panel({"gates": rows})))

    assert after < before * 0.45, (
        f"expected the panel to more than halve; {before:,d} -> {after:,d} bytes"
    )


## @brief A single row, an empty panel and a missing panel are all left alone.
## @version 1
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="no-gates-key"),
        pytest.param({"gates": []}, id="empty"),
        pytest.param({"other": 1}, id="unrelated"),
    ],
)
def test_nothing_to_compact_is_left_untouched(payload: dict) -> None:
    """No panel and an empty panel must pass through unchanged — an empty `gates` list is a
    measurement ("this symbol gates nothing here") and must not grow a `gates_shared` key
    claiming facts about zero rows.
    """
    assert _compact_gate_panel(dict(payload)) == payload


## @brief One row is compacted too, and loses nothing.
## @version 1
def test_a_single_row_still_round_trips() -> None:
    """With one row every field is trivially invariant, so all of them hoist and the row keeps
    only what varies. The saving is nil at this size and the reply must still carry every value —
    this is the case where a careless implementation drops the row's content entirely.
    """
    out = _compact_gate_panel({"gates": [_row("a.c", 10)]})

    merged = {**out["gates_shared"], **out["gates"][0]}
    assert merged["macro"] == "MBEDTLS_THREADING_C"
    assert merged["default_site"] == "include/mbedtls/mbedtls_config.h:3787"
    assert merged["file_path"] == "a.c"
    assert merged["line"] == 10
