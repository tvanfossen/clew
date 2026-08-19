# SPDX-License-Identifier: MIT
"""Per-module unit tests for the clew/ package.

Each module is exercised independently: doxygen helpers don't actually
spawn doxygen (they parse known Doxyfile shapes); call_edges Layer 1
runs against an in-memory sqlite with the expected `xrefs` /
`memberdef` rows pre-loaded; prose chunking runs against literal
markdown strings; reachability runs against synthetic call_edges.

@brief Per-module tests for the clew pipeline split.
@version 1
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from clew.call_edges import (
    _ast_caller_at_line,
    _ast_record_call_edge,
    _ts_language_for,
    build_call_edges,
    import_macro_hop_edges,
)
from clew.doxygen import (
    _build_doxyfile_content,
    _classify_doxygen_line,
    parse_doxyfile_value,
    sanitize_doxygen_text,
    synthesize_doxyfile,
    warn_if_no_function_bodies,
)
from clew.prose import SUPPLEMENTARY_PATTERNS, chunk_markdown
from clew.reachability import (
    DEFAULT_ENTRY_PATTERNS,
    _bfs_live_set,
    _gather_reachability_seeds,
    _write_symbol_liveness,
    mark_reachability,
)
from clew.requirements import (
    _extract_req_tags,
    _looks_like_test_function,
    import_req_edges,
    import_req_test_edges,
    ingest_requirements_yaml,
)
from clew.shared_key_edges import (
    _MAX_KEY_EDGES,
    NamePrefixPattern,
    detect_undeclared_accessor_families,
    import_shared_key_edges_declared,
    import_shared_key_edges_inferred,
    load_shared_key_patterns,
)


def test_synthesize_doxyfile_writes_minimal_driver(tmp_path: Path) -> None:
    """A repo that declares its scope but ships no Doxyfile gets a minimal one:
    PROJECT_NAME, an ABSOLUTE OUTPUT_DIRECTORY (so output resolves regardless of
    cwd), and an empty INPUT (the derived scope fills it via replace_input).
    The forced flags append the rest, so this is all the pipeline needs."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    out_dir = tmp_path / "build" / "docs.doxygen"
    doxyfile = synthesize_doxyfile(repo, out_dir)

    assert doxyfile.exists()
    assert doxyfile.parent == out_dir  # its parent is a usable work_dir
    text = doxyfile.read_text()
    assert "PROJECT_NAME = myrepo" in text
    assert f"OUTPUT_DIRECTORY = {out_dir}" in text
    assert Path(parse_doxyfile_value(doxyfile, "OUTPUT_DIRECTORY")).is_absolute()
    assert "INPUT =" in text
    # _build_doxyfile_content appends the forced GENERATE_SQLITE3 etc.
    content = _build_doxyfile_content(doxyfile, None, None, replace_input=False)
    assert "GENERATE_SQLITE3 = YES" in content


