# SPDX-License-Identifier: MIT
"""Every index scope names its tier, and every index scope is contained.

gh#20. The tier a scope came from is the whole answer to "was this boundary
chosen": a DECLARED scope is a decision, the Doxyfile tier is the repo's
documentation scope standing in, and the whole-repo tier is what a repo gets for
saying nothing. A consumer seeing a narrow root list has opposite responses
available — trust it, or go and declare one — and `scope.source` is what it chooses
between, which is why the tier has to reach `build_meta` and not only the log.

The second half is the counterweight to a wide scope. A nested clone of another
repository must stay out, because mixing two codebases into one `search` result is
worse than not having it, and the resulting index is not merely wide but WRONG about
which repository a symbol lives in. Containment therefore runs at one choke point
for every tier, so the widest scope in the tool cannot reach doxygen by a path the
narrowest one does not.

@brief Tier reporting and nested-repo containment for the index scope.
@version 2
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest
from gitfixture import repo_with_submodules

from clew import scope as sc
from clew.external import external_roots

## A gate that covers only Python under `src/`, exactly the shape that makes gate
## scope the wrong index scope: the C fixture beside it is deliberately exempt from
## the mandate and is still worth reasoning about.
_GATE_ONLY_PYTHON = """\
    repos:
      - repo: https://example.invalid/doxygen-guard
        rev: v1
        hooks:
          - id: doxygen-guard
            files: ^src/.*\\.py$
    """


## @brief Build a repo whose gate covers Python only, with a C fixture beside it.
## @param root Repo root to populate.
## @return The repo root.
## @version 1
## @dg_internal
def _repo_with_exempt_fixture(root: Path) -> Path:
    """@brief Materialise a repo whose gate is narrower than its interesting code."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "fixtures").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")
    (root / "fixtures" / "sample.c").write_text("int f(void) { return 0; }\n", encoding="utf-8")
    (root / ".pre-commit-config.yaml").write_text(
        textwrap.dedent(_GATE_ONLY_PYTHON), encoding="utf-8"
    )
    return root


## @brief A gate-only repo derives no scope, and the fallback says what to declare.
## @version 1
def test_a_gate_only_repo_falls_back_and_names_the_fix(tmp_path: Path, caplog) -> None:
    """The gate exempts the C fixture on purpose, and the index must not inherit that
    exemption. Nothing about the INDEX is declared here, so nothing is derived — and
    the reason a consumer reads has to name the section that would change it, because
    a diagnosis an owner cannot act on is half a diagnosis.

    @brief A gate-only repo yields the whole repo with actionable advice.
    @version 2
    """
    root = _repo_with_exempt_fixture(tmp_path / "repo")

    with caplog.at_level(logging.INFO):
        derived = sc.derive_scope_logged(root)

    assert derived.source == sc.SOURCE_WHOLE_REPO
    assert derived.roots == (root.resolve(),), "the gate's `files:` pattern supplies no boundary"
    assert sc.INDEX_SCOPE_SECTION in derived.reason, (
        "the undeclared tier must name the declaration that would replace it, or the "
        "report tells an owner they have a problem and not how to fix it"
    )
    ## The WARNING itself is what matters, not its old wording. gh#333 changed the
    ## sentence because "falling back to the Doxyfile INPUT" became a checkable and
    ## wrong claim about what got indexed — but the LEVEL must stay WARNING, so a
    ## boundary nobody chose is never mistaken for one somebody did.
    assert "WHOLE repository" in caplog.text
    assert any(rec.levelname == "WARNING" for rec in caplog.records)


## @brief A declared index scope is the tier that yields roots.
## @version 2
def test_a_declared_index_scope_is_the_decision(tmp_path: Path) -> None:
    """The other half of the distinction. Without this, reporting the tier could be a
    constant that happens to read correctly on the case someone looked at.

    @brief A declared scope reports its own tier and its own roots.
    @version 2
    """
    root = _repo_with_exempt_fixture(tmp_path / "repo")
    (root / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  index_scope:\n    roots: ['src', 'fixtures']\n", encoding="utf-8"
    )

    derived = sc.derive_scope(root)

    assert derived.source == sc.SOURCE_DECLARED
    assert derived.is_derived() is True
    assert sorted(p.name for p in derived.roots) == ["fixtures", "src"], (
        "the declaration is what lets the index and the gate disagree — the exempt "
        "fixture is indexable without loosening the quality bar"
    )


