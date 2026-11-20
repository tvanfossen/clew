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


## Entropic's real `entropic_create` description, trimmed: params, a return with a list, a
## declared `@threadsafety`, guard tags, and the definition's duplicate return.
_CREATE = (
    "<para>Allocates an engine handle.</para>"
    '<para><parameterlist kind="param"><parameteritem><parameternamelist>'
    '<parametername direction="out">handle</parametername></parameternamelist>'
    "<parameterdescription><para>Pointer to receive the new handle. </para>"
    "</parameterdescription></parameteritem></parameterlist>"
    '<simplesect kind="return"><para>ENTROPIC_OK on success.</para></simplesect>'
    '<parameterlist kind="retval"><parameteritem><parameternamelist>'
    "<parametername>ENTROPIC_ERROR_INVALID_ARGUMENT</parametername></parameternamelist>"
    "<parameterdescription><para>handle is NULL.</para></parameterdescription>"
    "</parameteritem></parameterlist>"
    "@threadsafety Single-threaded init/destroy. @req REQ-API-002 "
    '<simplesect kind="version"><para>1.8.0</para></simplesect></para>'
    '<para><simplesect kind="return"><para>ENTROPIC_OK on success. @req REQ-API-002 </para>'
    "</simplesect></para>"
)


def test_params_returns_and_retvals_are_structured() -> None:
    """ENTROPIC'S GAP 2: parameters, the return and return values flattened into one paragraph.
    Doxygen stores them as `<parameterlist>` / `<simplesect kind="return">`; they are read as such,
    and the definition's identical return collapses into one.

    @brief Structured params and returns.
    """
    from clew.wiki.apiref import parse_doc

    doc = parse_doc(_CREATE, ("threadsafety",))
    assert doc.params == (("handle", "out", "Pointer to receive the new handle."),)
    assert doc.returns == ("ENTROPIC_OK on success.",)
    assert doc.retvals == (("ENTROPIC_ERROR_INVALID_ARGUMENT", "handle is NULL."),)
    assert doc.prose == "Allocates an engine handle."


def test_a_declared_tag_is_a_labelled_field() -> None:
    """ENTROPIC'S GAP 1: `@threadsafety` (declared in `guard.validate.extra_tags`) printed raw. It
    is a labelled field; an undeclared `@word` stays in the prose as written.

    @brief Declared tags as fields.
    """
    from clew.wiki.apiref import parse_doc

    doc = parse_doc(_CREATE, ("threadsafety",))
    assert doc.fields == (("threadsafety", "Single-threaded init/destroy."),)
    assert "@threadsafety" not in doc.prose


def test_the_entry_renders_labelled_lists() -> None:
    """@brief Parameters, Returns, Return values and the field, each under its own label."""
    from clew.wiki.apiref import Symbol, _entry, parse_doc

    doc = parse_doc(_CREATE, ("threadsafety",))
    html = _entry(
        Symbol(
            "function", "entropic_create", "", "int entropic_create(handle)", "", "", 1, doc=doc
        ),
        {},
    )
    for label in ("Parameters", "Returns", "Return values", "threadsafety"):
        assert f"<dt>{label}</dt>" in html, label
    assert '<code>handle</code> <span class="dir">out</span>' in html


def test_a_class_shows_its_bases_and_derived() -> None:
    """ENTROPIC'S GAP 3: no inheritance. From the index's `compoundref`: a class lists what it
    inherits from and what derives from it.

    @brief Inheritance.
    """
    import sqlite3

    from clew.wiki.apiref import header_classes

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INT, found INT);"
        "CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, prot INT,"
        " file_id INT, line INT, briefdescription TEXT, detaileddescription TEXT);"
        "CREATE TABLE compoundref (rowid INTEGER PRIMARY KEY, base_rowid INT, derived_rowid INT,"
        " prot INT, virt INT);"
        "INSERT INTO path VALUES (1, 'include/a.h', 1, 1);"
        "INSERT INTO compounddef VALUES (1, 'ChatAdapter', 'class', 0, 1, 1, '', ''),"
        " (2, 'QwenAdapter', 'class', 0, 1, 9, '', ''), (3, 'Base', 'class', 0, 1, 20, '', '');"
        "INSERT INTO compoundref VALUES (1, 1, 2, 0, 0), (2, 3, 1, 0, 0);"
    )
    by_name = {c.name: c for c in header_classes(conn, "include/a.h")}
    assert by_name["ChatAdapter"].bases == ("Base",)
    assert by_name["ChatAdapter"].derived == ("QwenAdapter",)


