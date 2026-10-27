# SPDX-License-Identifier: MIT
"""THE SAME FACT, REACHABLE FROM ONE DIRECTION AND NOT THE OTHER (C3 of the 1.1.0 review).

`_with_defaults` resolves a gating macro's shipped default and attaches it to a gate, and
`test_shipped_config_tiebreak` pins the resolution rule itself. It is wired into exactly ONE
caller: `gates_covering`, which builds the FUNCTION subject's `gated_by` list.

The CONFIG subject's own `gates` list — what `dossier("MBEDTLS_PLATFORM_MEMORY")` returns, and
what `search(corpus="config")` routes a reader to — goes through `_gates`, which does not call
it. So:

    dossier("mbedtls_calloc")           -> gated_by rows CARRY default_state    (since b0c375a)
    dossier("MBEDTLS_PLATFORM_MEMORY")  -> gates rows carry NOTHING

A reader who asks about the FUNCTION learns which preprocessor branch the default build takes.
A reader who asks about the SYMBOL — the more direct question, and the one a config-corpus
search row points at — gets a list of sites where the symbol decides code, with no way to tell
which way the decision goes. The 12 weight behind mbedtls Q3's remaining marks is asked the
second way.

**THIS IS NOT A NEW RESOLUTION RULE AND MUST NOT BECOME ONE.** The join already exists, is
already tested, and already encodes which evidence outranks which. A second implementation for
the second caller is how two surfaces come to disagree about the same macro — the defect
`_key_edge_rows` exists to prevent one module over. The fix is one call.

@brief A config symbol's own gates carry the resolved default state.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q

MACRO = "MBEDTLS_PLATFORM_MEMORY"


##
# @brief An index whose gate layer and config_defaults both know this macro.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def gated(tmp_path: Path) -> Path:
    """The mbedtls Q3 shape at minimum size: two gate sites for one macro — the `#if` arm and
    the `#else` arm, which is why collapsing them would discard the half that says whether the
    code is there — and the three disagreeing `config_defaults` rows, one of which is the
    shipped header.

    `build_meta` carries `kconfig.source` so `KconfigSpace.found` is True for the reason its own
    docstring gives: `found` comes from the stamp, never from the table's presence.

    @brief Seed a gate layer plus disagreeing defaults.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE build_meta (key TEXT, value TEXT);
        CREATE TABLE kconfig_gates (
            symbol TEXT, macro TEXT, form TEXT, file_path TEXT, line INTEGER,
            origin TEXT, end_line INTEGER
        );
        CREATE TABLE config_defaults (
            macro TEXT, state TEXT, value TEXT, file_path TEXT, line INTEGER,
            doc TEXT, origin TEXT
        );
        """
    )
    conn.execute("INSERT INTO build_meta VALUES ('kconfig.source', 'config_header')")
    conn.executemany(
        "INSERT INTO kconfig_gates VALUES (?, ?, 'if_expr', 'include/mbedtls/platform.h', ?, "
        "'undeclared', ?)",
        [(MACRO, MACRO, 144, 160), (MACRO, MACRO, 167, 180)],
    )
    conn.executemany(
        "INSERT INTO config_defaults (macro, state, value, file_path, line, doc, origin) "
        "VALUES (?, ?, '', ?, 1, '', 'heuristic')",
        [
            (MACRO, "on", "configs/ext/tfm_mbedcrypto_config_profile_medium.h"),
            (MACRO, "off", "include/mbedtls/mbedtls_config.h"),
            (MACRO, "on", "tests/configs/user-config-malloc-0-null.h"),
        ],
    )
    conn.commit()
    conn.close()
    return db


## @brief The config subject's gates carry the resolved default state.
## @version 1
def test_a_config_symbols_own_gates_carry_the_resolved_default(gated: Path) -> None:
    """RED BEFORE THE FIX: `_gates` returns `KconfigGate` rows straight from SQL, so
    `default_state` holds its dataclass default and every site reads as "no default known"
    against an index that knows it.
    """
    space = q.kconfig_space(gated, MACRO)
    assert len(space.gates) == 2, "both preprocessor arms must survive"

    states = {gate.default_state for gate in space.gates}
    assert states == {"off"}, (
        f"the shipped config says off; the config subject reports {states} — a reader asking "
        f"about the symbol cannot tell which arm the default build takes"
    )
    assert all("mbedtls_config.h" in gate.default_site for gate in space.gates), (
        "the site must name the file that was believed, so a reader can disagree with the choice"
    )


## @brief The two surfaces agree about the same macro.
## @version 1
def test_the_function_route_and_the_symbol_route_report_the_same_default(gated: Path) -> None:
    """THE PROPERTY, NOT THE VALUE. Whatever the resolution rule decides, the function subject's
    `gated_by` and the config subject's `gates` must decide it identically, because they are the
    same join over the same rows. Asserting the shared answer rather than a literal is what makes
    this test fail if a second implementation is ever introduced for one of them — which is the
    outcome it exists to prevent, not the current `off`.
    """
    from clew.query.kconfig import gates_covering

    conn = sqlite3.connect(str(gated))
    try:
        covering, _unknown = gates_covering(conn, "include/mbedtls/platform.h", 150)
        by_function = {(g.line, g.default_state, g.default_site) for g in covering}
    finally:
        conn.close()

    space = q.kconfig_space(gated, MACRO)
    by_symbol = {(g.line, g.default_state, g.default_site) for g in space.gates if g.line == 144}

    assert by_function == by_symbol, (
        f"the two routes disagree about one macro: function route {by_function}, symbol route "
        f"{by_symbol}. One join, two callers — a second implementation is how they drift."
    )


## @brief An index with no config_defaults table still answers, thinly.
## @version 1
def test_a_gate_layer_without_defaults_reports_no_state_rather_than_raising(tmp_path: Path) -> None:
    """The graceful-degradation contract, on the path C3 adds. `_with_defaults` already returns
    the gates untouched when the table is absent; this pins that the new call site inherits that
    rather than being a second place to get it wrong.

    An ABSENT default is the honest answer for an index that holds no such measurement, and is
    distinct from `off` — which is why the field defaults to empty rather than to a state.
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE build_meta (key TEXT, value TEXT);
        CREATE TABLE kconfig_gates (
            symbol TEXT, macro TEXT, form TEXT, file_path TEXT, line INTEGER,
            origin TEXT, end_line INTEGER
        );
        """
    )
    conn.execute("INSERT INTO build_meta VALUES ('kconfig.source', 'config_header')")
    conn.execute(
        "INSERT INTO kconfig_gates VALUES (?, ?, 'if_expr', 'src/x.c', 10, 'undeclared', 20)",
        (MACRO, MACRO),
    )
    conn.commit()
    conn.close()

    space = q.kconfig_space(db, MACRO)
    assert len(space.gates) == 1
    assert space.gates[0].default_state == "", (
        "no defaults corpus means the state is UNKNOWN, which must not read as a measured state"
    )


## @brief More gating macros than one IN clause holds still resolve, all of them.
## @version 1
def test_more_macros_than_one_in_clause_still_all_resolve(tmp_path: Path) -> None:
    """C3 MADE THE WHOLE-REPO GATE LIST A CALLER OF THIS JOIN, and that changed the input size
    by three orders of magnitude: `gates_covering` resolves the handful of gates over one line,
    while `_gates(conn, None)` resolves every gating macro in the repository. Counted: RIOT's
    gate layer holds **2,029 distinct gating macros**, sassafras-class 503.

    `SQLITE_MAX_VARIABLE_NUMBER` is compile-time and defaulted to **999 before SQLite 3.32**, so
    one parameter per macro is over a documented default by a factor of two on a real target.
    NOT A CRASH REPRODUCED HERE — this interpreter links a build that accepts 32,766 — which is
    exactly why it needs a test rather than a trusted comment: on this machine the unchunked
    version passes.

    So the assertion is on COMPLETENESS ACROSS THE BOUNDARY, not on an exception: every macro
    must come back resolved, including the ones in the second and third chunk. A chunking bug
    that silently dropped the tail would be invisible to any test that only counted rows.

    @brief Every macro resolves regardless of how many chunks it takes.
    @return None.
    @version 1
    """
    from clew.query.kconfig import _MACRO_CHUNK, _with_defaults
    from clew.query.models import KconfigGate

    total = _MACRO_CHUNK * 2 + 7
    names = [f"CONFIG_THING_{i:05d}" for i in range(total)]

    db = tmp_path / "many.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE config_defaults (macro TEXT, state TEXT, value TEXT, file_path TEXT, "
        "line INTEGER, doc TEXT, origin TEXT)"
    )
    conn.executemany(
        "INSERT INTO config_defaults (macro, state, value, file_path, line, doc, origin) "
        "VALUES (?, 'on', '', 'include/project_config.h', 1, '', 'declared')",
        [(n,) for n in names],
    )
    conn.commit()

    gates = tuple(
        KconfigGate(symbol=n, macro=n, form="if_expr", file_path="src/x.c", line=i)
        for i, n in enumerate(names)
    )
    resolved = _with_defaults(conn, gates)
    conn.close()

    unresolved = [g.macro for g in resolved if g.default_state != "on"]
    assert not unresolved, (
        f"{len(unresolved)} of {total} macros lost their default across the chunk boundary, "
        f"first few: {unresolved[:5]}"
    )