def test_synthesize_doxyfile_declares_strip_from_path(tmp_path: Path) -> None:
    """The synthesized driver must strip the repo root from stored paths.

    Without it the #33 synthesis path stored ABSOLUTE paths — measured at 112 of
    112 rows on this repo's own index, each carrying the builder's home directory
    — and MCP publishes that column on every reply that names a file (the `file`
    field of a dossier, a search hit, a caller row). `list_files` used to be the
    example here and is deleted; the exposure is not, and naming a tool rather than
    the COLUMN is what let a deletion look like it had narrowed it. The pipeline's contract is
    that `path.name` is repo-root-relative; `fix_doxygen_paths` exists to restore
    exactly that, and it returned early precisely BECAUSE this key was unset.

    Only the SYNTHESIZED driver may set it. A repo shipping its own Doxyfile owns
    its STRIP_FROM_PATH, so it must not appear in the forced flags — overriding it
    would discard a declaration and defeat `fix_doxygen_paths`' reconstruction.
    Both halves are asserted, because the wrong fix satisfies the first.

    This is a PROXY for doxygen honouring the key; the real column is asserted in
    `tests/integration/test_self_index.py`. Stated because a proxy assertion that
    reads like a direct one is its own hazard."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    doxyfile = synthesize_doxyfile(repo, tmp_path / "build" / "docs.doxygen")

    strip = parse_doxyfile_value(doxyfile, "STRIP_FROM_PATH")
    assert strip, "the synthesized driver must declare STRIP_FROM_PATH"
    assert Path(strip).is_absolute(), "a relative strip prefix resolves against cwd"
    assert Path(strip) == repo.resolve(), "the prefix stripped must be the repo root"

    # Never forced onto a repo that supplied its own Doxyfile.
    own = tmp_path / "Doxyfile"
    own.write_text("PROJECT_NAME = theirs\n", encoding="utf-8")
    assert "STRIP_FROM_PATH" not in _build_doxyfile_content(own, None, None)


# ─── doxygen.sanitize_doxygen_text ──────────────────────────────────────────


def test_sanitize_doxygen_text_repairs_invalid_utf8(tmp_path: Path) -> None:
    """doxygen writes descriptions straight from source comments into its
    sqlite output; a non-UTF-8 comment lands as raw invalid bytes in a TEXT
    column. sanitize_doxygen_text must repair them in place (matching the docs
    server's read-side errors='replace') and leave clean rows untouched."""
    db = tmp_path / "doxy.db"
    conn = sqlite3.connect(str(db))
    for tbl in ("memberdef", "compounddef"):
        conn.execute(f"CREATE TABLE {tbl} (briefdescription TEXT, detaileddescription TEXT)")
    conn.execute("INSERT INTO memberdef VALUES (?, ?)", ("clean brief", "clean detail"))
    # 0xA4 is an invalid UTF-8 start byte (e.g. a latin-1/GBK source comment).
    conn.execute(
        "INSERT INTO memberdef VALUES (?, ?)",
        (b"bad \xa4 brief", b"detail \xa4\xa4 here"),
    )
    conn.commit()
    conn.close()

    fixed = sanitize_doxygen_text(db)
    assert fixed == 2, "both poisoned columns of the bad row should be repaired"

    check = sqlite3.connect(str(db))
    check.text_factory = bytes
    rows = check.execute(
        "SELECT briefdescription, detaileddescription FROM memberdef ORDER BY rowid"
    ).fetchall()
    check.close()
    # Every column now decodes as valid UTF-8 (would raise if still poisoned).
    for brief, detail in rows:
        brief.decode("utf-8")
        detail.decode("utf-8")
    # The clean row is untouched; the repaired bytes became U+FFFD.
    assert rows[0] == (b"clean brief", b"clean detail")
    assert b"\xef\xbf\xbd" in rows[1][0]


# ─── doxygen.parse_doxyfile_value ───────────────────────────────────────────


def test_parse_doxyfile_value_finds_simple_assignment(tmp_path: Path) -> None:
    f = tmp_path / "Doxyfile"
    f.write_text("OUTPUT_DIRECTORY     = build/docs\n")
    assert parse_doxyfile_value(f, "OUTPUT_DIRECTORY") == "build/docs"


def test_parse_doxyfile_value_returns_empty_for_missing_key(
    tmp_path: Path,
) -> None:
    f = tmp_path / "Doxyfile"
    f.write_text("OTHER_KEY = whatever\n")
    assert parse_doxyfile_value(f, "MISSING_KEY") == ""


def test_parse_doxyfile_value_handles_inline_comments(tmp_path: Path) -> None:
    f = tmp_path / "Doxyfile"
    f.write_text("# leading comment\nXML_OUTPUT = xml\n")
    assert parse_doxyfile_value(f, "XML_OUTPUT") == "xml"


# ─── doxygen._build_doxyfile_content ────────────────────────────────────────


def test_forced_output_dir_keeps_doxygen_out_of_the_target_repo(tmp_path: Path) -> None:
    """#53: clew is a READ-ONLY consumer of target repos, but honoring the
    repo's own Doxyfile (#49) meant honoring its OUTPUT_DIRECTORY too — a C++ codebase
    declares `docs/generated/doxygen`, so an index build wrote doxygen's
    sqlite3/xml straight into the working tree. That mutates a repo the operator
    may be mid-edit in, collides between concurrent builds, and shares a
    directory with output clew did not produce.

    The forced value must come LAST so it wins (doxygen takes the final
    assignment) and must be ABSOLUTE, since cwd stays the repo root so relative
    INPUT paths still resolve."""
    from clew.doxygen import (
        doxygen_db_path,
        effective_output_dir,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    doxyfile = repo / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = t\nOUTPUT_DIRECTORY = docs/generated/doxygen\n")
    scratch = tmp_path / "scratch.doxygen"

    content = _build_doxyfile_content(doxyfile, None, None, output_dir=scratch)
    assignments = [ln for ln in content.splitlines() if ln.startswith("OUTPUT_DIRECTORY")]
    assert assignments[-1] == f"OUTPUT_DIRECTORY = {scratch.resolve()}", (
        "the forced absolute path must be the LAST assignment doxygen sees"
    )

    # Every output-path resolver must agree with what was forced, or the
    # pipeline would look for its artifacts where they were not written.
    assert effective_output_dir(doxyfile, repo, scratch) == scratch.resolve()
    assert doxygen_db_path(doxyfile, repo, scratch).is_relative_to(scratch.resolve())


def test_output_dir_defaults_to_the_doxyfile_when_not_forced(tmp_path: Path) -> None:
    """Omitting the override keeps the original behaviour, so a caller that
    does not force a directory (the tests' own run_doxygen calls) is unchanged."""
    from clew.doxygen import effective_output_dir

    repo = tmp_path / "repo"
    repo.mkdir()
    doxyfile = repo / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = t\nOUTPUT_DIRECTORY = build/docs\n")
    assert effective_output_dir(doxyfile, repo) == (repo / "build" / "docs").resolve()
    assert (
        "OUTPUT_DIRECTORY"
        not in _build_doxyfile_content(doxyfile, None, None).split(
            "PROJECT_NAME = t\nOUTPUT_DIRECTORY = build/docs\n"
        )[-1]
    )


def test_build_doxyfile_appends_forced_flags(tmp_path: Path) -> None:
    f = tmp_path / "Doxyfile"
    f.write_text("PROJECT_NAME = test\n")
    out = _build_doxyfile_content(f, extra_input=None, extra_exclude=None)
    assert "GENERATE_SQLITE3 = YES" in out
    assert "GENERATE_XML" not in out
    assert "EXTRACT_ALL = YES" in out
    # Static funcs (common in generated gen/ code) + nested extra-input trees
    # must be indexed, or setters/callers in those dirs silently vanish.
    assert "EXTRACT_STATIC = YES" in out
    assert "RECURSIVE = YES" in out
    assert "PROJECT_NAME = test" in out  # original preserved


def test_build_doxyfile_appends_extra_input_clears_exclude(
    tmp_path: Path,
) -> None:
    f = tmp_path / "Doxyfile"
    f.write_text("EXCLUDE = vendor third_party\n")
    out = _build_doxyfile_content(
        f,
        extra_input=["subm/foo", "subm/bar"],
        extra_exclude=["subm/foo/deps"],
    )
    assert "INPUT += subm/foo" in out
    assert "INPUT += subm/bar" in out
    # Clear marker present
    assert "\nEXCLUDE =\n" in out
    # Re-exclude
    assert "EXCLUDE += subm/foo/deps" in out


def test_replacing_input_also_clears_the_repo_s_exclude_patterns(tmp_path: Path) -> None:
    """gh#333. `EXCLUDE_PATTERNS` is the GLOB spelling of `EXCLUDE`, and clearing one
    while leaving the other standing silently defeated the whole scope change on the
    target it was built for.

    Measured on [tvanfossen/entropic](https://github.com/tvanfossen/entropic), whose
    Doxyfile declares `EXCLUDE_PATTERNS = */extern/* */build/* */tests/*`: its
    llama.cpp submodule was added to INPUT by the new whole-repo scope and then
    dropped again by the surviving pattern. The build reported success and indexed 16
    vendored files, which looks exactly like a working measurement.

    ONLY UNDER `replace_input`, asserted in both directions below: a plain
    `--extra-exclude` build must leave the repo's own patterns exactly as written,
    because nothing there asked for the repo's scope statement to be replaced.
    """
    f = tmp_path / "Doxyfile"
    f.write_text("EXCLUDE = vendor\nEXCLUDE_PATTERNS = */extern/* */tests/*\n")

    replaced = _build_doxyfile_content(
        f, extra_input=["/repo"], extra_exclude=None, replace_input=True
    )
    assert "\nEXCLUDE_PATTERNS =\n" in replaced, (
        "an INPUT replacement that leaves EXCLUDE_PATTERNS standing admits a tree "
        "and then drops it again"
    )

    kept = _build_doxyfile_content(f, extra_input=None, extra_exclude=["src/legacy"])
    assert "\nEXCLUDE_PATTERNS =\n" not in kept
    assert "EXCLUDE_PATTERNS = */extern/* */tests/*" in kept


def test_build_doxyfile_extra_exclude_applies_standalone(tmp_path: Path) -> None:
    """--extra-exclude must work WITHOUT --extra-input (the natural way to just
    trim scope). Regression: the loader early-returned when extra_input was
    None, silently dropping extra_exclude. It is now APPENDED to the repo's own
    EXCLUDE (kept, not cleared — no extra_input means no submodule to un-hide).
    """
    f = tmp_path / "Doxyfile"
    f.write_text("EXCLUDE = vendor\n")
    out = _build_doxyfile_content(f, extra_input=None, extra_exclude=["src/legacy"])
    assert "EXCLUDE += src/legacy" in out  # applied standalone
    assert "EXCLUDE = vendor" in out  # repo's own EXCLUDE preserved (not cleared)
    # And with no extra args at all, nothing is appended.
    plain = _build_doxyfile_content(f, extra_input=None, extra_exclude=None)
    assert "EXCLUDE +=" not in plain


# ─── doxygen._classify_doxygen_line ─────────────────────────────────────────


def test_classify_doxygen_line_buckets() -> None:
    assert _classify_doxygen_line("warning: X") == "warning"
    assert _classify_doxygen_line("Error: oops") == "warning"  # case-insensitive
    assert _classify_doxygen_line("Preprocessing /a.c...") == "file"
    assert _classify_doxygen_line("Parsing file /b.h...") == "file"
    assert _classify_doxygen_line("Generating XML output...") == "phase"
    assert _classify_doxygen_line("Building member docs...") == "phase"
    assert _classify_doxygen_line("Doxygen version 1.x") == "other"


# ─── prose.chunk_markdown ───────────────────────────────────────────────────


def test_chunk_markdown_first_chunk_uses_filename() -> None:
    text = "Intro before any heading.\n\n# First heading\nbody\n"
    chunks = chunk_markdown(text, "README.md")
    assert chunks[0] == ("README.md", "Intro before any heading.")
    assert chunks[1] == ("First heading", "body")


def test_chunk_markdown_handles_three_levels() -> None:
    text = "# H1\nbodyA\n\n## H2\nbodyB\n\n### H3\nbodyC\n"
    chunks = chunk_markdown(text, "x.md")
    assert [(h, c) for h, c in chunks] == [
        ("H1", "bodyA"),
        ("H2", "bodyB"),
        ("H3", "bodyC"),
    ]


def test_chunk_markdown_empty_section_skipped() -> None:
    """Heading with no body in between shouldn't produce empty chunk."""
    text = "# A\n\n# B\nbody\n"
    chunks = chunk_markdown(text, "x.md")
    # Section A has no body — skipped.
    assert chunks == [("B", "body")]


def test_supplementary_patterns_includes_readme_and_docs() -> None:
    """Glob list must cover the standard layouts before runtime adds any."""
    assert "README.md" in SUPPLEMENTARY_PATTERNS
    assert "docs/*.md" in SUPPLEMENTARY_PATTERNS
    assert "docs/**/*.md" in SUPPLEMENTARY_PATTERNS


def test_ingest_one_doc_file_skips_non_utf8(tmp_path: Path) -> None:
    """Regression for 2026-05-14 mojibake bug: a GBK-encoded markdown
    file (iot_error_definition.md) was previously ingested via
    `read_text(errors="replace")`, substituting every invalid byte
    with U+FFFD. The garbage flowed to the model via
    `docs.search_prose` and caused hallucinated citations. The fix
    is strict UTF-8 decode; non-UTF-8 files are skipped + logged."""
    from clew.prose import _ingest_one_doc_file

    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE VIRTUAL TABLE supplementary_docs USING fts5(file_path, heading, content)")
    # GBK-encoded content with a 0x8F byte that is invalid in UTF-8.
    bad = tmp_path / "iot_error_definition.md"
    bad.write_bytes(b"# Title\n\xb4\x8f\xbf\xed bytes that are not utf-8\n")
    result = _ingest_one_doc_file(conn, bad, "iot_error_definition.md")
    assert result == 0, "non-UTF-8 file must be skipped, not ingested"
    rows = conn.execute("SELECT COUNT(*) FROM supplementary_docs").fetchone()
    assert rows[0] == 0


def test_ingest_one_doc_file_accepts_valid_utf8(tmp_path: Path) -> None:
    """Sanity-check the strict-decode change doesn't reject legitimate
    UTF-8 (including multi-byte characters)."""
    from clew.prose import _ingest_one_doc_file

    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE VIRTUAL TABLE supplementary_docs USING fts5(file_path, heading, content)")
    good = tmp_path / "ok.md"
    # Valid UTF-8 including a multi-byte char (é = 0xC3 0xA9).
    good.write_text("# Heading\nbody with é character\n", encoding="utf-8")
    result = _ingest_one_doc_file(conn, good, "ok.md")
    assert result == 1
    rows = conn.execute("SELECT heading, content FROM supplementary_docs").fetchall()
    assert rows[0][0] == "Heading"
    assert "é" in rows[0][1]


# ─── call_edges._ts_language_for ────────────────────────────────────────────


def test_ts_language_for_recognizes_extensions() -> None:
    """`.py` used to sit here alongside `.txt`/`.rs` as an unrecognised
    extension. That was the whole of #58's gap: `tree_sitter_python` was already
    installed and simply never routed, so every tree-sitter R1 layer (call edges,
    thread spawns, reachability seeds) was silently empty on a Python codebase —
    including clew itself, which is a pinned MCP target of itself.

    `.py` and (Rust support) `.rs` now resolve; `.txt` still must not, because a
    grammar this pipeline does not ship must fail closed rather than fall back to
    some other language's parser and FABRICATE structure (#50 is the
    C-grammar-on-a-C++-header version of exactly that mistake)."""
    assert _ts_language_for("foo.txt") is None
    assert _ts_language_for("dir/file.py") is not None
    assert _ts_language_for("dir/file.rs") is not None


# ─── call_edges._ast_caller_at_line ─────────────────────────────────────────


def test_ast_caller_at_line_finds_match_in_window() -> None:
    funcs = [
        (10, "foo", 1, 5),
        (20, "bar", 6, 12),
        (30, "baz", 13, 99),
    ]
    assert _ast_caller_at_line(funcs, 3) == 10
    assert _ast_caller_at_line(funcs, 7) == 20
    assert _ast_caller_at_line(funcs, 99) == 30
    assert _ast_caller_at_line(funcs, 100) is None


# ─── call_edges._ast_record_call_edge ───────────────────────────────────────


def test_ast_record_unique_match_resolved() -> None:
    edges_resolved: list = []
    edges_fuzzy: list = []
    _ast_record_call_edge(
        caller_rowid=10,
        callee_name="malloc",
        name_to_rowids={"malloc": [42]},
        edges_resolved=edges_resolved,
        edges_fuzzy=edges_fuzzy,
    )
    # Edges now carry their own provenance so an unwrapped member call is
    # separable from a bare-identifier one; 'ast' is the default.
    assert edges_resolved == [(10, 42, "ast")]
    assert edges_fuzzy == []


def test_ast_record_multi_match_records_nothing() -> None:
    """gh#347. THREE FUNCTIONS NAMED `init` AND ONE CALL SITE. This used to emit three edges,
    asserting three calls where exactly one occurred — the shape the owner retired: a name is a
    mutable human convention and proves no linkage, so `init` matching three memberdefs is not
    three-quarters of an answer, it is no answer.

    The pair with `test_ast_record_no_match_silent` below is now the whole specification: an
    unresolved call and an unmatched call are indistinguishable in the table, because neither
    was proven. Only a UNIQUE match creates a row.
    """
    edges_resolved: list = []
    edges_fuzzy: list = []
    _ast_record_call_edge(
        caller_rowid=10,
        callee_name="init",
        name_to_rowids={"init": [42, 43, 44]},
        edges_resolved=edges_resolved,
        edges_fuzzy=edges_fuzzy,
    )
    assert edges_resolved == []
    assert edges_fuzzy == [], "one call site must never become three edges"


def test_ast_record_no_match_silent() -> None:
    edges_resolved: list = []
    edges_fuzzy: list = []
    _ast_record_call_edge(
        caller_rowid=10,
        callee_name="external_symbol",
        name_to_rowids={},
        edges_resolved=edges_resolved,
        edges_fuzzy=edges_fuzzy,
    )
    assert edges_resolved == []
    assert edges_fuzzy == []


# ─── call_edges.build_call_edges (Layer 1) ──────────────────────────────────


@pytest.fixture
def synthetic_doxygen_db(tmp_path: Path) -> Path:
    """A minimal doxygen-shaped sqlite DB for Layer 1 tests."""
    db_path = tmp_path / "doxygen.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT,
            name TEXT
        );
        CREATE TABLE xrefs (
            src_rowid INTEGER,
            dst_rowid INTEGER,
            context TEXT
        );
        INSERT INTO memberdef (rowid, kind, name) VALUES
            (1, 'function', 'caller_a'),
            (2, 'function', 'callee_a'),
            (3, 'function', 'callee_b'),
            (4, 'variable', 'some_global');
        INSERT INTO xrefs (src_rowid, dst_rowid, context) VALUES
            (1, 2, 'inline'),     -- caller_a calls callee_a (inline)
            (1, 3, 'inline'),     -- caller_a calls callee_b
            (1, 4, 'inline'),     -- caller_a refs a variable, NOT a function
            (2, 3, 'declaration');-- not 'inline' context, ignored
        """,
    )
    conn.commit()
    conn.close()
    return db_path


def test_build_call_edges_imports_only_function_inline_xrefs(
    synthetic_doxygen_db: Path,
) -> None:
    build_call_edges(synthetic_doxygen_db)
    conn = sqlite3.connect(str(synthetic_doxygen_db))
    rows = conn.execute(
        "SELECT caller_rowid, callee_rowid, source, confidence "
        "FROM call_edges ORDER BY caller_rowid, callee_rowid",
    ).fetchall()
    conn.close()
    # Two function-to-function edges expected. Variable ref dropped.
    # Non-inline xref dropped.
    assert rows == [
        (1, 2, "doxygen_sqlite", "exact"),
        (1, 3, "doxygen_sqlite", "exact"),
    ]


## @brief A doxygen-shaped DB whose calls go THROUGH a function-like macro.
## @param tmp_path Per-test temporary directory.
## @return Path to the fixture database.
## @version 1
@pytest.fixture
def macro_hop_db(tmp_path: Path) -> Path:
    """Reproduces what doxygen really emits for a wrapper macro, which is the whole
    reason the hop is recoverable: a `#define` is a first-class memberdef of
    `kind='macro definition'`, and BOTH halves are in `xrefs` —
    `caller → macro` and `macro → wrapped function`.

    `noise_macro` is the control: a macro referenced by a caller but referencing no
    function, so it must compose nothing rather than an edge to itself.

    `initializer` IS THE COLUMN doxygen ALREADY populates with each `#define`'s expansion,
    measured at 82.9% of Mbed-TLS/mbedtls's 2,582 macro rows and 80.2% of entropic's 111. gh#350
    reads it, so the fixture carries it — including one macro with a NULL initializer, since
    "doxygen recorded no expansion" is a real and common state that must not read as "no macro".

    `ALT_SET_FOO` mediates the SAME producer→store_set pair as `STORE_SET_FOO`, which is the
    ambiguity `MIN(macro.rowid)` resolves. It adds no edge — the pair is already there and
    `UNIQUE(caller, callee, source)` holds one row — so it changes no count in the older tests.
    """
    db_path = tmp_path / "macro.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        -- The columns the QUERY layer needs as well as the pipeline's: `definition`,
        -- `file_id`/`bodyfile_id` and a `path` row. gh#350 is the first change to read this
        -- fixture back through `q.callees`, and a fixture thin enough for one direction only
        -- fails with `no such table: path` — an error about the FIXTURE, which reads as a
        -- defect in the code under test.
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, initializer TEXT,
            definition TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER
        );
        CREATE TABLE xrefs (src_rowid INTEGER, dst_rowid INTEGER, context TEXT);
        INSERT INTO path (rowid, name) VALUES (1, 'src/store.c');
        INSERT INTO memberdef
            (rowid, kind, name, initializer, definition, file_id, bodyfile_id,
             bodystart, bodyend) VALUES
            (1, 'function', 'producer', NULL, 'void producer', 1, 1, 10, 20),
            (2, 'macro definition', 'STORE_SET_FOO', 'store_set(FOO, (v)), logger("set")',
             NULL, 1, 1, 3, 3),
            (3, 'function', 'store_set', NULL, 'void store_set', 1, 1, 30, 40),
            -- A macro doxygen recorded NO expansion for: named, but with nothing to quote.
            (4, 'macro definition', 'noise_macro', NULL, NULL, 1, 1, 4, 4),
            (5, 'function', 'logger', NULL, 'void logger', 1, 1, 50, 60),
            (6, 'variable', 'a_global', NULL, NULL, 1, 1, 0, 0),
            (7, 'macro definition', 'ALT_SET_FOO', 'store_set(FOO, (v))', NULL, 1, 1, 5, 5);
        INSERT INTO xrefs (src_rowid, dst_rowid, context) VALUES
            (1, 2, 'inline'),   -- producer mentions the wrapper macro
            (2, 3, 'inline'),   -- the macro body calls store_set
            (2, 5, 'inline'),   -- ... and logger: a MULTI-call macro, both real
            (1, 4, 'inline'),   -- producer mentions a macro that calls nothing
            (2, 6, 'inline'),   -- the macro also touches a variable, not a call
            (1, 7, 'inline'),   -- producer ALSO reaches store_set through a second macro
            (7, 3, 'inline');
        """,
    )
    conn.commit()
    conn.close()
    return db_path