def test_a_return_repeated_inside_a_longer_one_is_shown_once() -> None:
    """FOUND ON ENTROPIC'S INDEX: the definition's block repeats "ENTROPIC_OK on success." and the
    declaration's carries it plus its error list. A return contained in another is dropped.

    @brief Returns de-duplicated by containment.
    """
    from clew.wiki.apiref import parse_doc

    xml = (
        '<para><simplesect kind="return"><para>OK on success. ERR on failure.</para></simplesect></para>'
        '<para><simplesect kind="return"><para>OK on success.</para></simplesect></para>'
    )
    assert parse_doc(xml).returns == ("OK on success. ERR on failure.",)


def test_a_class_declared_in_test_code_is_not_in_the_hierarchy() -> None:
    """FOUND ON ENTROPIC'S INDEX: `ChatAdapter`'s derived list carried test fixtures
    (`anonymous_namespace{adapter_base_test.cpp}::TestAdapter`). Test code is not public API.

    @brief Hierarchy excludes test classes.
    """
    import sqlite3

    from clew.wiki.apiref import header_classes

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INT, found INT);"
        "CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, prot INT,"
        " file_id INT, line INT, briefdescription TEXT, detaileddescription TEXT);"
        "CREATE TABLE compoundref (rowid INTEGER PRIMARY KEY, base_rowid INT, derived_rowid INT,"
        " prot INT, virt INT);"
        "CREATE TABLE test_scope (path_rowid INTEGER);"
        "INSERT INTO path VALUES (1, 'include/a.h', 1, 1), (2, 'tests/a_test.cpp', 1, 1);"
        "INSERT INTO compounddef VALUES (1, 'Base', 'class', 0, 1, 1, '', ''),"
        " (2, 'Real', 'class', 0, 1, 9, '', ''), (3, 'TestAdapter', 'class', 0, 2, 3, '', '');"
        "INSERT INTO compoundref VALUES (1, 1, 2, 0, 0), (2, 1, 3, 0, 0);"
        "INSERT INTO test_scope VALUES (2);"
    )
    (base,) = [c for c in header_classes(conn, "include/a.h") if c.name == "Base"]
    assert base.derived == ("Real",)


def test_a_declared_tag_inside_a_return_or_param_is_split_out() -> None:
    """ENTROPIC'S AUDIT (19f439fb, 33 cases): with no ALIASES, doxygen runs `@threadsafety` into
    the paragraph before it — the return's or a parameter's. Declared tags are split out of those
    texts too.

    @brief Declared tags inside returns and params.
    """
    from clew.wiki.apiref import parse_doc

    xml = (
        '<para><parameterlist kind="param"><parameteritem><parameternamelist>'
        "<parametername>hash</parametername></parameternamelist><parameterdescription>"
        "<para>Content hash. @threadsafety Safe from any thread</para></parameterdescription>"
        "</parameteritem></parameterlist>"
        '<simplesect kind="return"><para>Count. @threadsafety Takes the root lock.</para>'
        "</simplesect></para>"
    )
    doc = parse_doc(xml, ("threadsafety",))
    assert doc.params == (("hash", "", "Content hash."),)
    assert doc.returns == ("Count.",)
    assert set(doc.fields) == {
        ("threadsafety", "Safe from any thread"),
        ("threadsafety", "Takes the root lock."),
    }


