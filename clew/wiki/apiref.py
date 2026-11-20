# SPDX-License-Identifier: MIT
"""The public-API reference: one page per declared public header, from the index (PAPI, 2.0.0).

OWNER (Q/A 2026-11-19): a full public-API reference in the wiki, scoped to DECLARED public headers
(`wiki.api: [include/**]`) and generated from the index. Per header:

| section | what it holds |
|---|---|
| Functions | public functions declared there, with full signatures |
| Enums | each enumeration with its values and their initialisers |
| Types | typedefs; a function-pointer typedef is marked a HOOK POINT |
| Macros | `#define`s with their values |
| Variables | public variables |
| Classes | each class / struct declared there, with its public members |

EXCLUDED: a private or protected member (`prot` 1 or 2), and a symbol whose documentation carries
doxygen's `\\internal` section (the index keeps it, since the build forces INTERNAL_DOCS; it is not
API). A public `@utility` function IS public API — the tag is about requirements, not visibility.
Not doxygen parity: no class diagrams, no `\\defgroup` groups.

Off unless declared: no `wiki.api`, no tab.

@brief Build the public-API reference pages.
@version 1
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

## The member kinds the reference shows, in the page's section order.
_SECTIONS = (
    ("function", "Functions"),
    ("enumeration", "Enums"),
    ("typedef", "Types"),
    ("macro definition", "Macros"),
    ("variable", "Variables"),
)
_PUBLIC = 0


## @brief One public symbol of a header.
## @version 1
@dataclass(frozen=True)
class Symbol:
    """@brief Kind, name, scope, signature, brief, detail, line, value (initialiser)."""

    kind: str
    name: str
    scope: str
    signature: str
    brief: str
    detail: str
    line: int
    value: str = ""


## @brief Each declared public header's public symbols, from the index.
## @param conn Open connection.
## @param globs `wiki.api`: the public-header globs.
## @return {header path: symbols in line order}; {} when nothing is declared.
## @version 1
## @req REQ-DDB-WIKI-053
def header_symbols(conn: Any, globs: tuple[str, ...]) -> dict[str, list[Symbol]]:
    """@brief Read the API. @return Symbols by header."""
    if not globs:
        return {}
    out: dict[str, list[Symbol]] = {}
    for rowid, rel in conn.execute("SELECT rowid, name FROM path WHERE type = 1 ORDER BY name"):
        if not any(fnmatch.fnmatch(rel, g) for g in globs):
            continue
        rows = conn.execute(
            "SELECT kind, name, COALESCE(scope, ''), COALESCE(definition, ''), "
            "COALESCE(argsstring, ''), COALESCE(initializer, ''), COALESCE(briefdescription, ''), "
            "COALESCE(detaileddescription, ''), line, COALESCE(type, '') FROM memberdef "
            "WHERE file_id = ? AND COALESCE(prot, 0) = ? ORDER BY line",
            (rowid, _PUBLIC),
        )
        symbols = [
            Symbol(
                kind,
                name,
                scope,
                _signature(kind, definition, args, type_, name),
                doc_text(brief),
                doc_text(detail),
                int(line or 0),
                value.strip(),
            )
            for kind, name, scope, definition, args, value, brief, detail, line, type_ in rows
            if "<internal>" not in detail
        ]
        if symbols:
            out[str(rel)] = symbols
    return out


## @brief A symbol's signature as the header states it.
## @param kind The member kind.
## @param definition Doxygen's definition text.
## @param args The argument string.
## @param type_ The declared type.
## @param name The symbol's name.
## @return Signature.
## v2 (found on entropic's index): a function-pointer typedef reads as C, arguments once.
## @version 2
## @utility
def _signature(kind: str, definition: str, args: str, type_: str = "", name: str = "") -> str:
    """A FUNCTION IS ITS DEFINITION PLUS ARGUMENTS; a macro or enum value is its name alone. A
    FUNCTION-POINTER TYPEDEF is stored by doxygen as `typedef int(*) cb_t(int x)` — arguments
    already in the definition — so it is rebuilt as the C a reader writes: `typedef int(*cb_t)(int x)`.

    @brief Signature.
    @return Text.
    """
    if kind == "typedef" and type_.replace(" ", "").endswith("(*)"):
        return " ".join(f"typedef {type_.rstrip()[:-1]}{name}){args}".split())
    if kind == "function":
        return " ".join(f"{definition}{args}".split())
    return " ".join(definition.split())


## Guard tags that are traceability, not documentation, and the doxygen sections that carry them.
_GUARD_TAG = re.compile(r"@(?:req|utility|callback|version)\b[^@\n]*?(?=@|$)", re.M)
_VERSION_SECT = re.compile(r'<simplesect kind="version">.*?</simplesect>', re.S)


## @brief A doc comment's prose: doxygen XML removed, and the guard's traceability tags with it.
## @param xml Doxygen's description XML.
## @return Plain text.
## @version 1
## @req REQ-DDB-WIKI-053
def doc_text(xml: str) -> str:
    """FOUND ON ENTROPIC'S INDEX: `@req REQ-TYPE-002` and the `@version` simplesect read as API
    prose. Traceability belongs to the requirement pages; an API reader gets the description.

    @brief Clean a description.
    @return Text.
    """
    from ..query._common import strip_xml

    text = strip_xml(_VERSION_SECT.sub("", xml or ""))
    return " ".join(_GUARD_TAG.sub("", text).split())


## @brief The classes and structs a header declares, with their documentation.
## @param conn Open connection.
## @param rel The header.
## @return (name, kind, brief) in line order.
## @version 1
## @utility
def header_classes(conn: Any, rel: str) -> list[tuple[str, str, str]]:
    """@brief Public compounds of a file. @return Rows."""
    return [
        (str(n), str(k), doc_text(str(b or "")))
        for n, k, b in conn.execute(
            "SELECT c.name, c.kind, c.briefdescription FROM compounddef c JOIN path p "
            "ON p.rowid = c.file_id WHERE p.name = ? AND c.kind IN ('class', 'struct', 'union') "
            "AND COALESCE(c.prot, 0) = 0 ORDER BY c.line",
            (rel,),
        )
    ]


## @brief One header's reference page body.
## @param rel The header.
## @param symbols Its public symbols.
## @param classes Its classes / structs (name, kind, brief).
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-053
def api_html(rel: str, symbols: list[Symbol], classes: list[tuple[str, str, str]] = ()) -> str:
    """CLASS MEMBERS GO UNDER THEIR CLASS (a symbol whose scope names a class declared here); the
    rest by kind; enum values under their enum.

    @brief Render a header.
    @return HTML.
    """
    class_names = {name for name, _k, _b in classes} | {
        s.scope for s in symbols if s.scope and s.kind != "enumvalue" and "::" in s.scope
    }
    top = [s for s in symbols if s.scope not in class_names and s.kind != "enumvalue"]
    values = {}
    for s in symbols:
        if s.kind == "enumvalue":
            values.setdefault(s.scope, []).append(s)
    parts = [f'<p class="where"><code>{escape(rel)}</code></p>']
    for kind, heading in _SECTIONS:
        items = [s for s in top if s.kind == kind]
        if items:
            parts.append(f"<h2>{heading}</h2>" + "".join(_entry(s, values) for s in items))
    briefs = {name: brief for name, _k, brief in classes}
    for scope in sorted(class_names):
        members = [s for s in symbols if s.scope == scope]
        if not members and scope not in briefs:
            continue
        brief = f"<p>{escape(briefs.get(scope, ''))}</p>" if briefs.get(scope) else ""
        parts.append(
            f'<h2 class="api-class"><code>{escape(scope)}</code></h2>{brief}'
            + "".join(_entry(s, values) for s in members)
        )
    return "".join(parts)


## @brief One symbol's entry: signature, hook mark, brief, detail, values.
## @param symbol The symbol.
## @param values Enum name → its values.
## @return HTML.
## @version 1
## @utility
def _entry(symbol: Symbol, values: dict[str, list[Symbol]]) -> str:
    """A FUNCTION-POINTER TYPEDEF IS A HOOK POINT: a type a caller supplies a function for.

    @brief Entry.
    @return HTML.
    """
    hook = (
        ' <span class="hook">hook point</span>'
        if symbol.kind == "typedef" and "(*" in symbol.signature.replace(" ", "")
        else ""
    )
    head = f'<div class="api-entry" id="api-{escape(symbol.name)}"><p><code>{escape(symbol.signature or symbol.name)}</code>{hook}</p>'
    if symbol.kind == "macro definition" and symbol.value:
        head += f"<p>Value: <code>{escape(symbol.value)}</code></p>"
    body = "".join(f"<p>{escape(t)}</p>" for t in (symbol.brief, symbol.detail) if t)
    rows = "".join(
        f"<li><code>{escape(v.name)}</code> {escape(v.value)}</li>"
        for v in values.get(symbol.name, ())
    )
    return head + body + (f'<ul class="enum-values">{rows}</ul>' if rows else "") + "</div>"


## @brief Write the API tab: an index of headers and a page per header.
## @param db The index.
## @param globs `wiki.api`.
## @param source The Sphinx source directory.
## @return "api", or "" when nothing is declared or no header matched.
## @version 1
## @req REQ-DDB-WIKI-053
def api_pages(db: Path, globs: tuple[str, ...], source: Path) -> str:
    """@brief Write api.md and api-*.md. @return Page name or ""."""
    import re

    from ..query._common import connect

    with connect(db) as conn:
        headers = header_symbols(conn, globs)
        classes = {rel: header_classes(conn, rel) for rel in headers}
    if not headers:
        return ""
    items = []
    for rel, symbols in headers.items():
        name = "api-" + re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-")
        text = [
            "---",
            "orphan: true",
            "---",
            "",
            f"# {rel}",
            "",
            "```{raw} html",
            '<p class="crumbs"><a href="api.html">← API</a></p>',
            api_html(rel, symbols, classes[rel]),
            "```",
            "",
        ]
        (Path(source) / f"{name}.md").write_text("\n".join(text), encoding="utf-8")
        items.append(
            f'<li><a href="{name}.html"><code>{escape(rel)}</code></a> · {len(symbols)} symbols</li>'
        )
    index = [
        "# API",
        "",
        f"The public API: {len(headers)} declared public headers (`wiki.api`), from the index. "
        "Private members and `\\internal`-documented symbols are left out.",
        "",
        "```{raw} html",
        f'<ul class="api-headers">{"".join(items)}</ul>',
        "```",
        "",
    ]
    (Path(source) / "api.md").write_text("\n".join(index), encoding="utf-8")
    return "api"
