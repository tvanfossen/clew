# SPDX-License-Identifier: MIT
"""A grid refuses to measure a clew tree it cannot name.

WHY. `clew_dirty` was recorded in `run.json`, in every window and in `provision.json` — and read
by nothing. The 1.2.0 grid ran with `clew_dirty: true`, and its RESULTS.md had to explain after
the fact that `844fee55` does not resolve to the tree that answered. The target side already
refuses this (`check_revision`: "HEAD IS NOT THE TREE"); the tool under test did not.

UNKNOWN REFUSES TOO. When git cannot answer, `tool_identity` drops `clew_commit` rather than
blanking it, which is right for a record and wrong for a gate: a number that cannot be attributed
to a build of clew is not evidence about clew, so "nobody could check" is refused exactly like
"checked and dirty".

@brief Tests for the clew-tree refusal.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acceptance import __main__ as cli
from acceptance import provision, runner
from acceptance.grader.rubric import load

_SHA = "a" * 40
_MBEDTLS = Path(__file__).resolve().parent.parent / "acceptance/targets/mbedtls/questions.yaml"


## @brief A modified clew tree is refused, and the refusal names the remedy.
## @return None.
## @version 1
def test_a_dirty_clew_tree_is_refused() -> None:
    """@brief Dirty refuses.
    @version 1
    """
    with pytest.raises(ValueError, match="(?i)modified") as raised:
        runner.check_tool_tree({"clew_commit": _SHA, "clew_dirty": True})
    assert _SHA in str(raised.value), "the refusal does not name the commit it was measuring"


## @brief A clew tree git could not describe is refused.
## @return None.
## @version 1
def test_an_unknown_clew_tree_is_refused() -> None:
    """@brief Unknown refuses — absence is not cleanliness.
    @version 1
    """
    with pytest.raises(ValueError, match="(?i)cannot"):
        runner.check_tool_tree({"clew_build_version": "9"})


## @brief A clean clew tree at a known commit passes.
## @return None.
## @version 1
def test_a_clean_clew_tree_passes() -> None:
    """@brief Clean passes.
    @version 1
    """
    runner.check_tool_tree({"clew_commit": _SHA, "clew_dirty": False})


## @brief `generate` refuses before spending a cell when the clew tree is dirty.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @param capsys Pytest capture fixture.
## @return None.
## @version 1
def test_generate_refuses_a_dirty_clew_tree(tmp_path: Path, monkeypatch, capsys) -> None:
    """THE TARGET CHECK IS STUBBED so the only reason left to refuse is the clew tree; without
    that, a missing target checkout would return 1 and this test would pass for the wrong reason.

    @brief generate refuses.
    @version 1
    """
    spent: list[str] = []
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "run_cell", lambda cell, *_a, **_k: spent.append(cell.stem()))
    monkeypatch.setattr(runner, "tool_identity", lambda: {"clew_commit": _SHA, "clew_dirty": True})
    args = cli.argparse.Namespace(
        rubric=_MBEDTLS,
        models=["claude-haiku-5-5"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=tmp_path / "answers",
        mcp_config=None,
        timeout=60,
        resume=False,
    )

    assert cli.cmd_generate(args) == 1
    assert not spent, f"{len(spent)} cell(s) were generated against a modified clew tree"
    assert "REFUSED" in capsys.readouterr().err


## @brief `provision` refuses before fetching when the clew tree is dirty.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def test_provision_refuses_a_dirty_clew_tree(tmp_path: Path, monkeypatch) -> None:
    """BEFORE THE FETCH, because the fetch and the index build are the expensive steps and a
    dirty tree makes both worthless.

    @brief provision refuses.
    @version 1
    """
    fetched: list[Path] = []
    monkeypatch.setattr(provision, "fetch_pinned", lambda _r, repo: fetched.append(repo))
    monkeypatch.setattr(runner, "tool_identity", lambda: {"clew_commit": _SHA, "clew_dirty": True})

    with pytest.raises(provision.ProvisionError, match="(?i)modified"):
        provision.provision(load(_MBEDTLS), tmp_path / "mbedtls")
    assert not fetched, "the target was fetched for a clew tree that was going to be refused"
