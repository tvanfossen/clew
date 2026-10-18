# SPDX-License-Identifier: MIT
"""What a build leaves OFF, which an index of what exists cannot otherwise hold.

THE FIXTURE IS THE MEASURED FAILURE. On the first published acceptance grid the index-only arm
scored 0/3 on three mbedtls marks the shell arm got 2-3/3, all of them about what
`mbedtls_calloc` resolves to in a DEFAULT build. The index held the macro — twice — but both
rows came from alternative config profiles that DO define it, while the shipped header comments
it out and so produced nothing. The answer "this macro is defined, here and here" was true and
pointed the wrong way.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clew.config_defaults import (
    ensure_config_defaults_table,
    import_config_defaults,
    looks_like_config_header,
)

_SHIPPED = """\
/**
 * \\def FEATURE_PLATFORM_MEMORY
 *
 * Enable the platform memory allocation layer.
 */
//#define FEATURE_PLATFORM_MEMORY

/* #define FEATURE_SPACED_FORM */

#define FEATURE_ON_BY_DEFAULT

//#define FEATURE_WITH_VALUE 42
"""

_PROFILE = """\
#define FEATURE_PLATFORM_MEMORY
"""

_ORDINARY = """\
/* a note that mentions #define FEATURE_PLATFORM_MEMORY in passing */
//#define DEBUG_ONLY_LEFTOVER
int live(void) { return 0; }
"""


## @brief Build a tiny repo and index its configuration defaults.
## @param tmp_path Pytest temporary directory.
## @return (db path, rows) where rows are the stored config_defaults tuples.
## @version 1
def _build(tmp_path: Path):
    """@brief Index a fixture repo's config defaults.
    @return (db, rows).
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "include").mkdir(parents=True)
    (repo / "profiles").mkdir()
    (repo / "src").mkdir()
    (repo / "include" / "proj_config.h").write_text(_SHIPPED, encoding="utf-8")
    (repo / "profiles" / "tiny_config.h").write_text(_PROFILE, encoding="utf-8")
    (repo / "src" / "thing.c").write_text(_ORDINARY, encoding="utf-8")

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT)")
    for i, rel in enumerate(
        ("include/proj_config.h", "profiles/tiny_config.h", "src/thing.c"), start=1
    ):
        conn.execute("INSERT INTO path (rowid, name) VALUES (?, ?)", (i, rel))
    conn.commit()
    conn.close()

    import_config_defaults(db, repo)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT macro, state, value, file_path, line, origin FROM config_defaults ORDER BY macro"
    ).fetchall()
    conn.close()
    return db, rows


## @brief A commented-out define is recorded as off, not omitted.
## @return None.
## @version 1
def test_a_commented_out_define_is_recorded_as_off_by_default(tmp_path: Path) -> None:
    """THE WHOLE POINT. Without this row the only trace of the option in the index is the
    alternative profile that enables it, so an agent reads "defined" and answers the opposite
    of the truth for a default build.

    @brief Commented defines are off.
    @return None.
    @version 1
    """
    _, rows = _build(tmp_path)
    ## KEYED ON (macro, file), NOT macro ALONE. One macro legitimately has a row per header
    ## that decides it — that is the whole mbedtls shape — so a macro-keyed lookup silently
    ## returns whichever row sorted last and this assertion would then describe the wrong file.
    by = {(r[0], r[3]): r for r in rows}
    shipped = "include/proj_config.h"
    assert by[("FEATURE_PLATFORM_MEMORY", shipped)][1] == "off"
    ## BOTH COMMENT SPELLINGS. `//#define` with no space is mbedtls's; `/* #define X */` is the
    ## other common form, and recognising only one would silently halve the layer.
    assert by[("FEATURE_SPACED_FORM", shipped)][1] == "off"


## @brief An active define in the same header is recorded as on.
## @return None.
## @version 1
def test_an_active_define_is_recorded_as_on(tmp_path: Path) -> None:
    """ONE SCAN FOR BOTH STATES, so "on" and "off" cannot disagree about which options a header
    decides. A layer that recorded only the off ones would leave a reader unable to tell an
    enabled option from an option this header never mentions.

    @brief Active defines are on.
    @return None.
    @version 1
    """
    _, rows = _build(tmp_path)
    by = {(r[0], r[3]): r for r in rows}
    assert by[("FEATURE_ON_BY_DEFAULT", "include/proj_config.h")][1] == "on"


## @brief The value a commented define carries is kept beside its state.
## @return None.
## @version 1
def test_the_commented_value_is_kept(tmp_path: Path) -> None:
    """ "off" and "off, and it would be 42" are different answers, and the second is what a
    reader asking about a default actually wants.

    @brief Values survive.
    @return None.
    @version 1
    """
    _, rows = _build(tmp_path)
    by = {(r[0], r[3]): r for r in rows}
    assert by[("FEATURE_WITH_VALUE", "include/proj_config.h")][2] == "42"


