# SPDX-License-Identifier: MIT
"""The public-API reference: one page per declared public header, from the index (PAPI, 2.0.0).

OWNER (Q/A 2026-11-19): a full public-API reference in the wiki, scoped to DECLARED public headers
(`wiki.api: [include/**]`) and generated from the index: exported functions, enums with their
values, typedefs, macros, variables, and classes / structs with their public members; a
function-pointer typedef is marked a hook point. `\\internal`-documented symbols are excluded; a
public `@utility` function is still public API. Not doxygen parity: no class diagrams, no groups.

@brief Tests the API reference pages.
@version 1
"""

from __future__ import annotations

import sqlite3

from clew.wiki.apiref import api_html, header_classes, header_symbols

_SCHEMA = """
CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INT, found INT);
CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, scope TEXT, type TEXT,
  definition TEXT, argsstring TEXT, initializer TEXT, briefdescription TEXT,
  detaileddescription TEXT, line INT, prot INT, file_id INT, bodyfile_id INT);
CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, prot INT, file_id INT,
  line INT, briefdescription TEXT, detaileddescription TEXT);
INSERT INTO path VALUES (1, 'include/demo/api.h', 1, 1), (2, 'src/impl.cpp', 1, 1);
INSERT INTO memberdef VALUES
 (1, 'function', 'demo_open', NULL, 'int', 'int demo_open', '(const char *path)', NULL,
  '<para>Open a store.</para>', '<para>Returns 0 on success.</para>', 10, 0, 1, 2),
 (2, 'enumeration', 'demo_mode_t', NULL, NULL, 'enum demo_mode_t', '', NULL, '<para>Modes.</para>', '', 20, 0, 1, 0),
 (3, 'enumvalue', 'DEMO_READ', 'demo_mode_t', NULL, 'DEMO_READ', '', '= 1', '', '', 21, 0, 1, 0),
 (4, 'enumvalue', 'DEMO_WRITE', 'demo_mode_t', NULL, 'DEMO_WRITE', '', '= 2', '', '', 22, 0, 1, 0),
 (5, 'typedef', 'demo_cb', NULL, 'void(*', 'typedef void(* demo_cb) (int)', ')(int)', NULL,
  '<para>Called per event.</para>', '', 30, 0, 1, 0),
 (6, 'function', 'flush', 'demo::Store', 'void', 'void demo::Store::flush', '()', NULL,
  '<para>Flush it.</para>', '', 41, 0, 1, 2),
 (7, 'function', 'secret', 'demo::Store', 'void', 'void demo::Store::secret', '()', NULL, '', '', 42, 2, 1, 2),
 (8, 'function', 'hidden', NULL, 'void', 'void hidden', '()', NULL, '<para>Hidden.</para>',
  '<para><internal>Not for callers.</internal></para>', 50, 0, 1, 2),
 (9, 'macro definition', 'DEMO_VERSION', NULL, NULL, '#define DEMO_VERSION', '', '3', '', '', 5, 0, 1, 0),
 (10, 'function', 'impl_only', NULL, 'void', 'void impl_only', '()', NULL, '', '', 3, 0, 2, 2);
INSERT INTO compounddef VALUES (1, 'demo::Store', 'class', 0, 1, 40, '<para>A store.</para>', '');
"""


def _conn() -> sqlite3.Connection:
    """@brief A minimal index. @return Connection."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


def test_only_declared_public_headers_are_read() -> None:
    """@brief `include/**` holds the API; `src/impl.cpp` does not, whatever it defines."""
    headers = header_symbols(_conn(), ("include/**",))
    assert list(headers) == ["include/demo/api.h"]
    names = {s.name for s in headers["include/demo/api.h"]}
    assert "impl_only" not in names


def test_a_header_page_lists_its_public_api() -> None:
    """@brief Functions with signatures, enum values, hook typedefs, macros, class members."""
    conn = _conn()
    rel = "include/demo/api.h"
    html = api_html(rel, header_symbols(conn, ("include/**",))[rel], header_classes(conn, rel))
    assert "<code>int demo_open(const char *path)</code>" in html and "Open a store." in html
    assert "DEMO_READ" in html and "= 1" in html
    assert "demo_cb" in html and 'class="hook"' in html
    assert "DEMO_VERSION" in html
    store = html.split("demo::Store", 1)[1]
    assert "flush" in store and "A store." in html


def test_private_members_and_internal_symbols_are_not_public_api() -> None:
    """@brief `prot` private and a `\\internal`-documented function stay out."""
    names = {s.name for s in header_symbols(_conn(), ("include/**",))["include/demo/api.h"]}
    assert "secret" not in names and "hidden" not in names


def test_no_declared_headers_means_no_reference() -> None:
    """@brief `wiki.api` absent: nothing is read, so no tab is built."""
    assert header_symbols(_conn(), ()) == {}


def test_a_function_pointer_typedef_reads_as_c() -> None:
    """FOUND ON ENTROPIC'S INDEX: doxygen's definition for a function-pointer typedef is
    `typedef int(*) cb_t(int x)` (arguments included), and appending them again garbled it. The
    reference shows the C a reader would write: `typedef int(*cb_t)(int x)`.

    @brief Hook typedef signature.
    """
    from clew.wiki.apiref import _signature

    sig = _signature("typedef", "typedef int(*) cb_t(int x)", "(int x)", "int(*)", "cb_t")
    assert sig == "typedef int(*cb_t)(int x)"


def test_traceability_tags_are_not_api_prose() -> None:
    """FOUND ON ENTROPIC'S INDEX: `@req REQ-TYPE-002` and the `@version` simplesect read as
    documentation. They belong to the requirement pages; the API page shows the prose.

    @brief Doc text without guard tags.
    """
    from clew.wiki.apiref import doc_text

    xml = (
        "<para>Hook points. @req REQ-TYPE-002 @req REQ-TYPE-004 @utility </para>"
        '<simplesect kind="version"><para>2.0.6-rc16</para></simplesect>'
    )
    assert doc_text(xml) == "Hook points."
