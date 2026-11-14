# SPDX-License-Identifier: MIT
"""The fast tier: an edited file's own layers updated in place, everything else disclosed stale.

1.3.5, Track 2 (two-tier refresh, owner 2026-11-13), phase 3. A one-file save should not cost a
whole-index rebuild. The fast tier handles the common save — a body edit that keeps the file's
set of definitions — by shifting that file's symbol positions with the parser's own before/after
anchors and recomputing its text layers, in one transaction on the live index. Whole-index layers
are recorded as stale (`fast.*`, the `derived` axis) for the full refresh that follows.

WHAT IT REFUSES, and each refusal is a full build rather than a guess: an added, removed or
renamed definition (rowids and edges would move), a changed configuration input, more files than
the tier is for, or nothing changed at all.

@brief Tests for clew.fasttier.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.refresh_command import refresh_main

_SOURCE = """\
/** Fetch the widget. REQ-FT-001 */
export function fetchWidget(id: string): number {
  return id.length;
}

export function renderWidget(id: string): number {
  return fetchWidget(id) + 1;
}
"""


## @brief Build (or refresh) an index of a tree through the real CLI.
## @param repo The tree.
## @param out The index path.
## @param tier The refresh tier.
## @return None.
## @version 1
def _build(repo: Path, out: Path, tier: str = "full") -> None:
    """@brief A full build, or `clew refresh` (fast tier first). @return None."""
    if tier == "full":
        _run_pipeline(
            _build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)])
        )
    else:
        assert refresh_main(["--output", str(out), "--repo-root", str(repo)]) == 0


## @brief A tiny TypeScript repository and its first full index.
## @param tmp_path Scratch directory.
## @return (repo, index path).
## @version 1
def _indexed(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Make and index a repo. @return Paths."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "widget.ts").write_text(_SOURCE)
    out = tmp_path / "clew.db"
    _build(repo, out)
    return repo, out


## @brief One function's recorded body span.
## @param db The index.
## @param name Function name.
## @return (bodystart, bodyend).
## @version 1
def _span(db: Path, name: str) -> tuple[int, int]:
    """@brief Read a span. @return Span."""
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT bodystart, bodyend FROM memberdef WHERE name = ? AND kind = 'function' "
            "AND bodystart > 0",
            (name,),
        ).fetchone()
    return int(row[0]), int(row[1])


## @brief The `fast.*` build_meta section.
## @param db The index.
## @return The section, prefix stripped.
## @version 1
def _fast(db: Path) -> dict[str, str]:
    """@brief Read fast.* keys. @return Mapping."""
    with sqlite3.connect(db) as conn:
        return {
            k[len("fast.") :]: v
            for k, v in conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'fast.%'")
        }


def test_a_body_edit_is_applied_in_place_and_disclosed(tmp_path: Path) -> None:
    """THE CASE THE TIER IS FOR. Three lines inserted above both functions and one body edited:
    every span must land exactly where a full build puts it, and the record must name the file
    and the layers left behind.

    @brief A position-shifting body edit refreshes fast and matches a full build's spans.
    @return None.
    @version 1
    """
    repo, out = _indexed(tmp_path)
    edited = "// one\n// two\n// three\n" + _SOURCE.replace("id.length", "id.length * 2")
    (repo / "src" / "widget.ts").write_text(edited)
    _build(repo, out, tier="fast")
    fast = _fast(out)
    assert fast.get("pending") == "1", f"the fast tier did not run: {fast}"
    assert fast.get("files") == "src/widget.ts"
    ## A LAYER THE FAST TIER LEAVES BEHIND must be named. Since phase 5 the edited file's outgoing
    ## AST call edges are refreshed, so the probe is a layer that stays whole-index.
    assert "reachability" in fast.get("layers", "")
    fast_spans = {n: _span(out, n) for n in ("fetchWidget", "renderWidget")}

    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert fast_spans == {n: _span(reference, n) for n in ("fetchWidget", "renderWidget")}


def test_the_edited_files_text_layers_are_current(tmp_path: Path) -> None:
    """@brief A requirement id written into the file appears in req_mentions after a fast refresh.
    @return None.
    @version 1
    """
    repo, out = _indexed(tmp_path)
    with sqlite3.connect(out) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS requirements (id TEXT PRIMARY KEY)")
        conn.execute("INSERT OR IGNORE INTO requirements (id) VALUES ('REQ-FT-002')")
    (repo / "src" / "widget.ts").write_text(_SOURCE.replace("REQ-FT-001", "REQ-FT-002"))
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    with sqlite3.connect(out) as conn:
        found = conn.execute(
            "SELECT req_id FROM req_mentions WHERE file = 'src/widget.ts'"
        ).fetchall()
    assert ("REQ-FT-002",) in found


def test_an_added_definition_falls_back_to_a_full_build(tmp_path: Path) -> None:
    """A NEW SYMBOL NEEDS A ROW, ROWIDS AND EDGES, none of which the fast tier allocates; a full
    build answers it, and leaves no fast record behind.

    @brief A changed definition set refuses the fast tier.
    @return None.
    @version 1
    """
    repo, out = _indexed(tmp_path)
    (repo / "src" / "widget.ts").write_text(
        _SOURCE + "\nexport function newWidget(): number {\n  return 0;\n}\n"
    )
    _build(repo, out, tier="auto")
    assert _fast(out).get("pending") != "1"
    assert _span(out, "newWidget")[0] > 0


def test_a_full_build_clears_the_fast_record(tmp_path: Path) -> None:
    """@brief After a fast refresh, a full build leaves no pending record.
    @return None.
    @version 1
    """
    repo, out = _indexed(tmp_path)
    (repo / "src" / "widget.ts").write_text("// x\n" + _SOURCE)
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    _build(repo, out)
    assert _fast(out).get("pending") != "1"


def test_nothing_changed_is_not_a_fast_refresh(tmp_path: Path) -> None:
    """@brief An unchanged tree records no fast refresh.
    @return None.
    @version 1
    """
    repo, out = _indexed(tmp_path)
    _build(repo, out, tier="auto")
    assert _fast(out).get("pending") != "1"


def test_a_fast_refresh_does_not_poison_the_full_build_that_follows(tmp_path: Path) -> None:
    """THE CACHE INVARIANT. The fast tier writes cache payloads and never advances the cache's
    file record; the full build after it must therefore produce exactly what a full build of the
    same tree produces with no fast refresh in between — compared table by table.

    @brief fast + full == full, whole database.
    @return None.
    @version 1
    """
    import importlib.util

    repo, out = _indexed(tmp_path)
    (repo / "src" / "widget.ts").write_text("// moved\n" + _SOURCE.replace("+ 1", "+ 2"))
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    _build(repo, out)
    reference = tmp_path / "reference.db"
    _build(repo, reference)
    script = Path(__file__).resolve().parent.parent / "scripts" / "incremental_probe.py"
    spec = importlib.util.spec_from_file_location("incremental_probe", script)
    assert spec and spec.loader
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe.whole_db_diff(out, reference) == []


_CALLS = """\
export function alpha(): number {
  return 1;
}