## @brief Ordinary source is not mined for commented-out code.
## @return None.
## @version 1
def test_a_commented_define_in_ordinary_source_is_not_a_config_option(tmp_path: Path) -> None:
    """A COMMENTED DEFINE IN A .c FILE IS DEAD CODE, not a configuration decision. That is a
    different finding, and letting it into this layer would make every answer here less
    trustworthy — a reader could not tell an option the project offers from a line somebody
    abandoned.

    Also guards the inverse: a prose comment MENTIONING a define must not become a row, which
    is why the scan reads comment nodes and requires the define to be the whole comment.

    @brief Dead code stays out.
    @return None.
    @version 1
    """
    _, rows = _build(tmp_path)
    names = {r[0] for r in rows}
    assert "DEBUG_ONLY_LEFTOVER" not in names, "a commented define in .c is not an option"
    assert not any(r[3].endswith(".c") for r in rows), "no row may come from ordinary source"


## @brief An alternative profile's active define is recorded separately, not merged.
## @return None.
## @version 1
def test_two_headers_disagreeing_both_get_rows(tmp_path: Path) -> None:
    """THE EXACT mbedtls SHAPE: the shipped header says off, a profile says on, and BOTH are
    true of their own file. Collapsing them to one answer is what produced the wrong one — a
    consumer needs to see that the default is off and that something else turns it on.

    @brief Disagreeing headers coexist.
    @return None.
    @version 1
    """
    _, rows = _build(tmp_path)
    states = {(r[3], r[1]) for r in rows if r[0] == "FEATURE_PLATFORM_MEMORY"}
    assert ("include/proj_config.h", "off") in states
    assert ("profiles/tiny_config.h", "on") in states


## @brief The table exists even when a repo decides nothing.
## @return None.
## @version 1
def test_the_table_is_created_even_at_zero_rows(tmp_path: Path) -> None:
    """An EMPTY table means "we looked and this repo decides nothing"; an ABSENT one means the
    layer never ran. A consumer separating a correct negative from a detector failure needs
    both, and writing down the wrong one is the mistake this repo has made three times.

    @brief Empty is not absent.
    @return None.
    @version 1
    """
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    ensure_config_defaults_table(conn)
    found = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='config_defaults'"
    ).fetchone()
    conn.close()
    assert found, "the table must exist at zero rows"


## @brief The config-header heuristic is narrow and is labelled as a heuristic.
## @return None.
## @version 1
def test_header_detection_is_named_and_narrow(tmp_path: Path) -> None:
    """NAME-MATCHED, AND THE ROW SAYS SO. `origin` separates a header the operator declared
    from one this guessed at, so a consumer is never handed a guess as a fact.

    @brief Heuristic is labelled.
    @return None.
    @version 1
    """
    assert looks_like_config_header("include/mbedtls/mbedtls_config.h")
    assert looks_like_config_header("tests/configs/user-config-malloc-0-null.h")
    assert not looks_like_config_header("library/ssl_tls.c")
    assert not looks_like_config_header("include/mbedtls/platform.h")
    _, rows = _build(tmp_path)
    assert {r[5] for r in rows} == {"heuristic"}, "an unstated header is a guess, and says so"