def test_throws_are_rendered() -> None:
    """ENTROPIC'S AUDIT (5 functions): `@throws` / `@exception` is doxygen's
    `parameterlist kind="exception"`, and was dropped.

    @brief Throws.
    """
    from clew.wiki.apiref import Symbol, _entry, parse_doc

    xml = (
        '<para><parameterlist kind="exception"><parameteritem><parameternamelist>'
        "<parametername>std::runtime_error</parametername></parameternamelist>"
        "<parameterdescription><para>On a bad path.</para></parameterdescription>"
        "</parameteritem></parameterlist></para>"
    )
    doc = parse_doc(xml)
    assert doc.throws == (("std::runtime_error", "On a bad path."),)
    html = _entry(Symbol("function", "f", "", "void f()", "", "", 1, doc=doc), {})
    assert "<dt>Throws</dt>" in html


def test_a_declaration_takes_the_parts_only_its_definition_documents() -> None:
    """ENTROPIC'S AUDIT (~23 functions): the header declaration carries prose, while doxygen put
    the structured `parameterlist` / `simplesect` on the DEFINITION's memberdef (the `.cpp`). Each
    part the declaration lacks — params, returns, throws — is taken from the definition; a part it
    has is kept.

    @brief Declaration merges the definition's missing parts.
    """
    import sqlite3

    from clew.wiki.apiref import header_symbols

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        _SCHEMA.replace(
            "(1, 'include/demo/api.h', 1, 1), (2, 'src/impl.cpp', 1, 1)",
            "(1, 'include/demo/api.h', 1, 1), (2, 'src/impl.cpp', 1, 1)",
        )
    )
    conn.execute(
        "INSERT INTO memberdef VALUES (11, 'function', 'demo_open', NULL, 'int', 'int demo_open', "
        "'(const char *path)', NULL, '', ?, 5, 0, 2, 2)",
        (
            '<para><parameterlist kind="param"><parameteritem><parameternamelist>'
            "<parametername>path</parametername></parameternamelist><parameterdescription>"
            "<para>Where the store lives.</para></parameterdescription></parameteritem>"
            '</parameterlist><simplesect kind="return"><para>0 on success.</para></simplesect></para>',
        ),
    )
    (open_,) = [
        s
        for s in header_symbols(conn, ("include/**",))["include/demo/api.h"]
        if s.name == "demo_open"
    ]
    assert open_.doc.params == (("path", "", "Where the store lives."),)
    assert open_.doc.returns == ("0 on success.",)
    assert "Returns 0 on success." in open_.detail or open_.detail == "Returns 0 on success."


def test_a_class_named_twice_is_listed_once_by_its_qualified_name() -> None:
    """ENTROPIC'S AUDIT: "Derived by FilesystemServer, …, entropic::FilesystemServer" — the index
    holds both spellings. The qualified one stays.

    @brief Hierarchy names deduplicated.
    """
    from clew.wiki.apiref import _qualified_only

    assert _qualified_only(
        ("FilesystemServer", "GitServer", "entropic::FilesystemServer", "entropic::GitServer")
    ) == (
        "entropic::FilesystemServer",
        "entropic::GitServer",
    )


def test_a_class_is_found_by_its_members_scope_not_only_its_file() -> None:
    """ENTROPIC'S AUDIT: `ChatAdapter` showed no hierarchy on its header's page on entropic's index,
    though the class's members were listed there. A class whose members a header declares is
    looked up by name, whichever file its compounddef records.

    @brief Classes found by name.
    """
    import sqlite3

    from clew.wiki.apiref import header_classes

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INT, found INT);"
        "CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, prot INT,"
        " file_id INT, line INT, briefdescription TEXT, detaileddescription TEXT);"
        "CREATE TABLE compoundref (rowid INTEGER PRIMARY KEY, base_rowid INT, derived_rowid INT,"
        " prot INT, virt INT);"
        "INSERT INTO path VALUES (1, 'include/a.h', 1, 1), (2, 'src/a.cpp', 1, 1);"
        "INSERT INTO compounddef VALUES (1, 'ns::ChatAdapter', 'class', 0, 2, 1, '', ''),"
        " (2, 'ns::QwenAdapter', 'class', 0, 1, 9, '', '');"
        "INSERT INTO compoundref VALUES (1, 1, 2, 0, 0);"
    )
    by = {c.name: c for c in header_classes(conn, "include/a.h", scopes={"ns::ChatAdapter"})}
    assert by["ns::ChatAdapter"].derived == ("ns::QwenAdapter",)


