# SPDX-License-Identifier: MIT
"""External node sources: model files whose entries are trace targets (1.4.0 W7, #67).

Code generated from a model — a TOML key space, a JSON command table, a YAML topic list — should
trace to the MODEL ENTRY, not stop at a generated setter. A source is declared in `wiki.sources`
by its file, the dotted path to its items, and the fields holding each item's id, documentation
and (optionally) the requirements it serves:

  * items that are a MAPPING take their keys as ids (`[keys."net.timeout"]` → `net.timeout`);
  * items that are a LIST take the declared `id` field of each entry — or, when an entry is a
    bare scalar (a key manifest such as `["also", "chain"]`), the scalar itself.

A node is addressed as `<source>:<id>`. A function names the node it realises with a
`@node <source>:<id>` tag in its doc comment; `node_references` reads those from the index.

The format is the file's suffix — `.json`, `.toml`, `.yaml` / `.yml`. Nothing is guessed: an
unknown suffix, a missing file, an items path that does not resolve and a duplicated id are each a
named problem.

@brief Load external node sources and the functions that reference them.
@version 2
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists
from .config import SourceSpec

## A `@node <source>:<id>` tag: the FIRST WORD of a doc-comment line, as doxygen reads a command
## (after indentation and comment markers). A sentence that mentions the tag references nothing.
_NODE_TAG = re.compile(r"^[\s#*/!<]*@node\s+([\w.-]+:[^\s,;`]+)", re.MULTILINE)


## @brief One entry of an external source.
## @version 1
@dataclass(frozen=True)
class Node:
    """@brief Source name, id, doc, file and served requirements. @version 1"""

    source: str
    id: str
    doc: str
    file: str
    requirements: tuple[str, ...] = ()

    ## @brief The node's address, `<source>:<id>`.
    ## @return The address.
    ## @version 1
    ## @req REQ-DDB-WIKI-004
    @property
    def ref(self) -> str:
        """@brief Address. @return `<source>:<id>`."""
        return f"{self.source}:{self.id}"


## @brief Every node of every declared source.
## @param repo_root The repository (source paths are relative to it).
## @param specs The declared sources.
## @return (nodes, problems).
## @version 1
## @req REQ-DDB-WIKI-004
def load_nodes(repo_root: Path, specs: tuple[SourceSpec, ...]) -> tuple[list[Node], list[str]]:
    """@brief Load all sources. @return Nodes and problems."""
    nodes: list[Node] = []
    problems: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        try:
            items = _items(_parse(Path(repo_root) / spec.path), spec.items)
        except (OSError, ValueError) as exc:
            problems.append(f"source {spec.name!r} ({spec.path}): {exc}")
            continue
        for node in _nodes(spec, items, problems):
            if node.ref in seen:
                problems.append(f"source {spec.name!r}: id {node.id!r} is declared twice")
                continue
            seen.add(node.ref)
            nodes.append(node)
    return nodes, problems


## @brief The functions whose doc comment names each node, from the index.
## @param db The index.
## @return {node address: function names, sorted}.
## v2: only a line-leading tag counts (a prose mention in clew's own tests was read as one).
## @version 2
## @req REQ-DDB-WIKI-004
def node_references(db: Path | str) -> dict[str, tuple[str, ...]]:
    """@brief Read `@node` tags. @return References."""
    refs: dict[str, set[str]] = {}
    with connect(db) as conn:
        if not table_exists(conn, "memberdef"):
            return {}
        rows = conn.execute(
            "SELECT name, briefdescription, detaileddescription FROM memberdef "
            "WHERE kind = 'function' AND (briefdescription LIKE '%@node%' "
            "OR detaileddescription LIKE '%@node%')"
        )
        for name, brief, detail in rows:
            for ref in _NODE_TAG.findall(f"{brief or ''}\n{detail or ''}"):
                refs.setdefault(ref, set()).add(str(name))
    return {ref: tuple(sorted(names)) for ref, names in sorted(refs.items())}


## @brief Parse a source file by its suffix.
## @param path The file.
## @return The parsed document.
## @version 1
## @dg_internal
def _parse(path: Path) -> Any:
    """@brief Read JSON, TOML or YAML. @return Document."""
    suffix = path.suffix.lower()
    if not path.is_file():
        raise ValueError("file does not exist")
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".toml":
        from ..tomlcompat import require_toml_module

        return require_toml_module().loads(text)
    if suffix in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text)
    raise ValueError(f"unknown format {suffix!r} (json, toml, yaml)")


## @brief Follow a dotted items path into a document.
## @param doc The document.
## @param dotted The path; empty means the whole document.
## @return The items (a mapping or a list).
## @version 1
## @dg_internal
def _items(doc: Any, dotted: str) -> Any:
    """@brief Resolve the items path. @return Items."""
    for part in [p for p in dotted.split(".") if p]:
        if not isinstance(doc, dict) or part not in doc:
            raise ValueError(f"items path {dotted!r} does not resolve at {part!r}")
        doc = doc[part]
    if not isinstance(doc, (dict, list)):
        raise ValueError(f"items path {dotted!r} is neither a mapping nor a list")
    return doc


## @brief The nodes of one source's items.
## @param spec The source.
## @param items A mapping (keys are ids) or a list (the id field names each).
## @param problems Accumulated problems; appended to.
## @return Nodes.
## v2: a scalar list entry is its own id.
## @version 2
## @dg_internal
def _nodes(spec: SourceSpec, items: Any, problems: list[str]) -> list[Node]:
    """@brief Build nodes. @return Nodes."""
    pairs = items.items() if isinstance(items, dict) else ((None, e) for e in items)
    out = []
    for key, entry in pairs:
        fields = entry if isinstance(entry, dict) else {}
        node_id = key if key is not None else _entry_id(entry, fields, spec.id)
        if node_id is None or node_id == "":
            problems.append(f"source {spec.name!r}: an entry has no `{spec.id or 'id'}` field")
            continue
        reqs = fields.get(spec.req) if spec.req else None
        out.append(
            Node(
                source=spec.name,
                id=str(node_id),
                doc=str(fields.get(spec.doc) or ""),
                file=spec.path,
                requirements=tuple(str(r) for r in (reqs if isinstance(reqs, list) else [])),
            )
        )
    return out


## @brief The id of one list entry.
## @param entry The entry.
## @param fields The entry as a mapping ({} for a scalar).
## @param id_field The declared id field.
## @return The id, or None.
## @version 1
## @dg_internal
def _entry_id(entry: Any, fields: dict[str, Any], id_field: str) -> Any:
    """@brief A scalar is its own id; a mapping names it. @return Id or None."""
    if isinstance(entry, (str, int, float)) and not isinstance(entry, bool):
        return entry
    return fields.get(id_field)
