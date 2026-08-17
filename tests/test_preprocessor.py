# SPDX-License-Identifier: MIT
"""The declared PREPROCESSOR CONFIGURATION an index represents (gh#17).

Doxygen evaluates `#if defined(X)` while it parses, so these tests are built around
a fixture whose implementation sits INSIDE such a guard. That shape is the whole
point: the guarded function is not merely undocumented without the macro, it is
absent, and no amount of reading the index can tell you it should have been there.

Two tiers, deliberately. The BUILD tests run real doxygen and assert on the rows in
the resulting database, because the claim under test is "the macro reaches doxygen
and changes what is indexed" and only doxygen can settle that. The CONTENT tests
assert on the Doxyfile text instead, and they carry the two guarantees a build test
could not show honestly: that the emitted text is byte-identical to the
pre-gh#17 text for a target declaring nothing, and that the index cache's tree hash
moves when the declaration does.

@brief Tests for the declared preprocessor configuration.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline, build_index
from clew.declaration import KNOWN_SECTIONS, load_declaration
from clew.doxygen import doxyfile_content_for
from clew.indexcache import IndexCache
from clew.preprocessor import (
    CONFIG_HEADER_AUTO,
    SECTION_PREPROCESSOR,
    SOURCE_BOTH,
    SOURCE_CONFIG_HEADER,
    SOURCE_DECLARED,
    SOURCE_FLAG,
    SOURCE_NONE,
    PreprocessorConfig,
    doxyfile_lines,
    evaluate_condition,
    macros_from_header,
    resolve_preprocessor,
)

needs_doxygen = pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="asserting that a macro reaches doxygen needs the real doxygen binary",
)

## The fixture's whole reason for existing. `always_present` is outside every guard, so
## it indexes unconditionally and acts as the CONTROL: a build that finds neither
## function failed for some unrelated reason, and without the control that failure would
## read as "the macro was correctly not supplied".
GUARDED_SOURCE = """\
/** @brief Present in every configuration, whatever the macros say. */
int always_present(void) { return 1; }

#if defined(FIXTURE_FEATURE_C)
/** @brief Only parsed when FIXTURE_FEATURE_C is defined. */
int feature_entry(void) { return 2; }
#endif

#if defined(FIXTURE_WIDTH) && FIXTURE_WIDTH == 16
/** @brief Only parsed when FIXTURE_WIDTH is defined as exactly 16. */
int wide_entry(void) { return 3; }
#endif
"""

## A config header in the mbedtls idiom: the shipped configuration as top-level
## `#define`s, with the alternatives COMMENTED OUT rather than deleted. A flat scan
## must read the first and not the second, which is what makes the idiom readable
## without a preprocessor.
CONFIG_HEADER = """\
#ifndef FIXTURE_CONFIG_H
#define FIXTURE_CONFIG_H

#define FIXTURE_FEATURE_C
//#define FIXTURE_DISABLED_FEATURE
/* #define FIXTURE_ALSO_DISABLED */
#define FIXTURE_WIDTH 16 /* bits */

