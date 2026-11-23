# SPDX-License-Identifier: MIT
"""File and function dossiers carry who owns the file and the licence it declares (2.0.0, S2/S3/S5
served).

P2 built the `owners` (CODEOWNERS, kernel MAINTAINERS) and `file_licenses` (SPDX) layers; a layer
nothing serves changes nothing an agent can see. Measured by the P2 build on entropic: 656 owner
rows and 475 licence rows, reachable by no tool.

`owners` lists each owner with its role, its source format and the rule's line, so a reader can
check the match. `license` is the SPDX expression and its line. A function carries its FILE's, the
file `file` names. ABSENT when the layer did not run; an empty `owners` on a file dossier means
the rules ran and nothing matched.

@brief Tests ownership and licence on dossiers.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.query.subject import dossier

_FILES = {
    ".github/CODEOWNERS": "* @core\n/src/net/ @net-team @alice\n",
    "src/net/socket.c": "// SPDX-License-Identifier: Apache-2.0\n\n/** @brief Open. */\nint sock_open(void)\n{\n    return 3;\n}\n",
    "src/util.c": "/** @brief Helper. */\nint util_helper(void)\n{\n    return 1;\n}\n",
}


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """@brief Index the owned, licensed repo. @return (db, repo)."""
    base = tmp_path_factory.mktemp("own")
    repo = base / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = base / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db, repo


def test_a_file_names_its_owners_with_the_rule_that_matched(built) -> None:
    """@brief CODEOWNERS last match wins: the /src/net/ rule, line 2, two owners."""
    db, repo = built
    f = dossier(db, "src/net/socket.c", kind="file", repo_root=repo).file
    assert [(o.owner, o.source, o.rule_line) for o in f.owners] == [
        ("@net-team", "codeowners", 2),
        ("@alice", "codeowners", 2),
    ]
    assert (f.license.expression, f.license.line) == ("Apache-2.0", 1)


def test_a_function_carries_its_files_owners_and_license(built) -> None:
    """@brief Same records as the file's."""
    db, repo = built
    fn = dossier(db, "sock_open", repo_root=repo).function
    f = dossier(db, "src/net/socket.c", kind="file", repo_root=repo).file
    assert fn.owners == list(f.owners) and fn.license == f.license


def test_a_file_without_an_spdx_line_has_no_license(built) -> None:
    """@brief Absent, not an empty expression; the catch-all owner still applies."""
    db, repo = built
    f = dossier(db, "src/util.c", kind="file", repo_root=repo).file
    assert f.license is None
    assert [o.owner for o in f.owners] == ["@core"]