export function beta(): number {
  return 2;
}

export function gamma(): number {
  return alpha();
}
"""


## @brief The callees an index records for one caller, by name and source.
## @param db The index.
## @param caller The caller's name.
## @return Sorted (callee, source) pairs.
## @version 1
def _callees(db: Path, caller: str) -> list[tuple[str, str]]:
    """@brief Read one caller's edges. @return Pairs."""
    with sqlite3.connect(db) as conn:
        return sorted(
            conn.execute(
                "SELECT y.name, e.source FROM call_edges e "
                "JOIN memberdef x ON x.rowid = e.caller_rowid "
                "JOIN memberdef y ON y.rowid = e.callee_rowid WHERE x.name = ?",
                (caller,),
            ).fetchall()
        )


def test_the_edited_files_outgoing_calls_are_current(tmp_path: Path) -> None:
    """PHASE 5. A body edit that changes what a function calls is the commonest save there is;
    its outgoing edges must be the full build's, not the pre-edit ones.

    @brief After a fast refresh, an edited function's callees equal a full build's.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calls.ts").write_text(_CALLS)
    out = tmp_path / "clew.db"
    _build(repo, out)
    assert ("alpha", "ast") in _callees(out, "gamma")
    (repo / "src" / "calls.ts").write_text(_CALLS.replace("return alpha();", "return beta();"))
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _callees(out, "gamma") == _callees(reference, "gamma")
    assert "call_edges" not in _fast(out).get("layers", "").split(",")


def test_the_edited_files_code_text_is_current(tmp_path: Path) -> None:
    """PHASE 6. `search(corpus='code')` over an edited body must find the new text and not the
    old: the contentless corpus cannot delete by query, so the fast tier deletes each old row with
    the exact text the full stage indexed (from the cache) and inserts the new.

    @brief After a fast refresh, code search sees the edited body only.
    @return None.
    @version 1
    """
    from clew.code_text import search_code

    repo, out = _indexed(tmp_path)
    (repo / "src" / "widget.ts").write_text(_SOURCE.replace("id.length", "id.zebraquotient"))
    _build(repo, out, tier="fast")
    fast = _fast(out)
    assert fast.get("pending") == "1"
    assert "code_text" not in fast.get("layers", "").split(",")
    with sqlite3.connect(out) as conn:
        new_hits = search_code(conn, "zebraquotient", 10, repo)
        old_hits = search_code(conn, "length", 10, repo)
    assert [h.name for h in new_hits or []] == ["fetchWidget"]
    assert not old_hits, "the pre-edit body is still searchable"


_BLOCKING_C = """\
#include <zephyr/kernel.h>