#endif
"""


## @brief Write the guarded-source fixture repo and return its root.
## @param tmp_path Pytest temporary directory.
## @param declaration Text for `.clew.yaml`, or "" to write none.
## @param guard_config Text for `.doxygen-guard.yaml`, or "" to write none.
## @param doxyfile_extra Extra lines appended to the fixture's Doxyfile.
## @return The repo root.
## @version 1
def _fixture_repo(
    tmp_path: Path,
    declaration: str = "",
    guard_config: str = "",
    doxyfile_extra: str = "",
) -> Path:
    """The Doxyfile names `src` as its INPUT and nothing else, so the build indexes
    exactly the guarded file and the assertions cannot be confounded by another source.

    @brief Create a repo whose only source sits behind preprocessor guards.
    @return The repo root.
    @version 1
    """
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "feature.c").write_text(GUARDED_SOURCE, encoding="utf-8")
    (root / "include").mkdir()
    (root / "include" / "fixture_config.h").write_text(CONFIG_HEADER, encoding="utf-8")
    (root / "Doxyfile").write_text(
        f"PROJECT_NAME = fixture\nINPUT = src\nSTRIP_FROM_PATH = {root}\n{doxyfile_extra}",
        encoding="utf-8",
    )
    if declaration:
        (root / ".clew.yaml").write_text(declaration, encoding="utf-8")
    if guard_config:
        (root / ".doxygen-guard.yaml").write_text(guard_config, encoding="utf-8")
    return root


## @brief Build the fixture repo through the real pipeline, stating options inline.
## @param root Repo root to index.
## @param out Output database path.
## @param options Tier-1 declaration options to state, or None to state nothing.
## @return The built database path.
## @version 2
def _build(root: Path, out: Path, options: dict | None = None) -> Path:
    """`--predefined` IS GONE (22->6 collapse) and this is its replacement route: the same
    `options` mapping an embedding caller and the MCP server pass, keyed by the declaration
    name. `build_index` applies it through `apply_options` before the build starts, so a
    stated macro list lands on exactly the dest the flag wrote to.

    @brief Run the pipeline over the fixture repo.
    @return The output database path.
    @version 2
    """
    build_index(output=out, repo_root=root, doxyfile=root / "Doxyfile", options=options)
    return out


## @brief Build the fixture repo through the CLI's `--declare FILE` route.
## @param root Repo root to index.
## @param out Output database path.
## @param document YAML text for the stated declaration document.
## @return The built database path.
## @version 1
def _build_via_declare(root: Path, out: Path, document: str) -> Path:
    """THE OTHER HALF OF THE FOLD, and it must reach the same stage as the mapping above.
    `--declare` is the ONE surviving CLI route for every declaration section; it reads the
    YAML and hands the whole mapping to `apply_options`, the same function `options` goes
    through. Written OUTSIDE the repo on purpose — the point of the flag is a target you may
    not write into.

    @brief Run the pipeline with a stated declaration document on the command line.
    @return The output database path.
    @version 1
    """
    stated = out.parent / f"{out.stem}-declared.yaml"
    stated.write_text(document, encoding="utf-8")
    args = _build_argparser().parse_args(
        ["--output", str(out), "--repo-root", str(root), "--declare", str(stated)]
    )
    args.doxyfile = str(root / "Doxyfile")
    _run_pipeline(args)
    return out


## @brief Names of doxygen-sourced functions in a built index.
## @param db Built database path.
## @return Set of function names doxygen itself emitted.
## @version 1
def _doxygen_functions(db: Path) -> set[str]:
    """Restricted to `dg_source = 'doxygen'` ON PURPOSE, and the test is worthless
    without it. gh#11 makes tree-sitter recover `feature_entry` from the source text
    REGARDLESS of the macros, so an unfiltered query finds it either way and every
    assertion below would pass against a completely unwired PREDEFINED. The provenance
    column is what separates "doxygen parsed this branch" from "the parser saw the text".

    @brief Read the doxygen-emitted function names from a built index.
    @return Set of names.
    @version 1
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT name FROM memberdef WHERE kind = 'function' AND dg_source = 'doxygen'"
        ).fetchall()
    finally:
        conn.close()
    return {name for (name,) in rows}


