# SPDX-License-Identifier: MIT
"""Tests for gh#3 — `--extra-input` silently defeated by the Doxyfile's FILE_PATTERNS.

`--extra-input` adds a path to the indexed set. Nothing in this codebase sets or
clears `FILE_PATTERNS`, so when a target ships its own Doxyfile that file's
patterns apply verbatim to every `INPUT +=` line we append. If they match none of
the files under the added root, doxygen reads them and discards them, and the
build reports success with the requested files simply absent — which a consumer
discovers later as "that function is not in the database", reading as a parser
gap rather than a configuration one.

Every fixture is a SYNTHETIC repo in tmp_path. No real repo's paths, names or
patterns appear: the guard reads whatever a Doxyfile declares, so baking a real
target's shape in would defeat the test.

THE DISCRIMINATOR UNDER TEST is "the root holds files, and none of them match",
not "the root contributed nothing". An empty directory and an absent root also
contribute nothing, and the patterns are not why — a guard that fires on those
would be the "fires on the benign case" mistake this project has already shipped
once.

@brief Tests for the --extra-input / FILE_PATTERNS mismatch guard.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew import treescan as ts
from clew.doxygen import declared_file_patterns, effective_file_patterns
from clew.scope import SCOPE_DOXYFILE


## @brief Create a file (and its parent directories) with some content.
## @version 1
def _write(path: Path, content: str = "int x;\n") -> None:
    """@brief Write a fixture file, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