void idle(void) {
}

void waiter(void) {
    k_sleep(5);
}
"""


## @brief One file's blocking call sites, by holder name.
## @param db The index.
## @return Sorted (holder, line, primitive) rows.
## @version 1
def _blocking(db: Path) -> list[tuple[str, int, str]]:
    """@brief Read blocking_calls. @return Rows."""
    with sqlite3.connect(db) as conn:
        return sorted(
            conn.execute(
                "SELECT m.name, b.line, b.primitive FROM blocking_calls b "
                "JOIN memberdef m ON m.rowid = b.holder_rowid"
            ).fetchall()
        )


def test_the_edited_files_blocking_calls_are_current(tmp_path: Path) -> None:
    """PHASE 6. Blocking call sites belong wholly to one file — harvested from it, held by one of
    its functions — so the fast tier rewrites them; they must equal a full build's.

    @brief After a fast refresh, blocking call sites equal a full build's.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "wait.c").write_text(_BLOCKING_C)
    out = tmp_path / "clew.db"
    _build(repo, out)
    assert _blocking(out), "the fixture must record a blocking call"
    (repo / "src" / "wait.c").write_text("/* a */\n/* b */\n" + _BLOCKING_C)
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    assert "blocking_calls" not in _fast(out).get("layers", "").split(",")
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _blocking(out) == _blocking(reference)


def test_the_edited_files_file_scope_text_is_current(tmp_path: Path) -> None:
    """1.3.10: the file-scope corpus is rewritten in place too, so a macro added to a file-scope
    `#if` is found right after a fast refresh and the old one is not.

    @brief After a fast refresh, file-scope code search sees the edited file only.
    @return None.
    @version 1
    """
    from clew.code_text import search_code

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "wait.c").write_text("#if defined(OLD_GATE_MARK)\n#endif\n" + _BLOCKING_C)
    out = tmp_path / "clew.db"
    _build(repo, out)
    (repo / "src" / "wait.c").write_text("#if defined(NEW_GATE_MARK)\n#endif\n" + _BLOCKING_C)
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    assert "code_text" not in _fast(out).get("layers", "").split(",")
    with sqlite3.connect(out) as conn:
        assert [h.kind for h in search_code(conn, "NEW_GATE_MARK", 5, repo) or []] == ["file"]
        assert not search_code(conn, "OLD_GATE_MARK", 5, repo)