## @brief The build_meta rows under one prefix.
## @param db Built database path.
## @param prefix Key prefix to read (without the trailing dot).
## @return Mapping of unprefixed key to value.
## @version 1
def _meta(db: Path, prefix: str) -> dict[str, str]:
    """@brief Read a namespaced build_meta section.

    @return Unprefixed key -> value.
    @version 1
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT key, value FROM build_meta WHERE key LIKE ?", (f"{prefix}.%",)
        ).fetchall()
    finally:
        conn.close()
    return {key.split(".", 1)[1]: value for key, value in rows}


# --------------------------------------------------------------------------- #
# The build tier: does a declared macro actually change what doxygen indexes?
# --------------------------------------------------------------------------- #


## @brief A declared `predefined:` list reaches doxygen and indexes guarded code.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@needs_doxygen
def test_a_declared_predefined_list_reaches_doxygen(tmp_path: Path) -> None:
    """THE test for gh#17 part 1, and it fails before the change with
    `feature_entry` absent — nothing in the pipeline set `PREDEFINED`, so every
    occurrence of the word was prose in a warning.

    Asserted in BOTH directions against the same fixture, because only the negative
    half shows the macro is what did it: an undeclared build must NOT hold
    `feature_entry`. Without that, a doxygen version indexing guarded branches
    regardless would pass the positive half and the test would be measuring nothing.
    """
    declared = _fixture_repo(
        tmp_path / "yes",
        declaration="preprocessor:\n  predefined:\n    - FIXTURE_FEATURE_C\n",
    )
    bare = _fixture_repo(tmp_path / "no")

    with_macro = _doxygen_functions(_build(declared, tmp_path / "yes.db"))
    without = _doxygen_functions(_build(bare, tmp_path / "no.db"))

    assert "always_present" in with_macro, "the control function must index either way"
    assert "always_present" in without, "the control function must index either way"
    assert "feature_entry" in with_macro, "the declared macro did not reach doxygen"
    assert "feature_entry" not in without, (
        "the guarded function indexed with NO macro declared — this fixture cannot "
        "prove anything about PREDEFINED"
    )


## @brief The declaration works from the `x-clew` passthrough, not just a file.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@needs_doxygen
def test_the_declaration_works_from_the_guard_config_passthrough(tmp_path: Path) -> None:
    """The passthrough is the owner's STATED PREFERENCE — a repo running the gate already
    maintains `.doxygen-guard.yaml`, so declaring there adds no new artifact. It is also
    the half most likely to rot silently: the section could be read from a dedicated
    `.clew.yaml` and quietly ignored in the passthrough, and every test written
    against the dedicated file would still pass.

    Note there is NO `.clew.yaml` here at all, so a passthrough that failed to
    resolve would leave the macro unsupplied and `feature_entry` absent.
    """
    root = _fixture_repo(
        tmp_path,
        guard_config=(
            "validate:\n"
            "  tags:\n"
            "    req:\n"
            "      pattern: '^REQ-[0-9]+$'\n"
            "x-clew:\n"
            "  preprocessor:\n"
            "    predefined:\n"
            "      - FIXTURE_FEATURE_C\n"
        ),
    )
    functions = _doxygen_functions(_build(root, tmp_path / "out.db"))
    assert "feature_entry" in functions, (
        "the x-clew passthrough did not carry the preprocessor section"
    )


## @brief A declared config header supplies its macros, including a valued one.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@needs_doxygen
def test_a_declared_config_header_supplies_its_macros(tmp_path: Path) -> None:
    """gh#17 part 2, end to end. `wide_entry` is the load-bearing assertion: it sits
    behind `FIXTURE_WIDTH == 16`, so it indexes only if the harvest carried the macro's
    VALUE and not merely its name — which is the difference between reading a
    configuration and noticing one exists.
    """
    root = _fixture_repo(
        tmp_path,
        declaration="preprocessor:\n  config_header: include/fixture_config.h\n",
    )
    db = _build(root, tmp_path / "out.db")
    functions = _doxygen_functions(db)

    assert "feature_entry" in functions, "the header's bare #define was not supplied"
    assert "wide_entry" in functions, "the header's macro VALUE was not supplied"

    meta = _meta(db, "preprocessor")
    assert meta["source"] == SOURCE_CONFIG_HEADER
    assert meta["config_header"] == "include/fixture_config.h"


## @brief A repo whose own Doxyfile sets PREDEFINED keeps it, and gains ours.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@needs_doxygen
def test_a_repo_with_its_own_predefined_is_not_overridden(tmp_path: Path) -> None:
    """The regression this guards is a one-character one. Doxygen takes the LAST
    assignment to a key, so emitting `PREDEFINED =` instead of `PREDEFINED +=` would
    silently DISCARD the list a target's own Doxyfile declares — turning a feature that
    widens an index into one that narrows it, for exactly the repos already doing the
    right thing, with no error anywhere.

    So the Doxyfile declares `FIXTURE_FEATURE_C` and the declaration adds
    `FIXTURE_WIDTH=16`: both functions must index. Asserting only on the declared macro
    would pass under `=` as well.
    """
    root = _fixture_repo(
        tmp_path,
        declaration="preprocessor:\n  predefined:\n    - FIXTURE_WIDTH=16\n",
        doxyfile_extra="PREDEFINED = FIXTURE_FEATURE_C\n",
    )
    functions = _doxygen_functions(_build(root, tmp_path / "out.db"))
    assert "feature_entry" in functions, (
        "the repo's OWN Doxyfile PREDEFINED was discarded — PREDEFINED = rather than +="
    )
    assert "wide_entry" in functions, "the declared macro did not reach doxygen"


## @brief A stated `predefined` overrides the repo's declaration outright.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 2
@needs_doxygen
def test_an_explicit_flag_replaces_the_declaration(tmp_path: Path) -> None:
    """A STATED `predefined` REPLACES rather than merges, matching `entry_patterns`. The
    declaration is the repo's standing statement about which variant it ships; an
    operator stating macros is deliberately indexing a different one, and merging would
    produce a third configuration nobody asked for. So the declared `FIXTURE_FEATURE_C`
    must be GONE, which is the half that distinguishes replacement from union.

    STATED THROUGH `options` NOW THAT `--predefined` IS GONE (22->6 collapse), and the
    semantics are unchanged because the route lands on the same dest — which is the whole
    claim of the fold and the reason this test is the one that proves it. The provenance
    filter in `_doxygen_functions` is what makes it capable of proving anything: after a lost
    `predefined` the symbol is STILL in `memberdef` as `dg_source='ast'` (gh#11 recovers it
    from the source text), with no brief and no params, so a presence check reports healthy.
    """
    root = _fixture_repo(
        tmp_path,
        declaration="preprocessor:\n  predefined:\n    - FIXTURE_FEATURE_C\n",
    )
    functions = _doxygen_functions(
        _build(root, tmp_path / "out.db", {"predefined": ["FIXTURE_WIDTH=16"]})
    )
    assert "wide_entry" in functions, "the stated macro did not reach doxygen"
    assert "feature_entry" not in functions, (
        "the statement MERGED with the declaration instead of replacing it"
    )


## @brief A target declaring nothing records no preprocessor rows and indexes as before.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
@needs_doxygen
def test_an_undeclared_target_is_untouched(tmp_path: Path) -> None:
    """The inertness guarantee. gh#17 must not change what any existing target indexes,
    and an absent `preprocessor.*` section is what makes the recorded provenance honest —
    a missing key reads as "not recorded", where `source=none` would read as a decision
    that was made.
    """
    root = _fixture_repo(tmp_path)
    db = _build(root, tmp_path / "out.db")
    assert "feature_entry" not in _doxygen_functions(db)
    assert _meta(db, "preprocessor") == {}, "an undeclared target wrote preprocessor rows"


# --------------------------------------------------------------------------- #
# The content tier: the Doxyfile text, and the cache hash computed over it.
# --------------------------------------------------------------------------- #


## @brief The index-cache tree hash moves when the declared macros change.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_the_index_cache_tree_hash_notices_a_changed_predefined(tmp_path: Path) -> None:
    """THE silent-wrong-answer test. A changed `preprocessor:` declaration touches no
    source file and no Doxyfile, so if the macro text reached the doxygen RUN but not the
    hash, editing the declared macros would replay the previous configuration's parse
    straight out of cache and report success — a well-formed index of the variant the
    owner just stopped declaring, with nothing anywhere saying so.

    Three hashes, not two: the unconfigured one must differ from both, and the two
    configured ones must differ from EACH OTHER. A hash that merely noticed "some macros
    exist" would pass a two-way test and still serve a stale parse on every edit after
    the first.
    """
    root = _fixture_repo(tmp_path)
    doxyfile = root / "Doxyfile"
    cache = IndexCache(tmp_path / "cache.db", Path(root))
    try:
        shas = {
            label: cache.tree_sha(doxyfile_content_for(doxyfile, predefined=text), [])
            for label, text in (
                ("none", ""),
                ("feature", doxyfile_lines(PreprocessorConfig(macros=('"FIXTURE_FEATURE_C"',)))),
                ("width", doxyfile_lines(PreprocessorConfig(macros=('"FIXTURE_WIDTH=16"',)))),
            )
        }
    finally:
        cache.close()
    assert len(set(shas.values())) == 3, (
        f"the tree hash does not distinguish these configurations: {shas}"
    )


## @brief An undeclared target's Doxyfile text is byte-identical to the pre-gh#17 text.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_no_declaration_emits_no_doxyfile_lines(tmp_path: Path) -> None:
    """The other half of inertness, and the one a build test cannot show: not merely
    that an undeclared target indexes the same rows, but that doxygen is fed the same
    BYTES. `ENABLE_PREPROCESSING` is checked by name because forcing it unconditionally
    would be an invisible policy change on every existing target.
    """
    root = _fixture_repo(tmp_path)
    content = doxyfile_content_for(root / "Doxyfile")
    assert "PREDEFINED" not in content
    assert "ENABLE_PREPROCESSING" not in content
    assert content == doxyfile_content_for(root / "Doxyfile", predefined="")


## @brief Rendered Doxyfile text appends rather than assigns, and quotes every token.
## @return None.
## @version 1
def test_rendered_lines_append_and_quote() -> None:
    """Pins the two properties the build tests depend on but cannot isolate. `+=` is the
    reason a target's own PREDEFINED survives; quoting is the reason a value containing
    a space stays ONE macro rather than becoming three entries, two of them nonsense.
    """
    text = doxyfile_lines(PreprocessorConfig(macros=('"A"', '"B=1 + 2"')))
    assert "PREDEFINED = " not in text, "assignment would discard the target's own list"
    assert 'PREDEFINED += "A"' in text
    assert 'PREDEFINED += "B=1 + 2"' in text
    assert "ENABLE_PREPROCESSING = YES" in text, "PREDEFINED has no effect without it"


# --------------------------------------------------------------------------- #
# Header harvesting, discovery, and the refusals.
# --------------------------------------------------------------------------- #


## @brief The header scan reads live defines and skips commented-out ones.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_the_header_scan_reads_only_live_defines(tmp_path: Path) -> None:
    """The mbedtls idiom is a header of top-level defines with the alternatives COMMENTED
    OUT, so skipping `//#define` and `/* #define */` is not tidiness — it is the
    difference between reading the shipped configuration and reading every configuration
    the project supports at once.
    """
    header = tmp_path / "config.h"
    header.write_text(CONFIG_HEADER, encoding="utf-8")
    macros = macros_from_header(header)
    assert '"FIXTURE_FEATURE_C"' in macros
    assert '"FIXTURE_WIDTH=16"' in macros, "a trailing block comment leaked into the value"
    assert not any("DISABLED" in m for m in macros), "a commented-out define was harvested"
    assert '"FIXTURE_CONFIG_H"' in macros, "the include guard is a define like any other"


## @brief The scan honours #undef and refuses what a line-at-a-time read cannot see.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_the_header_scan_honours_undef_and_skips_the_unreadable(tmp_path: Path) -> None:
    """Three refusals, each because a wrong answer here is worse than no answer.
    `#undef` must win, or a header that REVOKES a macro is read as defining it. A
    function-like macro is not a configuration statement. A continued macro cannot be
    read a line at a time, and half a value handed to doxygen as a whole one is a wrong
    answer wearing the shape of a right one.
    """
    header = tmp_path / "config.h"
    header.write_text(
        "#define KEPT 1\n"
        "#define REVOKED 1\n"
        "#undef REVOKED\n"
        "#define FUNCLIKE(x) ((x) + 1)\n"
        "#define CONTINUED a \\\n    b\n",
        encoding="utf-8",
    )
    names = {m.strip('"').split("=", 1)[0] for m in macros_from_header(header)}
    assert names == {"KEPT"}, f"unexpected macros harvested: {names}"


## @brief `config_header: auto` finds a single conventional header.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_auto_discovery_finds_one_conventional_header(tmp_path: Path) -> None:
    """`auto` is OPT-IN, and this is the case it exists for: a Kconfig build has written
    `include/generated/autoconf.h` and the owner wants the index to represent it without
    restating the path.
    """
    root = tmp_path / "repo"
    (root / "include" / "generated").mkdir(parents=True)
    (root / "include" / "generated" / "autoconf.h").write_text(
        "#define CONFIG_FOO 1\n", encoding="utf-8"
    )
    config = resolve_preprocessor(
        root, {SECTION_PREPROCESSOR: {"config_header": CONFIG_HEADER_AUTO}}
    )
    assert config.macros == ('"CONFIG_FOO=1"',)
    assert config.config_header == "include/generated/autoconf.h"
    assert config.source == SOURCE_CONFIG_HEADER


## @brief `config_header: auto` REFUSES when two conventional headers exist.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_auto_discovery_refuses_two_candidates(tmp_path: Path) -> None:
    """Follows `precommit._guard_config_conventional` and `discover_doxyfile`, and the
    stakes here are higher than either. Choosing the wrong config header does not merely
    index the wrong FILES — it indexes a different VARIANT of the right ones, and every
    count taken from the result still looks legitimate.

    `declared` stays True while `macros` is empty, which is the whole of part 3's value:
    the resulting zero is attributable to a refusal rather than reading as "the owner
    said nothing".
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "autoconf.h").write_text("#define FROM_AUTOCONF 1\n", encoding="utf-8")
    (root / "config.h").write_text("#define FROM_CONFIG 1\n", encoding="utf-8")
    config = resolve_preprocessor(
        root, {SECTION_PREPROCESSOR: {"config_header": CONFIG_HEADER_AUTO}}
    )
    assert config.macros == (), "discovery guessed among two candidates"
    assert config.declared, "a refusal must still record that a configuration was declared"
    assert config.searched, "a refusal must name where it looked"


