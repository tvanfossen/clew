# SPDX-License-Identifier: MIT
"""An operator's exclusion is stated once, recorded, and honoured on every rebuild.

The index defaults to COMPLETE. Narrowing it is an explicit act, and the act has to
PERSIST — because a refresh RE-DERIVES scope from the repo's declarations and the
tree every single time (`cli._apply_scope` → `scope.derive_scope_logged`, plus a
second derivation in `cli._scope_provenance` for the stamp). Nothing in the build
path reads what a previous build stamped. So an exclusion that is not read back is
discarded on the next refresh with no error anywhere, which is this repo's most
frequently rediscovered defect shape.

`test_a_later_build_that_states_no_exclusion_still_honours_the_recorded_one` is the
assertion that matters. It fails against an implementation that accepts the argument,
applies it and stamps it but does not read it back — a build that looks correct at
every point except the second one.

@brief Operator-stated index exclusions: applied, stamped apart, replayed.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

pytestmark = pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="the exclusion tests build a real repo with the real doxygen binary",
)


## @brief Write a repo whose source splits into a kept tree and an excludable one.
## @param root Directory to create the repo in.
## @return Path to the repo's Doxyfile.
## @version 1
def _repo(root: Path) -> Path:
    """Two source trees and one markdown tree, so a single exclusion can be shown to
    remove one and leave the other — the shape the concrete case has (benchmark
    evidence under one directory, code everywhere else).

    @brief Create the two-tree fixture repo.
    @return The Doxyfile path.
    @version 1
    """
    (root / "src").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    (root / "src" / "keep.c").write_text(
        "/** @brief Kept. */\nvoid keep_me(void) {}\n", encoding="utf-8"
    )
    (root / "evidence" / "drop.c").write_text(
        "/** @brief Dropped. */\nvoid drop_me(void) {}\n", encoding="utf-8"
    )
    (root / "evidence" / "note.md").write_text("# evidence\n", encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nRECURSIVE = YES\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )
    return doxyfile


## @brief Build the fixture repo, optionally stating an exclusion.
## @param root Repo root.
## @param out Output database path.
## @param exclude Exclusion argv values, or None to state none at all.
## @return The built database path.
## @version 1
def _build(root: Path, out: Path, exclude: list[str] | None = None) -> Path:
    """`exclude=None` means the flag is ABSENT, which is the inherit case; an empty
    list means the flag was passed with no values, which is the clear case. The two
    must not collapse into one another, so the fixture keeps them distinct too.

    @brief Run the pipeline over the fixture repo.
    @return The output path.
    @version 1
    """
    argv = ["--output", str(out), "--repo-root", str(root)]
    if exclude is not None:
        argv += ["--exclude", *exclude]
    args = _build_argparser().parse_args(argv)
    ## `--exclude` SURVIVED the 22->6 collapse and `--doxyfile` did not, so this fixture
    ## keeps driving the real command line for the flag under test and states the Doxyfile on
    ## the dest. Reaching for `build_index` instead would move the argument under test off the
    ## command line, and the three states this file exists to pin (absent / empty / values)
    ## are a property of the PARSER's `nargs="*"`.
    args.doxyfile = str(_doxyfile_of(root))
    _run_pipeline(args)
    return out


## @brief The fixture repo's Doxyfile path.
## @param root Repo root.
## @return Path to the Doxyfile.
## @version 1
def _doxyfile_of(root: Path) -> Path:
    """@brief Name the fixture Doxyfile without rewriting it."""
    return root / "Doxyfile"


## @brief Function names present in a built index.
## @param db Database path.
## @return Set of memberdef names.
## @version 1
def _names(db: Path) -> set[str]:
    """@brief Read every indexed function name."""
    conn = sqlite3.connect(str(db))
    try:
        return {r[0] for r in conn.execute("SELECT name FROM memberdef")}
    finally:
        conn.close()


## @brief The `scope.*` build_meta section of a built index.
## @param db Database path.
## @return Mapping of unprefixed scope key to value.
## @version 1
def _scope_meta(db: Path) -> dict[str, str]:
    """@brief Read the stamped scope provenance."""
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'scope.%'").fetchall()
    finally:
        conn.close()
    return {key.split(".", 1)[1]: value for key, value in rows}


## @brief A stated exclusion removes its tree and leaves the rest indexed.
## @version 1
def test_a_stated_exclusion_removes_its_tree_and_keeps_the_rest(tmp_path: Path) -> None:
    """The negative half is the load-bearing one. An exclusion that removed
    EVERYTHING would satisfy "the evidence is gone" and be catastrophically wrong,
    and a build that indexes nothing is the outcome this repo calls the worst
    possible because it looks like an answer.

    @brief Exclusion is a narrowing, not an emptying.
    @version 1
    """
    root = tmp_path / "repo"
    _repo(root)
    db = _build(root, tmp_path / "clew.db", exclude=["evidence"])
    names = _names(db)
    assert "keep_me" in names, "an exclusion must not remove the tree it does not name"
    assert "drop_me" not in names, "the excluded tree is still indexed"


## @brief The operator's exclusion is stamped apart from the walker's excludes.
## @version 1
def test_an_operator_exclusion_is_stamped_apart_from_a_derived_exclude(tmp_path: Path) -> None:
    """A reader has to be able to tell "the operator excluded this" from "the walker
    pruned this", because the two invite opposite responses: a derived exclude is a
    fact about the tree and an operator exclude is a decision that can be revisited.
    Merging them into one `scope.excludes` list would make the decision unreadable.

    @brief Operator exclusions get their own build_meta key.
    @version 1
    """
    root = tmp_path / "repo"
    _repo(root)
    db = _build(root, tmp_path / "clew.db", exclude=["evidence"])
    meta = _scope_meta(db)
    assert meta.get("operator_excludes") == "evidence", meta
    assert "evidence" not in meta.get("excludes", ""), (
        "an operator exclusion must not be filed among the derived ones"
    )


## @brief A later build that states nothing still honours the recorded exclusion.
## @version 1
def test_a_later_build_that_states_no_exclusion_still_honours_the_recorded_one(
    tmp_path: Path,
) -> None:
    """THE ASSERTION THAT MATTERS. Scope is re-derived from scratch on every build, so
    an exclusion that is applied and stamped but never read back is silently dropped
    the next time anyone refreshes — and the refresh reports success, a healthy
    coverage ratio and a plausible file count while quietly re-indexing exactly what
    the operator removed.

    Both halves are checked on the second build: the files stay out AND the record
    stays in. Re-applying the exclusion without re-stamping it would pass the first
    half and lose the exclusion on the build after this one.

    @brief The exclusion survives a refresh that does not restate it.
    @version 1
    """
    root = tmp_path / "repo"
    _repo(root)
    out = tmp_path / "clew.db"
    _build(root, out, exclude=["evidence"])

    _build(root, out, exclude=None)

    names = _names(out)
    assert "keep_me" in names
    assert "drop_me" not in names, (
        "the recorded exclusion was discarded by a refresh that did not restate it"
    )
    assert _scope_meta(out).get("operator_excludes") == "evidence", (
        "the exclusion was re-applied but not re-recorded, so it dies on the next build"
    )


## @brief Passing the flag with no values clears a recorded exclusion.
## @version 1
def test_stating_an_empty_exclusion_clears_the_recorded_one(tmp_path: Path) -> None:
    """Persistence needs an exit. An absent flag means INHERIT and an empty flag means
    CLEAR; if those collapsed, an exclusion stated once could never be withdrawn
    except by deleting the database, and the index would be permanently narrowed by a
    decision nobody could see how to reverse.

    @brief An empty exclusion list is a withdrawal, not an inheritance.
    @version 1
    """
    root = tmp_path / "repo"
    _repo(root)
    out = tmp_path / "clew.db"
    _build(root, out, exclude=["evidence"])

    _build(root, out, exclude=[])

    assert "drop_me" in _names(out), "the exclusion was not cleared"
    assert "operator_excludes" not in _scope_meta(out), (
        "a cleared exclusion must leave no record claiming it is still in force"
    )


## @brief `status` surfaces both new records without any reader plumbing.
## @version 1
def test_status_reports_the_exclusion_and_the_stage_breakdown(tmp_path: Path) -> None:
    """Both records ride in existing namespaced sections — `scope.` and `refresh.` —
    which `db_status` already reads whole, so neither needed a new reader. That is the
    design working, and it is also exactly the kind of claim that is assumed rather
    than checked until a section reader is quietly narrowed to a key list.

    @brief The MCP status payload carries operator_excludes and the stage breakdown.
    @version 1
    """
    from clew.mcp_server import state as st

    root = tmp_path / "repo"
    _repo(root)
    registry = st.TargetRegistry(tmp_path / "state")
    target = registry.register(root)
    _build(root, Path(target.db_path), exclude=["evidence"])

    status = st.db_status(target)
    assert status["scope"]["operator_excludes"] == "evidence"
    assert "evidence" not in status["scope"].get("excludes", "")
    assert "=" in status["refresh"]["stages"], status["refresh"]


## @brief An exclusion outside the repository is refused, not silently mangled.
## @version 1
def test_an_exclusion_outside_the_repository_is_refused(tmp_path: Path) -> None:
    """The record is stored REPO-RELATIVE, so a path outside the repo has no honest
    stored form — and the nearest thing to one (its bare name) would replay as a
    DIFFERENT exclusion on the next build. It also cannot exclude anything, since
    nothing outside the repo is indexed. Refused rather than warned about: a warning
    on a successful build is indistinguishable from success.

    THE EXIT CODE IS ASSERTED, not merely the SystemExit. argparse exits 2 for an
    unrecognised flag, so a bare `raises(SystemExit)` passes before the feature
    exists at all — a green refusal test guarding nothing.

    @brief An out-of-repo exclusion fails the build.
    @version 1
    """
    root = tmp_path / "repo"
    _repo(root)
    with pytest.raises(SystemExit) as raised:
        _build(root, tmp_path / "clew.db", exclude=[str(tmp_path / "elsewhere")])
    assert raised.value.code == 1, "must be the pipeline's refusal, not argparse's"


## @brief Excluding the repository root is refused.
## @version 1
def test_excluding_the_repository_root_is_refused(tmp_path: Path) -> None:
    """`--exclude .` indexes nothing and reports success — a well-formed, empty,
    confident database. Same refusal for the same reason as the out-of-repo case.

    @brief Excluding everything fails the build.
    @version 1
    """
    root = tmp_path / "repo"
    _repo(root)
    with pytest.raises(SystemExit) as raised:
        _build(root, tmp_path / "clew.db", exclude=["."])
    assert raised.value.code == 1, "must be the pipeline's refusal, not argparse's"