def test_macro_hop_composes_the_two_hops_doxygen_already_recorded(
    macro_hop_db: Path,
) -> None:
    """The measured defect: both Layer-1 importers require BOTH endpoints to be
    `kind='function'`, so a `#define` in the middle discarded the pair and a caller whose
    only calls go through macros ended up with ZERO outgoing edges. Verified on a real C
    fixture — six such callers, six edges recovered.

    A MULTI-call macro yields several edges and all are real: expanding it at that site
    performs every call in its body. Non-function endpoints compose nothing."""
    build_call_edges(macro_hop_db)
    assert import_macro_hop_edges(macro_hop_db) == 2

    conn = sqlite3.connect(str(macro_hop_db))
    rows = conn.execute(
        "SELECT caller_rowid, callee_rowid, source, confidence FROM call_edges "
        "WHERE source = 'macro_hop' ORDER BY callee_rowid",
    ).fetchall()
    conn.close()
    assert rows == [
        (1, 3, "macro_hop", "resolved"),
        (1, 5, "macro_hop", "resolved"),
    ]


def test_macro_hop_is_resolved_not_exact(macro_hop_db: Path) -> None:
    """`exact` is reserved for what doxygen stated DIRECTLY. Both hops here are doxygen's
    own observations, so this outranks any name match — but the composition is ours, and
    labelling a joined edge `exact` would make it indistinguishable from an edge doxygen
    asserted about a single call site."""
    build_call_edges(macro_hop_db)
    import_macro_hop_edges(macro_hop_db)
    conn = sqlite3.connect(str(macro_hop_db))
    confidences = {
        r[0] for r in conn.execute("SELECT confidence FROM call_edges WHERE source='macro_hop'")
    }
    conn.close()
    assert confidences == {"resolved"}


def test_macro_hop_names_the_macro_that_made_the_edge(macro_hop_db: Path) -> None:
    """gh#350. A macro-hop edge is the ONE layer whose edge corresponds to no text in the
    caller's body — the call is written as a macro invocation, so searching `producer` for
    `store_set` finds nothing. Before this the caller saw an edge at confidence `resolved` and
    could not see what produced it.

    THE ROWID IS STORED, NOT THE TEXT. doxygen already keeps the expansion in
    `memberdef.initializer`, and copying it onto the edge would create a second place for it to
    go stale.

    Both edges of the MULTI-call macro name the same macro, which is the point: one macro
    invocation performs both calls."""
    build_call_edges(macro_hop_db)
    import_macro_hop_edges(macro_hop_db)

    conn = sqlite3.connect(str(macro_hop_db))
    rows = conn.execute(
        "SELECT e.callee_rowid, m.name FROM call_edges e "
        "JOIN memberdef m ON m.rowid = e.via_macro_rowid "
        "WHERE e.source = 'macro_hop' ORDER BY e.callee_rowid",
    ).fetchall()
    conn.close()

    assert rows == [(3, "STORE_SET_FOO"), (5, "STORE_SET_FOO")]


def test_a_pair_reachable_through_two_macros_names_one_deterministically(
    macro_hop_db: Path,
) -> None:
    """THE CHOICE THAT HAD TO BE MADE EXPLICIT. `UNIQUE(caller_rowid, callee_rowid, source)`
    holds ONE macro-hop row per pair, and this fixture reaches `store_set` from `producer`
    through both `STORE_SET_FOO` (rowid 2) and `ALT_SET_FOO` (rowid 7). Something must choose.

    Joining the macro to the UNIQUE key was the alternative and it is worse: it multiplies rows
    per neighbour, which is the inflation gh#38 removed — every neighbour list doubled and every
    depth cap truncating half the real edges.

    So the pair stays one row and `MIN(macro.rowid)` makes WHICH macro deterministic. A bare
    `DISTINCT` left it to whatever the query planner happened to return first, so two builds of
    the same commit could name different macros — a difference that would look like a change in
    the code. The macro named is therefore one WITNESS, not the only one, and the payload says so.
    """
    build_call_edges(macro_hop_db)
    import_macro_hop_edges(macro_hop_db)

    conn = sqlite3.connect(str(macro_hop_db))
    ## The row count is asserted FIRST: if the pair had split into two rows this test would
    ## still find rowid 2 among them and pass while the inflation shipped.
    n = conn.execute(
        "SELECT COUNT(*) FROM call_edges WHERE source='macro_hop' AND callee_rowid=3"
    ).fetchone()[0]
    via = conn.execute(
        "SELECT via_macro_rowid FROM call_edges WHERE source='macro_hop' AND callee_rowid=3"
    ).fetchone()[0]
    conn.close()

    assert n == 1, "one row per caller/callee pair — naming the macro must not multiply rows"
    assert via == 2, "MIN(macro.rowid): deterministic across builds of the same commit"


