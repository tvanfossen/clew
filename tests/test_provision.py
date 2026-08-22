# SPDX-License-Identifier: MIT
"""Tests for target provisioning — every step refuses rather than degrades.

No network and no real builds: git and the build subprocess are replaced. What matters here is
the ORDER of the refusals and that each one fires, not that git works.

@brief Tests for acceptance.provision.
@version 1
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import provision
from acceptance.grader.rubric import Question, Rubric


## @brief A rubric stub.
## @param declare Declaration sections, if any.
## @return Rubric.
## @version 1
def _rubric(declare: dict | None = None) -> Rubric:
    """@brief Minimal rubric for provisioning tests.
    @return Rubric.
    @version 1
    """
    return Rubric(
        target="owner/repo",
        commit="a" * 40,
        version="1.0.0",
        ground_truth="source",
        judge_model="claude-x-1",
        judge_samples_when_weight_at_least=2,
        questions=(Question(id="Q1", intent="i", prompt="p"),),
        declare=declare or {},
    )


## @brief An MCP config is never written for an index that does not exist.
## @return None.
## @version 1
def test_mcp_config_refuses_without_an_index(tmp_path: Path) -> None:
    """A config naming a database that was never built sends the index arm to an EMPTY index,
    which answers — badly — rather than refusing. The whole point of writing the config last is
    that it cannot exist before the thing it points at.

    @brief No config without an index.
    @return None.
    @version 1
    """
    with pytest.raises(provision.ProvisionError, match="does not exist"):
        provision.write_mcp_config(
            tmp_path / "absent.db", tmp_path, tmp_path / "mcp.json", tmp_path / "state"
        )


## @brief A written config names the target repo and the module server.
## @return None.
## @version 1
def test_mcp_config_names_the_target(tmp_path: Path) -> None:
    """@brief The config points at this target, not a derived default.
    @return None.
    @version 1
    """
    db = tmp_path / "clew.db"
    db.write_bytes(b"x")
    out = tmp_path / "mcp.json"
    provision.write_mcp_config(db, tmp_path / "repo", out, tmp_path / "state")
    doc = json.loads(out.read_text())
    args = doc["mcpServers"]["clew"]["args"]
    assert "--repo" in args
    assert str(tmp_path / "repo") in args, "a config that does not name the repo derives one"
    ## THE SERVER TAKES NO DATABASE PATH — it derives one from --repo under CLEW_STATE_HOME. So
    ## the config MUST carry the same state root the build used, or the server looks somewhere
    ## the build never wrote and registers no query tools, silently.
    env = doc["mcpServers"]["clew"]["env"]
    assert env["CLEW_STATE_HOME"] == str(tmp_path / "state")


## @brief A build that exits non-zero raises rather than leaving a partial index.
## @return None.
## @version 1
def test_failed_build_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief A failed build is not a provisioned target.
    @return None.
    @version 1
    """

    def run(argv, **_kw):
        return subprocess.CompletedProcess(argv, 1, "", "doxygen exploded")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(provision.ProvisionError, match="index build failed"):
        provision.build_index(_rubric(), tmp_path, tmp_path / "state", None)


## @brief A missing database is reported, not treated as an empty one.
## @return None.
## @version 1
def test_absent_index_is_refused(tmp_path: Path) -> None:
    """@brief No index is not an empty index.
    @return None.
    @version 1
    """
    with pytest.raises(provision.ProvisionError, match="no index was written"):
        provision.read_build_meta(tmp_path / "absent.db")


## @brief Fetching pins the SHA rather than a branch tip.
## @return None.
## @version 1
def test_fetch_asks_for_the_sha_not_a_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fetching a branch and checking out transfers a history, materialises a tip that may
    differ from the pin, and lands silently on whatever `main` happens to be once the commit is
    gone. `fetch --depth 1 <sha>` fails loudly instead.

    @brief The pin is fetched directly.
    @return None.
    @version 1
    """
    calls: list[tuple] = []

    def fake_git(cwd, *args):
        calls.append(args)
        return ""

    monkeypatch.setattr(provision, "_git", fake_git)
    rubric = _rubric()
    provision.fetch_pinned(rubric, tmp_path / "repo")
    fetches = [a for a in calls if a and a[0] == "fetch"]
    assert fetches, "nothing was fetched"
    assert rubric.commit in fetches[0], f"fetched something other than the pin: {fetches[0]}"
    assert not any("--branch" in a or "clone" in a for a in calls), "a branch tip is not the pin"


## @brief An already-pinned checkout is left alone, so provisioning is idempotent.
## @return None.
## @version 1
def test_existing_checkout_at_the_pin_is_not_refetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-provisioning must cost nothing, or a resumed run pays for every target again.

    @brief Idempotent provisioning.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rubric = _rubric()
    calls: list[tuple] = []
    monkeypatch.setattr(
        provision,
        "_git",
        lambda cwd, *a: (
            (calls.append(a), rubric.commit)[1] if a[0] == "rev-parse" else (calls.append(a), "")[1]
        ),
    )
    provision.fetch_pinned(rubric, repo)
    assert [a[0] for a in calls] == ["rev-parse"], f"did more than check HEAD: {calls}"
