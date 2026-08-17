# SPDX-License-Identifier: MIT
"""Declaration-driven requirements handling (no hardcoded @req/catalog format).

Covers the STRICTLY-NO-HARDCODING mandate: the @req id pattern and the
requirements-catalog column mapping come from the target repo's DECLARED
`.doxygen-guard.yaml`, with a permissive fallback when nothing is declared.

@brief Tests for declaration-driven @req pattern + format-tolerant catalog.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from clew.requirements import (
    _PERMISSIVE_REQ_ID_RE,
    _extract_req_tags,
    _is_flat_req_list,
    import_req_edges,
    ingest_requirements_yaml,
    load_guard_config,
    resolve_catalog_columns,
    resolve_req_id_pattern,
)


## @brief Build a minimal doxygen-shaped db with two @req-tagged functions.
## @param tmp_path Pytest tmp dir.
## @param tag_a @req token for function 1.
## @param tag_b @req token for function 2.
## @return Path to the db.
## @version 1
def _make_tagged_db(tmp_path: Path, tag_a: str, tag_b: str) -> Path:
    """Seed a path/memberdef db with two functions carrying `@req` tags.

    @brief Seed a doxygen-shaped db with @req-tagged memberdefs.
    @version 1
    """
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
        INSERT INTO path (rowid, name) VALUES (1, 'src/foo.c');
        """,
    )
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, briefdescription, detaileddescription) "
        "VALUES (?, 'function', ?, 1, ?, ?)",
        [
            (1, "fn_a", "Does A.", f"@req {tag_a}"),
            (2, "fn_b", "Does B.", f"@req {tag_b}"),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


# ─── permissive fallback (no guard config) ──────────────────────────────────


def test_permissive_fallback_matches_req_rejects_non_req() -> None:
    pattern = resolve_req_id_pattern(None)
    assert pattern is _PERMISSIVE_REQ_ID_RE
    # A reasonable REQ id matches; a non-REQ token does not.
    assert _extract_req_tags("@req REQ-0621", pattern) == ["REQ-0621"]
    assert _extract_req_tags("@req REQ-PROJ-NAV-002", pattern) == [
        "REQ-PROJ-NAV-002",
    ]
    assert _extract_req_tags("@req TICKET-42", pattern) == []
    assert _extract_req_tags("@req notareq", pattern) == []


def test_permissive_fallback_preserves_inferred_confidence() -> None:
    pattern = resolve_req_id_pattern(None)
    assert _extract_req_tags("@req REQ-0621 [inferred]", pattern) == [
        "REQ-0621",
    ]


def test_import_req_edges_permissive_default_populates(tmp_path: Path) -> None:
    # No pattern argument → permissive fallback; demobot-style ids populate.
    db = _make_tagged_db(tmp_path, "REQ-0621", "REQ-0900")
    import_req_edges(db)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT req_id, memberdef_rowid FROM req_edges ORDER BY memberdef_rowid",
    ).fetchall()
    conn.close()
    assert rows == [("REQ-0621", 1), ("REQ-0900", 2)]


# ─── declared pattern (C++-style nested repo) ───────────────────────────────


## @brief Write a .doxygen-guard.yaml declaring a C++-style @req pattern.
## @param tmp_path Pytest tmp dir.
## @param req_file Catalog file path to reference under impact.requirements.
## @return Path to the written config.
## @version 1
def _write_guard_config(tmp_path: Path, req_file: str) -> Path:
    """Write a guard config with a declared req pattern + catalog mapping.

    @brief Write a .doxygen-guard.yaml fixture.
    @version 1
    """
    cfg = tmp_path / ".doxygen-guard.yaml"
    cfg.write_text(
        "validate:\n"
        "  tags:\n"
        "    req:\n"
        '      pattern: "^REQ-X-[A-Z]+-[0-9]{3}$"\n'
        "impact:\n"
        "  requirements:\n"
        f"    file: {req_file}\n"
        "    format: yaml\n"
        '    id_column: "req_id"\n'
        '    name_column: "summary"\n',
        encoding="utf-8",
    )
    return cfg


