# SPDX-License-Identifier: MIT
"""Tests for gh#4 — the no-Doxyfile message misdescribes a supported path.

Indexing a repository that ships no Doxyfile is a SUPPORTED path: the pipeline
synthesises one and it works, and a Doxyfile-less target was deliberately kept as
a benchmark subject to keep that path exercised. The old message met a user on
that route and told them to pass `--doxyfile` — which, in the reachable case, is
the flag they had just passed. A message that misdescribes the situation costs the
reader their next twenty minutes on the wrong hypothesis, which is the same cost
as a silent wrong answer and is usually paid by whoever knows the codebase least.

Four situations, four distinct sentences, asserted here to be MUTUALLY DISTINCT
rather than merely non-empty — "the message changed" is not the property under
test, "the reader can tell which of these happened" is.

@brief Tests for Doxyfile-resolution messaging.
@version 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from clew import cli
from clew.scope import SCOPE_DOXYFILE
from clew.doxygen import (
    DOXYFILE_ABSENT,
    DOXYFILE_EXPLICIT_MISSING,
    DOXYFILE_NO_TARGET,
    DOXYFILE_REJECTED,
    describe_doxyfile_resolution,
    discover_doxyfile,
)


## @brief Build a namespace mimicking the parsed args the resolution prefix reads.
## @return Namespace with the Doxyfile-resolution fields set.
## @version 1
def _args(**over) -> argparse.Namespace:
    """@brief Minimal args namespace for resolution probing."""
    ## READ FROM `scope`, THE OWNING MODULE, not re-exported through `cli`. The 22->6
    ## collapse deleted the `--scope` flag whose `choices=` was the only thing importing this
    ## constant into `cli`, so reaching for it there was borrowing a name that existed by
    ## accident of one argument's declaration.
    base = {
        "doxyfile": None,
        "repo_root": None,
        "scope": SCOPE_DOXYFILE,
        "guard_config": None,
        "extra_input": None,
        "extra_exclude": None,
    }
    base.update(over)
    return argparse.Namespace(**base)


## @brief The explicitly-passed-but-absent case never proposes --doxyfile again.
## @version 1
def test_a_missing_explicit_doxyfile_does_not_propose_passing_one(tmp_path: Path) -> None:
    """The literal gh#4 complaint. The user passed --doxyfile; the path is not on
    disk; the old text answered "Pass --doxyfile". "Never proposes an action
    already taken" is the property, so this asserts the ABSENCE of that advice as
    well as the presence of the path that was actually tried."""
    missing = tmp_path / "nope" / "Doxyfile"
    outcome = describe_doxyfile_resolution(explicit=missing, repo_root=None, candidates=[])

    assert outcome.kind == DOXYFILE_EXPLICIT_MISSING
    assert str(missing) in outcome.message, "the message must name the path that was tried"
    assert "--repo-root" in outcome.message, "it must name the flag that changes the outcome"
    assert "pass --doxyfile" not in outcome.message.lower(), (
        "it must not propose the flag the user just used"
    )


## @brief With neither flag, nothing was searched — say so, and name synthesis.
## @version 1
def test_with_no_target_at_all_the_message_names_synthesis(tmp_path: Path) -> None:
    """No --doxyfile and no --repo-root: no directory was ever searched, so
    "Doxyfile not found" is not even true. The old text rendered the path as the
    literal string "None". The reader needs to know a repo root is what is missing,
    and that a repo with no Doxyfile is nonetheless indexable."""
    outcome = describe_doxyfile_resolution(explicit=None, repo_root=None, candidates=[])

    assert outcome.kind == DOXYFILE_NO_TARGET
    assert "--repo-root" in outcome.message
    assert "None" not in outcome.message, "no message should render a missing path as 'None'"


## @brief A repo with no Doxyfile is described as supported, not as an error.
## @version 1
def test_no_doxyfile_anywhere_is_described_as_supported(tmp_path: Path) -> None:
    """The bullet the issue leads with. A repo that ships none gets synthesis, and
    the message must SAY that rather than reading as a refusal — this is the
    sentence a reader meets on the route the tool handles well."""
    repo = tmp_path / "repo"
    repo.mkdir()
    outcome = describe_doxyfile_resolution(explicit=None, repo_root=repo, candidates=[])

    assert outcome.kind == DOXYFILE_ABSENT
    assert not outcome.is_error, "a repo with no Doxyfile is a supported configuration"
    assert "synthesi" in outcome.message.lower(), "it must say synthesis is what happens next"
    assert str(repo) in outcome.message


## @brief A rejected candidate says where it was found and why it was not used.
## @version 1
def test_a_rejected_candidate_says_where_and_why(tmp_path: Path) -> None:
    """`discover_doxyfile` refuses to guess among strays rather than picking
    alphabetically, because it was once caught selecting a test FIXTURE's Doxyfile
    to index a whole project. The message must carry that reasoning — a bare "not
    used" invites the reader to conclude the tool failed to find what it plainly
    did find."""
    repo = tmp_path / "repo"
    (repo / "sample").mkdir(parents=True)
    stray = repo / "sample" / "Doxyfile"
    stray.write_text("PROJECT_NAME = fixture\n")

    candidates = [stray]
    outcome = describe_doxyfile_resolution(explicit=None, repo_root=repo, candidates=candidates)

    assert outcome.kind == DOXYFILE_REJECTED
    assert not outcome.is_error, "refusing to guess still proceeds via synthesis"
    assert "sample/Doxyfile" in outcome.message, "it must say WHERE the candidate was found"
    lowered = outcome.message.lower()
    assert "--doxyfile" in outcome.message, "it must name the flag that selects one"
    assert "guess" in lowered or "wrong" in lowered, "it must say WHY it was not adopted"


## @brief The four sentences are mutually distinct.
## @version 1
def test_the_four_situations_produce_four_distinct_sentences(tmp_path: Path) -> None:
    """The point of the change is DISCRIMINATION, so this is the assertion that
    actually pins it. Four messages that all improved but two of which still read
    alike would leave the reader exactly where they started."""
    repo = tmp_path / "repo"
    (repo / "sample").mkdir(parents=True)
    (repo / "sample" / "Doxyfile").write_text("x\n")

    outcomes = [
        describe_doxyfile_resolution(
            explicit=tmp_path / "n" / "Doxyfile", repo_root=None, candidates=[]
        ),
        describe_doxyfile_resolution(explicit=None, repo_root=None, candidates=[]),
        describe_doxyfile_resolution(explicit=None, repo_root=repo, candidates=[]),
        describe_doxyfile_resolution(
            explicit=None, repo_root=repo, candidates=[repo / "sample" / "Doxyfile"]
        ),
    ]
    kinds = [o.kind for o in outcomes]
    assert len(set(kinds)) == 4, f"situations must be distinguishable, got {kinds}"
    messages = [o.message for o in outcomes]
    assert len(set(messages)) == 4, "each situation needs its own sentence"


## @brief Only the two no-target situations are errors.
## @version 1
def test_only_the_unresolvable_situations_are_errors(tmp_path: Path) -> None:
    """The is_error split is the behavioural claim in a message-only change: the
    two synthesis routes must stay non-errors, or a supported path becomes a
    refusal — which is the regression this change could most easily introduce."""
    repo = tmp_path / "repo"
    repo.mkdir()

    assert describe_doxyfile_resolution(None, None, []).is_error
    assert describe_doxyfile_resolution(tmp_path / "n" / "Doxyfile", None, []).is_error
    assert not describe_doxyfile_resolution(None, repo, []).is_error
    assert not describe_doxyfile_resolution(None, repo, [repo / "s" / "Doxyfile"]).is_error


## @brief Candidate enumeration is exposed so the message can name what was found.
## @version 1
def test_candidates_are_reported_without_being_adopted(tmp_path: Path) -> None:
    """`discover_doxyfile` still returns None for a stray — the refusal behaviour is
    unchanged — while the candidates it declined are separately readable, which is
    what lets the message say where they were. Both halves asserted together,
    because a change that started ADOPTING strays would fix the message and
    reintroduce the fixture-indexing defect."""
    from clew.doxygen import rejected_doxyfile_candidates

    repo = tmp_path / "repo"
    (repo / "sample").mkdir(parents=True)
    (repo / "sample" / "Doxyfile").write_text("x\n")

    assert discover_doxyfile(repo) is None, "a stray must still not be adopted"
    candidates = rejected_doxyfile_candidates(repo)
    assert [p.relative_to(repo).as_posix() for p in candidates] == ["sample/Doxyfile"]

    # A TRUSTED location is never reported as a rejected candidate — otherwise the
    # message would name the very file it went on to adopt.
    (repo / "docs").mkdir()
    (repo / "docs" / "Doxyfile").write_text("x\n")
    assert discover_doxyfile(repo) == repo / "docs" / "Doxyfile"
    assert repo / "docs" / "Doxyfile" not in rejected_doxyfile_candidates(repo)

    # A repo with no strays at all has nothing to report.
    bare = tmp_path / "bare"
    bare.mkdir()
    assert rejected_doxyfile_candidates(bare) == []


## @brief The CLI still refuses, and now with the discriminating message.
## @version 1
def test_the_cli_refusal_uses_the_new_message(tmp_path: Path, caplog) -> None:
    """End-to-end at the real refusal site, because a classifier that is correct in
    isolation and unwired changes nothing a user sees. Only the no-repo-root
    branches reach sys.exit; the synthesis branches are covered by the integration
    build tests."""
    missing = tmp_path / "nope" / "Doxyfile"
    args = _args(doxyfile=str(missing), output=str(tmp_path / "clew.db"))

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as excinfo:
        cli._run_pipeline(args)
    assert excinfo.value.code == 1
    assert str(missing.resolve()) in caplog.text
    assert "pass --doxyfile" not in caplog.text.lower()
