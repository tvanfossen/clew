# SPDX-License-Identifier: MIT
"""gh#39 route 2b — the parent declares scope for its NAMED sub-indexes.

THE CASE THIS EXISTS FOR. A repository vendors `deps/functional/b12-slam`, which itself
vendors nine of its own submodules — boost at 641 MB, opencv at 217 MB, pcl at 142 MB. That
sub-index cannot finish inside the 900 s doxygen cap, and nothing the parent could say would
trim it: `_sub_index_scope` builds a vendored sub-index from its `roots` alone, and a
`.clew.yaml` inside the nested tree is never read because declaration discovery is rooted at
the parent. The tree is upstream's, so putting a file in it is not an option either.

WHY THE PARENT'S DECLARATION AND NOT CALL METADATA. The alternative was stashing excludes in
the sub-index's own database on its first build and replaying them. That would put the value
somewhere only the operator who made the call can see, so two operators of one commit hold
different indexes — the shape gh#352 rejected, and the reason `options.*` tier rows exist at
all. A declaration is durable, reviewable in the same diff as the code, and readable by
everyone who clones the repository.

THE VOCABULARY IS `index_scope`'s, NOT A SECOND ONE. `roots` and `excludes` mean here exactly
what they mean there, and paths are repo-relative for the same reason — a declaration that
spelled the same two ideas differently one section over is how two readers of one file come to
disagree about what it says.

A NAME THAT MATCHES NO SUB-INDEX IS REFUSED. An accepted-but-unread key is this project's most
repeated defect, and a `sub_indexes:` block naming a tree that is not vendored here would
otherwise sit in the file doing nothing while its author believed it was trimming a build.

@brief Tests for per-sub-index scope declared by the parent repository.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.scope import FIRST_PARTY_INDEX


##
# @brief A repository whose vendored tree vendors more of its own.
# @param root Directory to build the repository in.
# @return The resolved repository root.
# @version 1
def _repo(root: Path) -> Path:
    """@brief Two vendored trees, one of them carrying a heavy child.
    @return The repo root, resolved.
    @version 1
    """
    (root / "app").mkdir(parents=True)
    for name in ("slam", "tinyfsm"):
        nested = root / "deps" / name
        nested.mkdir(parents=True)
        (nested / ".git").write_text(f"gitdir: ../../.git/modules/{name}\n", encoding="utf-8")
    heavy = root / "deps" / "slam" / "deps" / "boost"
    heavy.mkdir(parents=True)
    (heavy / ".git").write_text("gitdir: x/boost\n", encoding="utf-8")
    return root.resolve()


##
# @brief Write a `.clew.yaml` declaring scope for named sub-indexes.
# @param repo The repository root.
# @param body The `sub_indexes:` block, already rendered as YAML.
# @return None.
# @version 1
def _declare(repo: Path, body: str) -> None:
    """@brief Write the parent declaration.
    @version 1
    """
    (repo / ".clew.yaml").write_text(f"sub_indexes:\n{body}", encoding="utf-8")


def test_a_declared_exclude_reaches_the_named_sub_index(tmp_path: Path) -> None:
    """THE MOTIVATING CASE. The parent trims a vendored tree it does not own, and the trim
    lands on top of the derived nested-tree excludes rather than replacing them — the child
    trees still belong to their own sub-indexes.

    @brief A declared exclude joins the derived ones for that sub-index.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = _repo(tmp_path / "repo")
    _declare(repo, "  deps-slam:\n    excludes: [deps/slam/third_party]\n")
    target = target_for(repo, tmp_path / "state", name="deps-slam")

    _exclude, options = _sub_index_scope(target, repo, None, None)
    scope = options["index_scope"]
    assert scope["roots"] == ["deps/slam"]
    assert "deps/slam/third_party" in scope["excludes"], scope
    assert "deps/slam/deps/boost" in scope["excludes"], (
        "the derived child-tree excludes must survive the declared ones"
    )


def test_a_declaration_applies_only_to_the_sub_index_it_names(tmp_path: Path) -> None:
    """THE CONTROL. A block keyed by name must not leak onto a sibling — otherwise one heavy
    tree's trim would silently narrow every other vendored index in the repository.

    @brief A sibling sub-index is unaffected.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = _repo(tmp_path / "repo")
    _declare(repo, "  deps-slam:\n    excludes: [deps/slam/third_party]\n")
    sibling = target_for(repo, tmp_path / "state", name="deps-tinyfsm")

    _exclude, options = _sub_index_scope(sibling, repo, None, None)
    assert "deps/slam/third_party" not in (options["index_scope"].get("excludes") or [])


def test_first_party_honours_its_own_declared_excludes(tmp_path: Path) -> None:
    """FIRST-PARTY IS A SUB-INDEX LIKE ANY OTHER here, so the same block trims it. Its excludes
    join the caller's list rather than an `index_scope`, because that is how the first-party
    branch has always passed them.

    @brief A declared first-party exclude reaches the build.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = _repo(tmp_path / "repo")
    _declare(repo, f"  {FIRST_PARTY_INDEX}:\n    excludes: [app/generated]\n")
    target = target_for(repo, tmp_path / "state", name=FIRST_PARTY_INDEX)

    exclude, _options = _sub_index_scope(target, repo, ["build"], None)
    assert "app/generated" in exclude, exclude
    assert "build" in exclude, "the caller's own exclusions are still added to, never replaced"


def test_a_declared_name_that_is_not_a_sub_index_is_refused(tmp_path: Path) -> None:
    """AN ACCEPTED-BUT-UNREAD KEY IS THIS PROJECT'S MOST REPEATED DEFECT. A block naming a tree
    this repository does not vendor would sit in the file doing nothing while its author
    believed it was trimming a build — the same failure `_INDEX_SCOPE_KEYS` closes one level
    down, and the same one gh#5's reporter hit with `exclude:` for `excludes:`.

    @brief An unknown sub-index name is refused, naming what is buildable.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = _repo(tmp_path / "repo")
    _declare(repo, "  deps-nosuchtree:\n    excludes: [x]\n")
    target = target_for(repo, tmp_path / "state", name="deps-slam")

    with pytest.raises(ValueError, match="deps-nosuchtree"):
        _sub_index_scope(target, repo, None, None)


def test_an_unknown_key_inside_a_block_is_refused_by_name(tmp_path: Path) -> None:
    """THE ENTRY-LEVEL RULE `index_scope` ALREADY KEEPS, one section over: the section name is
    validated and the keys inside it must be too, or `exclude:` for `excludes:` parses to a
    perfectly valid mapping no consumer reads.

    @brief A misspelled key inside a sub-index block is refused.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = _repo(tmp_path / "repo")
    _declare(repo, "  deps-slam:\n    exclude: [deps/slam/third_party]\n")
    target = target_for(repo, tmp_path / "state", name="deps-slam")

    with pytest.raises(ValueError, match="exclude"):
        _sub_index_scope(target, repo, None, None)