## @brief Write a Doxyfile declaring the given body lines.
## @param root Directory the Doxyfile is written into.
## @param body Doxyfile text (e.g. "FILE_PATTERNS = *.h").
## @return Path to the written Doxyfile.
## @version 1
def _doxyfile(root: Path, body: str) -> Path:
    """@brief Materialise a synthetic Doxyfile."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "Doxyfile"
    path.write_text(f"PROJECT_NAME = fixture\nINPUT =\n{body}\n", encoding="utf-8")
    return path


## @brief Names of the roots a check flagged, relative to work_dir.
## @return Sorted basenames of the flagged roots.
## @version 1
def _flagged(roots: list[Path]) -> list[str]:
    """@brief Basenames of flagged roots, for stable assertions."""
    return sorted(p.name for p in roots)


## @brief FILE_PATTERNS is FORCED; the declaration is a reportable fact, not a policy.
## @version 2
def test_file_patterns_are_forced_and_the_declaration_is_only_reported(tmp_path: Path) -> None:
    """THIS TEST'S PREMISE WAS WITHDRAWN BY DECISION (gh#340), so it asserts the opposite of
    what it used to. It used to require that a DECLARED `FILE_PATTERNS` win — and that was the
    defect: scope has three independent keys, `INPUT` is replaced and `EXCLUDE` cleared, so a
    declared extension list was the last one able to veto a tree scope had already admitted.
    Measured on entropic, which declares `*.h *.hpp *.cpp *.md` while the submodule it vendors
    is `.c`/`.cu`/`.m`: the tree was admitted and then silently dropped, exit 0.

    So the build now forces doxygen's own default set, and BOTH halves are asserted — the
    declaration is ignored for the build AND still readable as a fact, because "why does the
    index hold more than the docs do" is a fair question with a real answer.

    @brief The forced set governs; the declaration is reportable.
    @version 2
    """
    declared = _doxyfile(tmp_path / "declared", "FILE_PATTERNS = *.h *.hpp")

    effective = effective_file_patterns(declared)
    assert effective != ["*.h", "*.hpp"], "a declaration must no longer veto the indexed tree"
    assert "*.c" in effective, "the extension entropic's own census lost must be included"
    assert declared_file_patterns(declared) == ["*.h", "*.hpp"], "still readable as a FACT"

    silent = _doxyfile(tmp_path / "silent", "# no FILE_PATTERNS here")
    assert effective_file_patterns(silent) == effective, "declared or not, the build is the same"
    ## Empty, NOT the defaults, when nothing is declared: "not recorded" and "recorded as
    ## doxygen's default" are different claims and only the caller knows which it needs.
    assert declared_file_patterns(silent) == []
    # Not asserted exhaustively — doxygen's default list is doxygen's business and
    # grows between releases. What matters is that it is the broad default set and
    # not an empty list, because empty would flag every root as matching nothing.
    assert len(effective) > 10


## @brief A root whose files match nothing is flagged.
## @version 1
def test_a_root_matching_no_pattern_is_flagged(tmp_path: Path) -> None:
    """THE GUARD'S QUESTION NARROWED WITH gh#340 and it still has one. It used to be "does the
    target's declared pattern list exclude this root" — impossible now that patterns are
    forced. It is now "does this root contain ANY file doxygen can parse at all", which is
    still reachable and still worth refusing: an `--extra-input` root contributing zero files
    is a flag the operator should be told to drop.

    So the fixture uses `.txt`, which is outside doxygen's 47-extension default. A `.c` root
    would now MATCH — which is the whole point of gh#340 — and a fixture kept on `.c` would
    have tested nothing while looking unchanged.
    """
    doxyfile = _doxyfile(tmp_path, "# patterns are forced; this declaration is ignored")
    _write(tmp_path / "library" / "notes.txt")
    _write(tmp_path / "library" / "README.rst")

    flagged = ts.roots_matching_no_file_pattern(doxyfile, tmp_path, ["library"], None, tmp_path)
    assert _flagged(flagged) == ["library"]


## @brief A root that does contribute files is left alone.
## @version 1
def test_a_root_that_contributes_files_is_not_flagged(tmp_path: Path) -> None:
    """The ordinary case must stay silent. One matching file under the root is
    enough — doxygen will read it, so the flag did its job."""
    doxyfile = _doxyfile(tmp_path, "FILE_PATTERNS = *.h")
    _write(tmp_path / "include" / "aes.h")
    _write(tmp_path / "include" / "notes.txt")

    flagged = ts.roots_matching_no_file_pattern(doxyfile, tmp_path, ["include"], None, tmp_path)
    assert flagged == []


## @brief An empty directory is not a pattern problem and must not fire.
## @version 1
def test_a_legitimately_empty_root_is_not_flagged(tmp_path: Path) -> None:
    """A guard that fires on the benign case is worse than no guard. An empty
    directory contributes zero files whatever the patterns say, so blaming
    FILE_PATTERNS for it would be a false alarm — and would train the reader to
    ignore the message in the case that matters.

    An ABSENT root is the same argument: nothing was excluded, there was nothing
    there. (Whether an absent --extra-input root deserves its own complaint is a
    separate question this guard deliberately does not answer.)"""
    doxyfile = _doxyfile(tmp_path, "FILE_PATTERNS = *.h")
    (tmp_path / "empty").mkdir()

    assert ts.roots_matching_no_file_pattern(doxyfile, tmp_path, ["empty"], None, tmp_path) == []
    assert ts.roots_matching_no_file_pattern(doxyfile, tmp_path, ["absent"], None, tmp_path) == []


## @brief A file excluded by --extra-exclude does not count as a contribution.
## @version 1
def test_an_excluded_file_does_not_count_as_a_match(tmp_path: Path) -> None:
    """The enumeration must honour the same EXCLUDE the build honours, or the
    guard would be satisfied by a file doxygen never reads — the exact
    "it looks like it worked" failure it exists to catch."""
    doxyfile = _doxyfile(tmp_path, "# patterns are forced; this declaration is ignored")
    _write(tmp_path / "gen" / "notes.txt")
    _write(tmp_path / "gen" / "vendor" / "api.h")

    # Without the exclude the vendored header matches, so the root is fine.
    assert ts.roots_matching_no_file_pattern(doxyfile, tmp_path, ["gen"], None, tmp_path) == []
    ## Excluding it leaves only an UNPARSEABLE file. Post-gh#340 the leftover has to be a
    ## `.txt` rather than a `.c`: with patterns forced, a `.c` matches and the root would be
    ## fine, so this test would have passed while exercising nothing.
    flagged = ts.roots_matching_no_file_pattern(
        doxyfile, tmp_path, ["gen"], ["gen/vendor"], tmp_path
    )
    assert _flagged(flagged) == ["gen"]


## @brief Matching is case-insensitive, which fails toward silence.
## @version 1
def test_pattern_matching_is_case_insensitive(tmp_path: Path) -> None:
    """`*.h` against `AES.H`. The two possible errors here are not symmetric: a
    false alarm refuses a build that would have worked, a missed case leaves the
    pre-existing silent behaviour. Case-insensitive matching admits MORE files and
    therefore flags FEWER roots, which is the safe direction for a hard failure."""
    doxyfile = _doxyfile(tmp_path, "FILE_PATTERNS = *.h")
    _write(tmp_path / "include" / "AES.H")

    assert ts.roots_matching_no_file_pattern(doxyfile, tmp_path, ["include"], None, tmp_path) == []


## @brief No --extra-input at all means nothing to check.
## @version 1
def test_no_extra_input_is_never_flagged(tmp_path: Path) -> None:
    """The guard is scoped to the flag it protects. A build with no --extra-input
    has no root whose contribution was requested, so there is nothing to blame."""
    doxyfile = _doxyfile(tmp_path, "FILE_PATTERNS = *.h")
    _write(tmp_path / "library" / "aes.c")

    assert ts.roots_matching_no_file_pattern(doxyfile, tmp_path, None, None, tmp_path) == []
    assert ts.roots_matching_no_file_pattern(doxyfile, tmp_path, [], None, tmp_path) == []


## @brief The CLI refusal names the root AND the patterns that excluded it.
## @version 1
def test_the_refusal_names_the_root_and_the_patterns(tmp_path: Path, caplog) -> None:
    """ "Done means" for gh#3: an --extra-input root that contributes nothing is an
    error naming the pattern that excluded it, not a silent no-op. Both halves are
    load-bearing — the root tells the user which flag to drop, the patterns tell
    them what to widen, and either alone leaves them guessing."""
    from clew.cli import _verify_extra_input_is_read

    doxyfile = _doxyfile(tmp_path, "# patterns are forced; this declaration is ignored")
    _write(tmp_path / "library" / "notes.txt")

    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as excinfo:
        _verify_extra_input_is_read(doxyfile, ["library"], None, tmp_path)
    assert excinfo.value.code == 1

    message = caplog.text
    assert "library" in message, "the message must name the root the user passed"
    ## The patterns it names are now the FORCED set, so `*.h` still appears — but for a
    ## different reason than before gh#340, and the assertion is kept because the message's
    ## job is unchanged: tell the operator what doxygen will actually match.
    assert "*.h" in message, "the message must name the patterns that excluded it"
    assert "FILE_PATTERNS" in message, "the message must name the key to widen"


## @brief A passing check returns without raising.
## @version 1
def test_the_check_is_silent_when_the_root_contributes(tmp_path: Path) -> None:
    """The guard must be invisible on every build that already worked."""
    from clew.cli import _verify_extra_input_is_read

    doxyfile = _doxyfile(tmp_path, "FILE_PATTERNS = *.h")
    _write(tmp_path / "include" / "aes.h")

    _verify_extra_input_is_read(doxyfile, ["include"], None, tmp_path)


## @brief The guard is actually WIRED into the pipeline, not merely correct.
## @version 1
def test_the_pipeline_refuses_before_running_doxygen(tmp_path: Path, caplog) -> None:
    """A check that is right in isolation and never called changes nothing a user
    sees — and an unwired guard is indistinguishable from the silent no-op it
    replaced, which is precisely gh#3. This drives the real entry point.

    It also pins the ORDER: the refusal must land before doxygen is spawned, so a
    doxygen binary is not a prerequisite for the guard to fire. `_run_pipeline`
    would need one to get any further, so reaching SystemExit(1) with the gh#3
    message is itself the evidence that nothing was built."""
    import argparse

    from clew import cli

    ## `.txt`, post-gh#340, and this fixture is why the ORDER assertion below is not decorative.
    ## With a `.c` root the forced patterns MATCH, the guard does not fire, `_run_pipeline` walks
    ## on past it — and the test then failed with `AttributeError: 'Namespace' object has no
    ## attribute 'no_index_cache'`, from this hand-built Namespace, several stages downstream.
    ## That error looked like an unrelated fixture defect and was in fact the guard not firing.
    doxyfile = _doxyfile(tmp_path, "# patterns are forced; this declaration is ignored")
    _write(tmp_path / "library" / "notes.txt")

    args = argparse.Namespace(
        doxyfile=str(doxyfile),
        output=str(tmp_path / "out" / "clew.db"),
        repo_root=str(tmp_path),
        ## From `scope`, the owning module. The 22->6 collapse deleted the `--scope` flag
        ## whose `choices=` was the only reason this constant was imported into `cli`.
        scope=SCOPE_DOXYFILE,
        guard_config=None,
        extra_input=["library"],
        extra_exclude=None,
    )
    with caplog.at_level("ERROR"), pytest.raises(SystemExit) as excinfo:
        cli._run_pipeline(args)
    assert excinfo.value.code == 1
    assert "contributes NOTHING" in caplog.text
    assert "*.h" in caplog.text


## @brief A derived scope root is never judged by this guard.
## @version 1
def test_scope_derived_roots_are_not_subject_to_the_guard(tmp_path: Path) -> None:
    """`_apply_scope` PREPENDS the derived scope roots — and on the whole-repo
    fallback the repo root itself — into the same `args.extra_input` list the user's
    entries live in. Judging the mutated list would refuse builds over roots the
    user never named, so the guard must run against the user's own entries only.

    Asserted at the boundary that makes it true: after `_apply_scope` has injected a
    root that matches nothing, the check still passes when the USER named nothing."""
    import argparse

    from clew import cli

    doxyfile = _doxyfile(tmp_path, "FILE_PATTERNS = *.h")
    _write(tmp_path / "library" / "aes.c")

    args = argparse.Namespace(
        doxyfile=str(doxyfile),
        repo_root=str(tmp_path),
        ## from-guard, not doxyfile: gh#333 made this the default and removed the
        ## `index_whole_repo` back door that used to reach the same scope from the
        ## narrow setting — two paths to one scope being two things that can disagree.
        scope=cli.SCOPE_FROM_GUARD,
        guard_config=None,
        extra_input=None,
        extra_exclude=None,
    )
    cli._apply_scope(args, tmp_path)
    assert args.extra_input == [str(tmp_path)], "the resolved scope injects the repo root"
    # The injected root holds only .c files behind a *.h pattern, yet must not refuse.
    cli._verify_extra_input_is_read(doxyfile, None, None, tmp_path)


## @brief The guard runs BEFORE _apply_scope, so derived roots are never judged.
## @version 1
def test_the_guard_runs_before_the_scope_is_folded_in(tmp_path: Path, monkeypatch) -> None:
    """The ORDERING is the mechanism, and it is invisible to any test that calls the
    check directly — swapping the two lines in `_run_pipeline` leaves every other
    test green while turning a working build into a refusal. So this drives
    `_run_pipeline` on the shape that distinguishes them: a repo whose DERIVED scope
    root holds only `.c` files behind a `FILE_PATTERNS = *.h` Doxyfile, with the user
    naming no --extra-input at all.

    Correct order → nothing to judge, the build proceeds. Reversed → the derived root
    is mistaken for a user request and the build is refused over a flag nobody passed.

    `_build_stages` is stubbed to a sentinel because the assertion is about which of
    the two outcomes the resolution prefix reaches, not about doxygen: reaching the
    sentinel IS the evidence the guard let the build through."""
    import argparse

    from clew import cli

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: https://example.invalid/doxygen-guard\n"
        "    rev: v1\n"
        "    hooks:\n"
        "      - id: doxygen-guard\n"
        "        files: ^src/.*\\.(c|h)$\n",
        encoding="utf-8",
    )
    (repo / ".clew.yaml").write_text("index_scope:\n  roots: [src]\n", encoding="utf-8")
    _write(repo / "src" / "only_impl.c")
    doxyfile = _doxyfile(repo, "FILE_PATTERNS = *.h")

    class _Reached(Exception):
        """@brief Sentinel proving the build got past the guard."""

    ## @brief Stand in for the build stages.
    ## @version 1
    def _sentinel(*_a, **_k) -> None:
        """@brief Raise the sentinel instead of building."""
        raise _Reached

    monkeypatch.setattr(cli, "_build_stages", _sentinel)

    args = argparse.Namespace(
        doxyfile=str(doxyfile),
        output=str(tmp_path / "out" / "clew.db"),
        repo_root=str(repo),
        scope=cli.SCOPE_FROM_GUARD,
        guard_config=None,
        extra_input=None,
        extra_exclude=None,
        rebuild=True,
        no_index_cache=True,
    )
    with pytest.raises(_Reached):
        cli._run_pipeline(args)
    assert args.extra_input, "the derived scope must have been folded in after the guard"
