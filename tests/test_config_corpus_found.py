# SPDX-License-Identifier: MIT
"""A REPLY THAT CARRIES FIVE HITS AND SAYS `found: false`.

`_search_config`'s own docstring records this, in the measurement that motivated its last fix:

    "Measured on mbedtls 2026-08-14: `search(corpus='config', text='MBEDTLS_THREADING_C')`
     returned 2,149,463 characters, all 12,096 rows, WHILE REPORTING `found: false` for a symbol
     named in `configured_macros` in the same reply."

The row-count half of that was fixed. The `found: false` half shipped, and it is still shipping.

**WHAT IT COST, replayed from the frozen 1.1.0 grid.** mbedtls Q1 asks what runs concurrently in a
default build. Three of three `index_only` cells called
`search(corpus="config", text="THREADING")`. The index holds 154 `kconfig_gates` rows and 3
`config_defaults` rows for `MBEDTLS_THREADING_C`, and the reply named five matching symbols in
`gate_symbol_names` — beside `found: false`. All three cells stopped pursuing configuration and
the question's central symbol never reached `dossier`.

**WHY THE FIELD IS NOT WRONG AND THE WIRE IS.** `KconfigSpace.found` means "this build located a
Kconfig file", which is a distinction the layer needs and which `test_kconfig` defends directly:
*"this fixture has no Kconfig — `found` must stay honest about that"*. mbedtls is configured by a
header, so `False` is the truth about Kconfig discovery.

The collision is that `found` means something else everywhere on this surface, and clew's own code
says so: `tools_query._verdict`'s negative test is `payload.get("found") is False or
payload.get("count") == 0`. One key, two meanings, and the reader cannot tell which it was handed.
So the library field keeps its name and its meaning, and the WIRE stops using the word for it.

@brief The config corpus must not report a negative while serving rows.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.mcp_server.tools_query import QueryTools


##
# @brief An index configured by a header rather than Kconfig, with gating symbols.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def header_configured(tmp_path: Path) -> Path:
    """The mbedtls shape at minimum size: no `kconfig.source` stamp — so
    `KconfigSpace.found` is correctly False — and a populated gate layer that the reply
    does have something to say about.

    @brief Seed a header-configured index with gates.
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
        """
    )
    conn.executemany(
        "INSERT INTO kconfig_gates VALUES (?, ?, 'if_expr', 'include/x/config.h', ?, "
        "'undeclared', ?)",
        [
            ("MBEDTLS_THREADING_C", "MBEDTLS_THREADING_C", 10, 20),
            ("MBEDTLS_THREADING_PTHREAD", "MBEDTLS_THREADING_PTHREAD", 30, 40),
        ],
    )
    conn.commit()
    conn.close()
    return db


##
# @brief A tool set bound to one database.
# @version 1
def _tools(db: Path) -> QueryTools:
    return QueryTools(lambda: db, lambda: db.parent)


## @brief A reply carrying symbol names must not read as a negative.
## @version 1
def test_a_config_reply_with_hits_is_not_a_negative(header_configured: Path) -> None:
    """RED BEFORE THE FIX: `gate_symbol_names` holds two symbols and the same envelope carries
    `found: false`.

    Asserted on the GENERIC key rather than on wording, because `found` is what every consumer
    of this surface branches on — including clew's own `_verdict`.
    """
    reply = _tools(header_configured).search(text="THREADING", corpus="config")

    assert reply.get("gate_symbol_names"), "precondition: the corpus must have matched something"
    assert reply.get("found") is not False, (
        f"the reply serves {len(reply['gate_symbol_names'])} matching symbol(s) and reports "
        f"found={reply.get('found')!r} — a reader branching on `found` is told there is nothing "
        f"here, which is what three mbedtls Q1 cells did"
    )


## @brief The Kconfig-discovery fact survives under its own name.
## @version 1
def test_the_kconfig_discovery_fact_is_still_reported(header_configured: Path) -> None:
    """THE FIX MUST NOT DELETE THE DISTINCTION. "no Kconfig in this repository" and "a Kconfig
    that failed to parse" are different facts and the layer exists to keep them apart — so the
    wire has to carry it, under a name that cannot be mistaken for "this reply found nothing".
    """
    reply = _tools(header_configured).search(text="THREADING", corpus="config")

    assert "kconfig_found" in reply, f"the discovery fact was dropped, not renamed: {sorted(reply)}"
    assert reply["kconfig_found"] is False, (
        "this fixture stamps no kconfig.source, so Kconfig discovery genuinely failed and must "
        "still say so"
    )


## @brief A genuinely empty config corpus still reports a negative.
## @version 1
def test_an_empty_config_corpus_still_reads_as_empty(tmp_path: Path) -> None:
    """THE OTHER HALF, and the one that keeps the fix from being a blanket `found: true`. A
    repository with no gating symbols at all must still hand back a negative — otherwise the
    change trades a false negative for a false positive, which is worse on this surface because
    a reader cannot check it.
    """
    db = tmp_path / "bare.db"
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
    conn.commit()
    conn.close()

    reply = _tools(db).search(text="NOTHING_MATCHES_THIS", corpus="config")

    assert not reply.get("gate_symbol_names")
    assert reply.get("found") is False, (
        "a corpus that matched nothing must still report a negative; the fix is about replies "
        "that DO carry rows"
    )
