# SPDX-License-Identifier: MIT
"""WHICH PARSER BUILT THIS INDEX, recorded rather than inferred.

B4, 1.1.0 MERGE REVIEW. `build_meta` recorded clew's own `build_version` and nine sections
about the repository and the boundary, and nothing at all about the TOOLCHAIN that produced
the rows. `lang-parsing-substrate` reads every byte of every target, and `clew/signature.py`'s
build-version-8 note is a measured record of one of its upgrades changing an index: on
mbedtls, 7 AST-recovered functions lost, two `ssl_parse_*` gained, three fabricated `if`
functions removed. An index that moved for that reason was indistinguishable from one that
moved because the code changed — the exact ambiguity every other section here exists to
remove.

`tool.` is its own section rather than a key under `coverage.` or `scope.` because it is a
fact about the BUILDER, not about the repository or what was indexed. The namespace is read
from `write_build_signature`'s prefix tuple, so a tenth section is a one-line change.

@brief The recorded build toolchain in build_meta.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.signature import write_build_signature


## @brief Read every build_meta row from a database.
## @return key -> value
## @version 1
def _meta(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return dict(conn.execute("SELECT key, value FROM build_meta").fetchall())
    finally:
        conn.close()


def test_the_tool_section_is_stamped_under_its_own_prefix(tmp_path: Path) -> None:
    """@brief A `tool` dict lands as `tool.*` rows. @version 1"""
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()

    write_build_signature(db, tool={"substrate_version": "0.11.2"})

    assert _meta(db)["tool.substrate_version"] == "0.11.2"


def test_an_unrecorded_toolchain_leaves_no_row(tmp_path: Path) -> None:
    """The falsy-drop rule, which every section here depends on: an absent key must read as
    "not recorded" rather than as a version that was read and was blank.

    @brief No `tool.*` row when nothing was measured. @version 1
    """
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()

    write_build_signature(db, tool={"substrate_version": ""})

    assert not [key for key in _meta(db) if key.startswith("tool.")]


def test_the_build_records_the_version_it_keyed_the_cache_on() -> None:
    """ONE SOURCE FOR BOTH. The cache key and the stamped row must name the same version, or
    an index can report a parser it was not built with — which is worse than reporting none,
    because a reader would act on it. Asserted by deriving both from `_cache_key_extra`.

    @brief The stamped version is the one in the cache key. @version 1
    """
    from clew.cli import _cache_key_extra, _substrate_meta

    keyed = [item.split("=", 1)[1] for item in _cache_key_extra() if item.startswith("substrate=")]

    assert keyed, "the cache key no longer names the substrate version"
    assert _substrate_meta() == {"substrate_version": keyed[0]}
