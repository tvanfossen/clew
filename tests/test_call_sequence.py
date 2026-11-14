# SPDX-License-Identifier: MIT
"""A function's calls in source order, each with the loop/branch frames that enclose it.

1.4.0 Track 4 (clew wiki), W2. A derived sequence diagram needs the order of the messages inside a
lane and the frames (loop / alt / try) around them. `call_edges` holds neither — a pair is one
row, `UNIQUE(caller, callee, source)`, with no site — so the sequence is read from the caller's
own source at query time: the same call-site harvester the index uses, plus the control
structures whose line span contains each site. Query-time, not stored, deliberately: it needs no
schema change and no rebuild, and a wiki is generated offline where parsing a handful of caller
files costs nothing.

@brief Tests for clew.query.callsites.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.query.callsites import call_sequence

_PY = '''\
def alpha():
    return 1


def beta():
    return 2


def gamma():
    return 3


def flow(items, ready):
    """Drive the flow."""
    if ready:
        alpha()
    else:
        gamma()
    for item in items:
        beta()
    gamma()
'''

_TS = """\
export function alpha(): number { return 1; }
export function beta(): number { return 2; }

export function flow(items: number[], ready: boolean): void {
  if (ready) {
    alpha();
  }
  for (const item of items) {
    try {
      beta();
    } catch (e) {
      alpha();
    }
  }
}
"""


## @brief Build an index of a one-file tree.
## @param tmp_path Scratch directory.
## @param name File name.
## @param text File text.
## @return (index path, repo root).
## @version 1
def _index(tmp_path: Path, name: str, text: str) -> tuple[Path, Path]:
    """@brief Build. @return Paths."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / name).write_text(text)
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out, repo


## @brief The sequence as (callee, frame kinds) pairs.
## @param seq The call sequence.
## @return Pairs.
## @version 1
def _shape(seq: list) -> list[tuple[str, list[str]]]:
    """@brief Flatten. @return Pairs."""
    return [(s.callee, [f.kind for f in s.frames]) for s in seq]


def test_python_calls_come_in_source_order_with_their_frames(tmp_path: Path) -> None:
    """@brief if/else and for frames, in line order.
    @return None.
    @version 1
    """
    db, repo = _index(tmp_path, "flow.py", _PY)
    seq = call_sequence(db, repo, "flow")
    assert _shape(seq) == [
        ("alpha", ["if"]),
        ("gamma", ["else"]),
        ("beta", ["loop"]),
        ("gamma", []),
    ], _shape(seq)
    assert [s.line for s in seq] == sorted(s.line for s in seq)


def test_typescript_calls_carry_loop_and_try_frames(tmp_path: Path) -> None:
    """@brief Nested frames are listed outermost first.
    @return None.
    @version 1
    """
    db, repo = _index(tmp_path, "flow.ts", _TS)
    assert _shape(call_sequence(db, repo, "flow")) == [
        ("alpha", ["if"]),
        ("beta", ["loop", "try"]),
        ("alpha", ["loop", "catch"]),
    ]


def test_an_unknown_function_has_no_sequence(tmp_path: Path) -> None:
    """ABSENT IS NOT EMPTY: no such function returns None, a function that calls nothing [].

    @brief None for an unknown name; [] for a leaf.
    @return None.
    @version 1
    """
    db, repo = _index(tmp_path, "flow.py", _PY)
    assert call_sequence(db, repo, "no_such_fn") is None
    assert call_sequence(db, repo, "alpha") == []