def test_the_query_layer_quotes_doxygens_own_expansion_verbatim(macro_hop_db: Path) -> None:
    """THE CONTROL THIS TASK ASKED FOR: the text a caller reads must be doxygen's own
    `initializer` for that macro, character for character. Comparing against the fixture's
    literal would only prove the fixture agrees with itself, so the expected value is READ BACK
    from `memberdef` in the assertion.

    PUBLISHED, NOT INTERPRETED. Nothing infers what the macro is for — that is the deliberate
    opposite of the rejected auto-discovery direction, which tried to derive a role from the
    expansion and could not, because one empty do-while shape is a disabled trace macro and a
    compiler hint and a portability stub at once."""
    from clew import query as q

    build_call_edges(macro_hop_db)
    import_macro_hop_edges(macro_hop_db)

    conn = sqlite3.connect(str(macro_hop_db))
    expected = conn.execute("SELECT initializer FROM memberdef WHERE rowid=2").fetchone()[0]
    conn.close()

    callees = {e.name: e for e in q.callees(macro_hop_db, "producer")}

    assert callees["store_set"].via_macro == "STORE_SET_FOO"
    assert callees["store_set"].via_macro_expansion == expected
    assert expected, "the fixture must carry a non-empty expansion or this asserts nothing"


def test_a_macro_with_no_recorded_expansion_is_still_named(macro_hop_db: Path) -> None:
    """`via_macro` SET with `via_macro_expansion` EMPTY is a real state, not a bug: 17-20% of
    macro rows on the measured public targets have no `initializer`. "This hop goes through
    THIS macro and doxygen recorded no body for it" is a different and more useful answer than
    silence, which is why the two fields are separate rather than one.

    Driven through the same fixture by pointing the edge at `noise_macro`, whose initializer is
    NULL — rather than by mutating the shipped rows, so the assertion is about the read path."""
    from clew import query as q

    build_call_edges(macro_hop_db)
    import_macro_hop_edges(macro_hop_db)
    conn = sqlite3.connect(str(macro_hop_db))
    conn.execute(
        "UPDATE call_edges SET via_macro_rowid=4 WHERE source='macro_hop' AND callee_rowid=3"
    )
    conn.commit()
    conn.close()

    edge = {e.name: e for e in q.callees(macro_hop_db, "producer")}["store_set"]

    assert edge.via_macro == "noise_macro", "the macro is named even with nothing to quote"
    assert edge.via_macro_expansion == ""


def test_macro_hop_adds_nothing_when_no_macro_mediates_a_call(
    synthetic_doxygen_db: Path,
) -> None:
    """NO INFLATION RISK, and this is the assertion that says so. Measured on both public
    targets — entropic (C++) and this repo's own Python self-index — the layer adds ZERO
    rows, because neither routes calls through wrapper macros. A layer that helps one
    codebase must not perturb every other."""
    build_call_edges(synthetic_doxygen_db)
    before = _count_edges(synthetic_doxygen_db)
    assert import_macro_hop_edges(synthetic_doxygen_db) == 0
    assert _count_edges(synthetic_doxygen_db) == before


## @brief Total call_edges rows in a database.
## @param db Database to count in.
## @return Row count.
## @version 1
def _count_edges(db: Path) -> int:
    """@brief Count call_edges rows.
    @return Row count.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0]
    finally:
        conn.close()


def test_build_call_edges_creates_indexes(
    synthetic_doxygen_db: Path,
) -> None:
    build_call_edges(synthetic_doxygen_db)
    conn = sqlite3.connect(str(synthetic_doxygen_db))
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='call_edges'",
        ).fetchall()
    }
    conn.close()
    assert "idx_call_edges_caller" in indexes
    assert "idx_call_edges_callee" in indexes


# ─── reachability ────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_reachability_db(tmp_path: Path) -> Path:
    """A minimal DB with memberdef + call_edges for reachability tests.

    Graph:
       main (1) → init (2) → helper (3)
                ↘ unused_helper (4) is dead
       app_main (5) → boot (6)
       orphan_func (7) is unreachable from any seed
    """
    db_path = tmp_path / "reach.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT,
            name TEXT
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER,
            callee_rowid INTEGER,
            source TEXT,
            confidence TEXT
        );
        INSERT INTO memberdef (rowid, kind, name) VALUES
            (1, 'function', 'main'),
            (2, 'function', 'do_init'),
            (3, 'function', 'helper'),
            (4, 'function', 'unused_helper'),
            (5, 'function', 'app_main'),
            (6, 'function', 'boot'),
            (7, 'function', 'orphan_func');
        INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) VALUES
            (1, 2, 'doxygen_sqlite', 'exact'),
            (2, 3, 'doxygen_sqlite', 'exact'),
            (5, 6, 'doxygen_sqlite', 'exact');
        """,
    )
    conn.commit()
    conn.close()
    return db_path


def test_gather_reachability_seeds_pattern_match(
    synthetic_reachability_db: Path,
) -> None:
    conn = sqlite3.connect(str(synthetic_reachability_db))
    pattern, _zero = _gather_reachability_seeds(
        conn,
        ["main", "app_main", "%init%"],
    )
    conn.close()
    # main(1), app_main(5), do_init(2). orphan_func should NOT match.
    assert pattern == {1, 2, 5}


def test_gather_reachability_seeds_zero_incoming(
    synthetic_reachability_db: Path,
) -> None:
    conn = sqlite3.connect(str(synthetic_reachability_db))
    _pattern, zero = _gather_reachability_seeds(conn, ["nope"])
    conn.close()
    # Functions with no non-fuzzy callers: main(1), app_main(5),
    # unused_helper(4), orphan_func(7). do_init(2), helper(3),
    # boot(6) all have callers.
    assert zero == {1, 4, 5, 7}


def test_bfs_live_set_walks_from_seeds(
    synthetic_reachability_db: Path,
) -> None:
    conn = sqlite3.connect(str(synthetic_reachability_db))
    live = _bfs_live_set(conn, {1, 5})  # start from main + app_main
    conn.close()
    # Reachable: main(1), do_init(2), helper(3), app_main(5), boot(6).
    # Not reachable from these seeds alone: unused_helper(4), orphan_func(7).
    assert live == {1, 2, 3, 5, 6}


def test_write_symbol_liveness_marks_correctly(
    synthetic_reachability_db: Path,
) -> None:
    conn = sqlite3.connect(str(synthetic_reachability_db))
    conn.execute(
        """
        CREATE TABLE symbol_liveness (
            memberdef_rowid INTEGER PRIMARY KEY,
            status TEXT
        )
        """,
    )
    live_count, total = _write_symbol_liveness(conn, {1, 2, 3, 5, 6})
    conn.commit()
    statuses = dict(
        conn.execute(
            "SELECT memberdef_rowid, status FROM symbol_liveness",
        ).fetchall(),
    )
    conn.close()
    assert live_count == 5
    assert total == 7
    assert statuses[1] == "live"
    assert statuses[4] == "orphan"
    assert statuses[7] == "orphan"


def test_mark_reachability_end_to_end(
    synthetic_reachability_db: Path,
) -> None:
    """Full mark_reachability call sets up symbol_liveness correctly."""
    mark_reachability(
        synthetic_reachability_db,
        entry_patterns=["main", "app_main"],
    )
    conn = sqlite3.connect(str(synthetic_reachability_db))
    statuses = dict(
        conn.execute(
            "SELECT memberdef_rowid, status FROM symbol_liveness",
        ).fetchall(),
    )
    conn.close()
    assert statuses[1] == "live"  # main (seeded by pattern)
    assert statuses[5] == "live"  # app_main (seeded by pattern)
    assert statuses[2] == "live"  # do_init reached from main
    assert statuses[3] == "live"  # helper reached from do_init
    assert statuses[6] == "live"  # boot reached from app_main
    # unused_helper (4) and orphan_func (7) are seeded as zero-incoming
    # and therefore live (conservative). The pure-orphan case requires
    # a graph where every function is reachable as a callee.
    # Here we just confirm the BFS reaches everything reachable.


def test_mark_reachability_no_edges_skips(tmp_path: Path) -> None:
    """Empty call_edges → log warning, leave symbol_liveness absent."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT,
            name TEXT
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER,
            callee_rowid INTEGER,
            source TEXT,
            confidence TEXT
        );
        INSERT INTO memberdef (rowid, kind, name) VALUES (1, 'function', 'x');
        """,
    )
    conn.commit()
    conn.close()
    mark_reachability(db)  # should not raise
    conn = sqlite3.connect(str(db))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        ).fetchall()
    }
    conn.close()
    assert "symbol_liveness" not in tables


def test_default_entry_patterns_covers_common_shapes() -> None:
    """Sanity-check the curated default list has the common ones."""
    assert "main" in DEFAULT_ENTRY_PATTERNS
    assert "%init%" in DEFAULT_ENTRY_PATTERNS
    assert "%task%" in DEFAULT_ENTRY_PATTERNS
    assert "%isr%" in DEFAULT_ENTRY_PATTERNS


# ─── requirements.ingest_requirements_yaml ──────────────────────────────────


def test_ingest_requirements_yaml_loads_rows(tmp_path: Path) -> None:
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    yaml_path = tmp_path / "requirements.yaml"
    yaml_path.write_text(
        """
        - id: REQ-0001
          block: startup
          title: Device boots and reports ready
          acceptance: Device emits ready event within 30s of power on
          priority: P0
        - id: REQ-0002
          block: connectivity
          title: Device connects to wifi
          acceptance: Device joins configured SSID within 60s
          priority: P1
        """,
    )
    ingest_requirements_yaml(db, yaml_path)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT id, block, title, acceptance, priority FROM requirements ORDER BY id",
    ).fetchall()
    conn.close()
    assert rows == [
        (
            "REQ-0001",
            "startup",
            "Device boots and reports ready",
            "Device emits ready event within 30s of power on",
            "P0",
        ),
        (
            "REQ-0002",
            "connectivity",
            "Device connects to wifi",
            "Device joins configured SSID within 60s",
            "P1",
        ),
    ]


