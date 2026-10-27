# SPDX-License-Identifier: MIT
"""Disagreeing config headers left a gate's default unstated, and an answer went confidently
backwards about the default build.

**MEASURED ON A GRADED CELL.** mbedtls Q3 asked how the library routes its allocations.
`dossier("mbedtls_calloc")` correctly returned BOTH preprocessor branches:

    site :144  gated_by MBEDTLS_PLATFORM_MEMORY        <- no default_state
    site :167  gated_by MBEDTLS_PLATFORM_MEMORY (#else) <- no default_state

The answer described the :144 branch — function-pointer indirection — as the normal path. The
default build has `MBEDTLS_PLATFORM_MEMORY` OFF, where platform.h:165-168 `#undef`s the names and
maps them straight to `calloc`/`free`, so there is no indirection at all. That mark is weight 3
and the answer stated its opposite with confidence.

**WHY IT COULD NOT TELL.** `MBEDTLS_PLATFORM_MEMORY` has three `config_defaults` rows that
disagree — `on` in `configs/ext/tfm_mbedcrypto_config_profile_medium.h`, `off` in the shipped
`include/mbedtls/mbedtls_config.h`, `on` in `tests/configs/user-config-malloc-0-null.h` — and all
three are `heuristic` origin. `_with_defaults` drops a macro whose guesses disagree unless a
DECLARED header settles it, so the gate came back with no default at all and the agent had nothing
to choose a branch with.

**DROPPING WAS RIGHT WHEN EVERY SITE WAS EQUALLY A GUESS, AND IS WRONG NOW THAT ONE IS THE
SHIPPED CONFIG.** An alternate profile and a test fixture are not peers of the repository's own
default header; treating them as peers is what turned a known fact into silence. The shipped site
settles it, and `default_site` names which file was believed so a reader can disagree.

A DECLARED HEADER STILL WINS over the shipped-path heuristic, because an operator naming a config
header is better evidence than a filename pattern.

@brief The shipped config settles a disagreement among guessed defaults.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


from clew.query.kconfig import _with_defaults
from clew.query.models import KconfigGate

MACRO = "MBEDTLS_PLATFORM_MEMORY"


##
# @brief One gate on the macro under test.
# @return The gate.
# @version 1
def _gate() -> KconfigGate:
    """@brief A gate to resolve defaults onto.
    @return The gate.
    @version 1
    """
    return KconfigGate(
        symbol=MACRO,
        macro=MACRO,
        form="if_expr",
        file_path="include/mbedtls/platform.h",
        line=138,
    )


##
# @brief Build a config_defaults table from (state, file, origin) triples.
# @param tmp_path Per-test temporary directory.
# @param rows The rows to insert.
# @return An open connection.
# @version 1
def _conn(tmp_path: Path, rows: list[tuple[str, str, str]]) -> sqlite3.Connection:
    """@brief Seed config_defaults.
    @return Open connection.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE config_defaults (macro TEXT, state TEXT, value TEXT, file_path TEXT, "
        "line INTEGER, doc TEXT, origin TEXT)"
    )
    conn.executemany(
        "INSERT INTO config_defaults (macro, state, value, file_path, line, doc, origin) "
        "VALUES (?, ?, '', ?, 1, '', ?)",
        [(MACRO, state, path, origin) for state, path, origin in rows],
    )
    conn.commit()
    return conn


##
# @brief The shipped config must settle a disagreement among guesses.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_the_shipped_config_settles_a_disagreement(tmp_path: Path) -> None:
    """THE REGRESSION, EXACTLY AS MEASURED: three heuristic rows, two saying on, the shipped one
    saying off. Before this the gate came back with no default and an answer picked the wrong
    branch.

    @brief A disagreement resolves to the shipped state.
    @return None.
    @version 1
    """
    conn = _conn(
        tmp_path,
        [
            ("on", "configs/ext/tfm_mbedcrypto_config_profile_medium.h", "heuristic"),
            ("off", "include/mbedtls/mbedtls_config.h", "heuristic"),
            ("on", "tests/configs/user-config-malloc-0-null.h", "heuristic"),
        ],
    )

    gate = _with_defaults(conn, (_gate(),))[0]

    assert gate.default_state == "off", (
        f"the shipped config says off and the gate reports {gate.default_state!r} — an agent "
        f"cannot tell which preprocessor branch is the default build"
    )
    assert "mbedtls_config.h" in gate.default_site, gate.default_site


