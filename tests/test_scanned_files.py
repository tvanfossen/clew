# SPDX-License-Identifier: MIT
"""The file set the parse-built front end is handed must be the file set the build declared.

B2, 1.1.0 MERGE REVIEW. `_scanned_files` is the fallback for a build whose doxygen stage never
ran — a Rust or JS/TS-only target. The doxygen stage enumerates `doxygen_input_roots` under the
resolved scope and stashes the result; the fallback walked `[repo_root]` instead, so a repository
declaring `index_scope.roots: [src]` had `node_modules/`, `vendor/` and `.git` internals handed
to `register_synth_paths` and written into the `path` table.

That is not only a wrong row count. `path` is the file set the index publishes, so a declaration
the owner made to keep a vendored tree out of the graph was honoured by one front end and ignored
by the other — the same split B3 produces between the gate and the index.

@brief Scope containment for the parse-built front end's file set.
@version 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from clew.cli import _scanned_files
from clew.scope import SOURCE_DECLARED, DerivedScope


## @brief A repo with a declared root, a vendored tree and a git directory.
## @return (repo root, the one path a declared build may report)
## @version 1
def _repo(tmp_path: Path) -> tuple[Path, str]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("export const x = 1;\n")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "index.js").write_text("module.exports = 1;\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "COMMIT_EDITMSG").write_text("wip\n")
    return tmp_path, "src/main.ts"


def test_a_declared_scope_bounds_the_parse_built_file_set(tmp_path: Path) -> None:
    """@brief A declared root excludes everything outside it. @version 1"""
    repo, wanted = _repo(tmp_path)
    args = argparse.Namespace(
        extra_exclude=[],
        scope_result=DerivedScope(
            source=SOURCE_DECLARED,
            reason="declared in the test",
            roots=(repo / "src",),
        ),
    )

    scanned = _scanned_files(args, repo)

    assert scanned == [wanted], (
        "the parse-built front end was handed files outside the declared scope, so the "
        f"`path` table publishes a tree the owner excluded: {scanned}"
    )


def test_an_undeclared_repo_still_walks_itself(tmp_path: Path) -> None:
    """THE CONTROL. Saying nothing still means the whole repository — the fix must bound a
    declaration, not quietly narrow every build that made none.

    @brief With no declared roots the walk is the repo. @version 1
    """
    repo, wanted = _repo(tmp_path)
    args = argparse.Namespace(extra_exclude=[], scope_result=None)

    scanned = _scanned_files(args, repo)

    assert wanted in scanned
    assert any(entry.startswith("node_modules/") for entry in scanned), (
        "nothing was declared, so the vendored tree is in scope by default"
    )


def test_the_doxygen_stages_own_enumeration_still_wins(tmp_path: Path) -> None:
    """When doxygen ran it already enumerated under the scope AND dropped binaries; re-walking
    here would undo `_drop_binary_files`.

    @brief A stashed scanned set is returned verbatim. @version 1
    """
    repo, _ = _repo(tmp_path)
    args = argparse.Namespace(scanned_files=["src/main.ts"], extra_exclude=[], scope_result=None)

    assert _scanned_files(args, repo) == ["src/main.ts"]