## @brief An include guard is not a configuration option.
## @return None.
## @version 1
def test_an_include_guard_is_not_an_option(tmp_path: Path) -> None:
    """`#ifndef FOO_H` / `#define FOO_H` IS "INCLUDE ME ONCE", NOT A FEATURE. Measured on the
    real mbedtls tree before this exclusion: 39 of 1,206 "on" rows were guards, and nobody asks
    whether MBEDTLS_CONFIG_H is enabled by default. Left in, they rank EXACT on their own names
    in the discovery surface and become pure noise — the same reason `kconfig_gates` excludes
    them from gating sites.

    STRUCTURAL, NOT A `_H` SUFFIX RULE. The discriminator is that the guarded block defines the
    SAME symbol it just tested, which no configuration option ever does. A suffix test misses
    guards spelled otherwise and would catch feature macros that legitimately end in _H.

    @brief Guards stay out.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "include").mkdir(parents=True)
    (repo / "include" / "guard_config.h").write_text(
        "#ifndef PROJ_CONFIG_H\n"
        "#define PROJ_CONFIG_H\n"
        "#define FEATURE_REAL_OPTION\n"
        "//#define FEATURE_OFF_OPTION\n"
        "#endif\n",
        encoding="utf-8",
    )
    db = tmp_path / "guard.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'include/guard_config.h')")
    conn.commit()
    conn.close()

    import_config_defaults(db, repo)
    conn = sqlite3.connect(str(db))
    names = {r[0] for r in conn.execute("SELECT macro FROM config_defaults").fetchall()}
    conn.close()

    assert "PROJ_CONFIG_H" not in names, "an include guard is not a configuration option"
    ## The real options inside the guarded block must survive it — a guard excludes ITSELF,
    ## not everything it wraps, which is every option in a guarded config header.
    assert "FEATURE_REAL_OPTION" in names
    assert "FEATURE_OFF_OPTION" in names


## @brief Build a one-gate index with optional config defaults.
## @param tmp_path Pytest temporary directory.
## @param name Database file name.
## @param defaults Rows for config_defaults, or None to omit the table entirely.
## @return Open connection positioned on the fixture.
## @version 1
def _gate_db(tmp_path: Path, name: str, defaults):
    """@brief One gate over src/platform.h:10-40, plus whatever defaults are given.
    @return Open connection.
    @version 1
    """
    conn = sqlite3.connect(str(tmp_path / name))
    conn.executescript(
        """
        CREATE TABLE kconfig_gates (symbol TEXT, macro TEXT, form TEXT, file_path TEXT,
                                    line INTEGER, end_line INTEGER, origin TEXT);
        INSERT INTO kconfig_gates VALUES
            ('FEATURE_X','FEATURE_X','if_expr','src/platform.h',10,40,'undeclared');
        """
    )
    if defaults is not None:
        ensure_config_defaults_table(conn)
        conn.executemany(
            "INSERT INTO config_defaults "
            "(macro,state,value,file_path,line,doc,origin) VALUES (?,?,?,?,?,?,?)",
            defaults,
        )
    conn.commit()
    return conn


## @brief A covering gate carries the shipped default of the macro it names.
## @return None.
## @version 1
def test_a_gate_carries_its_macros_shipped_default(tmp_path: Path) -> None:
    """THE JOIN THAT ANSWERS THE QUESTION, and the reason the harvest layer alone is worth
    nothing. `form` says "present when this symbol is set"; the default says whether it IS set.
    Only the two together answer "is this code compiled in", which is what the mbedtls marks
    asked and the index-only arm scored 0/3 on.

    @brief Gates carry defaults.
    @return None.
    @version 1
    """
    from clew.query.kconfig import gates_covering

    conn = _gate_db(
        tmp_path,
        "g.db",
        [("FEATURE_X", "off", "", "include/proj_config.h", 208, "", "declared")],
    )
    gates, _ = gates_covering(conn, "src/platform.h", 20)
    conn.close()
    assert len(gates) == 1
    assert gates[0].default_state == "off"
    assert gates[0].default_site == "include/proj_config.h:208"


## @brief The declared header outvotes an alternative profile.
## @return None.
## @version 1
def test_the_declared_header_wins_over_an_alternative_profile(tmp_path: Path) -> None:
    """THE EXACT mbedtls SHAPE. `MBEDTLS_PLATFORM_MEMORY` is commented out in the declared
    `mbedtls_config.h` and actively defined in two profiles under `configs/`. A default build
    reads the declared header, so it answers; the profiles describe other builds and must not
    outvote it. Letting them would reproduce the measured wrong answer with extra steps.

    @brief Declared beats heuristic.
    @return None.
    @version 1
    """
    from clew.query.kconfig import gates_covering

    conn = _gate_db(
        tmp_path,
        "w.db",
        [
            ("FEATURE_X", "off", "", "include/proj_config.h", 208, "", "declared"),
            ("FEATURE_X", "on", "", "configs/profile_a_config.h", 87, "", "heuristic"),
            ("FEATURE_X", "on", "", "configs/profile_b_config.h", 20, "", "heuristic"),
        ],
    )
    gates, _ = gates_covering(conn, "src/platform.h", 20)
    conn.close()
    assert gates[0].default_state == "off", "the shipped header decides the default build"
    assert gates[0].default_site == "include/proj_config.h:208"


## @brief Disagreeing guesses with no declared header decide nothing.
## @return None.
## @version 1
def test_disagreeing_profiles_leave_the_default_undecided(tmp_path: Path) -> None:
    """EMPTY MEANS UNDECIDED, NEVER OFF. With two profiles disagreeing and no declared header to
    settle it, naming either as "the default" is the confident wrong answer this whole layer
    exists to remove — rebuilt one level up, which is exactly how it would come back.

    @brief Ambiguity stays ambiguous.
    @return None.
    @version 1
    """
    from clew.query.kconfig import gates_covering

    conn = _gate_db(
        tmp_path,
        "a.db",
        [
            ("FEATURE_X", "off", "", "configs/a_config.h", 1, "", "heuristic"),
            ("FEATURE_X", "on", "", "configs/b_config.h", 1, "", "heuristic"),
        ],
    )
    gates, _ = gates_covering(conn, "src/platform.h", 20)
    conn.close()
    assert gates[0].default_state == "", "two guesses that disagree must not pick a winner"


## @brief An index built before this layer serves gates unchanged.
## @return None.
## @version 1
def test_an_index_without_the_table_still_serves_gates(tmp_path: Path) -> None:
    """THE TABLE IS NEW, SO EVERY INDEX IN EXISTENCE LACKS IT. A reader of an older index must
    get its gates with an empty default rather than an exception — the same tolerance every
    other column-added layer here carries.

    @brief Older indexes still work.
    @return None.
    @version 1
    """
    from clew.query.kconfig import gates_covering

    conn = _gate_db(tmp_path, "old.db", None)
    gates, _ = gates_covering(conn, "src/platform.h", 20)
    conn.close()
    assert len(gates) == 1 and gates[0].default_state == ""
