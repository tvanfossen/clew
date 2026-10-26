# SPDX-License-Identifier: MIT
"""What produced a number, recorded beside it.

A grid's artifacts named the target, the rubric and the seed and said NOTHING about the tool
under test — so a published score was attributable to everything except clew. These tests pin
the fields that close that gap, and the one field that cannot be substituted for.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import identity


## @brief The identity names the tool, not only what was asked of it.
## @return None.
## @version 1
def test_identity_records_the_clew_and_substrate_under_test() -> None:
    """`run.json` recorded target, commit, rubric version and digest, seed, models and
    replicates — every input except the one thing the grid is a measurement OF. A reader could
    not tell a score produced by 1.1.0 from one produced by 1.0.39.

    @brief The identity carries clew and substrate.
    @return None.
    @version 1
    """
    got = identity.tool_identity()
    assert got["clew_version"]
    assert len(got["clew_commit"]) == 40, "a short sha is ambiguous across a fork"
    assert isinstance(got["clew_dirty"], bool), "a measurement, present even when False"
    assert got["clew_build_version"] == str(identity.CLEW_BUILD_VERSION)
    assert got["substrate_version"]


## @brief The language set is what distinguishes the fork, so it is recorded as a set.
## @return None.
## @version 1
def test_the_substrate_language_set_is_recorded_not_just_its_version() -> None:
    """THE VERSION STRING CANNOT SETTLE THIS. The fork carrying 1.1.0's five grammars reports
    `0.11.2`, byte-identical to the published wheel, because the pull request carries no bump —
    which is the whole reason `clew.substrate` exists. A run record holding only the version
    cannot say which wheel answered, so it holds the compiled-in keys.

    @brief Languages are recorded.
    @return None.
    @version 1
    """
    langs = identity.tool_identity()["substrate_languages"]
    assert langs == sorted(langs), "recorded sorted, so two runs diff rather than reorder"
    assert "c" in langs and "python" in langs


## @brief An unreadable field is absent, never empty.
## @return None.
## @version 1
def test_a_field_that_could_not_be_read_is_dropped_rather_than_blanked() -> None:
    """ "NOBODY MEASURED" AND "NOTHING THERE" MUST NOT READ ALIKE. An empty string or an empty
    list in a published record reads as a finding; the key's absence reads as a gap. This is the
    same rule `clew/mcp_server/emptiness.py` enforces on the served scope.

    @brief Unreadable fields are omitted.
    @return None.
    @version 1
    """
    blank = identity.tool_identity(repo=Path("/nonexistent-tree-for-this-test"))
    assert "clew_commit" not in blank, "a sha that could not be read is not the empty sha"
    assert "clew_dirty" not in blank, "and nothing may claim the tree was clean"
    ## The fields that do not come from git are still there — a missing checkout is not a
    ## missing install.
    assert blank["clew_version"]
    assert blank["substrate_languages"]


## @brief A provisioned target leaves a record naming the build, not just the pin.
## @return None.
## @version 1
def test_provision_writes_a_record_naming_the_build(tmp_path: Path) -> None:
    """`build_version` WAS READ AND ONLY PRINTED. It survived a run only if the operator
    redirected stdout, and the database that carries it is gitignored on purpose. So the one
    number describing the index under test reached no committed file.

    @brief provision.json carries the build.
    @return None.
    @version 1
    """
    import json

    from acceptance import provision
    from acceptance.grader.rubric import load

    rubric = load(
        Path(__file__).resolve().parent.parent / "acceptance/targets/mbedtls/questions.yaml"
    )
    out = tmp_path / "provision.json"
    provision.write_provision_record(
        rubric,
        tmp_path / "clew.db",
        {"build_version": "8", "tool.substrate_version": "0.11.2"},
        out,
    )
    got = json.loads(out.read_text())
    assert got["commit"] == rubric.commit
    assert got["build_version"] == "8"
    ## THE FIELD A VERSION STRING CANNOT SUBSTITUTE FOR.
    assert "substrate_languages" in got
    assert got["clew_build_version"] == str(identity.CLEW_BUILD_VERSION)


## @brief The run record names the tool as well as the inputs.
## @return None.
## @version 1
def test_run_json_carries_the_tool_identity(tmp_path: Path, monkeypatch) -> None:
    """A reader holding only `answers/` must still be able to attribute the numbers. Provisioning
    records the same fields, but its file sits beside a gitignored database and a run assembled
    over several windows may be re-provisioned between them.

    @brief run.json carries clew.
    @return None.
    @version 1
    """
    import json

    from acceptance import __main__ as cli
    from acceptance import execute

    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "run_cell",
        lambda cell, *_a, **_k: execute.CellResult(
            cell.stem(), cell.arm, cell.model, True, tool_calls=1
        ),
    )
    rubric = Path(__file__).resolve().parent.parent / "acceptance/targets/freertos/questions.yaml"
    out = tmp_path / "answers"
    args = cli.argparse.Namespace(
        rubric=rubric,
        ## FIXTURE, NOT BEHAVIOUR. This said `m` (resp. `sonnet`) until `--models` began
        ## refusing an alias. What this test guards is unchanged; only the example string
        ## had to become a real pinned id to reach the code under test.
        models=["claude-sonnet-4-5-20250929"],
        replicates=1,
        seed=7,
        repo=tmp_path,
        out=out,
        mcp_config=None,
        timeout=60,
        resume=False,
    )
    assert cli.cmd_generate(args) == 0
    got = json.loads((out / "run.json").read_text())
    assert got["clew_build_version"] == str(identity.CLEW_BUILD_VERSION)
    assert "substrate_languages" in got


## @brief A build that reported on stdout still refuses with a reason.
## @return None.
## @version 1
def test_a_build_failure_carries_a_reason_even_when_stderr_is_empty(monkeypatch) -> None:
    """MEASURED ON THE FIRST PUBLISHED GRID'S PRE-FLIGHT. One target refused with exactly
    "index build failed (rc=1): " — the reason was the empty string, because the pipeline logs
    its progress and its doxygen failure to STDOUT and the refusal quoted only stderr. The
    operator is then told a build failed and nothing about why, on the one phase whose whole
    purpose is to fail cheaply and informatively.

    THE TAIL IS THE RIGHT END. A build prints thousands of progress lines before it fails, so
    the last characters are the ones carrying the failure; the head would be the file-typing
    chatter every build emits.

    @brief A refusal names the failure.
    @return None.
    @version 1
    """
    import subprocess

    from acceptance import provision

    class _Done:
        returncode = 1
        stdout = "file typing: skipping\nDoxygen exited with code 2\n"
        stderr = "   \n"

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Done())
    try:
        provision.build_index(object(), Path("/repo"), Path("/state"), None)
    except provision.ProvisionError as exc:
        assert "Doxygen exited with code 2" in str(exc)
    else:
        raise AssertionError("a failed build must refuse")


## @brief Grading reports progress as it goes rather than all at the end.
## @return None.
## @version 1
def test_grading_prints_each_cell_before_the_last_one_is_scored(tmp_path, monkeypatch) -> None:
    """A GRADE PASS IS ~3,400 JUDGE CALLS AND THE NOISE FLOOR NEEDS TWO OF THEM. An operator
    watching a log that prints nothing until the end cannot tell grading from a hang — the
    failure `matrix.py` already carries a line-buffering comment about, and collecting every
    line before printing any reintroduces it.

    THE ASSERTION IS INTERLEAVING, NOT TIMING. Both events go into one ordered list, so the
    test asks a structural question — did any cell's line reach the operator before the last
    cell was scored — which a collect-then-print implementation fails deterministically and a
    streaming one passes on any machine.

    @brief Progress is incremental.
    @return None.
    @version 1
    """
    import builtins

    import yaml

    from acceptance import __main__ as cli

    events: list[str] = []

    class _Stub:
        decisions: list = []

        def split_decisions(self) -> int:
            return 0

        def score(self) -> tuple[float, float]:
            return 0.5, 0.0

    def scored(*_a, **_k):
        events.append("scored")
        return _Stub()

    real_print = builtins.print

    def spy(*a, **k):
        events.append("printed")
        real_print(*a, **k)

    rubric = Path(__file__).resolve().parent.parent / "acceptance/targets/mbedtls/questions.yaml"
    qid = yaml.safe_load(rubric.read_text())["questions"][0]["id"]
    for i in range(1, 4):
        (tmp_path / f"{qid}_m_baseline_r{i}.md").write_text("answer", "utf-8")

    monkeypatch.setattr(cli, "score_question", scored)
    monkeypatch.setattr(builtins, "print", spy)
    args = cli.argparse.Namespace(rubric=rubric, answers=tmp_path, jobs=1)
    assert cli.cmd_grade(args) == 0
    monkeypatch.undo()

    last_scored = len(events) - 1 - events[::-1].index("scored")
    assert "printed" in events[:last_scored], (
        f"nothing reached the operator until every cell was graded: {events}"
    )


##
# @brief `generate` must refuse an answering model that is a client-resolved shortcut.
# @param tmp_path Pytest temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_generate_refuses_a_shortcut_answering_model(tmp_path: Path, monkeypatch) -> None:
    """**THIS IS THE 1.1.0 GAP, NARROWED BY A LATER RULING.** The judge was checked from the first
    release and the model being GRADED was never asked, so the published grid was judged by
    `claude-sonnet-4-5-20250929` and answered by `claude-haiku-5-5` with nothing recording it.

    v2: the fixture is `sonnet`, not `claude-haiku-5-5`. A first fix demanded a DATED id and
    thereby rejected every current-family model, blocking the harness; the owner ruled that the
    grid should move with the models and that the requirement is faithful recording, not
    immutability. A client-resolved shortcut is still refused, because the client maps it through
    configuration this harness never records.

    It refuses BEFORE any cell runs: `run_cell` is replaced with something that records being
    called, and the assertion is that it never was. A check that refused after spending the grid
    would pass a test that only looked at the exit code.

    @brief An alias answering model is refused before spending anything.
    @return None.
    @version 1
    """
    import json  # noqa: F401

    from acceptance import __main__ as cli

    FREERTOS = Path(__file__).resolve().parent.parent / "acceptance/targets/freertos/questions.yaml"
    spent: list[str] = []
    monkeypatch.setattr(cli, "run_cell", lambda cell, *_a, **_k: spent.append(cell.stem()))
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    out = tmp_path / "answers"
    args = cli.argparse.Namespace(
        rubric=FREERTOS,
        models=["sonnet"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=out,
        mcp_config=None,
        timeout=60,
        resume=False,
    )

    assert cli.cmd_generate(args) == 1, "a client-resolved shortcut was accepted"
    assert not spent, f"cells were spent before the refusal: {spent}"


##
# @brief Each `generate` must append a window record rather than overwrite the previous one.
# @param tmp_path Pytest temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_each_generate_appends_a_window_rather_than_overwriting(
    tmp_path: Path, monkeypatch
) -> None:
    """**THE 1.1.0 GRID CANNOT SAY HOW MANY SITTINGS BUILT IT.** `resumed` recorded which stems
    came from before — the right fact — but every `generate` REWROTE `run.json`, so after three
    capacity windows the record described only the last one. A grid assembled over several windows
    must not read as one pass.

    TWO WINDOWS ARE RUN AND BOTH ARE ASSERTED PRESENT, in order, with the first one's identity
    still intact. Asserting only `len(windows) == 2` would pass an implementation that appended a
    fresh pair each time, and asserting only the last would pass the overwrite this fixes.

    @brief Windows accumulate across generate invocations.
    @return None.
    @version 1
    """
    import json

    from acceptance import __main__ as cli
    from acceptance import execute

    FREERTOS = Path(__file__).resolve().parent.parent / "acceptance/targets/freertos/questions.yaml"
    monkeypatch.setattr(
        cli,
        "run_cell",
        lambda cell, *_a, **_k: execute.CellResult(cell.stem(), cell.arm, cell.model, True),
    )
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    out = tmp_path / "answers"

    def once(resume: bool) -> None:
        cli.cmd_generate(
            cli.argparse.Namespace(
                rubric=FREERTOS,
                models=["claude-sonnet-4-5-20250929"],
                replicates=1,
                seed=7,
                repo=tmp_path / "repo",
                out=out,
                mcp_config=None,
                timeout=60,
                resume=resume,
            )
        )

    once(resume=False)
    first = json.loads((out / "run.json").read_text())["windows"]
    once(resume=True)
    windows = json.loads((out / "run.json").read_text())["windows"]

    assert len(first) == 1, f"the first generate recorded {len(first)} window(s)"
    assert [w["ordinal"] for w in windows] == [1, 2], (
        f"windows did not accumulate in order; got {[w.get('ordinal') for w in windows]}"
    )
    assert windows[0] == first[0], "the first window's record was rewritten by the second"
    assert "clew_build_version" in windows[1], (
        f"a window carries no tool identity, so it cannot be attributed: {windows[1]}"
    )


##
# @brief A floating canonical model must be accepted and named in the window record.
# @param tmp_path Pytest temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_floating_model_is_accepted_and_recorded_as_floating(tmp_path: Path, monkeypatch) -> None:
    """**ACCEPTANCE WITHOUT DISCLOSURE WOULD REPRODUCE THE ORIGINAL DEFECT.** 1.1.0 answered with
    a floating id and recorded nothing about it. A date requirement then rejected every
    current-family model and blocked the harness, so the ruling is that the grid tracks the models
    and the run says which ids can move.

    Both halves asserted together: the run must SUCCEED on `claude-haiku-5-5` and must NAME it as
    floating. A change that accepted it silently passes the first assertion alone.

    @brief Floating models are accepted and disclosed.
    @return None.
    @version 1
    """
    import json

    from acceptance import __main__ as cli
    from acceptance import execute

    FREERTOS = Path(__file__).resolve().parent.parent / "acceptance/targets/freertos/questions.yaml"
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "run_cell",
        lambda cell, *_a, **_k: execute.CellResult(cell.stem(), cell.arm, cell.model, ok=True),
    )
    out = tmp_path / "answers"
    args = cli.argparse.Namespace(
        rubric=FREERTOS,
        models=["claude-haiku-5-5"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=out,
        mcp_config=None,
        timeout=60,
        resume=False,
    )

    assert cli.cmd_generate(args) == 0, "a current-family model was refused; the harness is blocked"

    window = json.loads((out / "run.json").read_text())["windows"][-1]
    assert window["models_floating"] == ["claude-haiku-5-5"], (
        f"the run accepted a floating id without recording it: {window}"
    )


##
# @brief A dated model must not be recorded as floating.
# @param tmp_path Pytest temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_dated_model_is_not_recorded_as_floating(tmp_path: Path, monkeypatch) -> None:
    """ABSENT RATHER THAN EMPTY. A run where nothing floated carries no `models_floating` key at
    all, so "nothing floated" and "nobody checked" cannot read alike — and a reader who finds the
    key knows it means something.

    @brief Dated models are not flagged.
    @return None.
    @version 1
    """
    import json

    from acceptance import __main__ as cli
    from acceptance import execute

    FREERTOS = Path(__file__).resolve().parent.parent / "acceptance/targets/freertos/questions.yaml"
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "run_cell",
        lambda cell, *_a, **_k: execute.CellResult(cell.stem(), cell.arm, cell.model, ok=True),
    )
    out = tmp_path / "answers"
    args = cli.argparse.Namespace(
        rubric=FREERTOS,
        models=["claude-sonnet-4-5-20250929"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=out,
        mcp_config=None,
        timeout=60,
        resume=False,
    )

    assert cli.cmd_generate(args) == 0
    window = json.loads((out / "run.json").read_text())["windows"][-1]
    assert "models_floating" not in window, f"a dated id was reported as floating: {window}"