def test_declared_pattern_read_from_guard_config(tmp_path: Path) -> None:
    cfg = load_guard_config(_write_guard_config(tmp_path, "requirements.yaml"))
    pattern = resolve_req_id_pattern(cfg)
    assert pattern.pattern == "^REQ-X-[A-Z]+-[0-9]{3}$"
    # Declared pattern matches its ids and rejects demobot-style REQ-0621.
    assert _extract_req_tags("@req REQ-X-FOO-001", pattern) == [
        "REQ-X-FOO-001",
    ]
    assert _extract_req_tags("@req REQ-0621", pattern) == []


def test_declared_catalog_columns_read_from_guard_config(tmp_path: Path) -> None:
    cfg = load_guard_config(_write_guard_config(tmp_path, "requirements.yaml"))
    assert resolve_catalog_columns(cfg) == ("req_id", "summary")


def test_declared_columns_default_when_no_config() -> None:
    assert resolve_catalog_columns(None) == ("id", "title")


def test_nested_domains_catalog_ingests_zero_but_tags_populate(
    tmp_path: Path,
) -> None:
    """C++-shaped repo: nested `domains:` catalog yields 0 rows gracefully,
    while req_edges still populate from tags matched by the declared pattern.
    """
    # Nested-domains catalog (a C++ codebase shape) — NOT a flat id-bearing list.
    catalog = tmp_path / "requirements.yaml"
    catalog.write_text(
        "domains:\n"
        "  slam:\n"
        "    requirements:\n"
        "      - id: REQ-X-BAZ-003\n"
        "        summary: Localize\n",
        encoding="utf-8",
    )
    cfg = load_guard_config(_write_guard_config(tmp_path, str(catalog)))

    db = _make_tagged_db(tmp_path, "REQ-X-FOO-001", "REQ-X-BAR-002")

    # Catalog ingestion must NOT crash and must ingest 0 rows.
    ingest_requirements_yaml(db, catalog, cfg)
    conn = sqlite3.connect(str(db))
    catalog_count = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    conn.close()
    assert catalog_count == 0

    # req_edges populate from the declared-pattern tags regardless.
    import_req_edges(db, resolve_req_id_pattern(cfg))
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT req_id FROM req_edges ORDER BY req_id",
    ).fetchall()
    conn.close()
    assert rows == [("REQ-X-BAR-002",), ("REQ-X-FOO-001",)]


# ─── xrefitem-alias form (a C++ codebase real-firmware shape) ──────────────────────────


def test_extract_req_tags_from_xrefdescription_alias_form() -> None:
    """a C++ codebase uses ALIASES 'req=@xrefitem req_trace ...', so doxygen stores the id
    inside an <xrefsect>/<xrefdescription> block, not a literal @req token.
    """
    pattern = re.compile(r"^REQ-PROJ-(HAL|SLAM)-[0-9]{3}$")
    text = (
        '<para><simplesect kind="version"><para>1.0.0 </para></simplesect>'
        '<xrefsect id="req_trace_1_req_trace000189"><xreftitle>Requirement'
        "</xreftitle><xrefdescription><para>REQ-PROJ-HAL-004 </para>"
        "</xrefdescription></xrefsect></para>"
    )
    assert _extract_req_tags(text, pattern) == ["REQ-PROJ-HAL-004"]


def test_xrefdescription_ignores_non_matching_tokens() -> None:
    # Only tokens matching the declared pattern survive; version/prose don't.
    pattern = re.compile(r"^REQ-PROJ-[A-Z]+-[0-9]{3}$")
    text = (
        "<xrefdescription><para>REQ-PROJ-NAV-002 localizes the robot 1.0.0"
        " </para></xrefdescription>"
    )
    assert _extract_req_tags(text, pattern) == ["REQ-PROJ-NAV-002"]


# ─── flat catalog + declared column mapping ─────────────────────────────────


def test_flat_catalog_declared_columns_ingest(tmp_path: Path) -> None:
    catalog = tmp_path / "requirements.yaml"
    catalog.write_text(
        "- req_id: REQ-X-FOO-001\n"
        "  summary: Foo works\n"
        "  block: foo\n"
        "  acceptance: foo emits\n"
        "  priority: P0\n",
        encoding="utf-8",
    )
    cfg = load_guard_config(_write_guard_config(tmp_path, str(catalog)))
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    ingest_requirements_yaml(db, catalog, cfg)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT id, block, title, acceptance, priority FROM requirements",
    ).fetchall()
    conn.close()
    assert rows == [("REQ-X-FOO-001", "foo", "Foo works", "foo emits", "P0")]


