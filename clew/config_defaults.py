# SPDX-License-Identifier: MIT
"""macro → on or off as the repository ships it.

WHAT THIS EXISTS TO FIX, measured on the first published acceptance grid. Asked what
`mbedtls_calloc` resolves to in a DEFAULT build, the index-only arm scored 0/3 on three marks
the shell arm got 2-3/3. Not because the index lacked the macro — it holds 5,420 macro
definitions and `MBEDTLS_PLATFORM_MEMORY` is two of them — but because of WHERE those two come
from:

    configs/ext/tfm_mbedcrypto_config_profile_medium.h:87   #define MBEDTLS_PLATFORM_MEMORY
    tests/configs/user-config-malloc-0-null.h:20            #define MBEDTLS_PLATFORM_MEMORY
    include/mbedtls/mbedtls_config.h:208                  //#define MBEDTLS_PLATFORM_MEMORY

Two alternative profiles define it. The shipped default comments it out, and a comment produces
no definition row. So the index answered "this macro is defined, here and here" — true, and
pointing the wrong way. THAT IS WORSE THAN A GAP: a gap yields "I do not know", this yields a
confident wrong answer, which is the failure `acceptance/DESIGN.md` opens by naming.

The gating relation was already there — `kconfig_gates` holds 11 sites for that macro including
the two in `platform.h` where the indirection is decided. The missing fact was one bit: whether
the header that OWNS the option leaves it on.

## A COMMENT IS THE DECLARATION

`//#define FOO` is not dead code in a configuration header; it is how a C project of this shape
writes "available, not enabled by default", and the doc block above it is the option's
documentation. So this reads COMMENT NODES from the parse rather than grepping text — a string
literal containing `#define` is not a comment, and the grammar already knows the difference.

## ABSENCE IS NOT "OFF"

A macro this scan never saw gets NO ROW. Reading an absent row as off would reintroduce exactly
the confident wrong answer the layer removes, one level up. Only a header that visibly decides
an option produces a row for it.

@brief Harvest configuration-option defaults into config_defaults.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest
from .indexcache import IndexCache
from .vocabulary import (
    CONFIG_DEFAULT_OFF,
    CONFIG_DEFAULT_ON,
    STAGE_CONFIG_DEFAULTS,
    check,
)

## A COMMENTED-OUT DEFINE, in the two spellings a configuration header uses. `//#define FOO`
## and `/* #define FOO */`, with any spacing — mbedtls writes the first with no space at all,
## Zephyr-style headers tend to the second.
##
## THE VALUE IS CAPTURED SEPARATELY because "off" and "off, and here is what it would be" are
## different answers, and an option whose commented form carries a value is telling a reader
## what the default WOULD become.
_COMMENTED = re.compile(
    r"^\s*(?://|/\*)\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*?)\s*(?:\*/)?\s*$"
)

## An ACTIVE define, read from the same header so "on" and "off" come from one scan and cannot
## disagree about which options a header decides.
_ACTIVE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*?)\s*$")

_COMMENT_NODE = "comment"
_DEFINE_NODE = "preproc_def"
_IFDEF_NODE = "preproc_ifdef"

## WHICH FILES OWN OPTIONS. A heuristic, and named as one — `origin` records it, so a consumer
## can tell a declared configuration header from a guessed one rather than being handed both as
## fact. Matching on the FILE NAME is what keeps a commented-out define in ordinary source out
## of the layer: that is dead code, a different finding, and mixing the two would make every
## answer here less trustworthy.
_CONFIG_NAME = re.compile(r"config", re.IGNORECASE)
_HEADER_SUFFIXES = (".h", ".hpp", ".hh", ".hxx")

ORIGIN_DECLARED = "declared"
ORIGIN_HEURISTIC = "heuristic"


## @brief Whether a repo-relative path looks like a configuration header.
## @param rel Repo-relative path, any separator.
## @return True when the name carries "config" and the suffix is a C header.
## @version 1
## @dg_internal
def looks_like_config_header(rel: str) -> bool:
    """NAME-MATCHED, NOT CONTENT-SNIFFED. A header full of commented-out defines might be a
    config header or might be a file somebody abandoned, and guessing from content would put
    the second into an answer about the first.

    @brief Config-header test.
    @return True for a plausibly option-owning header.
    @version 1
    """
    lower = rel.lower()
    if not lower.endswith(_HEADER_SUFFIXES):
        return False
    name = lower.rsplit("/", 1)[-1]
    return bool(_CONFIG_NAME.search(name))


## @brief The name a `preproc_def` node defines.
## @param node A `preproc_def` node.
## @return The macro name, or "".
## @version 1
## @dg_internal
def _define_name(node: Any) -> str:
    """@brief The defined macro's name.
    @return The name, or "".
    @version 1
    """
    field = node.child_by_field_name("name")
    return "" if field is None else field.text.decode("utf-8", "replace")


## @brief The symbol an `#ifndef X` / `#define X` include guard protects.
## @param node A `preproc_ifdef` node.
## @return The guarded symbol, or "" when this is not an include guard.
## @version 1
## @dg_internal
def _guard_name(node: Any) -> str:
    """STRUCTURAL, NOT A `_H` SUFFIX RULE — the same discriminator `kconfig_gates` uses, for
    the same reason. The guarded block DEFINES THE SAME SYMBOL it just tested, which no
    configuration option ever does: an option is set by somebody else.

    A suffix test is wrong twice over. mbedtls ships `MBEDTLS_THREADING_C`-style feature macros
    a suffix rule cannot see, and plenty of real guards do not end in `_H` at all.

    MEASURED ON mbedtls: 39 of 1,206 "on" rows were include guards before this. Nobody asks
    whether MBEDTLS_CONFIG_H is enabled by default, and left in they rank EXACT on their own
    names in the discovery surface — the noise `kconfig_gates` already had to clean out once.

    @brief The guarded symbol, if any.
    @return The name, or "".
    @version 1
    """
    field = node.child_by_field_name("name")
    if field is None:
        return ""
    guarded = field.text.decode("utf-8", "replace")
    for child in node.children:
        if child.type == _DEFINE_NODE and _define_name(child) == guarded:
            return guarded
    return ""


## @brief Create the configuration-default table.
## @param conn Open connection.
## @return None.
## @version 1
## @req REQ-DDB-PIPE-015
def ensure_config_defaults_table(conn: sqlite3.Connection) -> None:
    """CREATED EVEN AT ZERO ROWS, like `kconfig_gates`, and for the same reason: an empty table
    means "we looked and this repo decides nothing here", an absent one means "this layer never
    ran", and a consumer separating a correct negative from a detector failure needs both.

    @brief Create config_defaults.
    @version 1
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS config_defaults (
            macro     TEXT NOT NULL,
            state     TEXT NOT NULL {check("config_defaults", "state")},
            value     TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL,
            line      INTEGER NOT NULL,
            doc       TEXT NOT NULL DEFAULT '',
            origin    TEXT NOT NULL,
            UNIQUE(macro, file_path, line)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_config_defaults_macro ON config_defaults(macro)")
    conn.commit()


## @brief One file's configuration-option defaults.
## @version 1
class _DefaultsHarvester(Harvester):
    """Rowid-free, so it caches on the file's content sha like every other stage.

    Runs over EVERY indexed file rather than only headers: the path filter lives at import
    time, where the `path` table resolves a rowid to a name. Filtering here would need the
    harvester to know its own path, which the interface deliberately does not give it.

    @brief Per-file config-default harvester.
    @version 1
    """

    stage = STAGE_CONFIG_DEFAULTS
    stage_version = 1
    label = "config defaults"

    ## @brief Harvest one file's option defaults.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's raw bytes (unused; the tree carries the text).
    ## @return List of [macro, state, value, line] entries.
    ## @version 1
    ## @req REQ-DDB-PIPE-015
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """Returns LISTS, not tuples, so a cache hit and a fresh parse are structurally
        identical — the payload round-trips through JSON, where a tuple returns as a list.

        @brief Walk one file's defines and commented-out defines.
        @return Default entries for this file.
        @version 1
        """
        found: list[list[Any]] = []
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == _COMMENT_NODE:
                entry = _commented_define(node)
                if entry:
                    found.append(entry)
            elif node.type == _IFDEF_NODE:
                ## THE GUARD'S OWN DEFINE IS SKIPPED, NOT THE BLOCK IT WRAPS. Nearly every
                ## configuration header is wrapped in one, so descending is mandatory — what
                ## is dropped is the single `#define FOO_H` matching the `#ifndef FOO_H`.
                ##
                ## COMPARED BY NAME, NOT BY NODE IDENTITY. The parser hands out a fresh Python
                ## wrapper on every child access, so `child is guard_node` is never true and an
                ## identity filter silently keeps the guard it was written to drop.
                guard = _guard_name(node)
                stack.extend(
                    child
                    for child in node.children
                    if not (guard and child.type == _DEFINE_NODE and _define_name(child) == guard)
                )
                continue
            elif node.type == _DEFINE_NODE:
                entry = _active_define(node)
                if entry:
                    found.append(entry)
            stack.extend(node.children)
        return found


## @brief Read a commented-out define out of a comment node.
## @param node A `comment` node.
## @return [macro, state, value, line] or None.
## @version 1
## @dg_internal
def _commented_define(node: Any) -> list[Any] | None:
    """SINGLE-LINE COMMENTS ONLY. A block comment spanning an explanation and a define is prose
    about the option, not the option's state, and reading a define out of the middle of one
    would record a sentence as a configuration decision.

    @brief Parse a commented-out define.
    @return The entry, or None.
    @version 1
    """
    text = node.text.decode("utf-8", "replace")
    if "\n" in text:
        return None
    match = _COMMENTED.match(text)
    if match is None:
        return None
    return [match.group(1), CONFIG_DEFAULT_OFF, match.group(2), node.start_point[0] + 1]


## @brief Read an active define out of a preproc_def node.
## @param node A `preproc_def` node.
## @return [macro, state, value, line] or None.
## @version 1
## @dg_internal
def _active_define(node: Any) -> list[Any] | None:
    """@brief Parse an active define.
    @return The entry, or None.
    @version 1
    """
    text = node.text.decode("utf-8", "replace").split("\n", 1)[0]
    match = _ACTIVE.match(text)
    if match is None:
        return None
    return [match.group(1), CONFIG_DEFAULT_ON, match.group(2), node.start_point[0] + 1]


## @brief The config-default stage's harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-PIPE-015
def defaults_harvester() -> Harvester:
    """ONE CONSTRUCTION SITE, so the shared parse pass's cache key and this stage's key are
    equal by construction rather than by two edits staying in step.

    @brief Build this stage's harvester.
    @version 1
    """
    return _DefaultsHarvester()


## @brief Flatten a harvest result into insertable rows, keeping only config headers.
## @param conn Open connection (for the path table).
## @param harvested (path_rowid, payload) pairs from run_harvest.
## @param declared Repo-relative config headers the operator stated, if any.
## @return (macro, state, value, file_path, line, doc, origin) tuples.
## @version 1
## @dg_internal
def _rows_from_harvest(
    conn: sqlite3.Connection, harvested: list[tuple[int, Any]], declared: frozenset[str]
) -> list[tuple[str, str, str, str, int, str, str]]:
    """Stores the file NAME rather than the rowid, because doxygen reassigns rowids on every
    run and a stored one would silently re-point at a different file after a rebuild.

    @brief Turn payloads into config-default rows.
    @return Insertable tuples.
    @version 1
    """
    names = dict(conn.execute("SELECT rowid, name FROM path").fetchall())
    rows: list[tuple[str, str, str, str, int, str, str]] = []
    for path_rowid, payload in harvested:
        rel = str(names.get(path_rowid, ""))
        stated = rel in declared
        if not stated and not looks_like_config_header(rel):
            continue
        origin = ORIGIN_DECLARED if stated else ORIGIN_HEURISTIC
        for macro, state, value, line in payload or ():
            rows.append((str(macro), str(state), str(value), rel, int(line), "", origin))
    return rows


## @brief Fill config_defaults from the indexed source tree.
## @param db_path The index.
## @param repo_root The target tree.
## @param cache Index cache, when one is in use.
## @param declared Repo-relative configuration headers the operator stated.
## @return Row count.
## @version 1
## @req REQ-DDB-PIPE-015
def import_config_defaults(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
    declared: frozenset[str] = frozenset(),
) -> int:
    """@brief Harvest and store configuration-option defaults.
    @return Row count.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_config_defaults_table(conn)
        harvested = run_harvest(conn, repo_root, defaults_harvester(), cache)
        rows = _rows_from_harvest(conn, harvested, declared)
        conn.executemany(
            "INSERT OR IGNORE INTO config_defaults"
            "(macro, state, value, file_path, line, doc, origin) VALUES(?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    off = sum(1 for row in rows if row[1] == CONFIG_DEFAULT_OFF)
    logger.info(
        "config defaults: %d option(s) over %d header(s) — %d off by default, %d on",
        len(rows),
        len({row[3] for row in rows}),
        off,
        len(rows) - off,
    )
    return len(rows)
