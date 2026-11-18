# SPDX-License-Identifier: MIT
"""A single-symbol `#if defined(X)` has a polarity, and so does its `#else` (UPERF T5; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mbedtls F1, vetted): `#if defined(MBEDTLS_PLATFORM_MEMORY)`
at platform.h:138-163 and its `#else` at 163-168 were BOTH stored as `if_expr` — "polarity unknown
to this layer" — so "which branch is in the default build" could not be answered, though the
condition tests exactly one symbol. `#ifdef X` already carried its polarity; its spelled-out twin
did not. A condition this layer cannot evaluate (`&&`, a comparison, an `#elif`) stays `if_expr`.

@brief Tests per-branch polarity for single-symbol `#if` conditions.
@version 1
"""

from __future__ import annotations

import pytest

from clew.tsnode import Parser


def _gates(source: str) -> list[tuple]:
    """@brief The gate rows one C source yields. @return (macro, form, line, end) tuples."""
    from clew.kconfig_gates import gate_harvester

    tree = Parser("c").parse(source.encode())
    found = gate_harvester().harvest(tree, source.encode())
    return sorted(((g[1], g[2], g[3], g[4]) for g in found), key=lambda r: (r[2], r[1]))


@pytest.mark.parametrize(
    ("condition", "form"),
    [
        ("defined(A)", "ifdef"),
        ("defined A", "ifdef"),
        ("!defined(A)", "ifndef"),
        ("! defined ( A )", "ifndef"),
    ],
)
def test_a_single_defined_test_is_an_ifdef_or_ifndef(condition: str, form: str) -> None:
    """@brief `#if [!]defined(X)` carries X's polarity, and the `#else` the inverse."""
    inverse = {"ifdef": "ifndef", "ifndef": "ifdef"}[form]
    rows = _gates(f"#if {condition}\nint a;\n#else\nint b;\n#endif\n")
    assert rows == [("A", form, 1, 3), ("A", inverse, 3, 4)], rows


def test_a_compound_or_elif_condition_stays_unevaluated() -> None:
    """@brief `&&` and `#elif` keep `if_expr`: their presence depends on more than one symbol."""
    rows = _gates("#if defined(A) && defined(B)\nint a;\n#elif defined(C)\nint c;\n#endif\n")
    assert {form for _m, form, _l, _e in rows} == {"if_expr"}, rows


def test_a_spelled_out_include_guard_is_still_not_a_gate() -> None:
    """@brief `#if !defined(FOO_H)` + `#define FOO_H` is an include guard, like `#ifndef FOO_H`."""
    assert _gates("#if !defined(FOO_H)\n#define FOO_H\nint a;\n#endif\n") == []


def _macro_db(tmp_path):
    """@brief A minimal index: three same-name macro definitions under #if / #else. @return conn."""
    import sqlite3

    conn = sqlite3.connect(tmp_path / "clew.db")
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_id INTEGER, line INTEGER);
        CREATE TABLE kconfig_gates (symbol TEXT, macro TEXT, form TEXT, file_path TEXT, line INTEGER,
            end_line INTEGER, origin TEXT);
        CREATE TABLE config_defaults (macro TEXT, state TEXT, value TEXT, file_path TEXT, line INTEGER,
            doc TEXT, origin TEXT);
        INSERT INTO path VALUES (1, 'platform.h'), (2, 'user.c');
        -- platform.h: #if defined(MEM) (1-5) defines mem_calloc as a pointer; #else (5-8) as calloc
        INSERT INTO memberdef VALUES (10, 'mem_calloc', 'macro definition', 1, 3);
        INSERT INTO memberdef VALUES (11, 'mem_calloc', 'macro definition', 1, 7);
        INSERT INTO kconfig_gates VALUES ('MEM', 'MEM', 'ifdef', 'platform.h', 1, 5, 'source');
        INSERT INTO kconfig_gates VALUES ('MEM', 'MEM', 'ifndef', 'platform.h', 5, 8, 'source');
        INSERT INTO config_defaults VALUES ('MEM', 'off', '', 'config.h', 9, '', 'source');
        """
    )
    return conn


def test_a_same_name_macro_resolves_to_the_definition_the_default_build_compiles(tmp_path) -> None:
    """mbedtls F3: `{name: rowid}` kept whichever definition was read last. With MEM off as
    shipped, the `#else` definition is the one compiled.

    @brief The default build picks the definition.
    """
    from clew.macro_refs import macro_definitions

    conn = _macro_db(tmp_path)
    assert macro_definitions(conn)["mem_calloc"] == [11]
    conn.execute("UPDATE config_defaults SET state = 'on'")
    assert macro_definitions(conn)["mem_calloc"] == [10]


def test_an_undecided_symbol_keeps_every_definition(tmp_path) -> None:
    """No config row: the build's choice is unknown here, so neither definition is dropped.

    @brief Unknown activity keeps both.
    """
    from clew.macro_refs import macro_definitions

    conn = _macro_db(tmp_path)
    conn.execute("DELETE FROM config_defaults")
    assert sorted(macro_definitions(conn)["mem_calloc"]) == [10, 11]
