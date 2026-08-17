# SPDX-License-Identifier: MIT
"""The build CLI is SIX arguments, and every flag it lost has a route that still works.

The collapse (22 -> 6) is only safe if two separate claims hold, and they need separate
tests because a suite that pins one and not the other is exactly how a capability
disappears quietly:

  1. THE SURFACE IS THE SIX. Asserted as an exact set, not a subset — a subset assertion
     passes against a parser that quietly kept `--doxyfile`, which is the state this whole
     change exists to leave.
  2. EVERY REMOVED DEST STILL EXISTS, WITH THE DEFAULT ITS FLAG DECLARED. `build_index`
     sources its defaults BY PARSING so a value it does not name arrives with the parser's
     declared default, and `apply_options` ASSIGNS onto these dests — the option names ARE
     the dest names. Deleting a dest breaks both at once, and the second break is silent:
     `setattr` on a Namespace always succeeds, so a stated option would land on an
     attribute nothing reads and the build would report success.

`scope` gets its own assertion because it is the one whose divergence this repo has
already paid for: the parser declared `from-guard` while an older `build_index` signature
declared `doxyfile`, which is the gh#333 inversion (a repo PUNISHED for documenting
itself) reachable through one of two doors. After the collapse the parser default is the
only declaration of it left, so it is pinned here by value.

WHY THE ROUTE TESTS FILTER ON PROVENANCE. A fold is proven by showing the declaration
route reaches the same STAGE the flag did, and for `predefined` a presence check cannot
show that: gh#11 recovers a function from the source text whether or not the macro reached
doxygen, so after a LOST `predefined` the symbol is still in `memberdef` as
`dg_source='ast'` — with no brief, no params and no `@req` — and a health check reports
fine. Only `dg_source = 'doxygen'` can tell the two apart.

@brief Tests for the six-argument build surface and each fold's replacement route.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.buildoptions import BuildOptionError, accepted_options
from clew.cli import (
    _FOLDED_BUILD_DEFAULTS,
    _build_argparser,
    _run_pipeline,
    build_index,
)
from clew.declaration import KNOWN_SECTIONS
from clew.scope import SCOPE_DOXYFILE, SCOPE_FROM_GUARD

needs_doxygen = pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="proving a stated declaration reaches doxygen needs the real doxygen binary",
)

## THE SIX. Written out rather than derived from the parser, because a test that asks the
## parser what it registers and then asserts the parser registers that cannot fail.
EXPECTED_BUILD_ARGUMENTS = {
    "--output",
    "--repo-root",
    "--declare",
    "--exclude",
    "--rebuild",
    "--verbose",
}

## A source file whose implementation sits behind a macro guard, plus an unguarded CONTROL.
## The control is what separates "the macro did not arrive" from "the build failed for some
## unrelated reason" — without it, a build that indexed nothing at all would read as a
## correctly-withheld macro.
GUARDED_SOURCE = """\
/** @brief Present in every configuration, whatever the macros say. */
int surface_control(void) { return 1; }

#if defined(SURFACE_FEATURE)
/** @brief Present only when SURFACE_FEATURE is supplied to doxygen. */
int surface_guarded(void) { return 2; }
#endif
"""


## @brief Materialise a repo whose only function of interest is macro-guarded.
## @param root Repo root to create.
## @return The repo root.
## @version 1
def _guarded_repo(root: Path) -> Path:
    """@brief Write the guarded fixture repo and its Doxyfile.
    @return The repo root.
    @version 1
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "unit.c").write_text(GUARDED_SOURCE, encoding="utf-8")
    (root / "Doxyfile").write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nRECURSIVE = YES\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )
    return root


