# SPDX-License-Identifier: MIT
"""kernel-doc comments, read into their own `kerneldoc` layer (S6; index only).

2.0.0 (owner 2026-11-17, "like kernel docs"; ruled INDEX-ONLY: `clew guard` keeps its doxygen
rules, because a kernel-style tree will never carry `@version` or `@req`). The format is the Linux
kernel's (Documentation/doc-guide/kernel-doc.rst), used across kernel-family C:

    /**
     * foo() - Short description.
     * @bar: Description of bar.
     *
     * Longer description.
     *
     * Context: Process context; takes and releases the device lock.
     * Return: 0 on success, a negative errno otherwise.
     */

A block is kernel-doc when its first line names the item followed by ` - ` (`foo()`,
`struct foo`, `union`, `enum`, `typedef`, or `DOC: Title`). A block carrying a doxygen command
(`@brief`, `\\brief`) is doxygen's and never read here, so a mixed tree is read twice by nobody.

ITS OWN TABLE, NEVER `memberdef`. Doxygen also reads these blocks and gets them wrong (`\\arg` is
one of its list commands, so `@arg:` lines leak into the brief); writing over doxygen's rows would
make the two readings indistinguishable. The dossier serves this layer beside them (P3).

Written from the specification; the kernel's own `scripts/kernel-doc` is GPL-2.0 and is neither
vendored nor copied.

@brief The kernel-doc layer.
@version 1
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ._common import logger, within_repo
from .indexcache import IndexCache, memoized

## Bumped whenever extraction changes, so a cached result from older logic is not reused.
KERNELDOC_STAGE_VERSION = 1
## The C-family files kernel-doc lives in.
_SUFFIXES = (".c", ".h")
## One `/** ... */` block (not `/***`).
_BLOCK = re.compile(r"/\*\*(?!\*)(.*?)\*/", re.S)
## The identification line: `foo() - summary`, `struct foo - summary`, `DOC: Title`.
_HEAD = re.compile(
    r"^(?:(?P<kind>struct|union|enum|typedef)\s+)?(?P<name>[A-Za-z_]\w*)(?P<fn>\(\))?\s*-\s+(?P<brief>.+)$"
)
_DOC = re.compile(r"^DOC:\s*(?P<brief>.+)$")
## `@name:` (a parameter or member) and the two documented sections the dossier serves.
_PARAM = re.compile(r"^@(?P<name>[A-Za-z_]\w*|\.\.\.):\s*(?P<text>.*)$")
_SECTION = re.compile(r"^(?P<name>Return|Returns|Context):\s*(?P<text>.*)$")
## Doxygen's commands: a block using one is doxygen's, not kernel-doc.
_DOXYGEN = re.compile(r"[@\\](?:brief|version|param|return|req|file|details)\b")

_DDL = """
CREATE TABLE IF NOT EXISTS kerneldoc (
    file_path TEXT NOT NULL,
    line INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    brief TEXT NOT NULL,
    params TEXT NOT NULL,
    returns TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS kerneldoc_name ON kerneldoc(name);
"""


## @brief The kernel-doc blocks of one C source text.
## @param text The file's text.
## @return One dict per block: line, kind, name, brief, params, returns, context, description.
## @version 1
## @req REQ-DDB-INDEX-009
def parse_kerneldoc(text: str) -> list[dict]:
    """@brief Read every kernel-doc block. @return Blocks."""
    out = []
    for match in _BLOCK.finditer(text):
        body = [re.sub(r"^\s*\* ?", "", raw).rstrip() for raw in match.group(1).splitlines()]
        while body and not body[0].strip():
            body.pop(0)
        if not body or _DOXYGEN.search(match.group(1)):
            continue
        block = _block(body)
        if block is not None:
            block["line"] = text.count("\n", 0, match.start()) + 1
            out.append(block)
    return out


## @brief One block's fields, or None when its first line does not identify a kernel-doc item.
## @param body The block's lines, comment furniture removed.
## @return The fields, or None.
## @version 1
## @dg_internal
def _block(body: list[str]) -> dict | None:
    """A PARAMETER OR SECTION CONTINUES onto following indented lines, as the format allows.

    @brief Parse one block.
    @return Fields or None.
    """
    head = body[0].strip()
    doc = _DOC.match(head)
    item = None if doc else _HEAD.match(head)
    if not (doc or item):
        return None
    fields: dict = {
        "kind": "doc"
        if doc
        else (item.group("kind") or ("function" if item.group("fn") else "item")),
        "name": "" if doc else item.group("name"),
        "brief": (doc or item).group("brief").strip(),
        "params": {},
        "returns": "",
        "context": "",
        "description": "",
    }
    _sections(body[1:], fields)
    fields["params"] = json.dumps(fields["params"])
    return fields


## @brief Fill parameters, sections and the free description from a block's lines.
## @param lines The lines after the identification line.
## @param fields The block, filled in place.
## @return None.
## @version 1
## @dg_internal
def _sections(lines: list[str], fields: dict) -> None:
    """@brief Read the body. @return None."""
    target: tuple[str, str] | None = None
    prose: list[str] = []
    for line in lines:
        stripped = line.strip()
        param, section = _PARAM.match(stripped), _SECTION.match(stripped)
        if param:
            target = ("params", param.group("name"))
            fields["params"][param.group("name")] = param.group("text").strip()
        elif section:
            key = "context" if section.group("name") == "Context" else "returns"
            target = (key, "")
            fields[key] = section.group("text").strip()
        elif stripped and target and line.startswith((" ", "\t")):
            _append(fields, target, stripped)
        else:
            target = None
            prose.append(stripped)
    fields["description"] = "\n".join(prose).strip()


## @brief Append a continuation line to the field it continues.
## @param fields The block.
## @param target (field, parameter name).
## @param text The continuation.
## @return None.
## @version 1
## @dg_internal
def _append(fields: dict, target: tuple[str, str], text: str) -> None:
    """@brief Continue a field. @return None."""
    key, name = target
    if key == "params":
        fields["params"][name] = f"{fields['params'][name]} {text}".strip()
    else:
        fields[key] = f"{fields[key]} {text}".strip()


## @brief One file's kernel-doc blocks, through the content-keyed cache.
## @param cache The index cache, or None.
## @param repo_root The repository.
## @param rel The file.
## @return The blocks.
## @version 1
## @dg_internal
def kerneldoc_of(cache: IndexCache | None, repo_root: Path, rel: str) -> list[dict]:
    """@brief Memoized read. @return Blocks."""
    path = repo_root / rel

    def read() -> list[dict]:
        try:
            return parse_kerneldoc(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return []

    return memoized(cache, rel, path, "kerneldoc", KERNELDOC_STAGE_VERSION, rel, read) or []


## @brief Record every indexed C file's kernel-doc blocks.
## @param db_path The index.
## @param repo_root The repository.
## @param cache The run's index cache, or None.
## @return Blocks recorded.
## @version 1
## @req REQ-DDB-INDEX-009
def ingest_kerneldoc(db_path: Path, repo_root: Path, cache: IndexCache | None = None) -> int:
    """THE TABLE IS ALWAYS CREATED, empty in a tree with no kernel-doc.

    @brief Build the kernel-doc layer.
    @return Row count.
    """
    from .filedocs import _indexed_files

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_DDL)
        conn.execute("DELETE FROM kerneldoc")
        resolved: dict[str, str] = {}
        rows = []
        for rel in _indexed_files(conn):
            if not rel.endswith(_SUFFIXES):
                continue
            if (
                within_repo(
                    repo_root / rel, repo_root, setting=f"kernel-doc of {rel}", memo=resolved
                )
                is None
            ):
                continue
            rows += [_row(rel, b) for b in kerneldoc_of(cache, repo_root, rel)]
        conn.executemany(_INSERT, rows)
        conn.commit()
    finally:
        conn.close()
    logger.info("kerneldoc: %d block(s)", len(rows))
    return len(rows)


_INSERT = (
    "INSERT INTO kerneldoc (file_path, line, kind, name, brief, params, returns, context, "
    "description) VALUES (?,?,?,?,?,?,?,?,?)"
)


## @brief One block as a table row.
## @param rel Its file.
## @param b The block.
## @return The row.
## @version 1
## @dg_internal
def _row(rel: str, b: dict) -> tuple:
    """@brief Row. @return Tuple."""
    return (
        rel,
        b["line"],
        b["kind"],
        b["name"],
        b["brief"],
        b["params"],
        b["returns"],
        b["context"],
        b["description"],
    )


## @brief Rewrite one edited file's kernel-doc rows (the fast tier).
## @param conn Open connection, inside the fast tier's transaction.
## @param repo_root The repository.
## @param rel The edited file.
## @param cache The index cache.
## @return None.
## @version 1
## @req REQ-DDB-INDEX-006
def refresh_kerneldoc(
    conn: sqlite3.Connection, repo_root: Path, rel: str, cache: IndexCache
) -> None:
    """@brief The same rows `ingest_kerneldoc` writes, for one file. @return None."""
    if not rel.endswith(_SUFFIXES):
        return
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'kerneldoc'").fetchone() is None:
        return
    conn.execute("DELETE FROM kerneldoc WHERE file_path = ?", (rel,))
    conn.executemany(_INSERT, [_row(rel, b) for b in kerneldoc_of(cache, repo_root, rel)])