def test_ingest_requirements_yaml_reads_the_mapping_keyed_shape(tmp_path: Path) -> None:
    """The shape doxygen-guard 1.3.1 ships for its OWN catalog: a `requirements:`
    mapping keyed by requirement id, with the id as the key and `name` as the title
    field. Its schema is why — `formats_using_id_column` lists only csv and json, so a
    YAML catalog is keyed and self-describing.

    A REGRESSION TEST with a measured origin. Against the pinned public integration
    target (doxygen-guard at its own HEAD) a 9,534-byte catalog of 22 requirements
    ingested ZERO rows, and nothing errored — an empty table reads exactly like a repo
    with no catalog at all. That is the third time in this project that "no rows" turned
    out to be a claim about the DETECTOR rather than the data.

    The fixture deliberately uses `name`, not `title`, because the whole point is that
    the declared field mapping is honoured rather than this repo's own convention.

    Ids are the sanctioned meaningless placeholders, not the real target's. The first
    draft used the target's own real ids and a publishability gate refused them, on the
    rule "allowlist ONLY if invented". That gate is DELETED and NOTHING now checks which
    ids a fixture borrows. The convention still holds for the original reason: the shape
    is what this test asserts, and borrowing real ids to assert a shape buys nothing.
    The real-target verification lives outside the unit suite."""
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    yaml_path = tmp_path / "requirements.yaml"
    yaml_path.write_text(
        """
        requirements:
          REQ-X-FOO-001:
            name: Doxygen presence check
            subsystem: Validate
            min_version: v0.1.0
          REQ-X-BAR-002:
            name: Version staleness detection
            subsystem: Validate
        """,
    )
    ## name_column='name' as the guard's own config declares it; id_column is irrelevant
    ## to this shape and is passed as the csv default to prove it is not consulted.
    guard_cfg = {"impact": {"requirements": {"name_column": "name", "id_column": "Req ID"}}}
    ingest_requirements_yaml(db, yaml_path, guard_cfg)

    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT id, title FROM requirements ORDER BY id").fetchall()
    conn.close()
    ## Expected in `ORDER BY id` order, which is not declaration order — BAR sorts
    ## before FOO. Asserting the sorted order rather than reordering the fixture keeps
    ## the fixture reading like a real catalog, where ids are not in alphabetical order.
    assert rows == [
        ("REQ-X-BAR-002", "Version staleness detection"),
        ("REQ-X-FOO-001", "Doxygen presence check"),
    ]


def test_ingest_requirements_yaml_still_refuses_an_unrecognized_shape(tmp_path: Path) -> None:
    """Reading a second shape must not become "read anything". A nested `domains:` tree
    is parsed only by the owning repo's own scripts, and guessing at it would invent
    traceability rather than report it — so it stays 0 rows, with the table created so
    downstream LEFT JOINs still work."""
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    yaml_path = tmp_path / "requirements.yaml"
    yaml_path.write_text(
        """
        domains:
          navigation:
            requirements:
              - REQ-X-BAZ-003
        """,
    )
    ingest_requirements_yaml(db, yaml_path)

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    conn.close()
    assert count == 0


def test_ingest_requirements_yaml_none_path_creates_empty_table(
    tmp_path: Path,
) -> None:
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    ingest_requirements_yaml(db, None)
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    conn.close()
    assert count == 0


def test_ingest_requirements_yaml_missing_file_creates_empty_table(
    tmp_path: Path,
) -> None:
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    ingest_requirements_yaml(db, tmp_path / "does_not_exist.yaml")
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    conn.close()
    assert count == 0


# ─── requirements._extract_req_tags ─────────────────────────────────────────


def test_extract_req_tags_stated() -> None:
    assert _extract_req_tags("Handles startup. @req REQ-0042") == [
        "REQ-0042",
    ]


def test_extract_req_tags_inferred() -> None:
    assert _extract_req_tags("Handles startup. @req REQ-0042 [inferred]") == [
        "REQ-0042",
    ]


def test_extract_req_tags_no_tag_returns_empty() -> None:
    assert _extract_req_tags("Just a normal description, no requirement tag.") == []


def test_extract_req_tags_none_text_returns_empty() -> None:
    assert _extract_req_tags(None) == []


# ─── requirements.import_req_edges ──────────────────────────────────────────


@pytest.fixture
def req_tagged_db(tmp_path: Path) -> Path:
    """A minimal doxygen-shaped DB with @req-tagged memberdefs."""
    db_path = tmp_path / "doxy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER,
            briefdescription TEXT, detaileddescription TEXT
        );
        INSERT INTO path (rowid, name) VALUES
            (1, 'src/startup.c'), (2, 'tests/test_startup.c');
        INSERT INTO memberdef
            (rowid, kind, name, file_id, briefdescription, detaileddescription)
        VALUES
            (1, 'function', 'device_boot', 1, 'Boots the device.',
             '@req REQ-0001'),
            (2, 'function', 'test_device_boot', 2, 'Covers boot.',
             '@req REQ-0001'),
            (3, 'function', 'helper_no_req', 1, 'No requirement tag here.', '');
        """,
    )
    conn.commit()
    conn.close()
    return db_path


def test_import_req_edges_creates_expected_rows(req_tagged_db: Path) -> None:
    import_req_edges(req_tagged_db)
    conn = sqlite3.connect(str(req_tagged_db))
    rows = conn.execute(
        "SELECT req_id, memberdef_rowid FROM req_edges ORDER BY memberdef_rowid",
    ).fetchall()
    conn.close()
    assert rows == [
        ("REQ-0001", 1),
        ("REQ-0001", 2),
    ]


# ─── requirements._looks_like_test_function / import_req_test_edges ────────


def test_looks_like_test_function_name_prefix() -> None:
    assert _looks_like_test_function("test_foo", "src/foo.c") is True


def test_looks_like_test_function_file_path() -> None:
    assert _looks_like_test_function("foo", "tests/test_foo.c") is True


def test_looks_like_test_function_neither() -> None:
    assert _looks_like_test_function("device_boot", "src/startup.c") is False


def test_import_req_test_edges_links_only_test_named_memberdefs(
    req_tagged_db: Path,
) -> None:
    import_req_edges(req_tagged_db)
    import_req_test_edges(req_tagged_db)
    conn = sqlite3.connect(str(req_tagged_db))
    rows = conn.execute(
        "SELECT req_id, test_memberdef_rowid FROM req_test_edges",
    ).fetchall()
    conn.close()
    # rowid 2 (test_device_boot) is test-named; rowid 1 (device_boot) is not.
    assert rows == [("REQ-0001", 2)]


# ─── shared_key_edges (Layer 5) ──────────────────────────────────────────────


## @brief Build a doxygen-shaped db (path + memberdef) with no shared_key_edges yet.
## @version 1
def _make_shared_key_db(tmp_path: Path, functions: list[tuple[int, str, int, int]]) -> Path:
    """functions: list of (rowid, name, bodystart, bodyend), all in one file
    (file_id=1, path 'src/foo.c').

    @brief Seed a doxygen-shaped memberdef/path db for shared-key tests.
    @version 1
    """
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'src/foo.c')")
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?)",
        functions,
    )
    conn.commit()
    conn.close()
    return db_path


## @brief Write the writer/reader accessor-pattern YAML fixture.
## @version 1
def _write_shared_key_patterns_yaml(tmp_path: Path) -> Path:
    patterns_path = tmp_path / "shared_key_patterns.yaml"
    patterns_path.write_text(
        """
        writers:
          - pattern: "datamodel_set"
            key_arg_index: 0
        readers:
          - pattern: "datamodel_get"
            key_arg_index: 0
        """,
    )
    return patterns_path


def test_load_shared_key_patterns_parses_writers_and_readers(tmp_path: Path) -> None:
    patterns_path = _write_shared_key_patterns_yaml(tmp_path)
    writers, readers = load_shared_key_patterns(patterns_path)
    assert len(writers) == 1
    assert writers[0].pattern == "datamodel_set"
    assert writers[0].key_arg_index == 0
    assert len(readers) == 1
    assert readers[0].pattern == "datamodel_get"


## @brief Write a name_prefix-style (key-in-callee-name) pattern YAML fixture.
## @version 1
def _write_name_prefix_patterns_yaml(tmp_path: Path) -> Path:
    patterns_path = tmp_path / "shared_key_patterns_prefix.yaml"
    patterns_path.write_text(
        """
        writers:
          - name_prefix: "STORE_SET_"
        readers:
          - name_prefix: "STORE_GET_"
        """,
    )
    return patterns_path


def test_load_shared_key_patterns_parses_name_prefix(tmp_path: Path) -> None:
    patterns_path = _write_name_prefix_patterns_yaml(tmp_path)
    writers, readers = load_shared_key_patterns(patterns_path)
    assert len(writers) == 1
    assert writers[0].prefix == "STORE_SET_"
    assert len(readers) == 1
    assert readers[0].prefix == "STORE_GET_"


def test_import_shared_key_edges_inferred_name_prefix_key_in_callee_name(
    tmp_path: Path,
) -> None:
    """The real generated-data-model convention confirmed live: one accessor
    function PER KEY, no key argument at all — the key is the remainder
    of the callee name after a fixed prefix
    (STORE_SET_ROBOT_SOUND_EVENT_SET(value),
    STORE_GET_ROBOT_SOUND_EVENT_SET())."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void handle_ping_cmd(void) {\n"
        "    STORE_SET_ROBOT_SOUND_EVENT_SET(true);\n"
        "}\n"
        "\n"
        "void handle_sound_event_findme(void) {\n"
        "    STORE_GET_ROBOT_SOUND_EVENT_SET();\n"
        "}\n",
    )
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "handle_ping_cmd", 1, 3), (2, "handle_sound_event_findme", 5, 7)],
    )
    patterns_path = _write_name_prefix_patterns_yaml(tmp_path)

    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [(1, 2, "ROBOT_SOUND_EVENT_SET")]