# ─── _is_flat_req_list unit coverage ────────────────────────────────────────


def test_is_flat_req_list_recognizes_flat() -> None:
    assert _is_flat_req_list([{"id": "REQ-1"}], "id") is True


def test_is_flat_req_list_rejects_nested_dict() -> None:
    assert _is_flat_req_list({"domains": {}}, "id") is False


def test_is_flat_req_list_rejects_empty_and_scalar() -> None:
    assert _is_flat_req_list([], "id") is False
    assert _is_flat_req_list("nope", "id") is False


def test_is_flat_req_list_honors_declared_id_column() -> None:
    assert _is_flat_req_list([{"req_id": "REQ-1"}], "req_id") is True


# ─── a rejected guard config must not kill the build ─────────────────────────


def test_a_guard_config_rejected_by_doxygen_guard_is_survived(tmp_path: Path, caplog) -> None:
    """`doxygen_guard.config.load_config` does not RAISE on a bad config — it calls
    `sys.exit(1)`. `SystemExit` derives from BaseException, so it sailed straight
    through this loader's `except Exception` handler, whose own comment says
    "config is optional; never fatal", and out through the CLI.

    The damage was disproportionate to the cause: this loader runs AFTER the doxygen
    run and after every edge-import stage, so a target repo with one stray top-level
    key in its `.doxygen-guard.yaml` burned an entire build and then died at exit 1
    with a message from a different tool.

    Both halves are asserted. Returning None is the "never fatal" contract. The
    WARNING is the other half and matters just as much: the declared `@req` pattern
    is now unavailable and the build silently falls back to the permissive default,
    which is the "runs on built-in defaults without saying so" outcome the
    no-hardcoding mandate exists to prevent."""
    import logging

    from clew import requirements as requirements_module

    config_path = tmp_path / ".doxygen-guard.yaml"
    config_path.write_text("stray_top_level_key: true\n", encoding="utf-8")

    class _Rejecting:
        @staticmethod
        def load_config(_path):
            raise SystemExit(1)

    import sys

    sys.modules["doxygen_guard"] = type(sys)("doxygen_guard")
    sys.modules["doxygen_guard"].config = _Rejecting  # type: ignore[attr-defined]
    sys.modules["doxygen_guard.config"] = _Rejecting  # type: ignore[assignment]
    try:
        with caplog.at_level(logging.WARNING):
            result = requirements_module.load_guard_config(config_path)
    finally:
        for name in ("doxygen_guard", "doxygen_guard.config"):
            sys.modules.pop(name, None)

    assert result is None, "a rejected config must degrade to defaults, not propagate"
    assert any("INVALID" in rec.message for rec in caplog.records), (
        "falling back to built-in defaults silently is the failure mode being fixed"
    )


# ─── #62: a tag that ENDS a doc block (no space before `</para>`) ────────────
#
# `@req` is an unknown command to doxygen, so it is absorbed into whatever
# paragraph command precedes it. When the tag is the LAST line of the block there
# is no separating space and the stored text ends `...-001</para>`. Both strings
# below are VERBATIM from a built clew.db. Nothing pinned this, and the whole
# suite passed while 104 tagged functions in this repo produced 20 edges.


def test_extract_req_tags_id_terminated_by_markup_not_just_whitespace() -> None:
    pattern = resolve_req_id_pattern(None)
    glued = '<simplesect kind="version"><para>6 @req REQ-DDB-PIPE-004</para>\n'
    assert _extract_req_tags(glued, pattern) == ["REQ-DDB-PIPE-004"], (
        "an id glued to its closing tag used to be captured as "
        "'REQ-DDB-PIPE-004</para>', fail the declared pattern, and be dropped silently"
    )
    spaced = '<simplesect kind="version"><para>3 @req REQ-DDB-PIPE-005 </para>\n'
    assert _extract_req_tags(spaced, pattern) == ["REQ-DDB-PIPE-005"], (
        "the spaced form already worked and must keep working"
    )


