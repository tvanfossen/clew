# SPDX-License-Identifier: MIT
"""Tests for declaration-driven index scope derivation (`clew.scope`).

Every fixture here is a SYNTHETIC repo built in tmp_path. No real repo's paths,
names or patterns appear — the point of the module under test is that it reads
whatever a repo declares, so baking a real repo's shape into the tests would
defeat it.

@brief Tests for scope derivation from a repo's pre-commit declaration.
@version 1
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from clew import precommit as pc
from clew import scope as sc


## @brief Create a file (and its parent directories) with some content.
## @version 1
def _write(path: Path, content: str = "int x;\n") -> None:
    """@brief Write a fixture file, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


## @brief Build a synthetic repo with a doxygen-guard hook declaration.
## @param root Repo root to populate.
## @param config Full `.pre-commit-config.yaml` text.
## @version 1
def _repo(root: Path, config: str) -> Path:
    """@brief Materialise a synthetic repo carrying a pre-commit config."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".pre-commit-config.yaml").write_text(textwrap.dedent(config), encoding="utf-8")
    return root


## @brief Parse the collapsed six-argument build CLI and state the folded dests.
## @param output The --output path.
## @param folded Dest names and values the removed flags used to write.
## @return The parsed namespace, carrying the stated values.
## @version 1
def _args(output: Path, **folded: object):
    """THE FOLD'S LOAD-BEARING PROPERTY, ASSERTED RATHER THAN ASSUMED. The build CLI went
    from 22 arguments to 6; every dest the removed flags wrote to SURVIVES with its declared
    default, because `build_index` sources its defaults by parsing and `apply_options` lands
    a stated value on one of those dests. `hasattr` is checked here, not merely relied on, so
    dropping a dest from `_FOLDED_BUILD_DEFAULTS` fails these tests instead of silently
    creating a namespace attribute that no parser default ever supplied.

    @brief Build a parsed namespace with folded dests stated.
    @return The namespace.
    @version 1
    """
    from clew.cli import _build_argparser

    parsed = _build_argparser().parse_args(["--output", str(output)])
    for name, value in folded.items():
        assert hasattr(parsed, name), (
            f"{name!r} is not a surviving build dest — the 22->6 collapse keeps every dest "
            "with its declared default, and this assertion is what pins that"
        )
        setattr(parsed, name, value)
    return parsed


## @brief Roots reported by a derivation, as repo-relative POSIX strings.
## @return Sorted repo-relative paths of the derived INPUT roots.
## @version 1
def _rel_roots(derived: sc.DerivedScope, root: Path) -> list[str]:
    """@brief Repo-relative view of the derived INPUT roots."""
    return sorted(p.relative_to(root.resolve()).as_posix() for p in derived.roots)


## @brief Repo-relative view of the derived EXCLUDE paths.
## @return Sorted repo-relative paths of the derived EXCLUDEs.
## @version 1
def _rel_excludes(derived: sc.DerivedScope, root: Path) -> list[str]:
    """@brief Repo-relative view of the derived EXCLUDE paths."""
    return sorted(p.relative_to(root.resolve()).as_posix() for p in derived.excludes)


_SIMPLE_CONFIG = """\
    repos:
      - repo: https://example.invalid/doxygen-guard
        rev: v1
        hooks:
          - id: doxygen-guard
            files: ^(src|lib)/.*\\.(c|h)$
    """


## @brief The gate's `files:` pattern must NOT supply index roots.
## @version 1
def test_a_gate_pattern_alone_derives_no_index_scope(tmp_path: Path) -> None:
    """THE POINT OF THE THREE-TIER CHAIN. A `files:` regex answers what must be
    DOCUMENTED. Standing in for the index decision it narrowed the index to the
    quality bar — and, sitting above the whole-repo tier, it shadowed the fallback
    that would have covered the rest.

    So a repo whose only declaration is the gate derives NOTHING, and the resolution
    drops to the whole repository (gh#333 removed the Doxyfile tier in between). The
    `.c` file the gate exempts is the measurable consequence: it is out of the
    mandate and squarely inside the repo, so it must be inside the scope.

    `is_derived()` stays FALSE, and that is not a contradiction with the whole-repo
    tier having roots: it asks whether the repo DECLARED a boundary, which is what
    the callers gating on it (`propose`, `init`) actually want to know.

    @brief A doxygen-guard hook contributes no index roots.
    @version 2
    """
    root = _repo(tmp_path / "repo", _SIMPLE_CONFIG)
    _write(root / "src" / "a.c")
    _write(root / "vendor" / "huge" / "d.c")

    derived = sc.derive_scope(root)

    assert derived.source == sc.SOURCE_WHOLE_REPO
    assert not derived.is_derived(), "the gate is not a declaration"
    assert derived.roots == (root.resolve(),), "the gate's boundary is not an index boundary"


## @brief No declaration at all yields the whole repo, and says why.
## @version 3
def test_no_declaration_yields_the_whole_repo(tmp_path: Path) -> None:
    """Fail safe and loud: the tier is explicit in both the source and the reason,
    never a silent guess, and the reason names where a declaration was looked for so
    "declares nothing" is distinguishable from "we looked in the wrong place".

    THE REASON MUST STILL CARRY THE SEARCH (gh#333). Folding the Doxyfile tier away
    deleted the function that phrased that clause, and the clause is gh#16's whole
    substance — without it a repo whose config we failed to FIND and a repo that
    declares nothing produce the same sentence.

    @brief An undeclared repo takes the whole-repo tier with a reason naming the search.
    @version 3
    """
    root = tmp_path / "repo"
    _write(root / "src" / "a.c")

    derived = sc.derive_scope(root)

    assert derived.source == sc.SOURCE_WHOLE_REPO
    assert not derived.is_derived()
    assert derived.roots == (root.resolve(),)
    assert sc.INDEX_SCOPE_SECTION in derived.reason
    assert pc.GUARD_CONFIG_NAME in derived.reason


## @brief A pre-commit config with other hooks but no doxygen-guard reads as no hook.
## @version 3
def test_other_hook_ids_are_ignored(tmp_path: Path) -> None:
    """The hook is matched by ID, never by repo URL or position. A config full of
    other hooks — including ones with their own `files:` patterns — declares no
    doxygen mandate.

    Asserted through `discover_guard_config`, the live consumer of the hook
    lookup. The decoy hook carries its OWN `--config` arg naming a file that
    EXISTS, which is what gives this test teeth: matching the first hook by
    position instead of by id would read that argument and report another tool's
    config as this repo's guard config. `tools/` is deliberately not one of the
    conventional guard-config directories, so nothing else can find it either.

    @brief The gate declaration is located by hook id alone.
    @version 3
    """
    root = _repo(
        tmp_path / "repo",
        """\
        repos:
          - repo: https://example.invalid/other
            rev: v1
            hooks:
              - id: some-other-linter
                files: ^src/.*\\.c$
                args: ["--config", "tools/other-linter.yaml"]
        """,
    )
    _write(root / "src" / "a.c")
    _write(root / "tools" / "other-linter.yaml", "other-linter: {}\n")

    location = pc.discover_guard_config(root)

    assert location.path is None, "another hook's --config is not this repo's guard config"
    assert location.source == pc.GUARD_SOURCE_NONE


## @brief The hook id is matched even for a `repo: local` declaration.
## @version 3
def test_local_repo_hook_is_found(tmp_path: Path) -> None:
    """Adopting repos run doxygen-guard either from its upstream URL or as a
    `repo: local` system hook — reading the declaration must not care which.

    Asserted through `discover_guard_config`, the live consumer of the hook
    lookup. The declared config sits in `tools/`, which the conventional finder
    does not search, so it is reachable ONLY by locating the `repo: local` hook
    by its id — a fallback cannot answer for the mechanism under test.

    @brief A `repo: local` doxygen-guard hook is found by id.
    @version 3
    """
    root = _repo(
        tmp_path / "repo",
        """\
        repos:
          - repo: local
            hooks:
              - id: doxygen-guard
                entry: doxygen-guard validate
                language: system
                files: ^core/.*\\.c$
                args: ["validate", "--config", "tools/guard.yaml"]
        """,
    )
    _write(root / "core" / "a.c")
    _write(root / "tools" / "guard.yaml", "validate: {}\n")

    location = pc.discover_guard_config(root)

    assert location.path == (root / "tools" / "guard.yaml").resolve()
    assert location.source == pc.GUARD_SOURCE_HOOK_ARGS


## @brief Dot-directories are excluded from the whole-repo scope, not indexed.
## @version 1
def test_dot_directories_are_excluded_from_the_whole_repo_scope(tmp_path: Path) -> None:
    """Virtualenvs and tool caches live in dot-directories, and the whole-repo root
    is handed to doxygen unwalked — so the rule that prunes them has to travel as an
    EXCLUDE entry or it does not apply at all.

    @brief A dot-directory under the whole-repo root is excluded.
    @version 1
    """
    root = tmp_path / "repo"
    _write(root / "src" / "a.c")
    _write(root / ".venv" / "lib" / "vendor.c")

    scope = sc.whole_repo_scope(root)

    assert scope.source == sc.SOURCE_WHOLE_REPO
    assert _rel_roots(scope, root) == ["."], "the repo itself is the one INPUT root"
    assert ".venv" in _rel_excludes(scope, root)
    assert "src" not in _rel_excludes(scope, root)


## @brief `--scope from-guard` folds the declared roots into the build arguments.
## @version 2
def test_cli_apply_scope_replaces_input(tmp_path: Path) -> None:
    """The declared roots become the INPUT list (replace_input), with any
    explicit --extra-input appended on top rather than discarded.

    @brief A declared index scope becomes the build's INPUT.
    @version 2
    """
    from clew.cli import _apply_scope

    root = _repo(tmp_path / "repo", _SIMPLE_CONFIG)
    _write(root / "src" / "a.c")
    (root / ".clew.yaml").write_text("index_scope:\n  roots: [src]\n", encoding="utf-8")

    args = _args(
        tmp_path / "clew.db",
        doxyfile=str(root / "Doxyfile"),
        scope=sc.SCOPE_FROM_GUARD,
        extra_input=["/elsewhere"],
    )
    _apply_scope(args, root)

    assert args.replace_input is True
    assert args.extra_input == [str(root.resolve() / "src"), "/elsewhere"]


## @brief A stated `doxyfile` scope is an EXPLICIT opt-out and leaves the build args untouched.
## @version 3
def test_cli_apply_scope_doxyfile_is_inert(tmp_path: Path) -> None:
    """gh#333 flipped the DEFAULT to `from-guard`, and this is the surviving narrow
    path: an operator who passes `--scope doxyfile` gets the Doxyfile's own INPUT and
    no derivation at all.

    Stated EXPLICITLY here rather than relying on the parser default, which is the
    whole point of the flip — a test that took the default would have silently
    started asserting the new behaviour under the old name.

    THE FLAG IS GONE AND THE VALUE IS NOT (22->6 collapse). `doxyfile` scope is build
    MECHANICS, not a declaration, so it has no section and never should; it stays reachable
    on the typed surface (`build_index(scope=…)`, `index(action='refresh', scope=…)`) and is
    stated here on the dest those go through. Deleting the value with the flag would have
    removed the only opt-out from gh#333's whole-repo default.

    @brief An explicit doxyfile scope applies no derived roots.
    @version 3
    """
    from clew.cli import _apply_scope

    root = _repo(tmp_path / "repo", _SIMPLE_CONFIG)
    _write(root / "src" / "a.c")
    args = _args(
        tmp_path / "clew.db",
        doxyfile=str(root / "Doxyfile"),
        scope=sc.SCOPE_DOXYFILE,
    )
    _apply_scope(args, root)

    assert args.scope == sc.SCOPE_DOXYFILE
    assert args.replace_input is False
    assert args.extra_input is None


## @brief The parser default is from-guard, so a bare invocation indexes the whole repo.
## @version 1
def test_cli_apply_scope_default_replaces_the_doxyfile_input(tmp_path: Path) -> None:
    """THE INVERSION gh#333 FIXES, asserted from the CLI surface. A repo that ships a
    Doxyfile and declares no index scope used to keep the Doxyfile's INPUT — its
    published-API subset — while an otherwise identical repo WITHOUT a Doxyfile got
    its whole tree. The default now replaces INPUT in both cases.

    `replace_input` is the load-bearing assertion, not `extra_input`: it is what
    tells the Doxyfile writer to discard the target's own INPUT rather than prepend
    to it, so a test that checked only the root list would pass against a build that
    indexed the union of both.

    @brief The default scope replaces a shipped Doxyfile's INPUT with the repo root.
    @version 1
    """
    from clew.cli import _apply_scope

    root = _repo(tmp_path / "repo", _SIMPLE_CONFIG)
    _write(root / "src" / "a.c")
    args = _args(tmp_path / "clew.db", doxyfile=str(root / "Doxyfile"))
    _apply_scope(args, root)

    assert args.scope == sc.SCOPE_FROM_GUARD, (
        "gh#333 flipped the default, and the 22->6 collapse must not have moved it: the "
        "parser default is the ONLY declaration of it left in the tool"
    )
    assert args.replace_input is True
    assert args.extra_input == [str(root.resolve())]


## @brief A repo with no declaration gets the whole repo under from-guard.
## @version 2
def test_cli_apply_scope_indexes_the_whole_repo_without_a_declaration(tmp_path: Path) -> None:
    """The undeclared branch must not half-apply. It used to `return` before
    replacing anything, handing INPUT back to the Doxyfile; gh#333 makes it fold a
    real whole-repo scope, so `replace_input` is True and the repo root is the root
    list.

    @brief An undeclared repo folds the whole-repo scope into the build args.
    @version 2
    """
    from clew.cli import _apply_scope

    root = tmp_path / "repo"
    _write(root / "src" / "a.c")
    args = _args(
        tmp_path / "clew.db",
        doxyfile=str(root / "Doxyfile"),
        scope=sc.SCOPE_FROM_GUARD,
    )
    _apply_scope(args, root)

    assert args.replace_input is True
    assert args.extra_input == [str(root.resolve())]


## @brief An unparseable pre-commit config falls back to the whole-repo tier.
## @version 3
def test_unparseable_config_falls_back_to_the_whole_repo(tmp_path: Path) -> None:
    """A malformed config is never guessed at — scope derivation drops to the
    whole-repo tier instead of half-reading it. FAILING OPEN is deliberate here and
    is the opposite of the fail-closed rule elsewhere: a scope that cannot be read
    yields a WIDER index, never a narrower one, because a silently narrow index is
    the failure this project keeps paying for.

    @brief A malformed pre-commit config leaves scope on the whole-repo tier.
    @version 3
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".pre-commit-config.yaml").write_text("repos: [ unbalanced\n", encoding="utf-8")

    assert sc.derive_scope(root).source == sc.SOURCE_WHOLE_REPO


## @brief A valid-but-non-dict config does not crash guard-config discovery.
## @version 2
def test_non_dict_config_does_not_crash_guard_discovery(tmp_path: Path) -> None:
    """Parses cleanly yet isn't the expected mapping — the `isinstance(data,
    dict)` guard in `_load_precommit_config` must return None rather than hand a
    LIST to `_find_guard_hook`, which would raise `AttributeError` on `.get`.
    Distinct from the unparseable case (this YAML is valid, just the wrong shape).

    Asserted through `discover_guard_config`, which reaches that guard on its
    hook-args step; the repo has no root-level guard config, so the step is
    actually taken rather than short-circuited.

    @brief Valid non-dict YAML reads as 'no declaration'.
    @version 2
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".pre-commit-config.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")

    location = pc.discover_guard_config(root)

    assert location.path is None
    assert location.source == pc.GUARD_SOURCE_NONE


## @brief Build a repo whose guard gates only src/ but which has more code.
## @param root Repo root to create.
## @return None.
## @version 1
def _repo_gating_only_src(root: Path) -> None:
    """@brief Seed src/, vendor/ and tests/ with a guard hook covering src/ only."""
    for sub in ("src", "vendor", "tests"):
        (root / sub).mkdir(parents=True)
        (root / sub / "a.c").write_text(f"void {sub}_fn(void){{}}\n", encoding="utf-8")
    (root / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: doxygen-guard\n"
        "        name: doxygen-guard\n"
        "        entry: doxygen-guard validate\n"
        "        language: system\n"
        "        files: ^src/.*\\.c$\n",
        encoding="utf-8",
    )


## @brief A declaration is the only tier that yields index roots.
## @version 2
def test_an_index_scope_declaration_is_what_yields_roots(tmp_path: Path) -> None:
    """#57: index scope used to be identical to GATE scope, but they answer different
    questions — the gate says what MUST be documented, the index says what should be
    reasonable-about. Coupling them forced a repo to loosen its quality bar to widen
    its graph. Here the gate covers `src/` alone while `vendor/` and `tests/` are the
    trees a reader wants; the declaration is what lets them differ.

    @brief Declared roots override, and the gate alone yields none.
    @version 2
    """
    root = tmp_path / "repo"
    root.mkdir()
    _repo_gating_only_src(root)

    ## The gate alone yields the WHOLE REPO (gh#333), not nothing — so the thing that
    ## distinguishes a declaration is that it NARROWS, which is the assertion below.
    assert sc.derive_scope(root).roots == (root.resolve(),), "the gate declares no boundary"

    (root / ".clew.yaml").write_text(
        "index_scope:\n  roots: [src, vendor, tests]\n", encoding="utf-8"
    )
    declared = sc.derive_scope(root)
    assert declared.source == sc.SOURCE_DECLARED
    assert sorted(p.name for p in declared.roots) == ["src", "tests", "vendor"]
    assert declared.is_derived() is True, "a declared scope is the only tier that narrows"


## @brief A stale declared root is dropped rather than passed to doxygen.
## @version 2
def test_declared_index_scope_drops_paths_that_do_not_exist(tmp_path: Path) -> None:
    """A stale entry must not reach doxygen, which would report a confusing
    'input not found'. It is dropped with a warning instead.

    @brief Non-existent declared roots and excludes are dropped.
    @version 2
    """
    root = tmp_path / "repo"
    root.mkdir()
    _repo_gating_only_src(root)
    (root / ".clew.yaml").write_text(
        "index_scope:\n  roots: [src, gone]\n  excludes: [also_gone]\n", encoding="utf-8"
    )
    scope = sc.derive_scope(root)
    assert [p.name for p in scope.roots] == ["src"]
    assert scope.excludes == ()


## @brief An empty or absent index_scope falls through to the whole-repo tier.
## @version 3
def test_empty_or_absent_index_scope_falls_back_to_the_whole_repo(tmp_path: Path) -> None:
    """An unusable section must read as "nothing was declared" and drop to the next
    tier, never as a declared-and-empty scope — which would blank the index. Since
    gh#333 the next tier is the whole repository rather than the Doxyfile, so the
    consequence of getting this wrong got LOUDER, not quieter: an empty declared
    scope would now be the one way to reach an empty index.

    @brief An unusable index_scope section yields the whole repo, not empty roots.
    @version 3
    """
    root = tmp_path / "repo"
    root.mkdir()
    _repo_gating_only_src(root)

    (root / ".clew.yaml").write_text("shared_key_patterns:\n  writers: []\n", encoding="utf-8")
    assert sc.derive_scope(root).source == sc.SOURCE_WHOLE_REPO
    assert sc.derive_scope(root).roots == (root.resolve(),)

    (root / ".clew.yaml").write_text("index_scope:\n  roots: []\n", encoding="utf-8")
    assert sc.derive_scope(root).source == sc.SOURCE_WHOLE_REPO
    assert sc.derive_scope(root).roots == (root.resolve(),)
