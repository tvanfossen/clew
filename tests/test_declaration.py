# SPDX-License-Identifier: MIT
"""A target repo's `.clew.yaml` declaration (task #51).

Every convention override was a CLI flag, and the MCP server passes none of them
— so through the MCP server, the primary surface, the built-in defaults WERE the
whole policy. That is precisely the hardcoded-only assumption the no-hardcoding
mandate exists to prevent.

@brief Tests for declaration.py and its CLI wiring.
@version 2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.declaration import (
    KNOWN_SECTIONS,
    SECTION_DATA_MODEL,
    SECTION_ENTRY_PATTERNS,
    SECTION_SHARED_KEY,
    SECTION_THREADS,
    declared_path,
    load_declaration,
    section,
)
from clew.shared_key_edges import load_shared_key_patterns
from clew.threads import DEFAULT_SPAWN_PATTERNS, load_thread_patterns
from clew.treescan import manifest_key


def test_absent_declaration_is_not_an_error(tmp_path: Path) -> None:
    """Most repos declare nothing and run entirely on built-in defaults, so an
    absent file is the norm rather than a failure."""
    assert load_declaration(tmp_path) == {}
    assert load_declaration(None) == {}


def test_malformed_declaration_degrades_to_defaults(tmp_path: Path) -> None:
    """A typo must not fail a build that would otherwise succeed — it warns and
    falls back, rather than taking the repo's index down with it."""
    (tmp_path / ".clew.yaml").write_text("shared_key_patterns: [oops\n", encoding="utf-8")
    assert load_declaration(tmp_path) == {}

    (tmp_path / ".clew.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    assert load_declaration(tmp_path) == {}


def test_sections_mirror_the_standalone_manifest_formats(tmp_path: Path) -> None:
    """A section holds EXACTLY what the corresponding standalone file holds, so
    a repo can move an existing manifest's contents in verbatim and the same
    parser handles both delivery routes."""
    (tmp_path / ".clew.yaml").write_text(
        "shared_key_patterns:\n"
        "  writers:\n"
        '    - name_prefix: "Store_Set_"\n'
        "  readers:\n"
        '    - name_prefix: "Store_Get_"\n'
        "thread_patterns:\n"
        "  spawns:\n"
        '    - name: "osThreadNew_wrapper"\n'
        "      entry_arg_index: 1\n",
        encoding="utf-8",
    )
    decl = load_declaration(tmp_path)

    writers, readers = load_shared_key_patterns(section(decl, SECTION_SHARED_KEY))
    assert len(writers) == 1
    assert len(readers) == 1

    spawns = load_thread_patterns(section(decl, SECTION_THREADS))
    names = {p.name for p in spawns}
    # The declared wrapper is MERGED over the defaults, never replacing them.
    assert "osThreadNew_wrapper" in names
    assert {p.name for p in DEFAULT_SPAWN_PATTERNS} <= names


def test_declared_path_section_resolves_relative_to_the_repo(tmp_path: Path) -> None:
    """Formats that are not YAML (the ingot data-model TOML) are NAMED by the
    section rather than inlined; the path stays repo-relative so the
    declaration is portable."""
    (tmp_path / "model.toml").write_text("", encoding="utf-8")
    decl = {SECTION_DATA_MODEL: "model.toml"}
    assert declared_path(decl, SECTION_DATA_MODEL, tmp_path) == (tmp_path / "model.toml").resolve()

    # Declared but missing warns and yields None rather than failing the build.
    assert declared_path({SECTION_DATA_MODEL: "gone.toml"}, SECTION_DATA_MODEL, tmp_path) is None
    assert declared_path({}, SECTION_DATA_MODEL, tmp_path) is None


def test_inline_manifest_still_busts_the_stage_cache(tmp_path: Path) -> None:
    """manifest_key folds a manifest's CONTENT into the affected stage's cache
    key. A declaration delivered as a mapping must hash the same way a file
    does, or editing `.clew.yaml` would silently reuse stale extractions."""
    a = {"writers": [{"name_prefix": "A_"}]}
    b = {"writers": [{"name_prefix": "B_"}]}
    assert manifest_key(a) == manifest_key(dict(a)), "hash must be content-stable"
    assert manifest_key(a) != manifest_key(b), "a changed declaration must invalidate"
    assert manifest_key(None) == ""


def test_explicit_flag_wins_over_the_declaration(tmp_path: Path) -> None:
    """The file is the repo's standing statement; a flag is a deliberate
    one-off override, so the flag takes precedence."""
    from clew.cli import _declared_or_flag

    decl = {SECTION_SHARED_KEY: {"writers": [{"name_prefix": "FROM_DECL_"}]}}
    explicit = tmp_path / "patterns.yaml"
    explicit.write_text("writers: []\n", encoding="utf-8")

    assert _declared_or_flag(str(explicit), decl, SECTION_SHARED_KEY) == explicit.resolve()
    assert _declared_or_flag(None, decl, SECTION_SHARED_KEY) == decl[SECTION_SHARED_KEY]
    assert _declared_or_flag(None, {}, SECTION_SHARED_KEY) is None


def test_entry_patterns_declaration_replaces_the_guesses_not_the_facts() -> None:
    """#34: a repo whose handlers are reached only through indirect dispatch has
    no static caller for them, so liveness marks them orphan. Naming that
    convention reclaims them — measured on a C++ codebase, declaring its dispatch naming
    takes orphans from 61 to 17, and the survivors (now_ms, parse_bool,
    read_file, slurp) are genuine utility leaves.

    REWRITTEN FOR gh#319, and the old contract is what the rewrite is about. This
    test used to assert that a declaration EXTENDS the whole default set while an
    explicit flag REPLACES it — two different meanings of "supersede" for one
    setting, so moving a value from `.clew.yaml` onto the command line
    silently dropped `main`, `app_main` and every guess with them. Its final line
    (`_entry_patterns(explicit, decl) == ["only_this"]`) PINNED that collapse as
    intended behaviour.

    Both stated tiers now displace only the tier-5 name-shape guesses, and the
    tier-3 language/platform entry points accumulate beneath whatever is stated.
    The full rule is exercised in tests/test_tiers.py; this keeps the
    declaration-shaped case where the declaration format is tested."""
    import argparse

    from clew.cli import _entry_patterns
    from clew.reachability import DEFAULT_ENTRY_PATTERNS, ENTRY_PATTERN_FACTS

    args = argparse.Namespace(entry_patterns=None)
    decl = {SECTION_ENTRY_PATTERNS: ["%trampoline%", "dispatch_%"]}

    declared = _entry_patterns(args, decl)
    assert set(ENTRY_PATTERN_FACTS) <= set(declared.values), "facts must survive"
    assert "%trampoline%" in declared.values and "dispatch_%" in declared.values
    assert "%init%" not in declared.values, "a declaration replaces the guesses"

    # No declaration: exactly the defaults, unchanged.
    assert list(_entry_patterns(args, {}).values) == DEFAULT_ENTRY_PATTERNS

    # An explicit flag beats the declaration — and still cannot drop a fact.
    explicit = argparse.Namespace(entry_patterns=["only_this"])
    assert list(_entry_patterns(explicit, decl).values) == [*ENTRY_PATTERN_FACTS, "only_this"]


def test_string_list_section_ignores_a_malformed_value(tmp_path: Path) -> None:
    """A non-list value degrades to 'declared nothing' with a warning rather
    than being coerced — seeding something unintended into reachability would
    mark genuinely dead code live, which is worse than a false orphan."""
    from clew.declaration import string_list

    assert string_list({SECTION_ENTRY_PATTERNS: ["a", "b"]}, SECTION_ENTRY_PATTERNS) == ["a", "b"]
    assert string_list({SECTION_ENTRY_PATTERNS: "not a list"}, SECTION_ENTRY_PATTERNS) == []
    assert string_list({SECTION_ENTRY_PATTERNS: {"k": "v"}}, SECTION_ENTRY_PATTERNS) == []
    assert string_list({}, SECTION_ENTRY_PATTERNS) == []


# ─── a misspelled section is refused, not silently defaulted ─────────────────


def test_an_unknown_section_is_refused(tmp_path: Path) -> None:
    """The no-hardcoding mandate's worst case, closed at document level.

    A singular/plural slip parses to valid YAML that NO consumer reads, so the
    build ran entirely on built-in defaults — while `load_declaration` logged
    "declares shared_key_pattern" and told the owner the file was honoured.
    Substituting our assumptions for a declaration the author did write, and
    reporting success, is precisely what the mandate forbids.

    `dispatch.py::_reject_unknown` closed this one level down; this lifts it to the
    document, which is where the quietest slips live."""
    import pytest

    from clew.declaration import load_declaration
    from clew.vocabulary import DeclarationError

    (tmp_path / ".clew.yaml").write_text(
        "shared_key_pattern:\n  - prefix: Store_Set\nthread_pattern:\n  - name: spawn\n",
        encoding="utf-8",
    )
    with pytest.raises(DeclarationError) as exc:
        load_declaration(tmp_path)

    message = str(exc.value)
    assert "shared_key_pattern" in message and "thread_pattern" in message
    assert "shared_key_patterns" in message, "the refusal must name the ALLOWED spellings"


def test_every_known_section_is_accepted(tmp_path: Path) -> None:
    """The negative control. Without it the refusal above would pass just as
    happily against a loader that rejected everything, and a declaration format
    nobody can use is worse than one that mis-reads a typo."""
    from clew.declaration import KNOWN_SECTIONS, load_declaration

    body = "".join(f"{section}: []\n" for section in sorted(KNOWN_SECTIONS))
    (tmp_path / ".clew.yaml").write_text(body, encoding="utf-8")

    assert set(load_declaration(tmp_path)) == set(KNOWN_SECTIONS)


# ─── event_tags: a mis-typed ROLE is refused, not defaulted ──────────────────


def test_a_declared_event_tag_vocabulary_is_read_and_normalised(tmp_path: Path) -> None:
    """The accessor's happy path, and the reason the section exists: a repo whose
    bus is documented `@broadcasts`/`@reacts` had no way to say so, because
    `import_event_edges` took the vocabulary as a parameter no caller passed."""
    from clew.declaration import declared_event_tags
    from clew.event_edges import CONSUMER, PRODUCER

    decl = {"event_tags": {"Broadcasts": "Producer", "reacts": "consumer"}}
    assert declared_event_tags(decl) == {"broadcasts": PRODUCER, "reacts": CONSUMER}

    # Undeclared is None, NOT {} — the importer's parameter distinguishes them, and
    # only None means "keep the built-in verbs".
    assert declared_event_tags({}) is None
    assert declared_event_tags({"event_tags": {}}) is None
    assert declared_event_tags({"event_tags": []}) is None


def test_an_unknown_event_role_is_refused(tmp_path: Path) -> None:
    """FAIL CLOSED, one level below the section allow-list. Degrading a misspelled
    `producers:` to a default would file an emitter as a handler, and a REVERSED
    edge is worse than a missing one: these rows carry `declared=1` and
    `confidence='high'` because an author asserted them, so `chain_trace` would
    report causality flowing the wrong way with the strongest grading the pipeline
    can give."""
    from clew.declaration import declared_event_tags
    from clew.vocabulary import DeclarationError

    with pytest.raises(DeclarationError) as exc:
        declared_event_tags({"event_tags": {"broadcasts": "producers"}})

    message = str(exc.value)
    assert "broadcasts" in message, "the refusal must name the offending tag"
    assert "producer" in message and "consumer" in message, "and the allowed roles"


def test_the_index_scope_spelling_cannot_drift() -> None:
    """`index_scope` is owned by `scope.py` but repeated as a literal in
    `declaration.py`'s allow-list, because neither module imports the other.

    Duplicated spellings drift silently — that is the whole lesson of
    `vocabulary.py`, which centralised 26 restated CHECK constraints. This pins the
    two together so a rename in one place fails here instead of making every
    `index_scope:` declaration a refused unknown section."""
    from clew.declaration import KNOWN_SECTIONS
    from clew.scope import INDEX_SCOPE_SECTION

    assert INDEX_SCOPE_SECTION in KNOWN_SECTIONS


def test_declaration_can_live_in_the_guard_config_passthrough(tmp_path: Path) -> None:
    """The owner's call: "doxygen-guard.yaml should have a -x option for us to pass
    relevant args in now."

    doxygen-guard reserves the `x-` prefix for consumers (`config --schema` reports
    `passthrough_prefix: "x-"` at contract_version 2) and `load_config` preserves such keys
    verbatim. So a repo declares in the ONE file it already maintains for the gate, and
    needs no file that exists only for this tool.

    Every alternative shape was rejected on its own merits and it is worth recording why,
    because each looks reasonable alone: args-only cannot work (the MCP server has no argv —
    the hole `.clew.yaml` was created to close), a second checked-in file is
    maintenance the owner does not want, and a file under our state directory is INVISIBLE,
    which is worse than maintained."""
    (tmp_path / ".doxygen-guard.yaml").write_text(
        "validate:\n"
        "  tags:\n"
        "    req:\n"
        "      pattern: '^REQ-X-[A-Z]+-[0-9]{3}$'\n"
        "x-clew:\n"
        "  index_scope:\n"
        "    include: ['^src/']\n",
        encoding="utf-8",
    )
    declared = load_declaration(tmp_path)
    assert declared.get("index_scope") == {"include": ["^src/"]}


def test_a_dedicated_declaration_file_wins_over_the_passthrough(tmp_path: Path) -> None:
    """Precedence, matching every other rule here: the MORE SPECIFIC declaration wins
    (CLI flag > declaration file > guard passthrough > guard config > Doxyfile). A repo
    carrying both is stating that the dedicated file is the one it maintains."""
    (tmp_path / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  index_scope:\n    include: ['^from-guard/']\n", encoding="utf-8"
    )
    (tmp_path / ".clew.yaml").write_text(
        "index_scope:\n  include: ['^from-dedicated/']\n", encoding="utf-8"
    )
    assert load_declaration(tmp_path)["index_scope"] == {"include": ["^from-dedicated/"]}


def test_an_unknown_section_in_the_passthrough_is_still_refused(tmp_path: Path) -> None:
    """A misspelling is as quiet in the passthrough as in the dedicated file — it parses,
    nothing reads it, and the build runs on built-in defaults while reporting the
    declaration was honoured. The document-level allow-list must therefore apply to BOTH
    sources, not just the one it was written for."""
    (tmp_path / ".doxygen-guard.yaml").write_text(
        "x-clew:\n  thread_pattern:\n    spawns: []\n", encoding="utf-8"
    )
    from clew.vocabulary import DeclarationError

    with pytest.raises(DeclarationError, match="unknown section"):
        load_declaration(tmp_path)


def test_a_guard_config_without_a_passthrough_declares_nothing(tmp_path: Path) -> None:
    """The common case: a repo runs the gate and has never heard of this tool. It must get
    built-in defaults silently, not a warning and not an error."""
    (tmp_path / ".doxygen-guard.yaml").write_text("validate:\n  exclude: []\n", encoding="utf-8")
    assert load_declaration(tmp_path) == {}


## @brief A stated declaration document identifies itself in build_meta by content.
## @return None.
## @version 1
def test_stated_document_meta_identifies_the_document_by_content(tmp_path: Path) -> None:
    """WHY THIS EXISTS AT ALL, because the obvious alternative was tried and shipped broken.
    `options.*` records which TIER won per option, and it CANNOT answer "was this document
    applied". Measured on mbedtls 2026-08-14: one document declaring `locks`, `vendored` and
    `preprocessor` produced an index reading `options.locks.tier=explicit` (replayed from an
    older build), `options.predefined.tier=heuristic`, and no vendored row at all. Every reader
    reported health and a graded run was invalid.
    """
    from clew.declaration import stated_document_meta

    raw = b"vendored:\n  - 3rdparty\nlocks:\n  locks: []\n"
    meta = stated_document_meta(raw, {"vendored": ["3rdparty"], "locks": {}})
    assert meta["stated_sections"] == "locks, vendored", "sections must be SORTED, not file order"
    assert len(meta["stated_sha256"]) == 64

    ## CONTENT-ADDRESSED: one byte's difference must produce a different identity, or a document
    ## edited after the build that stated it would still certify as applied — which is the
    ## quieter half of the defect above.
    other = stated_document_meta(raw + b"\n", {"vendored": ["3rdparty"], "locks": {}})
    assert other["stated_sha256"] != meta["stated_sha256"]
    assert other["stated_sections"] == meta["stated_sections"], (
        "the SECTION LIST is unchanged by a whitespace edit, which is why the sha is the "
        "load-bearing half rather than the section names"
    )

    ## NO PATH ANYWHERE IN IT. A stated document lives in the consumer's tree, so a path here
    ## publishes the builder's machine layout through every MCP reply.
    assert not any("/" in value for value in meta.values()), f"a path leaked into {meta}"


## @brief The build records which document was stated, and records nothing when none was.
## @return None.
## @version 1
def test_build_meta_records_the_stated_declaration(tmp_path: Path) -> None:
    """Both halves. A recorded document is what makes the harness gate possible; an ABSENT
    section is what makes "no document was stated" honestly readable, rather than presenting as
    a statement that was made and was blank.
    """
    import sqlite3

    from clew.signature import write_build_signature

    db = tmp_path / "clew.db"
    write_build_signature(db, declaration={"stated_sha256": "ab" * 32, "stated_sections": "locks"})
    conn = sqlite3.connect(str(db))
    held = dict(conn.execute("SELECT key, value FROM build_meta"))
    conn.close()
    assert held["declaration.stated_sha256"] == "ab" * 32
    assert held["declaration.stated_sections"] == "locks"

    db2 = tmp_path / "plain.db"
    write_build_signature(db2)
    conn = sqlite3.connect(str(db2))
    held2 = dict(conn.execute("SELECT key, value FROM build_meta"))
    conn.close()
    assert not [k for k in held2 if k.startswith("declaration.")], (
        "a build with no stated document must write NO declaration row — the harness gate reads "
        "absence as 'not stated', so a placeholder row would certify a policy nobody stated"
    )


## @brief A declared Doxyfile is used; a declared path that is not there REFUSES.
## @return None.
## @version 1
def test_a_declared_doxyfile_is_reachable_and_a_missing_one_refuses(tmp_path: Path) -> None:
    """gh#420. `discover_doxyfile` matches the NAME `Doxyfile` in the repo root, `docs/` and
    `doc/` and refuses to guess further, because it was once caught selecting a test FIXTURE's
    Doxyfile to index a whole project. Mbed-TLS ships `doxygen/mbedtls.doxyfile` — wrong
    directory AND wrong filename — so it was unreachable from discovery, and until this section
    existed there was no way to state it either. `--doxyfile` could name it on one command line,
    which is the shape the mandate calls not-a-declaration: unrecorded, unreplayed, and
    unreachable from the MCP surface.

    BOTH HALVES, and the second is the fail-closed one. A stated path that is not a file must
    refuse rather than fall through to whole-repo synthesis, because synthesis is a LEGITIMATE
    build — so the result would be a well-formed index of a different thing, reporting success.
    That is why `doxyfile` is in `PATH_OPTIONS_MUST_EXIST` while `requirements` is not: a missing
    catalog degrades to empty metadata over the same rows, a missing Doxyfile changes which
    source is compiled in.
    """
    from types import SimpleNamespace

    from clew.buildoptions import BuildOptionError, apply_options
    from clew.declaration import SECTION_DOXYFILE

    assert SECTION_DOXYFILE in KNOWN_SECTIONS, "declarable, or the document-level gate refuses it"

    doxydir = tmp_path / "doxygen"
    doxydir.mkdir()
    (doxydir / "mbedtls.doxyfile").write_text(
        "INPUT = ../include\nFILE_PATTERNS = *.h\n", encoding="utf-8"
    )

    ## RESOLVED AGAINST THE REPO ROOT, not the process's cwd — an MCP server's cwd is not the
    ## target repo, and the declaration states the path an author would write in-tree.
    args = SimpleNamespace()
    applied = apply_options(args, {SECTION_DOXYFILE: "doxygen/mbedtls.doxyfile"}, tmp_path)
    assert applied == [SECTION_DOXYFILE]
    assert Path(args.doxyfile) == doxydir / "mbedtls.doxyfile"

    ## AND THE REFUSAL NAMES THE PATH. A typo'd declaration silently indexing the whole repo is
    ## the "wrong answer beats no answer" failure this whole section is shaped around.
    with pytest.raises(BuildOptionError) as refusal:
        apply_options(SimpleNamespace(), {SECTION_DOXYFILE: "doxygen/typo.doxyfile"}, tmp_path)
    assert "typo.doxyfile" in str(refusal.value)

    ## THE CONTRAST THAT JUSTIFIES THE SET: a missing `requirements` catalog is NOT refused here,
    ## because each loader reports its own absent document with the context to say what it was for.
    ok = SimpleNamespace()
    assert apply_options(ok, {"requirements": "nope.yaml"}, tmp_path) == ["requirements"]