def test_name_prefix_exact_prefix_match_has_no_key_remainder(tmp_path: Path) -> None:
    """A callee name that is EXACTLY the prefix (no remainder) must not
    match — there is no key to extract, so it's not a valid accessor call
    for this convention, not an unresolved one."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void caller(void) {\n    STORE_SET_(1);\n}\n",
    )
    db_path = _make_shared_key_db(tmp_path, [(1, "caller", 1, 3)])
    patterns_path = _write_name_prefix_patterns_yaml(tmp_path)

    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM shared_key_edges").fetchone()[0]
    unresolved_before = 0  # exact-prefix-only is simply not a match, not unresolved
    conn.close()
    assert count == unresolved_before


def test_import_shared_key_edges_inferred_literal_key_match(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void caller_a(void) {\n"
        '    datamodel_set("KEY_A");\n'
        "}\n"
        "\n"
        "void caller_b(void) {\n"
        '    datamodel_get("KEY_A");\n'
        "}\n",
    )
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "caller_a", 1, 3), (2, "caller_b", 5, 7)],
    )
    patterns_path = _write_shared_key_patterns_yaml(tmp_path)

    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, declared, "
        "source, confidence FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [(1, 2, "KEY_A", "unknown", 0, "shared_key_inferred", "medium")]


def test_import_shared_key_edges_inferred_queue_handle_pointer_unwrapped(
    tmp_path: Path,
) -> None:
    # Async-queue dataflow: the queue handle is passed by address
    # (`QUEUESEND(&msg_queue, m)`), so _resolve_literal_key must unwrap the
    # pointer_expression to the inner identifier for enqueue->dequeue pairs
    # to compose across the queue boundary.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void producer_task(void) {\n"
        "    QUEUESEND(&msg_queue, msg);\n"
        "}\n"
        "\n"
        "void consumer_task(void) {\n"
        "    QUEUERECEIVE(&msg_queue, &msg);\n"
        "}\n",
    )
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "producer_task", 1, 3), (2, "consumer_task", 5, 7)],
    )
    patterns_path = tmp_path / "queue_patterns.yaml"
    patterns_path.write_text(
        """
        writers:
          - pattern: "QUEUESEND"
            key_arg_index: 0
        readers:
          - pattern: "QUEUERECEIVE"
            key_arg_index: 0
        """,
    )

    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, declared, "
        "source, confidence FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [
        (1, 2, "msg_queue", "unknown", 0, "shared_key_inferred", "medium"),
    ]


def test_import_shared_key_edges_inferred_non_literal_key_unresolved(
    tmp_path: Path,
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void caller_c(void) {\n    int key = get_key();\n    datamodel_set(key);\n}\n",
    )
    db_path = _make_shared_key_db(tmp_path, [(1, "caller_c", 1, 4)])
    patterns_path = _write_shared_key_patterns_yaml(tmp_path)

    # Must not crash on a computed (non-literal) key argument.
    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM shared_key_edges").fetchone()[0]
    conn.close()
    assert count == 0


def test_import_shared_key_edges_inferred_no_patterns_uses_ingot_defaults(
    tmp_path: Path,
) -> None:
    """With no --shared-key-patterns, the pass now falls back to the built-in
    ingot accessor defaults instead of skipping (a repo whose whole causal
    layer went missing simply because a flag was omitted is the failure this
    guards against). The fixture has no `DataModel_Set_/Get_` accessors, so the
    defaults fire but match nothing: the table IS created and holds 0 edges —
    'ran and found none', not 'never ran'."""
    db_path = _make_shared_key_db(tmp_path, [])
    import_shared_key_edges_inferred(db_path, tmp_path, None)
    conn = sqlite3.connect(str(db_path))
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shared_key_edges'",
    ).fetchone()
    n = conn.execute("SELECT count(*) FROM shared_key_edges").fetchone()[0]
    conn.close()
    assert has_table is not None, "the defaulted pass must run and create the table"
    assert n == 0, "no ingot accessors in the fixture ⇒ zero edges (no false positives)"


def test_import_shared_key_edges_inferred_ingot_defaults_fire(
    tmp_path: Path,
) -> None:
    """The heart of the default: a repo using the ingot per-key accessor
    convention (DataModel_Set_<KEY> / DataModel_Get_<KEY>) gets its shared-key
    seam WITHOUT passing --shared-key-patterns. This is what a bare
    build_or_refresh must do so chain_trace has seams to cross."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = (
        "void producer(void) {\n"
        "    DataModel_Set_SOUND_EVENT(3);\n"
        "}\n"
        "void consumer(void) {\n"
        "    int v = DataModel_Get_SOUND_EVENT();\n"
        "    (void)v;\n"
        "}\n"
    )
    (src_dir / "foo.c").write_text(src)
    functions = [(1, "producer", 1, 3), (2, "consumer", 4, 7)]
    db_path = _make_shared_key_db(tmp_path, functions)
    # No patterns file — the built-in ingot defaults must supply the edge.
    import_shared_key_edges_inferred(db_path, tmp_path, None)
    conn = sqlite3.connect(str(db_path))
    edges = conn.execute(
        "SELECT w.name, r.name, key_name FROM shared_key_edges s "
        "JOIN memberdef w ON w.rowid=s.writer_rowid "
        "JOIN memberdef r ON r.rowid=s.reader_rowid",
    ).fetchall()
    conn.close()
    assert ("producer", "consumer", "SOUND_EVENT") in edges, (
        f"ingot default should link producer->consumer on SOUND_EVENT; got {edges}"
    )


## @brief Seed a path/memberdef pair for the zero-bodies diagnostic.
## @param tmp_path Per-test temporary directory.
## @param files (name, has_body) per indexed file.
## @return Path to the seeded database.
## @version 1
def _bodies_db(tmp_path: Path, files: list[tuple[str, bool]]) -> Path:
    """@brief Seed indexed files, each with or without a function body.

    @return Database path.
    @version 1
    """
    db_path = tmp_path / "bodies.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        "CREATE TABLE path (name TEXT);"
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,"
        " file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER);"
    )
    for index, (name, has_body) in enumerate(files, start=1):
        conn.execute("INSERT INTO path (rowid, name) VALUES (?, ?)", (index, name))
        if has_body:
            conn.execute(
                "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend)"
                " VALUES ('function', ?, ?, ?, 1, 9)",
                (f"fn_{index}", index, index),
            )
    conn.commit()
    conn.close()
    return db_path


def test_indexed_implementation_with_zero_function_bodies_warns(tmp_path: Path) -> None:
    """A build that indexes source and extracts NOTHING reports success today.

    MEASURED on a real C library whose implementation sits behind
    `#if defined(<FEATURE>_C)` guards: 30 `.c` files in `path`, ZERO functions
    with a body in any of them, and a normal summary printed. The database
    described a library with no implementation, and every AST and call-graph
    layer read empty against it. Supplying PREDEFINED took the same build to 322
    bodies.

    clew must not GUESS a target's feature macros — that is the target's
    declaration to make — so this warns rather than failing or fixing. But the
    ratio is never legitimately zero for a real C/C++ codebase, so silence was
    the wrong default.

    @brief Zero bodies across indexed implementation files is reported.
    @version 1
    """
    db_path = _bodies_db(tmp_path, [("src/a.c", False), ("src/b.c", False)])
    assert warn_if_no_function_bodies(db_path) == 2


def test_a_header_only_index_does_NOT_warn(tmp_path: Path) -> None:
    """The counter-case, and the reason the check requires implementation files.

    A header-only library, or a docs-oriented Doxyfile carrying
    `FILE_PATTERNS = *.h`, legitimately indexes zero `.c` bodies. Both are real:
    the same C library above ships a Doxyfile that indexes headers ONLY, so a
    naive "no bodies anywhere" check would have fired on a correct build and
    trained the reader to ignore it.

    @brief Headers with no bodies are not a defect and must not warn.
    @version 1
    """
    db_path = _bodies_db(tmp_path, [("include/a.h", False), ("include/b.h", False)])
    assert warn_if_no_function_bodies(db_path) == 0


def test_implementation_with_at_least_one_body_does_NOT_warn(tmp_path: Path) -> None:
    """One real body is enough to prove the preprocessor is satisfied.

    @brief A partially-extracted index is not the failure this catches.
    @version 1
    """
    db_path = _bodies_db(tmp_path, [("src/a.c", True), ("src/b.c", False)])
    assert warn_if_no_function_bodies(db_path) == 0


def test_undeclared_accessor_families_sees_MACRO_defined_accessors(tmp_path: Path) -> None:
    """The diagnostic must read `kind='macro definition'`, not functions alone.

    A repo whose accessor family is macro-defined produces ZERO `kind='function'`
    rows, so a functions-only query stays silent — and that silence reads as
    evidence the repo has no dataflow.

    The literal is load-bearing: `macro definition` is what doxygen emits, and a
    fixture using any other spelling proves only that it agrees with the code.

    @brief Macro-defined accessor families are detected, not invisible.
    @version 2
    """
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'src/store.h')")
    ## Macros only — deliberately NOT one function row, so the test fails
    ## against a `kind='function'` query rather than passing by accident.
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES (?, 'macro definition', ?, 1, 1, 0, 0)",
        [
            (1, "Store_Set_ALPHA"),
            (2, "Store_Set_BETA"),
            (3, "Store_Set_GAMMA"),
            (4, "Store_Set_DELTA"),
            (5, "Store_Set_EPSILON"),
        ],
    )
    conn.commit()

    fams = {f.prefix: f.keys for f in detect_undeclared_accessor_families(conn, [])}
    conn.close()
    ## `Store_Set_`, with the separator: the prefix group is what a
    ## `NamePrefixPattern` would be declared as, so it carries the trailing `_`.
    assert fams.get("Store_Set_") == 5, (
        "a macro-defined accessor family must be surfaced; the diagnostic read "
        f"only kind='function' and was structurally blind to it. got: {fams}"
    )


def test_detect_undeclared_accessor_families(tmp_path: Path) -> None:
    """The advisory diagnostic surfaces set/get accessor FAMILIES (one function
    per key, shared long prefix) that no active pattern covers — both CamelCase
    (`Store_SetAreaData`) and snake+underscore (`Foo_Set_BAR`) — while rejecting
    the shapes that are NOT a data model: an object setter with no leading token
    (`set_level`), a lowercase command handler (`handle_get_stage_list_cmd`), a
    family below the key threshold, and a family already covered by a pattern."""
    functions = [
        # CamelCase family (5 keys) — should be suggested.
        (1, "Store_SetAreaData", 1, 1),
        (2, "Store_SetBleData", 2, 2),
        (3, "Store_SetCleanStatus", 3, 3),
        (4, "Store_SetDockCoordData", 4, 4),
        (5, "Store_SetHeartbeat", 5, 5),
        # Object setters — no leading token before the verb ⇒ excluded.
        (6, "set_level", 6, 6),
        (7, "set_speed", 7, 7),
        # Lowercase command handler ⇒ excluded (key is a verb phrase, not a key).
        (8, "handle_get_stage_list_cmd", 8, 8),
        # Below-threshold family (only 2 keys) ⇒ excluded.
        (9, "Tiny_SetA", 9, 9),
        (10, "Tiny_SetB", 10, 10),
        # A family that IS covered by an active pattern ⇒ excluded.
        (11, "DataModel_Set_ALPHA", 11, 11),
        (12, "DataModel_Set_BETA", 12, 12),
        (13, "DataModel_Set_GAMMA", 13, 13),
        (14, "DataModel_Set_DELTA", 14, 14),
    ]
    db_path = _make_shared_key_db(tmp_path, functions)
    conn = sqlite3.connect(str(db_path))
    fams = detect_undeclared_accessor_families(conn, [NamePrefixPattern("DataModel_Set_")])
    conn.close()
    fam_map = {f.prefix: f.keys for f in fams}
    assert fam_map.get("Store_Set") == 5, (
        f"Store_Set family (5 keys) should be suggested; got {fams}"
    )
    prefixes = set(fam_map)
    assert not any(p.startswith("set_") for p in prefixes), "object setters must not cluster"
    assert not any("handle" in p for p in prefixes), "command handler must be excluded"
    assert "Tiny_Set" not in prefixes, "below-threshold family must be excluded"
    assert not any(p.startswith("DataModel_Set") for p in prefixes), "covered family excluded"