## @brief Auto discovery never reaches a test/mock config header.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_auto_discovery_ignores_a_mock_config_header(tmp_path: Path) -> None:
    """Many Kconfig projects ship a hand-written mock config header for unit tests.
    Discovering it would index a configuration NOBODY SHIPS, wearing the authority of a
    recorded declaration — so no conventional location lies under a test directory, and
    a `*_config.h` glob (which gh#17 floats) is deliberately absent for the same reason.

    Naming that file explicitly still works, and is the intended escape hatch: then the
    choice was made by a person and `preprocessor.config_header` records it.
    """
    root = tmp_path / "repo"
    (root / "tests" / "include").mkdir(parents=True)
    mock = root / "tests" / "include" / "mock_config.h"
    mock.write_text("#define MOCK_ONLY 1\n", encoding="utf-8")

    discovered = resolve_preprocessor(
        root, {SECTION_PREPROCESSOR: {"config_header": CONFIG_HEADER_AUTO}}
    )
    assert discovered.macros == (), "discovery reached a mock config header"

    named = resolve_preprocessor(
        root, {SECTION_PREPROCESSOR: {"config_header": "tests/include/mock_config.h"}}
    )
    assert named.macros == ('"MOCK_ONLY=1"',), "an explicitly named header must be honoured"