def test_the_gates_own_report_is_not_swept_into_the_docs(tmp_path) -> None:
    """ENTROPIC'S AUDIT: 12 toctree warnings for `docs/generated/impact`. The guard writes its
    impact report (`impact.md`, no title) under its `report_dir`, and a `docs/**` glob swept it in
    as a doc page. The wiki leaves the gate's report directory out of the prose.

    @brief The impact report is not a doc page.
    """
    from clew.wiki.build import _prose
    from clew.wiki.config import WikiConfig
    from clew.wiki.tracepages import impact_path

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n")
    report = impact_path(tmp_path, WikiConfig()).parent
    report.mkdir(parents=True)
    (report / "impact.md").write_text("| req | fn |\n")
    source = tmp_path / "_src"
    source.mkdir()
    rels = {rel for _page, rel in _prose(tmp_path, WikiConfig(docs=("docs/**/*.md",)), source)}
    assert "docs/guide.md" in rels and not any(r.endswith("impact.md") for r in rels), rels


def test_code_text_doxygen_stored_verbatim_is_kept_and_structured() -> None:
    """ENTROPIC'S AUDIT OF f6ff1f7c (23 entries, 83 of 1,482 include/ descriptions): doxygen
    stores code text verbatim inside its XML, so `(n_tokens < 2)` or `std::atomic<bool>` made the
    fragment unparseable. The entry fell back to one flat paragraph with no Parameters or Returns,
    and the fallback stripped `< 2)` AS A TAG — text lost silently.

    @brief Stray `<` and `&` are text, and the doc stays structured.
    """
    from clew.wiki.apiref import parse_doc

    xml = (
        '<para><parameterlist kind="param"><parameteritem><parameternamelist>'
        "<parametername>n_tokens</parametername></parameternamelist><parameterdescription>"
        "<para>Count (fails when n_tokens < 2).</para></parameterdescription></parameteritem>"
        '</parameterlist><simplesect kind="return"><para>A std::atomic<bool> & a flag.</para>'
        "</simplesect></para>"
    )
    doc = parse_doc(xml)
    assert doc.params == (("n_tokens", "", "Count (fails when n_tokens < 2)."),)
    assert doc.returns == ("A std::atomic<bool> & a flag.",)


def test_the_flat_text_keeps_a_less_than_sign() -> None:
    """ENTROPIC'S AUDIT OF f6ff1f7c: "- ENTROPIC_ERROR_INVALID_CONFIG (n_tokens < 2)" rendered as
    "(n_tokens ENTROPIC_ERROR_EVAL_FAILED …" — briefs and the flat fallback stripped `< 2)` as a tag.

    @brief doc_text keeps code text.
    """
    from clew.wiki.apiref import doc_text

    assert doc_text("<para>Fails (n_tokens < 2) on a std::atomic<bool>.</para>") == (
        "Fails (n_tokens < 2) on a std::atomic<bool>."
    )


def test_text_that_looks_like_a_doxygen_element_is_kept() -> None:
    """ENTROPIC'S AUDIT, the last 3 of 1,485: `<root>/sub/.gitignore` and `"summary":"<summary>"`
    are text, though `summary` is also a doxygen element name. An element name whose opens and
    closes do not balance is text.

    @brief Unbalanced element names are text.
    """
    from clew.wiki.apiref import doc_text

    assert (
        doc_text("<para>Path (e.g. <root>/sub/.gitignore).</para>")
        == "Path (e.g. <root>/sub/.gitignore)."
    )
    assert doc_text('<para>{"summary":"<summary>"}</para>') == '{"summary":"<summary>"}'
    ## A SELF-CLOSING element with attributes is markup, not an unclosed open. (A tag boundary is
    ## a space, as the regex strip always made it, so adjacent paragraphs never run together.)
    assert (
        doc_text('<para>See <image type="html" name="a.png"/><ulink url="u">it</ulink>.</para>')
        == "See it ."
    )