## @brief Build a C file where `n_writers` functions write a key and `n_readers` read it.
## @param tmp_path Test temp directory.
## @param key_name The shared key both sides name.
## @param n_writers How many distinct writer functions to emit.
## @param n_readers How many distinct reader functions to emit.
## @return Path to the built database.
## @version 1
def _shared_key_shape(
    tmp_path: Path,
    key_name: str,
    n_writers: int,
    n_readers: int,
) -> Path:
    """Parameterised over BOTH sides, which the fixture it replaces was not: the old
    one hard-coded a single reader, so the only shape it could express was the funnel
    — and it asserted that shape produced nothing (gh#28).

    @brief Emit a writers x readers shared-key fixture and index it.
    @return Path to the built database.
    @version 1
    """
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    lines: list[str] = []
    functions: list[tuple[int, str, int, int]] = []
    rowid = 1
    line_no = 1
    for role, count, accessor in (("writer", n_writers, "set"), ("reader", n_readers, "get")):
        for i in range(count):
            start = line_no
            lines.append(f"void {role}_{i}(void) {{\n")
            lines.append(f'    datamodel_{accessor}("{key_name}");\n')
            lines.append("}\n")
            line_no += 3
            functions.append((rowid, f"{role}_{i}", start, line_no - 1))
            rowid += 1
    (src_dir / "foo.c").write_text("".join(lines))
    db_path = _make_shared_key_db(tmp_path, functions)
    import_shared_key_edges_inferred(db_path, tmp_path, _write_shared_key_patterns_yaml(tmp_path))
    return db_path


## @brief Count the edges a given key contributed.
## @param db_path Built database.
## @param key_name Key to count.
## @return Number of shared_key_edges rows for that key.
## @version 1
def _key_edge_count(db_path: Path, key_name: str) -> int:
    """@brief Read back one key's edge count.
    @return Row count for the key.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM shared_key_edges WHERE key_name = ?", (key_name,)
    ).fetchone()[0]
    conn.close()
    return count


## @brief A funnel key — many writers, ONE reader — survives fan-out suppression.
## @version 1
def test_shared_key_funnel_key_survives_suppression(tmp_path: Path) -> None:
    """THE gh#28 DEFECT, and this test replaces one that asserted the opposite.

    The test that used to live here built 9 writers and 1 reader and asserted the key
    produced ZERO edges. That is exactly the funnel shape gh#28 was filed about, so
    the buggy behaviour was pinned by a passing test — which is why it survived. The
    per-side ceiling is not being loosened out of taste: a funnel contributes
    `writers x 1` edges, which is linear, while the O(n^2) blob the ceiling exists to
    stop needs both sides large.

    A funnel is also the most valuable shape the layer can find — every producer in
    the codebase converging on one consumer, where the single reader is the place the
    meaning lives.

    @brief Many writers into one reader are not suppressed.
    @version 1
    """
    n_writers = _MAX_KEY_EDGES // 2
    db_path = _shared_key_shape(tmp_path, "FUNNEL_KEY", n_writers, 1)
    assert _key_edge_count(db_path, "FUNNEL_KEY") == n_writers


## @brief A broadcast key — one writer, many readers — survives too.
## @version 1
def test_shared_key_broadcast_key_survives_suppression(tmp_path: Path) -> None:
    """The funnel's dual, and suppressed by the same per-side test for the same wrong
    reason. `1 x readers` is linear.

    @brief One writer out to many readers is not suppressed.
    @version 1
    """
    n_readers = _MAX_KEY_EDGES // 2
    db_path = _shared_key_shape(tmp_path, "BROADCAST_KEY", 1, n_readers)
    assert _key_edge_count(db_path, "BROADCAST_KEY") == n_readers


## @brief A genuine quadratic fan-out key is still suppressed entirely.
## @version 1
def test_shared_key_quadratic_fanout_key_still_suppressed(tmp_path: Path) -> None:
    """THE CONTROL, without which the two tests above only prove the ceiling was
    removed rather than re-aimed. A generic status-flag key touched by many writers
    AND many readers is the noise blob the suppression exists for: 9 x 9 = 81 edges,
    above the 64-edge ceiling, and it must still yield nothing.

    Note how close this sits to the funnel above — 9 writers is FEWER writers than
    the funnel case has, and it is suppressed while the funnel is admitted. That is
    the point: the discriminator is the product, not the size of the larger side.

    @brief A many-to-many key is suppressed.
    @version 1
    """
    db_path = _shared_key_shape(tmp_path, "STATUS_FLAG", 9, 9)
    assert 9 * 9 > _MAX_KEY_EDGES, "fixture must exceed the ceiling to be a control"
    assert _key_edge_count(db_path, "STATUS_FLAG") == 0


## @brief A key at exactly the ceiling is admitted; the boundary is inclusive.
## @version 1
def test_shared_key_at_the_edge_ceiling_is_admitted(tmp_path: Path) -> None:
    """8 x 8 = 64 is the OLD rule's maximum admission, and it must still be admitted:
    the product ceiling was chosen to be exactly that number so no key the previous
    rule allowed is newly discarded. A test on the boundary is the only thing that
    holds that promise.

    @brief The 8x8 key the old per-side rule admitted is still admitted.
    @version 1
    """
    db_path = _shared_key_shape(tmp_path, "BOUNDARY_KEY", 8, 8)
    assert _key_edge_count(db_path, "BOUNDARY_KEY") == _MAX_KEY_EDGES


## @brief A suppressed key is named in the log, not just counted.
## @version 1
def test_shared_key_suppressed_key_is_named_in_the_log(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """gh#28's secondary ask. The layer reported `6 fan-out keys suppressed` and never
    which, so a reader whose key returned nothing had no way to learn it was one of
    the six short of reading the module source.

    @brief The suppressed key's name and shape appear at INFO.
    @version 1
    """
    with caplog.at_level(logging.INFO, logger="clew"):
        _shared_key_shape(tmp_path, "NOISY_KEY", 9, 9)
    assert "NOISY_KEY" in caplog.text
    assert "9 writers x 9 readers" in caplog.text


def test_import_shared_key_edges_inferred_case_label_is_a_reader_site(
    tmp_path: Path,
) -> None:
    """A `switch (key) { case KEY_X: ...; }` dispatch is a real-world
    reader shape with no accessor call at all — a plain writer call plus a
    case label sharing the same literal must still produce an edge."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void caller_a(void) {\n"
        '    datamodel_set("KEY_A");\n'
        "}\n"
        "\n"
        "void dispatcher(int key) {\n"
        "    switch (key) {\n"
        "        case KEY_A:\n"
        "            break;\n"
        "        default:\n"
        "            break;\n"
        "    }\n"
        "}\n",
    )
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "caller_a", 1, 3), (2, "dispatcher", 5, 12)],
    )
    patterns_path = _write_shared_key_patterns_yaml(tmp_path)

    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [(1, 2, "KEY_A")]