## @brief A named-but-missing config header records the declaration and warns.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_missing_named_header_is_still_recorded(tmp_path: Path) -> None:
    """The misspelled-path case, and the reason `as_meta` records a macro count of ZERO
    rather than dropping it. A declaration that produced nothing is a finding; recorded
    as absent it would be indistinguishable from a repo that declared nothing at all.
    """
    root = tmp_path / "repo"
    root.mkdir()
    config = resolve_preprocessor(
        root, {SECTION_PREPROCESSOR: {"config_header": "include/typo_config.h"}}
    )
    assert config.declared
    assert config.source == SOURCE_CONFIG_HEADER
    assert config.as_meta()["macro_count"] == "0", "a measured zero must be persisted"


# --------------------------------------------------------------------------- #
# Resolution rules and provenance.
# --------------------------------------------------------------------------- #


## @brief A declared macro beats a harvested one of the same name.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_declared_macro_wins_over_the_header(tmp_path: Path) -> None:
    """Doxygen's behaviour on a duplicated PREDEFINED name is not something to rely on,
    so the collision is resolved where the rule can be stated: the owner typed one of
    these by hand and the other was read out of a file.
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "cfg.h").write_text("#define WIDTH 8\n#define ONLY_IN_HEADER 1\n", encoding="utf-8")
    config = resolve_preprocessor(
        root,
        {SECTION_PREPROCESSOR: {"predefined": ["WIDTH=16"], "config_header": "cfg.h"}},
    )
    assert '"WIDTH=16"' in config.macros
    assert '"WIDTH=8"' not in config.macros, "the header overrode a hand-written declaration"
    assert '"ONLY_IN_HEADER=1"' in config.macros, "the header's other macros were dropped"
    assert config.source == SOURCE_BOTH


## @brief Provenance distinguishes flag, declaration, header and nothing.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_provenance_names_the_source(tmp_path: Path) -> None:
    """Part 3's actual claim. Every one of these must be distinguishable in `build_meta`,
    because an index of a multi-variant codebase is an index of ONE variant and a
    consumer comparing two indexes needs to know which.
    """
    root = tmp_path / "repo"
    root.mkdir()
    assert resolve_preprocessor(root, {}).source == SOURCE_NONE
    assert resolve_preprocessor(root, {}, ["A"]).source == SOURCE_FLAG
    declared = resolve_preprocessor(root, {SECTION_PREPROCESSOR: {"predefined": ["A"]}})
    assert declared.source == SOURCE_DECLARED
    assert declared.as_meta()["predefined"] == '"A"'


## @brief A non-list `predefined:` is refused rather than iterated character by character.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_scalar_predefined_is_refused(tmp_path: Path) -> None:
    """A string here would otherwise be iterated CHARACTER BY CHARACTER into a hundred
    one-letter macros — a build that succeeds while feeding doxygen nonsense, which is
    strictly worse than ignoring the key.
    """
    root = tmp_path / "repo"
    root.mkdir()
    config = resolve_preprocessor(root, {SECTION_PREPROCESSOR: {"predefined": "FIXTURE_A"}})
    assert config.macros == (), "a scalar was coerced into per-character macros"


## @brief The section name is registered in the declaration allow-list.
## @return None.
## @version 1
def test_the_section_is_a_known_declaration_section() -> None:
    """`declaration.KNOWN_SECTIONS` spells the name as its own literal, because
    `preprocessor.py` and `declaration.py` deliberately do not import each other. This
    pins the two spellings together, exactly as the existing `index_scope` test does — an
    unregistered section is REFUSED, so a drift here would make every declaration
    carrying it fail to load.
    """
    assert SECTION_PREPROCESSOR in KNOWN_SECTIONS


## @brief A misspelled section name is refused, not silently ignored.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_misspelled_section_is_refused(tmp_path: Path) -> None:
    """The allow-list's whole purpose, checked for this section specifically.
    `preprocessors:` parses to a perfectly valid mapping that nothing reads, so the build
    would run with NO macros while the log reported the declaration was honoured — and
    here that means silently indexing a different variant than the owner declared.
    """
    from clew.vocabulary import DeclarationError

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".clew.yaml").write_text("preprocessors:\n  predefined:\n    - A\n", encoding="utf-8")
    with pytest.raises(DeclarationError, match="preprocessors"):
        load_declaration(root)


## @brief `defined_names` strips doxygen token quoting and any `=value`.
## @return None.
## @version 1
def test_defined_names_strips_quoting_and_values() -> None:
    """gh#35 asks "is X defined" of a field built to render a Doxyfile, so its entries are
    `'"NAME"'` / `'"NAME=v"'` with the quotes in the string. A caller doing that stripping
    itself is a caller that can drift; this pins the one place it happens.

    A macro defined to `0` is DEFINED — that is what `defined(X)` means — and conflating
    it with undefined would pick the wrong branch."""
    cfg = PreprocessorConfig(macros=('"MBEDTLS_THREADING_PTHREAD"', '"MBEDTLS_X=0"'))
    assert cfg.defined_names == frozenset({"MBEDTLS_THREADING_PTHREAD", "MBEDTLS_X"})


## @brief A `defined` atom is decided both ways, and negation inverts it.
## @return None.
## @version 1
def test_evaluate_condition_decides_defined_atoms() -> None:
    """The two forms real code uses, plus `#ifdef`'s normalised spelling."""
    on = frozenset({"A"})
    assert evaluate_condition("defined(A)", on) is True
    assert evaluate_condition("defined A", on) is True
    assert evaluate_condition("defined(B)", on) is False
    assert evaluate_condition("!defined(A)", on) is False
    assert evaluate_condition("!defined(B)", on) is True