def test_extract_req_tags_keeps_inferred_when_marker_abuts_markup() -> None:
    pattern = resolve_req_id_pattern(None)
    # The terminator lookahead was satisfied by the space BEFORE `[inferred]`, so
    # the marker group backtracked away and an inference was recorded as a stated
    # fact — the worse of the two failures, because confidence is exactly what
    # tells a reader whether an author asserted the link or a tool guessed it.
    assert _extract_req_tags("@req REQ-0621 [inferred]</para>", pattern) == [
        "REQ-0621",
    ]
    assert _extract_req_tags("@req REQ-0621 [inferred] </para>", pattern) == [
        "REQ-0621",
    ]


def test_this_repo_DECLARES_where_its_own_requirements_catalog_lives() -> None:
    """Dogfooding, pinned — and it was NOT true when this test was written.

    `bd2d34e` taught the index to honour `impact.requirements.file` because a repo that
    declares its catalog had the declaration read by the gate and ignored by the index. We
    shipped that fix for other repos and never applied it to ourselves: this repo's
    `.doxygen-guard.yaml` had no `impact:` section, so a bare `--scope from-guard` build
    ingested ZERO catalog rows.

    The failure was invisible from the side anyone looks at. `req_edges` populate from TAGS,
    independently of the catalog, so coverage read 30/34 while every one of those 34
    requirements came back with no title, status or acceptance. The MCP server passes no
    flags at all, so through the product's actual interface the catalog could never load.

    Asserting the declaration rather than a built database keeps this a fast unit test and
    pins the thing that broke: not "does ingestion work" (it always did, given a path) but
    "does the path reach it without a human typing a flag".
    """
    import yaml

    from clew.declaration import GUARD_CONFIG_NAME

    cfg = yaml.safe_load(
        Path(__file__).resolve().parents[1].joinpath(GUARD_CONFIG_NAME).read_text()
    )
    declared = (cfg.get("impact") or {}).get("requirements", {}).get("file")
    assert declared, (
        f"{GUARD_CONFIG_NAME} must declare impact.requirements.file, or our own index "
        "silently ingests no catalog — the exact hole bd2d34e closed for other repos"
    )
    catalog = Path(__file__).resolve().parents[1] / str(declared)
    assert catalog.exists(), f"declared catalog {declared} does not exist"


def test_the_guard_s_KEYED_catalog_vocabulary_populates_every_column() -> None:
    """One catalog, two vocabularies — and reading only ours emptied the metadata.

    Our flat shape says `{block, title, acceptance, priority}`. doxygen-guard's keyed YAML
    catalog says `{subsystem, name, acceptance_criteria}`, with `name` its only required
    field, and our own extras move behind the `x-` passthrough prefix. Converting this repo's
    catalog to the keyed shape (so the GATE could read the same file the INDEX reads) left all
    36 `requirements` rows with a NULL title, block, acceptance and priority.

    The failure hid in the usual place: `req_edges` come from TAGS, not the catalog, so
    coverage still read 32/36 while every row's metadata was gone. Same shape as the catalog
    that would not load at all — whichever surface is easy to check kept working.
    """
    from clew.requirements import _first

    keyed = {
        "subsystem": "schema",
        "name": "Lock layer",
        "acceptance_criteria": "locks + lock_acquisitions populate",
        "x-priority": "P2",
    }
    assert _first(keyed, "block", "subsystem") == "schema"
    assert _first(keyed, "title", "name", "title") == "Lock layer"
    assert (
        _first(keyed, "acceptance", "acceptance_criteria") == "locks + lock_acquisitions populate"
    )
    assert _first(keyed, "priority", "x-priority") == "P2"

    # Our own flat vocabulary must keep working — the aliases are additive, not a swap.
    flat = {"block": "query", "title": "Dossier", "acceptance": "returns rows", "priority": "P1"}
    assert _first(flat, "block", "subsystem") == "query"
    assert _first(flat, "title", "name", "title") == "Dossier"
    assert _first(flat, "acceptance", "acceptance_criteria") == "returns rows"
    assert _first(flat, "priority", "x-priority") == "P1"

    # An absent key must be None, not the empty string: NULL is what says "not declared",
    # and "" would read as a declared-but-blank title in every consumer.
    assert _first({}, "title", "name") is None
