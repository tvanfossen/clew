# SPDX-License-Identifier: MIT
"""Every JS/TS property key a symbol defines or assigns, with its holder (F1-mm; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mattermost F1, Q1 m2): `buildRequestOptions` writes
`requestOptions.retryPolicyConfiguration = {retryLimit: 0}`, and the default it overrides is the
`retryPolicyConfiguration: {retryLimit: 3, ...}` literal in `NetworkManager.DEFAULT_CONFIG`. Every
winning cell followed that key with grep; every losing index cell had no route from one to the
other. The shared-key layer is the C/Python analogue (accessor calls) and holds 0 rows there.

A ROW PER KEY SITE: an object-literal key (`pair`, shorthand property) or the property of an
assignment's member-expression target (`x.key = ...`), with its line and its HOLDER, the nearest
enclosing named construct (function, method, variable, class field). Rowid-free, so it caches on
content like every stage, and a non-JS file yields an empty payload.

@brief The JS/TS property-key layer.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest
from .indexcache import IndexCache
from .vocabulary import STAGE_PROPERTY_KEYS

## Node types that name a holder, and the field that carries the name.
_HOLDERS = {
    "function_declaration": "name",
    "generator_function_declaration": "name",
    "method_definition": "name",
    "variable_declarator": "name",
    "public_field_definition": "name",
    "field_definition": "property",
}
## Key spellings a literal pair can carry; a computed key names nothing at parse time.
_KEY_NODES = ("property_identifier", "string", "number")

## Payload kinds.
KIND_LITERAL = "literal"
KIND_ASSIGN = "assign"


## @brief The key text a pair or member target names, or "".
## @param node The key or property node.
## @return The key.
## @version 1
## @dg_internal
def _key_text(node: Any) -> str:
    """@brief Read a key. @return Text or ""."""
    if node is None or node.type not in _KEY_NODES:
        return ""
    text = node.text.decode("utf-8", "replace")
    return text[1:-1] if node.type == "string" else text


## @brief The name a holder node declares, or None when it is not a holder.
## @param node A node.
## @return The name, or None.
## @version 1
## @dg_internal
def _holder_name(node: Any) -> str | None:
    """@brief Name a holder. @return Name or None."""
    field = _HOLDERS.get(node.type)
    named = node.child_by_field_name(field) if field else None
    return named.text.decode("utf-8", "replace") if named is not None else None


## @brief The key one node defines or assigns, and its kind.
## @param node A node.
## @return (key, kind), or None.
## @version 1
## @dg_internal
def _site(node: Any) -> tuple[str, str] | None:
    """`pair` (`key: v`) and shorthand (`{key}`) are literal keys; an assignment whose left side
    is a member expression assigns its property. Anything else names no key.

    @brief Classify one node.
    @return (key, kind) or None.
    """
    found = None
    if node.type == "pair":
        found = (_key_text(node.child_by_field_name("key")), KIND_LITERAL)
    elif node.type == "shorthand_property_identifier":
        found = (node.text.decode("utf-8", "replace"), KIND_LITERAL)
    elif node.type == "assignment_expression":
        left = node.child_by_field_name("left")
        if left is not None and left.type == "member_expression":
            found = (_key_text(left.child_by_field_name("property")), KIND_ASSIGN)
    return found if found and found[0] else None


## @brief Per-file property-key harvester.
## @version 1
class _PropertyKeyHarvester(Harvester):
    """@brief Property-key harvester.
    @version 1
    """

    stage = STAGE_PROPERTY_KEYS
    stage_version = 1
    label = "property keys"

    ## @brief Harvest one file's key sites.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's bytes (unused).
    ## @return [[key, line, holder, kind], ...], or [] for a non-JS file.
    ## @version 1
    ## @req REQ-DDB-INDEX-011
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """A WALK THAT CARRIES THE HOLDER: each node is visited with the nearest enclosing holder's
        name, so a key nested three literals deep inside `DEFAULT_CONFIG` is still held by it.

        @brief Walk the tree.
        @return Rows.
        """
        from .jsast import is_js_tree

        if not is_js_tree(tree):
            return []
        found: list[list[Any]] = []
        stack: list[tuple[Any, str]] = [(tree.root_node, "")]
        while stack:
            node, holder = stack.pop()
            here = _holder_name(node) or holder
            site = _site(node)
            if site is not None and holder:
                found.append([site[0], node.start_point[0] + 1, holder, site[1]])
            stack.extend((child, here) for child in node.children)
        return sorted(found, key=lambda r: (r[1], r[0]))


## @brief The property-key stage's harvester.
## @return A Harvester; built the same way everywhere so the cache key agrees.
## @version 1
## @req REQ-DDB-INDEX-011
def property_key_harvester() -> Harvester:
    """ONE CONSTRUCTION SITE, shared with the plan's parse pass. @brief Build it. @return It."""
    return _PropertyKeyHarvester()


## @brief Create the property_keys table.
## @param conn Open connection.
## @return None.
## @version 1
## @req REQ-DDB-INDEX-011
def ensure_property_keys_table(conn: sqlite3.Connection) -> None:
    """Created unconditionally, so a tree with no JS/TS yields an EMPTY table, not an absent one.

    @brief Create the table.
    @return None.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS property_keys (
          path_rowid INTEGER NOT NULL REFERENCES path(rowid),
          key TEXT NOT NULL,
          line INTEGER NOT NULL,
          holder TEXT NOT NULL,
          kind TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_property_keys_key ON property_keys(key);
        CREATE INDEX IF NOT EXISTS idx_property_keys_path ON property_keys(path_rowid, line);
        """
    )


## @brief Record every indexed JS/TS file's property-key sites.
## @param db_path The index.
## @param repo_root The repository.
## @param cache The run's index cache, or None.
## @return Rows recorded.
## @version 1
## @req REQ-DDB-INDEX-011
def import_property_keys(db_path: Path, repo_root: Path, cache: IndexCache | None = None) -> int:
    """@brief Fill property_keys. @return Row count."""
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_property_keys_table(conn)
        conn.execute("DELETE FROM property_keys")
        rows = [
            (src, key, line, holder, kind)
            for src, payload in run_harvest(conn, repo_root, property_key_harvester(), cache)
            for key, line, holder, kind in payload or ()
        ]
        conn.executemany(
            "INSERT INTO property_keys (path_rowid, key, line, holder, kind) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("property keys: %d site(s)", len(rows))
    return len(rows)