## @brief Function names DOXYGEN itself emitted, never the parser's recoveries.
## @param db Built database.
## @return The set of doxygen-sourced function names.
## @version 1
def _doxygen_functions(db: Path) -> set[str]:
    """THE PROVENANCE FILTER IS THE TEST. Drop it and every assertion below passes with the
    macro route completely unwired, because `dg_source='ast'` recovers the guarded function
    from the source text regardless of what doxygen was told.

    @brief Read the doxygen-emitted function names.
    @return Their names.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT name FROM memberdef WHERE kind='function' AND dg_source='doxygen'"
            )
        }
    finally:
        conn.close()


## @brief The build CLI registers exactly six arguments.
## @return None.
## @version 1
def test_the_build_cli_is_exactly_six_arguments() -> None:
    """AN EXACT SET, and that is the whole point. `>=` would pass against a parser that
    quietly kept the seventeen removed flags, and `<=` against one that lost `--exclude`.

    @brief Pin the build surface at six named arguments.
    @version 1
    """
    parser = _build_argparser()
    registered = {
        name
        for action in parser._actions
        for name in action.option_strings
        if name not in ("-h", "--help")
    }
    assert registered == EXPECTED_BUILD_ARGUMENTS, (
        "the build surface is SIX arguments; anything else means a flag was re-added or "
        f"lost. Unexpected: {sorted(registered - EXPECTED_BUILD_ARGUMENTS)}; missing: "
        f"{sorted(EXPECTED_BUILD_ARGUMENTS - registered)}"
    )


## @brief Every folded dest survives a bare parse, carrying its flag's declared default.
## @return None.
## @version 1
def test_every_folded_dest_survives_with_its_declared_default() -> None:
    """THE SILENT HALF OF THE COLLAPSE. `apply_options` reaches a stated value onto one of
    these dests with `setattr`, which ALWAYS succeeds — so a deleted dest would take the
    statement, be read by nobody, and the build would report success on the built-in
    defaults. That is the precise failure the tier-1 surface exists to remove, reintroduced
    by its own plumbing.

    `build_index` depends on the same property from the other direction: it parses
    `["--output", …]` and relies on every option it does not name arriving with the parser's
    declared default rather than None.

    @brief Pin the surviving dests and their defaults.
    @version 1
    """
    args = _build_argparser().parse_args(["--output", "/tmp/does-not-matter.db"])
    for dest, default in _FOLDED_BUILD_DEFAULTS.items():
        assert hasattr(args, dest), (
            f"{dest!r} lost its dest, so a stated option would land on an attribute "
            "nothing reads and the build would report success"
        )
        assert getattr(args, dest) == default, (
            f"{dest!r} parsed to {getattr(args, dest)!r}, not the declared {default!r} — "
            "the collapse changes what a caller can SAY, never what a value MEANS"
        )


## @brief The scope default is from-guard and is declared in exactly one place.
## @return None.
## @version 1
def test_the_scope_default_is_from_guard_and_declared_once() -> None:
    """gh#333's INVERSION, pinned. Honouring a Doxyfile's INPUT meant a repo shipping one
    got its published-API subset while a repo shipping none got its whole tree, so a repo
    was punished for documenting itself. The divergence that made it reachable was a parser
    default of `from-guard` against a `build_index` signature default of `doxyfile`.

    `SCOPE_DOXYFILE` is asserted to still be a REAL value, not merely absent from the CLI:
    it is the only opt-out from whole-repo indexing and it survived on the typed surface.

    @brief Pin the scope default and the survival of the opt-out.
    @version 1
    """
    assert _FOLDED_BUILD_DEFAULTS["scope"] == SCOPE_FROM_GUARD
    args = _build_argparser().parse_args(["--output", "/tmp/x.db"])
    assert args.scope == SCOPE_FROM_GUARD
    assert SCOPE_DOXYFILE != SCOPE_FROM_GUARD, "the opt-out must remain a distinct value"


## @brief Every declaration section is statable, and only `predefined` has no section.
## @return None.
## @version 1
def test_every_declaration_section_has_a_matching_option() -> None:
    """BOTH DIRECTIONS, so a section added without an option fails here rather than being
    discovered as unreachable — which is the shape CLAUDE.md records as "a declaration
    reachable only from argv is not a declaration", read the other way round.

    `predefined` is the ONE documented asymmetry: an option with no section, kept as an
    alias for `preprocessor.predefined` because a bare macro list is the common case.

    @brief Pin the option/section correspondence in both directions.
    @version 1
    """
    options = set(accepted_options())
    sections = set(KNOWN_SECTIONS)
    assert sections - options == set(), (
        f"section(s) with no way to state them: {sorted(sections - options)}"
    )
    assert options - sections == {"predefined"}, (
        "the only option that is not a section is the documented `predefined` alias; "
        f"found {sorted(options - sections)}"
    )


## @brief A `--declare` document is refused when it names something nothing reads.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_declare_document_naming_an_unknown_section_is_refused(tmp_path: Path) -> None:
    """REFUSED, NOT IGNORED, and it must be refused BEFORE the build starts. A dropped
    section produces a build whose policy is not what the caller stated and which reports
    success — the one failure mode `--declare` exists to remove, at its own front door.

    @brief A misspelled section fails the build instead of silently defaulting.
    @version 1
    """
    document = tmp_path / "declared.yaml"
    document.write_text("entry_pattern:\n  - main\n", encoding="utf-8")
    args = _build_argparser().parse_args(
        [
            "--output", str(tmp_path / "out.db"),
            "--repo-root", str(tmp_path),
            "--declare", str(document),
        ]
    )  # fmt: skip
    with pytest.raises(BuildOptionError) as caught:
        _run_pipeline(args)
    assert "entry_pattern" in str(caught.value), "the refusal must name the offending key"


## @brief An empty `--declare` document states nothing rather than withdrawing everything.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_empty_declare_document_states_nothing(tmp_path: Path) -> None:
    """THE THREE STATES SURVIVE THE MOVE. `yaml.safe_load` returns None for an empty file,
    and if that were normalised to `[]` per option every plain refresh through `--declare`
    would become a WITHDRAWAL of the operator's own earlier statement. Absent must inherit.

    @brief An empty stated document leaves every dest at its default.
    @version 1
    """
    from clew.cli import _apply_declared_document

    document = tmp_path / "empty.yaml"
    document.write_text("", encoding="utf-8")
    args = _build_argparser().parse_args(
        ["--output", str(tmp_path / "out.db"), "--declare", str(document)]
    )
    assert _apply_declared_document(args) == []
    assert args.entry_patterns is None, "absent must INHERIT, never withdraw"
    assert args.predefined is None


## @brief A `--declare` document reaches the same dests the inline `options` mapping does.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_declare_and_inline_options_reach_the_same_dests(tmp_path: Path) -> None:
    """ONE ROUTE, TWO DOORS. `--declare` reads the YAML and hands the whole mapping to
    `apply_options` — the same function the `options` argument goes through — so the two
    cannot validate differently or land differently. Asserted by comparing the resulting
    namespaces rather than by reading the code, because "they call the same function" is a
    claim about today's implementation and this is a claim about the behaviour.

    @brief The file route and the mapping route produce the same namespace.
    @version 1
    """
    from clew.buildoptions import apply_options
    from clew.cli import _apply_declared_document

    document = tmp_path / "declared.yaml"
    document.write_text(
        "entry_patterns: [main, cmd_%]\n"
        "preprocessor:\n  predefined: [SURFACE_FEATURE]\n"
        "index_scope:\n  roots: [src]\n"
        "requirements: docs/requirements.yaml\n",
        encoding="utf-8",
    )
    inline = {
        "entry_patterns": ["main", "cmd_%"],
        "preprocessor": {"predefined": ["SURFACE_FEATURE"]},
        "index_scope": {"roots": ["src"]},
        "requirements": "docs/requirements.yaml",
    }

    from_file = _build_argparser().parse_args(
        [
            "--output", str(tmp_path / "a.db"),
            "--repo-root", str(tmp_path),
            "--declare", str(document),
        ]
    )  # fmt: skip
    _apply_declared_document(from_file)

    from_mapping = _build_argparser().parse_args(
        ["--output", str(tmp_path / "b.db"), "--repo-root", str(tmp_path)]
    )
    apply_options(from_mapping, inline, tmp_path)

    for dest in ("entry_patterns", "preprocessor", "index_scope", "requirements"):
        assert getattr(from_file, dest) == getattr(from_mapping, dest), (
            f"the --declare file and the inline mapping disagree on {dest!r}, so the two "
            "routes are not one route"
        )


## @brief A stated `index_scope` reaches the INPUT list `--extra-input` used to write.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_stated_index_scope_reaches_the_input_list(tmp_path: Path) -> None:
    """THE FOLD OF `--extra-input` / `--extra-exclude`, PROVEN AT THE DEST. Both flags wrote
    into `args.extra_input` / `args.extra_exclude`, and `_apply_scope` folds a resolved scope
    into exactly those two lists — so the fold target is literally the same list the flags
    appended to, and this asserts the stated roots arrive there.

    `roots` are absolute after the fold because `_declared_index_scope` resolves them against
    the repo, which is what makes the excludes containable.

    @brief A stated index_scope becomes the build's INPUT and EXCLUDE lists.
    @version 1
    """
    from clew.cli import _apply_declared_document, _apply_scope

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.c").write_text("int a;\n", encoding="utf-8")
    (root / "vendor").mkdir()
    (root / "vendor" / "b.c").write_text("int b;\n", encoding="utf-8")
    document = tmp_path / "declared.yaml"
    document.write_text("index_scope:\n  roots: [src]\n  excludes: [vendor]\n", encoding="utf-8")

    args = _build_argparser().parse_args(
        [
            "--output", str(tmp_path / "out.db"),
            "--repo-root", str(root),
            "--declare", str(document),
        ]
    )  # fmt: skip
    _apply_declared_document(args)
    _apply_scope(args, root)

    assert args.replace_input is True, (
        "a stated scope must REPLACE the Doxyfile's INPUT, not prepend to it — gh#333"
    )
    assert args.extra_input == [str((root / "src").resolve())]
    assert args.extra_exclude == [str((root / "vendor").resolve())]


## @brief A stated `requirements` path reaches the catalog dest the flag wrote to.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_stated_requirements_path_reaches_the_catalog_dest(tmp_path: Path) -> None:
    """THE FOLD OF `--requirements`. It was an argparse flag and NOTHING else, so an agent
    refreshing through MCP could not name a catalog at all. Relative to the REPO, not to the
    process's cwd, because an embedding server's cwd is not the target repo.

    @brief A stated catalog path lands on args.requirements, repo-relative.
    @version 1
    """
    from clew.cli import _apply_declared_document

    document = tmp_path / "declared.yaml"
    document.write_text(
        "requirements: docs/reqs.yaml\nenrich: docs/topics.yaml\n", encoding="utf-8"
    )
    args = _build_argparser().parse_args(
        [
            "--output", str(tmp_path / "out.db"),
            "--repo-root", str(tmp_path / "repo"),
            "--declare", str(document),
        ]
    )  # fmt: skip
    _apply_declared_document(args)

    assert args.requirements == str(tmp_path / "repo" / "docs" / "reqs.yaml")
    assert args.enrich == str(tmp_path / "repo" / "docs" / "topics.yaml")


## @brief The target's own declaration supplies a catalog path nothing stated.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_declared_requirements_section_fills_an_unstated_catalog(tmp_path: Path) -> None:
    """TIER 2 FOR THE SAME TWO KEYS, so a repo that owns its tree writes them down once
    instead of restating them per build. Tier 1 still wins, which is checked in the same
    test rather than a separate one: the two orderings are one decision and splitting them
    lets a change break one while the other keeps passing.

    @brief A declared path fills the dest, and a stated one outranks it.
    @version 1
    """
    from clew.cli import _apply_declared_paths

    repo = tmp_path / "repo"
    repo.mkdir()
    declaration = {"requirements": "docs/declared.yaml", "enrich": "docs/topics.yaml"}

    inherited = _build_argparser().parse_args(["--output", str(tmp_path / "a.db")])
    assert _apply_declared_paths(inherited, declaration, repo) == ["requirements", "enrich"]
    assert inherited.requirements == str(repo / "docs" / "declared.yaml")

    stated = _build_argparser().parse_args(["--output", str(tmp_path / "b.db")])
    stated.requirements = "/absolute/stated.yaml"
    assert _apply_declared_paths(stated, declaration, repo) == ["enrich"]
    assert stated.requirements == "/absolute/stated.yaml", "tier 1 must outrank tier 2"


## @brief A stated `predefined` reaches doxygen through the declaration route.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@needs_doxygen
def test_a_stated_predefined_reaches_doxygen_through_declare(tmp_path: Path) -> None:
    """THE FOLD OF `--predefined`, PROVEN AT THE STAGE AND NOT AT THE DEST. Every other route
    test above can stop at the namespace, because the dest is what the flag wrote. This one
    cannot: the claim is that the macro reaches DOXYGEN and changes what is indexed, and only
    a real doxygen run settles that.

    THE PROVENANCE FILTER IS WHAT MAKES IT CAPABLE OF FAILING. gh#11 recovers
    `surface_guarded` from the source text whether or not the macro arrived, so
    `dg_source='ast'` would satisfy a presence check on a completely unwired route — with no
    brief, no params and no `@req`, i.e. an index that reads healthy and describes a variant
    the build never had. `surface_control` is the other half: it is outside every guard, so a
    build that finds neither function failed for an unrelated reason, and without it that
    failure would read as a correctly-withheld macro.

    @brief A --declare'd predefined macro changes what doxygen indexes.
    @version 1
    """
    root = _guarded_repo(tmp_path / "repo")
    document = tmp_path / "declared.yaml"
    document.write_text("preprocessor:\n  predefined:\n    - SURFACE_FEATURE\n", encoding="utf-8")

    without = tmp_path / "without.db"
    build_index(output=without, repo_root=root, doxyfile=root / "Doxyfile")
    baseline = _doxygen_functions(without)
    assert "surface_control" in baseline, "the control is missing — the build itself failed"
    assert "surface_guarded" not in baseline, (
        "the guarded function indexed with NO macro supplied, so this fixture cannot "
        "distinguish a working route from a broken one"
    )

    stated = tmp_path / "stated.db"
    args = _build_argparser().parse_args(
        [
            "--output", str(stated),
            "--repo-root", str(root),
            "--declare", str(document),
        ]
    )  # fmt: skip
    args.doxyfile = str(root / "Doxyfile")
    _run_pipeline(args)

    functions = _doxygen_functions(stated)
    assert "surface_control" in functions, "the control is missing — the build itself failed"
    assert "surface_guarded" in functions, (
        "the stated `preprocessor: predefined:` never reached doxygen. Note this can only "
        "be seen through dg_source='doxygen': the AST recovery puts the symbol in memberdef "
        "either way, with no brief and no params"
    )