## @brief AND and OR fold with C's precedence and parenthesised groups.
## @return None.
## @version 1
def test_evaluate_condition_folds_boolean_operators() -> None:
    """`||` binds looser than `&&`, so `defined(A) && defined(B) || defined(C)` is
    `(A&&B) || C`. Splitting on `&&` first would read it as `A && (B||C)` and give the
    opposite answer for A undefined, C defined."""
    on = frozenset({"A", "C"})
    assert evaluate_condition("defined(A) && defined(C)", on) is True
    assert evaluate_condition("defined(A) && defined(B)", on) is False
    assert evaluate_condition("defined(B) || defined(C)", on) is True
    assert evaluate_condition("defined(A) && defined(B) || defined(C)", on) is True
    assert evaluate_condition("defined(A) && (defined(B) || defined(C))", on) is True
    assert evaluate_condition("(defined(B) || defined(D))", on) is False
    # `(X) && (Y)` also starts with `(` and ends with `)`. A parenthesis-stripper that
    # tested only startswith/endswith would mangle it into `X) && (Y` and read UNKNOWN.
    assert evaluate_condition("(defined(A)) && (defined(C))", on) is True
    assert evaluate_condition("(defined(A)) && (defined(B))", on) is False


## @brief An expression the evaluator cannot read is UNKNOWN, never False.
## @return None.
## @version 1
def test_evaluate_condition_reports_unknown_rather_than_guessing() -> None:
    """THE LOAD-BEARING CASE for gh#35. None means "we do not know which branch is live",
    and it must never collapse to False — a False here would DELETE the live edge of every
    binding guarded by an expression this evaluator cannot parse, which is worse than the
    over-complete graph gh#35 is fixing.

    Arithmetic, comparisons, a bare `#if X` read as a value, and `__has_include` are all
    real `#if` grammar and all outside what a `defined`-only evaluator can settle."""
    on = frozenset({"A"})
    assert evaluate_condition("_POSIX_VERSION >= 200809L", on) is None
    assert evaluate_condition("A", on) is None
    assert evaluate_condition("__has_include(<foo.h>)", on) is None
    assert evaluate_condition("!(A + 1)", on) is None