## @brief The declared reason must name the file the declaration was read from.
## @version 1
def test_the_declared_reason_names_the_file_it_was_read_from(tmp_path: Path) -> None:
    """A declaration carried by the guard config's `x-` passthrough used to be
    reported as `index_scope declared in <root>/.clew.yaml` — a file that
    need not exist. A provenance string naming the wrong file is worse than none,
    because it is checkable and wrong (`discover_doxyfile`'s lesson).

    @brief The provenance names the real declaration file.
    @version 1
    """
    root = _repo_with_exempt_fixture(tmp_path / "repo")
    (root / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  index_scope:\n    roots: ['src']\n", encoding="utf-8"
    )

    reason = sc.derive_scope(root).reason

    assert ".doxygen-guard.yaml" in reason, "the passthrough's own file is where it was read"
    assert ".clew.yaml" not in reason, (
        "naming a file that does not exist sends the owner to edit nothing"
    )


## @brief A declared root INDEXES a nested foreign repository rather than cutting it out.
## @version 2
def test_a_declared_root_indexes_a_nested_repository(tmp_path: Path) -> None:
    """THE REVERSAL gh#333 MAKES, at the declared tier. This used to assert the
    opposite — that a nested clone under a declared root is excluded and warned
    about — on the argument that two codebases in one `search` result cannot be told
    apart. The premise was right and the remedy was backwards: entropic wraps
    llama.cpp, and a `chain_trace` that stops at the boundary answers "this call
    leaves the repo" when it could answer what the call does. They are told apart by
    being TAGGED (gh#335), which `external_roots` is the detection half of.

    ASSERTED AS AN ABSENCE FROM `excludes`, deliberately. A test that only checked
    the tag would pass against a scope that still excluded the tree, because a
    detector and an exclusion are independent — and then the tag would be a label on
    rows that do not exist.

    @brief A nested git repository under a declared root is indexed, not excluded.
    @version 2
    """
    root = _repo_with_exempt_fixture(tmp_path / "repo")
    ## A DECLARED submodule (a gitlink), not a bare `.git`: the last assertion below couples the
    ## scope half to the tag half, and since gh#352 those are two predicates — descent sees any
    ## separate git tree, the tag sees only what the parent recorded as a dependency.
    nested = root / "evidence" / "other_project"
    repo_with_submodules(root, "evidence/other_project")
    (nested / "src").mkdir(parents=True)
    (nested / "src" / "theirs.c").write_text("int theirs(void) { return 1; }\n", encoding="utf-8")
    (root / "evidence" / "notes.md").write_text("# ours\n", encoding="utf-8")
    (root / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  index_scope:\n    roots: ['src', 'evidence']\n", encoding="utf-8"
    )

    derived = sc.derive_scope(root)

    excluded = {p.resolve() for p in derived.excludes}
    assert nested.resolve() not in excluded, (
        "gh#333: a nested repository is indexed and tagged, never cut out of the scope"
    )
    assert (root / "evidence").resolve() in {p.resolve() for p in derived.roots}
    ## And it is DETECTABLE as somebody else's, which is what makes indexing it safe.
    assert "evidence/other_project" in external_roots(root)


