# SPDX-License-Identifier: MIT
"""A class composed by a mixin helper has its bases, and a same-named interface does not hide it.

FOUND BY THE 1.3.0 GRID. mattermost-mobile's `index_only` arm lost Q5 by 19 points: asked how
`ServerDataOperator` is built, it never found `mix(ServerDataOperatorBase).with(...)`. Two defects,
both verified against the run's own index:

* `class ServerDataOperator extends mix(Base).with(A, B, ...)` recorded NO bases: the heritage is a
  CALL EXPRESSION, and the base reader only read names. Every class named as an ARGUMENT in a
  heritage expression is what the expression composes; the helpers (`mix`, `with`) are not bases.
  That covers mixwith, ts-mixer's `Mixin(A, B)` and a project's own helper without naming any.
* An interface and a class of the SAME qualified name — TypeScript declaration merging, which is
  exactly how such a class is typed — collapsed to one candidate, so `dossier("ServerDataOperator")`
  returned the interface and never listed the class. Two compounds of different KINDS are two
  declarations; only same-kind duplicates are one.

@brief Tests for mixin-composed classes and merged declarations.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import lang_parsing_substrate as lps

from clew.cli import _build_argparser, _run_pipeline
from clew.jsast import harvest_definitions
from clew.query.corpus import lookup_class

## `AMix`/`BMix` are declared, as a real tree declares each mixin's interface: a base link is
## only drawn to a compound the index holds.
_SRC = b"""\
type Constructor<T> = new (...args: any[]) => T;
export class Base { batch() { return 1; } }
export const AHandler = <T extends Constructor<Base>>(s: T) => class extends s { a() { return 1; } };
export const BHandler = <T extends Constructor<Base>>(s: T) => class extends s { b() { return 2; } };
export interface AMix { a(): number }
export interface BMix { b(): number }
export interface Operator extends AMix, BMix {}
export class Operator extends mix(Base).with(AHandler, BHandler) { run() { return 3; } }
"""


## @brief A class composed by `mix(...).with(...)` has every argument class as a base.
## @return None.
## @version 1
def test_a_mixin_composed_class_has_its_argument_classes_as_bases() -> None:
    """@brief Operator's bases are Base, AHandler, BHandler — not mix or with.
    @return None.
    @version 1
    """
    out = harvest_definitions(lps.parse_tree("typescript", _SRC), _SRC)
    classes = [c for c in out["classes"] if c["name"] == "Operator" and c["kind"] == "class"]
    assert classes, out["classes"]
    assert classes[0]["bases"] == ["Base", "AHandler", "BHandler"], classes[0]


## @brief A same-named interface and class are both candidates.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_merged_interface_and_class_are_both_candidates(tmp_path: Path) -> None:
    """@brief lookup_class('Operator') lists the interface AND the class.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/op.ts").write_text(_SRC.decode(), encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    entry = lookup_class(out, "Operator")
    kinds = {c.kind for c in entry.candidates if c.qualified.endswith("::Operator")}
    assert kinds == {"interface", "class"}, entry.candidates


## @brief A class dossier carries its declaration line, and the class wins over its interface twin.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_class_dossier_shows_its_declaration_and_prefers_the_class(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX TRANSCRIPTS, not a reconstruction: in 0 of 3 index-only cells did any
    reply contain `mix(ServerDataOperatorBase)` — a class dossier carried members and bases but no
    source, and picked the interface over the class. In 3 of 3 cells with a shell, the agent read
    the file and found it. The declaration is the answer, so it is carried.

    @brief Operator's dossier is the class, with `extends mix(Base).with(...)` in its declaration.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/op.ts").write_text(_SRC.decode(), encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    reply = QueryTools(lambda: out, lambda: repo).dossier("Operator")
    assert reply["kind"] == "class", reply.get("kind")
    text = "\n".join(reply["declaration"]["lines"])
    assert "mix(Base).with(AHandler, BHandler)" in text, reply.get("declaration")


## @brief A class dossier names its merged same-name interface, with that interface's bases.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_class_dossier_names_its_merged_interface(tmp_path: Path) -> None:
    """FROM THE 1.3.0-TS-FIX2 TRANSCRIPTS: with the class now chosen, index-only agents still
    missed that `interface ServerDataOperator extends ...Mix` types the composed class — the
    interface was one line in `candidates`, with no bases. TypeScript MERGES the two declarations
    into one type, so the class dossier carries the other half: its kind, line, bases and head.

    @brief Operator's dossier has `merged` = the interface, bases AMix and BMix.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/op.ts").write_text(_SRC.decode(), encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    reply = QueryTools(lambda: out, lambda: repo).dossier("Operator")
    merged = reply.get("merged")
    assert merged and merged[0]["kind"] == "interface", reply
    assert merged[0]["bases"] == ["src::op::AMix", "src::op::BMix"], merged
    assert "extends AMix, BMix" in "\n".join(merged[0]["declaration"]["lines"]), merged


## @brief A Python class dossier carries its `class X(Base):` line too.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_python_class_dossier_shows_its_declaration(tmp_path: Path) -> None:
    """ACROSS THE BOARD, not TypeScript only: the declaration is where every language states what a
    class inherits.

    @brief Child's declaration names Base.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(
        "class Base:\n    def a(self):\n        return 1\n\n\n"
        "class Child(Base):\n    def b(self):\n        return 2\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    reply = QueryTools(lambda: out, lambda: repo).dossier("Child")
    assert "class Child(Base):" in "\n".join(reply["declaration"]["lines"]), reply