## @brief UNKNOWN beside a decisive operand does not weaken a known answer.
## @return None.
## @version 1
def test_unknown_is_short_circuited_by_a_decisive_operand() -> None:
    """`defined(A) || <unreadable>` IS true when A is defined, and `defined(B) &&
    <unreadable>` IS false when B is not. Poisoning the whole expression with UNKNOWN
    would grade down edges whose branch really is determined — the false-weakening
    direction, which costs traversal in `mark_reachability` and the thread BFS."""
    on = frozenset({"A"})
    assert evaluate_condition("defined(A) || _POSIX_VERSION >= 1", on) is True
    assert evaluate_condition("defined(B) && _POSIX_VERSION >= 1", on) is False
    assert evaluate_condition("defined(B) || _POSIX_VERSION >= 1", on) is None
    assert evaluate_condition("defined(A) && _POSIX_VERSION >= 1", on) is None


## @brief The two real mbedtls guards resolve oppositely under one configuration.
## @return None.
## @version 1
def test_the_mbedtls_threading_guards_are_mutually_exclusive() -> None:
    """gh#35's filed case, as written in `library/threading.c`: line 103 binds
    `threading_mutex_lock_pthread` under `defined(MBEDTLS_THREADING_PTHREAD)` and line 127
    binds `threading_mutex_fail` under `defined(MBEDTLS_THREADING_ALT)`. Exactly one holds
    in any real build, and this is the evaluation that lets the emitter say which."""
    cfg = PreprocessorConfig(
        macros=('"MBEDTLS_THREADING_C"', '"MBEDTLS_THREADING_PTHREAD"'),
        source=SOURCE_DECLARED,
    )
    names = cfg.defined_names
    assert evaluate_condition("defined(MBEDTLS_THREADING_C)", names) is True
    assert evaluate_condition("defined(MBEDTLS_THREADING_PTHREAD)", names) is True
    assert evaluate_condition("defined(MBEDTLS_THREADING_ALT)", names) is False


