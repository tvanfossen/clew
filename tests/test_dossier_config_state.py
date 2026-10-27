# SPDX-License-Identifier: MIT
"""A config macro's shipped default was indexed, and `dossier` reported a misleading answer.

**MEASURED ON TWO GRADED CELLS.** `dossier("MBEDTLS_PLATFORM_MEMORY")` reported

    file = configs/ext/tfm_mbedcrypto_config_profile_medium.h:87     <- a TFM profile header
    macros[] = that profile, plus tests/configs/user-config-malloc-0-null.h

and did not mention `include/mbedtls/mbedtls_config.h` AT ALL — where the macro is **commented
out**. An agent asking whether it is enabled is shown a `#define` in a profile header and nothing
else, which reads as ENABLED. The shipped default is off.

The data was present the whole time: `config_defaults` held 1,471 rows for that target, 283 of
them `state='off'`, including `MBEDTLS_PLATFORM_MEMORY` off at `mbedtls_config.h:208`. `dossier`
exposed none of them.

**WHY `macros[]` COULD NOT HAVE SHOWN IT.** That list comes from `memberdef WHERE kind='macro
definition'` — doxygen's view, which holds only ACTIVE `#define`s. A commented-out default is not
a definition, so it lives only in `config_defaults`. The two layers answer different questions and
the dossier carried only the first.

Cost: 7 of mbedtls Q3's failed marks and 3 of Q4's are config-state claims — "is it commented out
in the shipped config", "is there indirection in a DEFAULT build". Q3 scored 34.5% against a
baseline of 69.0 and made five calls, none to `corpus="config"`; it reached the macros by
`dossier` and was told nothing about their state.

@brief A macro subject must report its configured default state.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.query.subject import dossier


##
# @brief An index where a macro is active in a profile header and commented out in the shipped one.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def config_db(tmp_path: Path) -> Path:
    """Reproduces the mbedtls shape exactly: the ONLY `memberdef` row is the profile header, so a
    dossier built from definition sites alone cannot help reporting the misleading one. The
    shipped config's `off` row exists solely in `config_defaults`, which is where a commented-out
    default has to live.

    @brief Seed memberdef + config_defaults with a disagreeing pair.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, line INTEGER,
            definition TEXT, argsstring TEXT, initializer TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        CREATE TABLE config_defaults (
            macro TEXT, state TEXT, value TEXT, file_path TEXT, line INTEGER,
            doc TEXT, origin TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, name, type) VALUES (?, ?, 1)",
        [(1, "configs/ext/profile_medium.h"), (2, "include/mbedtls/mbedtls_config.h")],
    )
    conn.execute(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "line, definition, argsstring, initializer, briefdescription, detaileddescription, static)"
        " VALUES (10, 'macro definition', 'MBEDTLS_PLATFORM_MEMORY', 1, 1, 0, 0, 87, "
        "'#define MBEDTLS_PLATFORM_MEMORY', '', '', '', '', 0)"
    )
    conn.executemany(
        "INSERT INTO config_defaults (macro, state, value, file_path, line, doc, origin) "
        "VALUES (?, ?, '', ?, ?, '', 'heuristic')",
        [
            ("MBEDTLS_PLATFORM_MEMORY", "on", "configs/ext/profile_medium.h", 87),
            ("MBEDTLS_PLATFORM_MEMORY", "off", "include/mbedtls/mbedtls_config.h", 208),
        ],
    )
    conn.commit()
    conn.close()
    return db


##
# @brief The dossier must report the macro's configured state.
# @param config_db The seeded database.
# @return None.
# @version 1
def test_a_macro_dossier_reports_its_configured_state(config_db: Path) -> None:
    """THE REGRESSION, NAMED. Nothing in the reply said `off`, said `mbedtls_config.h`, or said
    "commented out" — the three things the failed marks asked for.

    @brief Config state reaches the reply.
    @return None.
    @version 1
    """
    reply = dossier(config_db, "MBEDTLS_PLATFORM_MEMORY")
    ## A macro subject rides in the `function` section of the envelope — one envelope, one
    ## populated section — and `wire.one` flattens it for the served payload.
    sites = reply.function.config_defaults

    assert sites, f"the dossier carries no config state at all: {sites!r}"
    seen = {(s.file, s.state) for s in sites}
    assert ("include/mbedtls/mbedtls_config.h", "off") in seen, (
        f"the SHIPPED config's off state is missing — the one the marks asked for: {seen}"
    )


##
# @brief The shipped config site must be distinguishable from a profile header.
# @param config_db The seeded database.
# @return None.
# @version 1
def test_the_shipped_config_is_not_buried_among_profiles(config_db: Path) -> None:
    """**LISTING IT IS NOT ENOUGH IF IT READS AS ONE OPTION AMONG MANY.** `MBEDTLS_ERROR_C` DID
    include the shipped site in `macros[]` — third, unordered, with no state — and its mark failed
    anyway. A reader has to be able to tell which site is the default build.

    @brief The shipped site is identifiable.
    @return None.
    @version 1
    """
    reply = dossier(config_db, "MBEDTLS_PLATFORM_MEMORY")
    sites = list(reply.function.config_defaults)

    assert sites, "no config state to order"
    assert sites[0].file == "include/mbedtls/mbedtls_config.h", (
        f"a profile header outranks the shipped config: {[s.file for s in sites]}"
    )
