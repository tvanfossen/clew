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
    assert "call_edges" in fast.get("layers", "")
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