## @brief With nothing declared, every guard is UNKNOWN rather than dead.
## @return None.
## @version 1
def test_an_undeclared_configuration_decides_nothing() -> None:
    """A target that declares no configuration must not have its conditional bindings
    read as dead — that would empty the layer. `defined(X)` against an empty set is
    legitimately False for the DOXYGEN parse, but for BRANCH SELECTION the honest verdict
    is that we were told nothing, which the emitter reads off `declared` rather than off
    this function."""
    cfg = PreprocessorConfig()
    assert cfg.declared is False
    assert cfg.defined_names == frozenset()


## @brief An explicit macro list overrides the macros WITHOUT discarding the declared header.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_explicit_list_keeps_the_declared_config_header(tmp_path: Path) -> None:
    """THE ACCEPTANCE BUILD DISCARDED ITS OWN DECLARED HEADER ON EVERY RUN. `resolve_preprocessor`
    returned on `if explicit:` before reading the declaration at all, so a `config_header:` stated
    in the SAME section as `predefined:` was silently dropped the moment a macro list was passed —
    and `clew/cli.py` promotes a declared `predefined:` to exactly that argument. An
    accepted-but-unread key is this project's most repeated defect; this was an instance.

    WHAT THE FLAG LEGITIMATELY OVERRIDES IS THE MACRO LIST, and that is still asserted below: the
    override wins, `source` stays `flag`, and the header is not merged into `macros`. Where the
    repository states its own defaults is a fact ABOUT THE REPOSITORY and does not become untrue
    because the operator indexed a different variant.

    THAT IS WHAT MAKES `stated_only` COMPUTABLE, which is the payoff: the overridden names the
    header does NOT define are exactly the ones that ship OFF, and that is the sentence two graded
    marks ask for.

    @brief An explicit list overrides macros and keeps the declared header and split.
    @return None.
    @version 1
    """
    root = tmp_path / "repo"
    (root / "include").mkdir(parents=True)
    (root / "include" / "config.h").write_text(
        "#define SHIPPED_ON 1\n//#define SHIPPED_OFF\n", encoding="utf-8"
    )
    declaration = {
        SECTION_PREPROCESSOR: {
            "predefined": ["SHIPPED_OFF"],
            "config_header": "include/config.h",
        }
    }

    config = resolve_preprocessor(root, declaration, explicit=["SHIPPED_OFF"])

    assert config.source == SOURCE_FLAG, "an explicit list still wins outright"
    assert config.macros == ('"SHIPPED_OFF"',), (
        f"the override must replace the macro list, not merge the header into it; got "
        f"{config.macros}"
    )
    assert config.config_header == "include/config.h", (
        "the declared header was discarded by the explicit branch — the defect this test exists "
        "for. It is a fact about the repository and survives an override of the macro list."
    )
    assert config.stated_only == ("SHIPPED_OFF",), (
        f"`stated_only` must name the overridden macros the header does not define, which is what "
        f"lets the reply say they ship OFF; got {config.stated_only}"
    )
    ## THE NEGATIVE HALF: a macro the header DOES define must not be reported as shipping off.
    both = resolve_preprocessor(root, declaration, explicit=["SHIPPED_OFF", "SHIPPED_ON"])
    assert both.stated_only == ("SHIPPED_OFF",), (
        f"SHIPPED_ON is defined in the header, so it must not be listed as operator-only; got "
        f"{both.stated_only}"
    )
