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
    ## Entropic's gaps 1 and 2: the description, structured (params, returns, declared fields).
    doc: "Doc | None" = None


## @brief A symbol's documentation, structured as doxygen stored it (entropic's gaps 1 and 2).
## @version 1
@dataclass(frozen=True)
class Doc:
    """@brief Prose, parameters (name, direction, text), returns, return values, declared fields."""

    prose: str = ""
    params: tuple[tuple[str, str, str], ...] = ()
    returns: tuple[str, ...] = ()
    retvals: tuple[tuple[str, str], ...] = ()
    fields: tuple[tuple[str, str], ...] = ()


## @brief A class or struct a header declares, with its place in the hierarchy (gap 3).
## @version 1
@dataclass(frozen=True)
class ClassInfo:
    """@brief Name, kind, brief, the classes it inherits from, and those deriving from it."""

    name: str
    kind: str
    brief: str
    bases: tuple[str, ...] = ()
    derived: tuple[str, ...] = ()


## @brief Each declared public header's public symbols, from the index.
## @param conn Open connection.
## @param globs `wiki.api`: the public-header globs.
## @param tags Tags the repository declares (`guard.validate.extra_tags`), shown as fields.
## @return {header path: symbols in line order}; {} when nothing is declared.
## v2 (entropic's gaps 1 and 2): each symbol carries its structured `doc`.
## @version 2
## @req REQ-DDB-WIKI-053
def header_symbols(
    conn: Any, globs: tuple[str, ...], tags: tuple[str, ...] = ()
) -> dict[str, list[Symbol]]:
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
        symbols = []
        for kind, name, scope, definition, args, value, brief, detail, line, type_ in rows:
            if "<internal>" in detail:
                continue
            doc = parse_doc(detail, tags)
            sig = _signature(kind, definition, args, type_, name)
            symbols.append(
                Symbol(
                    kind,
                    name,
                    scope,
                    sig,
                    doc_text(brief),
                    doc.prose,
                    int(line or 0),
                    value.strip(),
                    doc,
                )
            )
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


## @brief The classes and structs a header declares, with their documentation and hierarchy.
## @param conn Open connection.
## @param rel The header.
## @return ClassInfo in line order.
## v2 (entropic's gap 3): bases and derived classes, from the index's `compoundref`.
## @version 2
## @utility
def header_classes(conn: Any, rel: str) -> list[ClassInfo]:
    """AN INDEX WITHOUT `compoundref` shows no hierarchy rather than failing.

    @brief Public compounds of a file.
    @return Classes.
    """
    from ..query._common import table_exists

    rows = conn.execute(
        "SELECT c.rowid, c.name, c.kind, c.briefdescription FROM compounddef c JOIN path p "
        "ON p.rowid = c.file_id WHERE p.name = ? AND c.kind IN ('class', 'struct', 'union') "
        "AND COALESCE(c.prot, 0) = 0 ORDER BY c.line",
        (rel,),
    ).fetchall()
    links = table_exists(conn, "compoundref")
    tests = _NOT_TEST if table_exists(conn, "test_scope") else ""
    out = []
    for rowid, name, kind, brief in rows:
        bases = _related(conn, _BASES + tests, rowid) if links else ()
        derived = _related(conn, _DERIVED + tests, rowid) if links else ()
        out.append(ClassInfo(str(name), str(kind), doc_text(str(brief or "")), bases, derived))
    return out


## A class declared in TEST code is not public API (found on entropic: test fixtures listed as
## `ChatAdapter`'s derived classes), so the hierarchy leaves out classes in `test_scope` files.
_NOT_TEST = " AND c.file_id NOT IN (SELECT path_rowid FROM test_scope)"
_BASES = (
    "SELECT c.name FROM compoundref r JOIN compounddef c ON c.rowid = r.base_rowid "
    "WHERE r.derived_rowid = ?"
)
_DERIVED = (
    "SELECT c.name FROM compoundref r JOIN compounddef c ON c.rowid = r.derived_rowid "
    "WHERE r.base_rowid = ?"
)


