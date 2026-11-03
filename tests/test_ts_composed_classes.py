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

_SRC = b"""\
type Constructor<T> = new (...args: any[]) => T;
export class Base { batch() { return 1; } }
export const AHandler = <T extends Constructor<Base>>(s: T) => class extends s { a() { return 1; } };
export const BHandler = <T extends Constructor<Base>>(s: T) => class extends s { b() { return 2; } };
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
