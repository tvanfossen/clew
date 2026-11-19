# SPDX-License-Identifier: MIT
"""`clew wiki check` reports a DECLARED docs glob that matches nothing, never a default (2.0.0).

FOUND BY A CONSUMER (the entropic session, adopting clew at 2.0.0), reproduced: with no `wiki:`
section at all, a repository whose prose is Markdown only got "`wiki.docs` entry 'docs/**/*.rst'
matches no file". The repository never wrote that glob; it is one of the built-in defaults
(`DEFAULT_DOCS`), and a default that finds nothing is not a fault. A glob the repository declares
and that matches nothing still is.

@brief Tests that only declared docs globs are checked.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.check import check_wiki


def _repo(tmp_path: Path, decl: str | None) -> tuple[Path, Path]:
    """@brief A Markdown-only repo, indexed. @return (repo, db)."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Readme\n")
    (repo / "docs/guide.md").write_text("# Guide\n")
    (repo / "main.c").write_text("int main(void) { return 0; }\n")
    if decl is not None:
        (repo / ".clew.yaml").write_text(decl)
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return repo, db


def test_a_default_docs_glob_that_matches_nothing_is_not_a_problem(tmp_path: Path) -> None:
    """@brief No wiki: section, no .rst files: no docs problem."""
    repo, db = _repo(tmp_path, None)
    assert not [p for p in check_wiki(repo, db) if "wiki.docs" in p]


def test_a_declared_docs_glob_that_matches_nothing_is_still_reported(tmp_path: Path) -> None:
    """@brief A glob the repository wrote is checked."""
    repo, db = _repo(tmp_path, 'wiki:\n  docs: ["README.md", "handbook/*.md"]\n')
    assert [p for p in check_wiki(repo, db) if "wiki.docs" in p] == [
        "`wiki.docs` entry 'handbook/*.md' matches no file"
    ]