def test_import_shared_key_edges_inferred_default_case_is_not_a_match(
    tmp_path: Path,
) -> None:
    """`default:` has no value field — it must be skipped silently, never
    counted unresolved and never matched as a key."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "foo.c").write_text(
        "void dispatcher(int key) {\n"
        "    switch (key) {\n"
        "        default:\n"
        "            break;\n"
        "    }\n"
        "}\n",
    )
    db_path = _make_shared_key_db(tmp_path, [(1, "dispatcher", 1, 6)])
    patterns_path = _write_shared_key_patterns_yaml(tmp_path)

    import_shared_key_edges_inferred(db_path, tmp_path, patterns_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM shared_key_edges").fetchone()[0]
    conn.close()
    assert count == 0


def test_import_shared_key_edges_declared_event_edge(tmp_path: Path) -> None:
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "handle_ping_cmd", 1, 3), (2, "handle_sound_event_findme", 5, 8)],
    )
    data_model_path = tmp_path / "data_model.toml"
    data_model_path.write_text(
        """
        [[keys]]
        name = "ROBOT_SOUND_EVENT_TYPE"
        persistent = false
        event = true
        writers = ["handle_ping_cmd"]
        readers = ["handle_sound_event_findme"]
        """,
    )

    import_shared_key_edges_declared(db_path, data_model_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, declared, "
        "source, confidence FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [
        (1, 2, "ROBOT_SOUND_EVENT_TYPE", "event", 1, "shared_key_declared", "high"),
    ]


def test_import_shared_key_edges_declared_yaml_manifest(tmp_path: Path) -> None:
    # data-model-style YAML manifest (same keys: shape as the ingot TOML) — the
    # --data-model parser dispatches on suffix (.yaml/.yml -> YAML).
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "handle_ping_cmd", 1, 3), (2, "handle_sound_event_findme", 5, 8)],
    )
    data_model_path = tmp_path / "data_model.yaml"
    data_model_path.write_text(
        "keys:\n"
        "  - name: ROBOT_SOUND_EVENT_TYPE\n"
        "    event: true\n"
        "    writers: [handle_ping_cmd]\n"
        "    readers: [handle_sound_event_findme]\n",
    )

    import_shared_key_edges_declared(db_path, data_model_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, declared FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [(1, 2, "ROBOT_SOUND_EVENT_TYPE", "event", 1)]


def test_import_shared_key_edges_declared_dedups_decl_def_rows(
    tmp_path: Path,
) -> None:
    # A function declared in a header AND defined in a .c file has two
    # memberdef rows (decl: file_id != bodyfile_id; def: file_id ==
    # bodyfile_id). Resolving a manifest writer/reader NAME must NOT
    # cross-product decl x def into duplicate edges — one manifest edge =
    # one row. Regression: previously inserted 4x (2 writers x 2 readers).
    db_path = _make_shared_key_db(
        tmp_path,
        [(1, "handle_ping_cmd", 1, 3), (2, "handle_sound_event_findme", 5, 8)],
    )
    conn = sqlite3.connect(str(db_path))
    # Header-declaration rows for the same two names: file_id (2) != bodyfile_id
    # (1) marks them as declarations, not definitions.
    conn.execute("INSERT INTO path (rowid, name) VALUES (2, 'inc/foo.h')")
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES (?, 'function', ?, 2, 1, ?, ?)",
        [(3, "handle_ping_cmd", 1, 1), (4, "handle_sound_event_findme", 1, 1)],
    )
    conn.commit()
    conn.close()

    data_model_path = tmp_path / "data_model.toml"
    data_model_path.write_text(
        """
        [[keys]]
        name = "ROBOT_SOUND_EVENT_TYPE"
        event = true
        writers = ["handle_ping_cmd"]
        readers = ["handle_sound_event_findme"]
        """,
    )
    import_shared_key_edges_declared(db_path, data_model_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name FROM shared_key_edges",
    ).fetchall()
    conn.close()
    # Definition rows preferred (1 -> 2), exactly one edge, not four.
    assert rows == [(1, 2, "ROBOT_SOUND_EVENT_TYPE")]


def test_import_shared_key_edges_declared_no_path_skips(tmp_path: Path) -> None:
    db_path = _make_shared_key_db(tmp_path, [])
    import_shared_key_edges_declared(db_path, None)
    conn = sqlite3.connect(str(db_path))
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shared_key_edges'",
    ).fetchone()
    conn.close()
    assert has_table is None


def test_discover_doxyfile_refuses_to_guess_among_strays(tmp_path: Path) -> None:
    """#55, found by dogfooding clew on itself. discover_doxyfile used to
    fall back to sorted(repo.glob("*/Doxyfile"))[0] — ANY subdirectory, picked
    alphabetically. On clew that selected sample/Doxyfile, the demobot TEST
    FIXTURE, to index the whole project, and ran doxygen with cwd=sample/.

    It was masked because --scope from-guard replaces INPUT; under
    --scope doxyfile the fixture's own INPUT would have been honoured and
    clew would have indexed demobot instead of itself — silently, producing
    a well-formed database describing the wrong code.

    A wrong Doxyfile is worse than none, because none triggers synthesis from
    the declared scope (#33)."""
    from clew.doxygen import discover_doxyfile

    repo = tmp_path / "repo"
    (repo / "sample").mkdir(parents=True)
    (repo / "sample" / "Doxyfile").write_text("PROJECT_NAME = fixture\n")
    assert discover_doxyfile(repo) is None, "a fixture Doxyfile must not be adopted"

    # Doxygen's own conventional locations ARE trusted.
    (repo / "docs").mkdir()
    (repo / "docs" / "Doxyfile").write_text("PROJECT_NAME = real\n")
    assert discover_doxyfile(repo) == repo / "docs" / "Doxyfile"

    # A root Doxyfile always wins.
    (repo / "Doxyfile").write_text("PROJECT_NAME = root\n")
    assert discover_doxyfile(repo) == repo / "Doxyfile"


def test_a_declared_shared_key_pattern_beats_a_built_in_default() -> None:
    """#32's first defect. `_match_accessor` is FIRST-MATCH, and the resolver used to
    append declared patterns AFTER the built-in defaults — so a declared pattern whose
    prefix collided with a default could never match, and the DEFAULT's `dispatch_mode`
    was stamped on the edge instead. Silently: the edge still appeared, carrying the wrong
    accessor-class provenance, which is worse than no edge because it is plausible.

    That inverted this repo's one universal configuration rule, which every other surface
    follows: a DECLARATION beats a built-in default (scope's declaration > guard >
    Doxyfile; a CLI flag over `.clew.yaml`; `key_alias_prefixes` REPLACING rather
    than extending). This merge was the single place that had it backwards.

    Asserts the OUTCOME — which dispatch_mode a matched name receives — rather than list
    order, because list order is the mechanism and could be satisfied while the matcher
    still picked wrongly."""
    from clew.shared_key_edges import (
        DEFAULT_SHARED_KEY_WRITERS,
        _match_accessor,
        resolve_shared_key_patterns,
    )

    ## Take a real built-in prefix so the collision is genuine rather than hypothetical.
    builtin = next(p for p in DEFAULT_SHARED_KEY_WRITERS if hasattr(p, "prefix"))
    assert builtin.dispatch_mode != "queued", "fixture assumes the default is not 'queued'"

    declared = {"writers": [{"name_prefix": builtin.prefix, "dispatch_mode": "queued"}]}
    writers, _readers, _aliases = resolve_shared_key_patterns(declared)

    probe = f"{builtin.prefix}SOME_KEY"
    mode = _match_accessor(probe, writers)
    assert mode is not None, "the declared prefix must still match"
    assert mode[2] == "queued", (
        f"the DECLARED dispatch_mode must win over the built-in default's; got {mode[2]!r}"
    )

    ## And with nothing declared, the default must still apply — the fix must not have
    ## simply disabled the built-ins.
    plain_writers, _r, _a = resolve_shared_key_patterns(None)
    assert _match_accessor(probe, plain_writers)[2] == builtin.dispatch_mode


def test_a_declared_catalog_path_is_honoured_without_a_cli_flag(tmp_path: Path) -> None:
    """doxygen-guard issue #7: a repo that DECLARES where its catalog lives had that
    declaration honoured by the gate and ignored by the index. `--requirements` or nothing
    — so the repo had to say it twice, and through the MCP server (which passes no such
    flag) the declaration could never be honoured at all. Same argv-only hole
    `.clew.yaml` exists to close, left open on this one field.

    Verified end to end on the pinned public integration target: 23 requirements ingest
    with no flag at all."""
    from clew.requirements import declared_catalog_path

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "reqs.yaml").write_text("requirements: {}\n", encoding="utf-8")
    cfg = {"impact": {"requirements": {"file": "docs/reqs.yaml"}}}

    assert declared_catalog_path(cfg, tmp_path) == (tmp_path / "docs" / "reqs.yaml").resolve()
    ## No declaration and no config are both simply "nothing declared", not errors.
    assert declared_catalog_path({}, tmp_path) is None
    assert declared_catalog_path(None, tmp_path) is None


def test_the_catalog_precedence_is_declaration_then_convention(tmp_path: Path) -> None:
    """TWO RESOLVERS DISAGREED, AND ONLY ONE DOOR SHOWED IT. `cli` resolved
    `--requirements or declared_catalog_path(...)` and never looked for a conventional file.
    The MCP server COMPOSED `repo/"requirements.yaml"` and passed it in the EXPLICIT-FLAG
    slot — so through MCP the convention outranked a repo's DECLARED
    `impact.requirements.file`, and through the CLI the convention did not exist at all.

    A repo with both got a different catalog depending on which entry point built it, with no
    warning and two indexes that each looked fine.

    THE HALF A NAIVE FIX BREAKS SILENTLY is asserted second. Deleting the composition without
    moving the discovery would stop ingesting the conventional catalog that this repository
    and most adopters actually use — and nothing would fail, because `@req` edges populate
    from TAGS regardless. Only the catalog metadata would quietly go missing, which is the
    disarmed-gate shape this project keeps finding.

    @brief Declaration beats convention; convention still resolves when nothing is declared.
    @version 1
    """
    from clew.requirements import resolve_catalog_path

    declared = tmp_path / "docs" / "reqs.yaml"
    declared.parent.mkdir()
    declared.write_text("requirements: {}\n", encoding="utf-8")
    conventional = tmp_path / "requirements.yaml"
    conventional.write_text("requirements: {}\n", encoding="utf-8")
    cfg = {"impact": {"requirements": {"file": "docs/reqs.yaml"}}}

    ## BOTH present: the declaration wins. This is the case that differed per entry point.
    assert resolve_catalog_path(cfg, tmp_path) == declared.resolve()

    ## Nothing declared: the convention answers, or adopters lose their catalog in silence.
    assert resolve_catalog_path({}, tmp_path) == conventional

    ## Neither: None, not an invented path.
    conventional.unlink()
    assert resolve_catalog_path({}, tmp_path) is None


def test_a_declared_catalog_that_does_not_exist_degrades_rather_than_raising(
    tmp_path: Path,
) -> None:
    """A catalog is OPTIONAL metadata — `req_edges` populate from tags regardless — so a
    stale declared path must degrade to "no catalog" with a warning, not fail a build that
    has already spent a doxygen run. Raising here would make a one-line typo in someone
    else's config cost them the whole index."""
    from clew.requirements import declared_catalog_path

    cfg = {"impact": {"requirements": {"file": "docs/not_here.yaml"}}}
    assert declared_catalog_path(cfg, tmp_path) is None


def test_an_unstated_scope_keeps_the_parsers_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE EMBEDDING ENTRY POINT CONTRADICTED ITS OWN DOCSTRING. `build_index` says
    "defaults are sourced by parsing rather than restated here, so a flag added to
    `_build_argparser` reaches this path with its intended default" — and then `scope`
    alone restated one, with the OPPOSITE value: signature `SCOPE_DOXYFILE`, parser
    `SCOPE_FROM_GUARD`.

    That is the gh#333 inversion in the one function written to prevent divergence: an
    embedding caller omitting `scope` got Doxyfile scope, so a repo that ships a Doxyfile
    was indexed to its published-API subset while a repo shipping none got its whole tree —
    punished for documenting itself.

    THE PLAN CALLED THIS A NO-OP because "both callers pass it explicitly". There are NINE
    call sites and FIVE pass no scope at all, so the change is a real behaviour change for
    them. The full integration tier passes either way, which is why this test exists: a
    green suite after the edit is equally consistent with the edit doing NOTHING, and that
    would prove nothing at all.

    `scope` now defaults to None and is assigned only when stated, matching `repo_root`,
    `doxyfile`, `requirements` and `exclude` — so there is ONE source of truth for the
    default instead of two that must be kept in step.

    @brief An unstated scope inherits the parser default, not a restated one.
    @version 1
    """
    from clew import cli
    from clew.scope import SCOPE_DOXYFILE, SCOPE_FROM_GUARD

    seen: list[str] = []
    monkeypatch.setattr(cli, "_run_pipeline", lambda args: seen.append(args.scope))

    cli.build_index(output="/tmp/unused.db")
    assert seen == [SCOPE_FROM_GUARD], "an unstated scope must be the parser's default"

    ## AND A STATED SCOPE STILL WINS, or the fix has made the parameter inert.
    cli.build_index(output="/tmp/unused.db", scope=SCOPE_DOXYFILE)
    assert seen[-1] == SCOPE_DOXYFILE