## @brief Names one hierarchy query returns, sorted.
## @param conn Open connection.
## @param sql The query, one `?` for the class rowid.
## @param rowid The class.
## @return Names.
## @version 1
## @utility
def _related(conn: Any, sql: str, rowid: int) -> tuple[str, ...]:
    """@brief Run. @return Names."""
    return tuple(sorted({str(r[0]) for r in conn.execute(sql, (rowid,))}))


## @brief One header's reference page body.
## @param rel The header.
## @param symbols Its public symbols.
## @param classes Its classes / structs (name, kind, brief).
## @return HTML.
## v2: entropic's PAPI gaps 1-3 (2.0.0)
## @version 2
## @req REQ-DDB-WIKI-053
def api_html(rel: str, symbols: list[Symbol], classes: list[ClassInfo] = ()) -> str:
    """CLASS MEMBERS GO UNDER THEIR CLASS (a symbol whose scope names a class declared here); the
    rest by kind; enum values under their enum.

    @brief Render a header.
    @return HTML.
    """
    class_names = {c.name for c in classes} | {
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
    info = {c.name: c for c in classes}
    for scope in sorted(class_names):
        members = [s for s in symbols if s.scope == scope]
        if not members and scope not in info:
            continue
        c = info.get(scope)
        brief = f"<p>{escape(c.brief)}</p>" if c and c.brief else ""
        parts.append(
            f'<h2 class="api-class" id="api-{escape(scope)}"><code>{escape(scope)}</code></h2>'
            f"{brief}{_hierarchy(c)}" + "".join(_entry(s, values) for s in members)
        )
    return "".join(parts)


## @brief One symbol's entry: signature, hook mark, brief, detail, values.
## @param symbol The symbol.
## @param values Enum name → its values.
## @return HTML.
## v2: entropic's PAPI gaps 1-3 (2.0.0)
## @version 2
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
    body += _doc_lists(symbol.doc)
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
## v2: passes the declared doc tags (entropic's gaps 1-3, 2.0.0)
## @version 2
## @req REQ-DDB-WIKI-053
def api_pages(db: Path, globs: tuple[str, ...], source: Path, tags: tuple[str, ...] = ()) -> str:
    """@brief Write api.md and api-*.md. @return Page name or ""."""
    import re

    from ..query._common import connect

    with connect(db) as conn:
        headers = header_symbols(conn, globs, tags)
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


## @brief Parse doxygen's description XML into labelled parts (entropic's gaps 1 and 2).
## @param xml The detailed-description XML.
## @param tags Tags the repository declares (`guard.validate.extra_tags`), rendered as fields.
## @return The structured doc.
## @version 1
## @req REQ-DDB-WIKI-053
def parse_doc(xml: str, tags: tuple[str, ...] = ()) -> Doc:
    """Doxygen stores parameters, the return and return values as `<parameterlist>` and
    `<simplesect kind="return">`; they are read as structure rather than flattened into prose. A
    declaration's block and its definition's often repeat the return: identical ones collapse. A
    fragment that will not parse falls back to the flat text, never to nothing.

    @brief Structure a description.
    @return Doc.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(f"<root>{xml or ''}</root>")
    except ET.ParseError:
        return Doc(prose=doc_text(xml))
    params: list[tuple[str, str, str]] = []
    retvals: list[tuple[str, str]] = []
    for plist in root.iter("parameterlist"):
        for item in plist.iter("parameteritem"):
            text = _flat(item.find("parameterdescription"))
            for name in item.iter("parametername"):
                label = "".join(name.itertext()).strip()
                if plist.get("kind") == "retval":
                    retvals.append((label, text))
                else:
                    params.append((label, name.get("direction", ""), text))
    returns = [_flat(s) for s in root.iter("simplesect") if s.get("kind") == "return"]
    _drop(root, {"parameterlist", "simplesect"})
    prose, fields = _fields(" ".join("".join(root.itertext()).split()), tags)
    return Doc(
        prose=prose,
        params=tuple(dict.fromkeys(params)),
        returns=_distinct(returns),
        retvals=tuple(dict.fromkeys(retvals)),
        fields=fields,
    )


## @brief Returns without repeats: one contained in another is dropped (found on entropic).
## @param returns The return texts, in order.
## @return Distinct texts.
## @version 1
## @utility
def _distinct(returns: list[str]) -> tuple[str, ...]:
    """A DEFINITION'S BLOCK OFTEN REPEATS the first sentence of the declaration's return; that
    repeat says nothing the longer one does not.

    @brief De-duplicate.
    @return Texts.
    """
    texts = [r for r in dict.fromkeys(returns) if r]
    return tuple(r for r in texts if not any(r != o and r in o for o in texts))


## @brief An element's text, whitespace collapsed and guard tags dropped.
## @param element An XML element, or None.
## @return Text.
## @version 1
## @utility
def _flat(element: Any) -> str:
    """@brief Flatten. @return Text."""
    if element is None:
        return ""
    return " ".join(_GUARD_TAG.sub("", " ".join("".join(element.itertext()).split())).split())


## @brief Remove every element with one of these tags from the tree, keeping their tail text.
## @param root The tree.
## @param names Tags to remove.
## @return None.
## @version 1
## @utility
def _drop(root: Any, names: set[str]) -> None:
    """THE TAIL STAYS: `</simplesect> @threadsafety …` keeps the text after the removed element.

    @brief Prune.
    @return None.
    """
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag in names:
                tail = child.tail or ""
                index = list(parent).index(child)
                parent.remove(child)
                if index == 0:
                    parent.text = (parent.text or "") + tail
                else:
                    prev = list(parent)[index - 1]
                    prev.tail = (prev.tail or "") + tail


## @brief Split declared tags out of prose as fields; guard tags dropped.
## @param text The prose.
## @param tags Declared tag names.
## @return (prose, ((tag, text), ...)).
## @version 1
## @utility
def _fields(text: str, tags: tuple[str, ...]) -> tuple[str, tuple[tuple[str, str], ...]]:
    """AN UNDECLARED `@word` STAYS in the prose as written: only what the repository declares is
    known to be a field.

    @brief Fields.
    @return Prose and fields.
    """
    fields = []
    for tag in tags:
        pattern = re.compile(rf"@{re.escape(tag)}\b\s*(.*?)(?=\s@\w|$)")
        for match in pattern.finditer(text):
            fields.append((tag, " ".join(_GUARD_TAG.sub("", match.group(1)).split())))
        text = pattern.sub("", text)
    return " ".join(_GUARD_TAG.sub("", text).split()), tuple(dict.fromkeys(fields))


## @brief The labelled lists for a structured doc: parameters, returns, return values, fields.
## @param doc The doc, or None.
## @return HTML.
## @version 1
## @utility
def _doc_lists(doc: Doc | None) -> str:
    """@brief Definition lists. @return HTML."""
    if doc is None:
        return ""
    parts = []
    if doc.params:
        items = "".join(
            f"<li><code>{escape(n)}</code>"
            + (f' <span class="dir">{escape(d)}</span>' if d else "")
            + (f" — {escape(t)}" if t else "")
            + "</li>"
            for n, d, t in doc.params
        )
        parts.append(f"<dt>Parameters</dt><dd><ul>{items}</ul></dd>")
    if doc.returns:
        parts.append("<dt>Returns</dt>" + "".join(f"<dd>{escape(r)}</dd>" for r in doc.returns))
    if doc.retvals:
        items = "".join(f"<li><code>{escape(v)}</code> — {escape(t)}</li>" for v, t in doc.retvals)
        parts.append(f"<dt>Return values</dt><dd><ul>{items}</ul></dd>")
    for tag, text in doc.fields:
        parts.append(f"<dt>{escape(tag)}</dt><dd>{escape(text)}</dd>")
    return f'<dl class="api-doc">{"".join(parts)}</dl>' if parts else ""


## @brief A class's inheritance line (entropic's gap 3).
## @param info The class, or None.
## @return HTML.
## @version 1
## @utility
def _hierarchy(info: ClassInfo | None) -> str:
    """@brief Inherits from / derived by, each linked to its entry on the page. @return HTML."""
    if info is None or not (info.bases or info.derived):
        return ""

    def names(items: tuple[str, ...]) -> str:
        return ", ".join(f'<a href="#api-{escape(n)}"><code>{escape(n)}</code></a>' for n in items)

    lines = []
    if info.bases:
        lines.append(f"Inherits from {names(info.bases)}.")
    if info.derived:
        lines.append(f"Derived by {names(info.derived)}.")
    return f'<p class="hierarchy">{" ".join(lines)}</p>'