##
# @brief A declared header must still outrank the shipped-path heuristic.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_declared_header_still_wins(tmp_path: Path) -> None:
    """THE PRECEDENCE THAT MUST NOT INVERT. An operator naming a config header is better evidence
    than a filename pattern, so a declared row wins even when a shipped-looking path disagrees.

    @brief Declared beats shipped-path.
    @return None.
    @version 1
    """
    conn = _conn(
        tmp_path,
        [
            ("off", "include/mbedtls/mbedtls_config.h", "heuristic"),
            ("on", "configs/my_declared_config.h", "declared"),
        ],
    )

    gate = _with_defaults(conn, (_gate(),))[0]

    assert gate.default_state == "on", (
        f"a declared header was overruled by the shipped-path heuristic: {gate.default_state!r}"
    )


##
# @brief A disagreement with NO shipped site must still be dropped.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_disagreement_with_no_shipped_site_is_still_dropped(tmp_path: Path) -> None:
    """THE ORIGINAL RULE SURVIVES WHERE IT WAS RIGHT. When every site really is an equal guess,
    inventing one is worse than silence — the gate must still come back unstated rather than
    picking arbitrarily.

    @brief An unresolvable disagreement stays unstated.
    @return None.
    @version 1
    """
    conn = _conn(
        tmp_path,
        [
            ("on", "configs/profile_a.h", "heuristic"),
            ("off", "configs/profile_b.h", "heuristic"),
        ],
    )

    gate = _with_defaults(conn, (_gate(),))[0]

    assert not gate.default_state, (
        f"an unresolvable disagreement invented a default: {gate.default_state!r}"
    )


##
# @brief When every site AGREES, the shipped config is still the one to cite.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_agreeing_sites_still_cite_the_shipped_config(tmp_path: Path) -> None:
    """THE OTHER HALF OF THE SAME EVIDENCE PROBLEM, found by replaying the frozen mbedtls index.
    `dossier("MBEDTLS_THREADING_C")` now reports `default_state: 'off'` correctly — all three
    `config_defaults` rows agree — and cites
    `default_site: 'configs/config-symmetric-only.h:73'`.

    That is an ALTERNATE BUILD PROFILE. The repository's own shipped header says the same thing at
    `include/mbedtls/mbedtls_config.h:3787`, and it is the file a default build actually reads.
    With no disagreement to settle, `_with_defaults` kept the first row it encountered, which is
    whichever file path sorted first — `configs/` before `include/`.

    THE STATE WAS NEVER WRONG; THE CITATION WAS. mbedtls Q3's marks are about what the DEFAULT
    build does, and `default_site` is the field a reader follows to check the claim. Sending them
    to a non-default profile invites them to doubt a correct answer — and `default_site` exists
    precisely "so a reader can disagree with the choice", which it cannot do usefully against a
    file that is not in play.

    `is_shipped_config` is already the rule for the disagreement case one function up, so this
    adds no new judgement about which file is authoritative — it applies the existing one when
    the states happen to match.

    @brief An agreeing set cites the repository's own header.
    @return None.
    @version 1
    """
    conn = _conn(
        tmp_path,
        [
            ("off", "configs/config-symmetric-only.h", "heuristic"),
            ("off", "include/mbedtls/mbedtls_config.h", "heuristic"),
            ("off", "tests/configs/config_test_driver.h", "heuristic"),
        ],
    )

    gate = _with_defaults(conn, (_gate(),))[0]

    assert gate.default_state == "off", "the state was already right and must stay right"
    assert "mbedtls_config.h" in gate.default_site, (
        f"with every site agreeing, the citation must still be the repository's own shipped "
        f"header rather than whichever path sorted first: {gate.default_site!r}"
    )


##
# @brief A declared header still outranks the shipped-path heuristic when they agree.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_declared_header_still_wins_an_agreeing_set(tmp_path: Path) -> None:
    """THE PRECEDENCE MUST NOT INVERT. An operator naming a config header is better evidence than
    a filename pattern, and that holds whether or not the states agree — so the agreeing-set rule
    is a tie-break among HEURISTIC rows, never a promotion over a declared one.

    @brief Declared beats shipped-path even with no disagreement.
    @return None.
    @version 1
    """
    conn = _conn(
        tmp_path,
        [
            ("off", "include/mbedtls/mbedtls_config.h", "heuristic"),
            ("off", "custom/operator_declared.h", "declared"),
        ],
    )

    gate = _with_defaults(conn, (_gate(),))[0]

    assert "operator_declared.h" in gate.default_site, (
        f"a declared header must outrank the shipped-path heuristic: {gate.default_site!r}"
    )