## @brief An already-declared exclude must not be reported twice.
## @version 1
def test_an_already_excluded_nested_repository_is_not_re_reported(tmp_path: Path, caplog) -> None:
    """An owner who has already declared the exclusion has made the decision. A
    warning there would train them to ignore the warning that matters.

    @brief A declared exclude suppresses the nested-repository warning.
    @version 1
    """
    root = _repo_with_exempt_fixture(tmp_path / "repo")
    nested = root / "evidence" / "other_project"
    (nested / ".git").mkdir(parents=True)
    (root / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  index_scope:\n"
        "    roots: ['src', 'evidence']\n"
        "    excludes: ['evidence/other_project']\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        derived = sc.derive_scope(root)

    assert nested.resolve() in {p.resolve() for p in derived.excludes}
    assert not any("nested" in rec.message.lower() for rec in caplog.records), (
        "a decision already taken is not a finding"
    )


## @brief Build a repo that declares nothing at all, with a DECLARED submodule inside it.
## @param root Repo root to populate.
## @return The nested repository's directory.
## @version 2
## @dg_internal
def _undeclared_repo_with_nested_clone(root: Path) -> Path:
    """No pre-commit config and no clew declaration, which is what puts the build on the
    whole-repo path: the repo root itself becomes the one INPUT root, so the nested tree is inside
    it by construction rather than by a pattern folding it in.

    A REAL GITLINK, not a bare `.git` directory, since gh#352 half 2. The caller asserts both
    halves at once — the scope admits the tree AND the tag detects it — and after the split those
    are two different predicates: descent sees any separate git tree, while the tag sees only what
    the parent RECORDS as a dependency. A `.git`-only fixture would still satisfy the scope half
    and silently stop satisfying the tag half, so the coupled assertion has to be built on the
    stricter of the two. (The stray-clone case the old fixture actually described is now covered
    where it belongs, by `test_a_stray_developer_clone_the_parent_tracks_is_first_party`.)

    @brief Materialise an undeclared repo declaring a submodule inside it.
    @return The nested repository directory.
    @version 2
    """
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")
    repo_with_submodules(root, "evidence/other_project")
    nested = root / "evidence" / "other_project"
    (nested / "theirs.py").write_text("def theirs():\n    pass\n", encoding="utf-8")
    return nested


## @brief The whole-repo root INDEXES a nested foreign repository rather than cutting it out.
## @version 2
def test_the_whole_repo_scope_indexes_a_nested_repository(tmp_path: Path) -> None:
    """The same reversal at the tier that reaches FURTHEST — its single root is the
    repo itself, so it is the tier a foreign clone is most certain to sit inside, and
    it is what a repo lands on by saying nothing, which is the common case.

    Driven through `cli._apply_scope`, because that is where the scope becomes build
    arguments: a change made in `scope.py` alone could be undone by a CLI path that
    re-derives, and this is the surface doxygen actually receives.

    @brief A nested git repository under the whole-repo root is indexed, not excluded.
    @version 2
    """
    import argparse

    from clew import cli

    root = tmp_path / "repo"
    nested = _undeclared_repo_with_nested_clone(root)
    args = argparse.Namespace(
        scope=sc.SCOPE_FROM_GUARD,
        guard_config=None,
        extra_input=None,
        extra_exclude=None,
    )

    cli._apply_scope(args, root)

    assert args.replace_input is True
    assert args.extra_input == [str(root.resolve())], "the whole-repo root is the INPUT"
    assert str(nested.resolve()) not in (args.extra_exclude or []), (
        "gh#333: a nested repository inside the whole-repo root is indexed and tagged"
    )
    assert "evidence/other_project" in external_roots(root)


## @brief A nested repository's OWN gitignore still keeps its build output out.
## @version 1
def test_a_nested_repository_s_own_gitignore_is_honoured(tmp_path: Path) -> None:
    """THE CONTROL THAT STOPS gh#333 RE-ADMITTING BUILD DETRITUS. `git ls-files
    --ignored` is opaque through a submodule boundary, so the parent's sweep reports
    nothing inside a nested tree — and a nested tree is now INDEXED, which is exactly
    when its `build/` starts to matter. entropic's `examples/*/build/_deps/**` is
    CMake FetchContent output (a vendored JSON library, an HTTP library, a fuzzer
    test suite) and must stay out.

    A REAL `git init`, not a bare `.git` directory, because the thing under test is
    what `git ls-files` reports and a fake tree makes it report nothing — which would
    pass this test for the wrong reason.

    @brief A submodule's own .gitignore is collected and honoured.
    @version 1
    """
    import shutil

    from gitfixture import git_run

    root = tmp_path / "repo"
    nested = _undeclared_repo_with_nested_clone(root)
    ## Through `gitfixture.git_run`, not a bare `subprocess.run`, and the difference is
    ## load-bearing: it scrubs the `GIT_DIR` a pre-commit hook inherits. With that variable
    ## set, `git init <path>` initialises the repository it NAMES instead of the one it is
    ## given, so `nested/.git` is never created and this test dies on a missing directory —
    ## which is exactly how it failed under `git commit` while passing under
    ## `pre-commit run --all-files`.
    git_run(tmp_path, "init", "-q", str(root))
    ## `_undeclared_repo_with_nested_clone` makes a bare `.git` DIRECTORY; replace it
    ## with a real repository so `git ls-files` inside it actually answers.
    shutil.rmtree(nested / ".git")
    git_run(tmp_path, "init", "-q", str(nested))
    (nested / ".gitignore").write_text("build/\n", encoding="utf-8")
    (nested / "build" / "_deps").mkdir(parents=True)
    (nested / "build" / "_deps" / "vendored.c").write_text("int v(void){return 0;}\n", "utf-8")

    excludes = {p.resolve() for p in sc.whole_repo_scope(root).excludes}

    assert (nested / "build").resolve() in excludes, (
        "the nested repo's own .gitignore is invisible to the parent's git ls-files, "
        "so it has to be asked for separately or vendored build output walks back in"
    )
    assert nested.resolve() not in excludes, "the nested repo itself is still indexed"


## @brief Every tier now names roots, so no scope can be a rootless pass-through.
## @version 2
def test_no_tier_hands_back_a_rootless_scope(tmp_path: Path) -> None:
    """gh#333 DELETED THE ONE SHAPE THAT COULD BE ROOTLESS. The Doxyfile fallback
    carried a reason and nothing else, which meant the indexed tree was decided by a
    file this module never reads — and that indirection is exactly how a repo ended
    up indexing its published-API subset without anything saying so.

    Asserted as a property of EVERY undeclared repo rather than of one tier, because
    the failure this guards against is a future tier reintroducing the shape: a scope
    with no roots silently hands the decision back to doxygen.

    @brief An undeclared repo always resolves to a scope with real roots.
    @version 2
    """
    root = tmp_path / "repo"
    nested = root / "src" / "other_project"
    (nested / ".git").mkdir(parents=True)

    derived = sc.derive_scope(root)

    assert derived.source == sc.SOURCE_WHOLE_REPO
    assert derived.is_derived() is False, "nothing was DECLARED, which is a separate question"
    assert derived.roots == (root.resolve(),), "a rootless scope hands the decision to doxygen"
    assert nested.resolve() not in {p.resolve() for p in derived.excludes}


## @brief The tier that actually ran must reach build_meta, where a consumer reads it.
## @version 2
def test_the_winning_tier_reaches_the_stamped_provenance(tmp_path: Path) -> None:
    """`DerivedScope` living in the build's memory is what gh#20's first half was
    already about: the pipeline computed the scope decision and logged it, and the log
    is gone by the time anyone queries. `scope.*` in `build_meta` is the surface
    `status` reads, so the tier has to be stamped there or it does not exist.

    THE `--scope doxyfile` CASE IS THE ONE THAT CATCHES A LIE, and gh#333 moved which
    case that is. The tier used to depend on whether a Doxyfile had been RESOLVED
    hundreds of lines away, so the stamp had to read `args.index_whole_repo` or it
    would write `doxyfile` on a build that indexed everything. `derive_scope` no
    longer consults the Doxyfile, so the only remaining way for the stamp and the
    build to disagree is the explicit `--scope doxyfile` opt-out — under which
    `_apply_scope` folds nothing, and stamping the resolved whole-repo tier would
    describe a scope the build did not use.

    @brief The scope provenance stamp records the tier the build took.
    @version 3
    """
    import argparse

    from clew.cli import _scope_provenance

    root = _repo_with_exempt_fixture(tmp_path / "undeclared")
    declared_root = _repo_with_exempt_fixture(tmp_path / "declared")
    (declared_root / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  index_scope:\n    roots: ['src']\n", encoding="utf-8"
    )
    resolved = argparse.Namespace(scope=sc.SCOPE_FROM_GUARD, guard_config=None)
    narrowed = argparse.Namespace(scope=sc.SCOPE_DOXYFILE, guard_config=None)

    assert _scope_provenance(declared_root, resolved)["source"] == sc.SOURCE_DECLARED
    assert _scope_provenance(root, resolved)["source"] == sc.SOURCE_WHOLE_REPO, (
        "a build that indexed the whole repository must not be stamped as a Doxyfile scope"
    )
    assert _scope_provenance(root, narrowed)["source"] == sc.SOURCE_DOXYFILE, (
        "the explicit opt-out really does index the Doxyfile's INPUT, and must say so"
    )
    assert "inherited" not in _scope_provenance(root, resolved), (
        "nothing is inherited from the gate any more, and a stamped key nothing sets "
        "is a fact a consumer would read as one"
    )


## @brief scope_provenance reuses apply_scope's own derivation instead of re-walking.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_scope_provenance_reuses_apply_scopes_derivation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIELD-REPORTED cost, from a real repo with 1.2GB under one nested tree: `derive_scope`
    ran TWICE per build — once inside `_apply_scope` to fold the boundary into the build
    args, once again inside `_scope_provenance` to record it — each a full
    `nested_repo_roots`/`_gitignored_paths` walk of the whole repository. `_scope_provenance`
    even had its OWN timing segment specifically because this was already known to be
    expensive; nothing before this fix skipped the second walk.

    Verified by MONKEYPATCHING `derive_scope` (the function `_scope_provenance` falls back
    to) to raise if called at all — `_apply_scope` calls `derive_scope_logged`, a different
    name, so this isolates exactly the redundant call without touching the real derivation
    machinery underneath either of them.

    @brief _apply_scope's own DerivedScope is reused, not re-derived, by _scope_provenance.
    @version 1
    """
    import argparse

    from clew import cli as clew_cli
    from clew.cli import _apply_scope, _scope_provenance

    root = _repo_with_exempt_fixture(tmp_path / "reused")
    args = argparse.Namespace(
        scope=sc.SCOPE_FROM_GUARD,
        guard_config=None,
        doxyfile=None,
        exclude=None,
        extra_input=None,
        extra_exclude=None,
    )
    _apply_scope(args, root)
    assert args.scope_result is not None, "premise: _apply_scope must stash what it derived"

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("derive_scope was called again — the cached scope was not reused")

    monkeypatch.setattr(clew_cli, "derive_scope", _boom)
    provenance = _scope_provenance(root, args)

    assert provenance["source"] == sc.SOURCE_WHOLE_REPO


## @brief scope_provenance's own fallback re-derivation also honours a stated scope.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_scope_provenance_fallback_also_reads_a_stated_scope(tmp_path: Path) -> None:
    """THE LATENT MISMATCH THIS FIX ALSO CLOSES, found while tracing the redundant walk:
    `_scope_provenance`'s own re-derivation call never passed `stated` — a tier-1 caller's
    own `index_scope` (e.g. a vendored sub-index's `roots` override) — so a caller reaching
    this function WITHOUT going through `_apply_scope` first (this test) could get back
    provenance describing a DIFFERENT boundary than the one a caller who DID pass `stated`
    actually built. Exercises the fallback path specifically — no `scope_result` cached.

    @brief The fallback re-derivation path also honours args.index_scope when present.
    @version 1
    """
    import argparse

    from clew.cli import _scope_provenance

    root = _repo_with_exempt_fixture(tmp_path / "stated_fallback")
    args = argparse.Namespace(
        scope=sc.SCOPE_FROM_GUARD,
        guard_config=None,
        doxyfile=None,
        exclude=None,
        index_scope={"roots": ["src"]},
    )

    provenance = _scope_provenance(root, args)

    assert provenance["source"] == sc.SOURCE_DECLARED, (
        f"a stated index_scope must be honoured by the fallback path too, got: {provenance}"
    )
