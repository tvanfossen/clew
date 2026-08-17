# SPDX-License-Identifier: MIT
"""TIER 1, REACHABLE — gh#332.

Two tests carry the change. `test_nothing_stated_changes_nothing` is the control: a
surface that cannot be silent would rewrite the policy of every build that ignores it.
`test_one_bad_entry_applies_nothing` is the property that makes a refusal worth having —
a partially-applied policy builds with a mixture of what was asked for and what was not,
and reports success.

The rest are the fail-closed cases, and they are split by LEVEL on purpose. A misspelled
section is loud; an out-of-vocabulary ROLE parses into a perfectly valid mapping that no
consumer reads, which is the quiet half and the one CLAUDE.md records eating a whole
dataflow layer through `key_arg_idx` for `key_arg_index`.

gh#360 adds the INLINE form of the six manifest options and its tests are the same shape,
one level in. The marquee case is `test_a_misspelled_entry_field_is_refused`: `key_arg_idx`
for `key_arg_index` is the exact slip CLAUDE.md records as the quiet one, and the loaders
cannot catch it because `entry.get(name, default)` cannot tell a misspelling from an
omission. The control beside it is that the PATH form still behaves identically — the
reversal adds a route and must not change the one an operator already uses.

@brief Tests for the tier-1 build options surface.
@version 2
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from clew import buildoptions as bo


## @brief A namespace carrying the dests the real parser defines, all unset.
## @return An argparse.Namespace with None/empty defaults.
## @version 1
def _args() -> argparse.Namespace:
    """Deliberately does NOT define `event_tags`: the real parser has no such flag, so a
    test that pre-seeded the attribute would hide whether `apply_options` creates it — and
    that attribute's absence is the whole reason the key needed a route.

    @brief A bare argument namespace.
    @return The namespace.
    @version 1
    """
    return argparse.Namespace(
        entry_patterns=None,
        predefined=None,
        shared_key_patterns=None,
        thread_patterns=None,
        locks=None,
        dispatch=None,
        mqtt_dispatch=None,
        data_model=None,
    )


# ─── the control: an unstated option changes nothing ──────────────────────────


## @brief None and {} both leave every setting alone.
## @return None.
## @version 1
def test_nothing_stated_changes_nothing() -> None:
    """THE CONTROL ON THE WHOLE SURFACE. Every caller that does not care about options
    forwards its own optional argument, so if this path assigned anything — a default, an
    empty list — it would silently replace the target's declaration on every ordinary
    refresh. That is the exact shape of the `exclude=None` bug this repo already fixed one
    layer up, where normalising None to [] turned every refresh into a withdrawal.

    @brief An unstated option list is a no-op.
    @version 1
    """
    for stated in (None, {}):
        args = _args()
        assert bo.apply_options(args, stated, Path("/repo")) == []
        assert args.entry_patterns is None
        assert not hasattr(args, "event_tags")


# ─── fail closed: the document level ──────────────────────────────────────────


## @brief An unknown section is refused by name, and the message lists what is accepted.
## @return None.
## @version 1
def test_an_unknown_option_is_refused_by_name() -> None:
    """Naming the accepted set in the message is the load-bearing half. "unknown option"
    alone leaves a caller guessing at a vocabulary they cannot see, and this surface exists
    precisely so an agent does not have to guess.

    @brief An unknown key raises, naming itself and the accepted set.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError) as caught:
        bo.apply_options(_args(), {"lock_patterns": "locks.yaml"}, Path("/repo"))

    assert "lock_patterns" in str(caught.value)
    assert "locks" in str(caught.value), "the message must list the accepted keys"


## @brief A correctly-spelled DERIVED key is refused with the reason, not as unknown.
## @return None.
## @version 1
def test_a_derived_option_is_refused_with_its_reason() -> None:
    """`key_alias_prefixes` is resolved FROM the shared-key document plus the ecosystem
    defaults. Reporting it as "unknown" would send the reader hunting a typo in a key that
    is spelled correctly and simply is not theirs to set — this repo's recorded phantom-hunt
    shape, where a wrong label cost a real debugging detour.

    @brief A derived key raises with an explanation.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError) as caught:
        bo.apply_options(_args(), {"key_alias_prefixes": ["DM_KEY_"]}, Path("/repo"))

    message = str(caught.value)
    assert "cannot be stated" in message
    assert "shared_key_patterns" in message, "say what to state instead"
    assert "unknown" not in message, "a correctly-spelled key must not read as a typo"


# ─── fail closed: the entry level, which is the quiet one ─────────────────────


## @brief An out-of-vocabulary event role is refused rather than stored.
## @return None.
## @version 1
def test_a_bad_event_role_is_refused_not_stored() -> None:
    """THE QUIET LEVEL. `{"broadcasts": "produce"}` is a valid mapping, so without this
    check the build succeeds, the bus stays undeclared, and the gh#320 diagnostics report
    `broadcasts` as an unclaimed alias while the caller believes they claimed it — a
    disagreement between two surfaces with nothing to explain it.

    @brief An unrecognised role raises, naming the entry and the accepted roles.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError) as caught:
        bo.apply_options(_args(), {"event_tags": {"broadcasts": "produce"}}, Path("/repo"))

    message = str(caught.value)
    assert "broadcasts='produce'" in message, "name the offending entry, not just the key"
    assert "producer" in message and "consumer" in message


## @brief A bare string for a list option is refused, not silently split into characters.
## @return None.
## @version 1
def test_a_bare_string_is_not_accepted_as_a_list() -> None:
    """`list("app_main")` is eight single-character entry patterns, every one of which
    matches nothing — a policy that is silently and completely wrong while looking populated.

    @brief A string where a list belongs raises.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError, match="list of strings"):
        bo.apply_options(_args(), {"entry_patterns": "app_main"}, Path("/repo"))


## @brief Validation completes before any assignment.
## @return None.
## @version 1
def test_one_bad_entry_applies_nothing() -> None:
    """A half-applied policy builds with a mixture of what the caller stated and what they
    did not, and reports success. Iteration order makes this a real risk rather than a
    theoretical one: the valid key here is accepted FIRST, so a loop that assigned as it
    went would leave it set.

    @brief A rejected mapping leaves the namespace untouched.
    @version 1
    """
    args = _args()

    with pytest.raises(bo.BuildOptionError):
        bo.apply_options(
            args,
            {"entry_patterns": ["app_main"], "event_tags": {"reacts": "nonsense"}},
            Path("/repo"),
        )

    assert args.entry_patterns is None, "a refused mapping must apply NOTHING"


# ─── what a valid statement does ──────────────────────────────────────────────


## @brief Inline options land on their dests, including one the parser never defines.
## @return None.
## @version 1
def test_inline_options_are_applied_including_event_tags() -> None:
    """`event_tags` is the key that proves the gap gh#332 closes: there is deliberately no
    `--event-tags` flag, so the attribute does not exist until this creates it. Before, the
    only way to state a bus vocabulary was to edit the target repository's own tree — which
    an operator indexing someone else's dependency cannot reasonably do.

    @brief Inline options are applied and event_tags is created.
    @version 1
    """
    args = _args()

    applied = bo.apply_options(
        args,
        {
            "entry_patterns": ["app_main", "task_*"],
            "predefined": ["MBEDTLS_SSL_PROTO_TLS1_3"],
            "event_tags": {"broadcasts": "producer", "reacts": "consumer"},
        },
        Path("/repo"),
    )

    assert applied == ["entry_patterns", "event_tags", "predefined"]
    assert args.entry_patterns == ["app_main", "task_*"]
    assert args.event_tags == {"broadcasts": "producer", "reacts": "consumer"}


## @brief A relative document path resolves against the REPO, not the caller's cwd.
## @return None.
## @version 1
def test_a_relative_path_resolves_against_the_repo_root() -> None:
    """An embedding server's working directory is not the target repository, so resolving
    against the process cwd would silently look for the document somewhere the operator
    never meant — and the loader's "file not found" would name a path the caller did not
    write. An absolute path is left alone.

    @brief Relative paths resolve under repo_root; absolute ones are untouched.
    @version 1
    """
    args = _args()

    bo.apply_options(
        args,
        {"shared_key_patterns": "cfg/keys.yaml", "locks": "/etc/locks.yaml"},
        Path("/repo"),
    )

    assert args.shared_key_patterns == "/repo/cfg/keys.yaml"
    assert args.locks == "/etc/locks.yaml", "an absolute path is the caller's own"


# ─── gh#360: a manifest may be STATED, not only pointed at ────────────────────


## @brief An inline manifest document reaches the dest unchanged.
## @return None.
## @version 1
def test_a_manifest_may_be_stated_inline() -> None:
    """THE REVERSAL. Before this, an agent that wanted to declare accessor patterns had to
    Write a YAML file somewhere — impossible inside a third-party repo it must leave
    byte-identical, and untracked (or `git clean`ed) anywhere else. The document is passed
    through as the mapping every loader already accepts for the declaration route, so no
    file exists at any point.

    @brief A stated document lands on its dest as a mapping.
    @version 1
    """
    args = _args()

    applied = bo.apply_options(
        args,
        {"shared_key_patterns": {"writers": [{"name_prefix": "Store_Set"}]}},
        Path("/repo"),
    )

    assert applied == ["shared_key_patterns"]
    assert args.shared_key_patterns == {"writers": [{"name_prefix": "Store_Set"}]}


## @brief The path form is unchanged by the inline form existing.
## @return None.
## @version 1
def test_the_path_form_still_works_for_a_manifest() -> None:
    """THE CONTROL ON THE REVERSAL. The decision being reversed was right about an operator
    with a shell — a recorded path is reproducible — so the new route must be additive. If
    this ever fails, the reversal has cost the case the original decision was made for.

    @brief A stated path is still resolved as a path.
    @version 1
    """
    args = _args()

    bo.apply_options(args, {"thread_patterns": "cfg/threads.yaml"}, Path("/repo"))

    assert args.thread_patterns == "/repo/cfg/threads.yaml"


## @brief A misspelled ENTRY field is refused rather than silently defaulted.
## @return None.
## @version 1
def test_a_misspelled_entry_field_is_refused() -> None:
    """THE QUIET LEVEL, AND THE WHOLE REASON THE INLINE FORM IS VALIDATED HARDER THAN A FILE.
    `key_arg_idx` parses to a perfectly valid mapping; `load_shared_key_patterns` reads
    `entry.get("key_arg_index", 0)`, so the misspelling is indistinguishable from an omission
    and the whole dataflow layer is keyed off argument 0 — with the build reporting success
    and the edges looking legitimate. Nothing downstream can catch this, which is why it is
    caught here.

    @brief An unknown entry key raises, naming it and the allowed set.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError) as caught:
        bo.apply_options(
            _args(),
            {"shared_key_patterns": {"writers": [{"pattern": "S_*", "key_arg_idx": 1}]}},
            Path("/repo"),
        )

    message = str(caught.value)
    assert "key_arg_idx" in message, "name the offending field"
    assert "key_arg_index" in message, "and the spelling that would have worked"
    assert "writers[1]" in message, "and where it sits, since a list has many entries"


## @brief A misspelled top-level key inside an inline manifest is refused.
## @return None.
## @version 1
def test_an_unknown_document_key_in_an_inline_manifest_is_refused() -> None:
    """The singular/plural slip one level in: `writer:` for `writers:` is a valid mapping
    that no consumer reads, so the build runs entirely on built-in defaults while reporting
    that the statement was honoured. Same refusal `declaration.load_declaration_located`
    makes for a section name.

    @brief An unknown document key raises, naming the allowed set.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError) as caught:
        bo.apply_options(
            _args(),
            {"shared_key_patterns": {"writer": [{"name_prefix": "S_"}]}},
            Path("/repo"),
        )

    message = str(caught.value)
    assert "'writer'" in message
    assert "writers" in message and "readers" in message


## @brief A `key_alias_prefixes` list beside the two entry lists is accepted.
## @return None.
## @version 1
def test_a_documents_non_entry_key_is_accepted() -> None:
    """THE NEGATIVE HALF of the document-level gate, and it is the half that would have
    shipped a false refusal: `shared_key_patterns` legitimately carries a
    `key_alias_prefixes` list of strings beside `writers`/`readers`, so deriving the allowed
    document keys from the entry schemas would reject a correct statement.

    @brief A valid non-entry document key passes.
    @version 1
    """
    args = _args()
    stated = {"writers": [{"name_prefix": "S_"}], "key_alias_prefixes": ["DM_KEY_"]}

    bo.apply_options(args, {"shared_key_patterns": stated}, Path("/repo"))

    assert args.shared_key_patterns == stated


## @brief An entry missing its required key is refused, not skipped.
## @return None.
## @version 1
def test_an_entry_missing_its_required_key_is_refused() -> None:
    """`load_thread_patterns` does `if not name: continue` — a spawn entry whose `name` is
    misspelled or absent is DROPPED silently, so a caller who declared three wrappers gets
    two and no message. The refusal turns that into an error the caller can act on.

    @brief A required key that is absent raises.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError, match="missing required key"):
        bo.apply_options(
            _args(),
            {"thread_patterns": {"spawns": [{"entry_arg_index": 0}]}},
            Path("/repo"),
        )


## @brief An accessor entry declaring neither convention is refused.
## @return None.
## @version 1
def test_an_accessor_entry_with_neither_convention_is_refused() -> None:
    """An entry is EITHER the argument-based convention (`pattern`) or the name-based one
    (`name_prefix`). One with neither parses, is loaded, and matches nothing — an accessor
    layer that is present, empty and indistinguishable from a repo with no dataflow.

    @brief An entry declaring none of its either/or keys raises.
    @version 1
    """
    with pytest.raises(bo.BuildOptionError, match="declares none of"):
        bo.apply_options(
            _args(),
            {"shared_key_patterns": {"readers": [{"dispatch_mode": "queued"}]}},
            Path("/repo"),
        )


## @brief `dispatch` carries no local schema, because its own loader is stricter.
## @return None.
## @version 1
def test_dispatch_is_validated_by_its_own_loader_not_a_second_copy() -> None:
    """A second copy of the dispatch schema here would be free to drift from the parser that
    reads it, and a drifted allow-list refuses correct declarations. `load_dispatch_manifest`
    already refuses an unknown key at the document level and inside each of its three entry
    shapes, so the absence of an entry in `MANIFEST_SCHEMAS` is a decision — asserted here
    together with the refusal that justifies it, so removing one without the other fails.

    @brief The dispatch document is refused by its own loader.
    @version 1
    """
    from clew.dispatch import load_dispatch_manifest
    from clew.vocabulary import DeclarationError

    assert "dispatch" not in bo.MANIFEST_SCHEMAS
    assert "dispatch" in bo.MANIFEST_OPTIONS

    args = _args()
    bo.apply_options(args, {"dispatch": {"interfacs": []}}, Path("/repo"))

    with pytest.raises(DeclarationError, match="interfacs"):
        load_dispatch_manifest(args.dispatch)


## @brief An empty stated document is a withdrawal, not a statement.
## @return None.
## @version 1
def test_an_empty_stated_document_falls_back_to_the_declaration() -> None:
    """The absent/empty/replaces convention `--exclude` and `--entry-patterns` keep, at the
    per-option level. `{}` is falsy, so `cli._declared_or_flag` falls through to the target's
    own declaration — which is the only way to undo a statement without deleting anything.

    @brief An empty document yields the declared section.
    @version 1
    """
    from clew.cli import _declared_or_flag
    from clew.declaration import SECTION_SHARED_KEY

    declared = {"writers": [{"name_prefix": "FROM_DECL_"}]}
    decl = {SECTION_SHARED_KEY: declared}

    args = _args()
    bo.apply_options(args, {"shared_key_patterns": {}}, Path("/repo"))

    assert _declared_or_flag(args.shared_key_patterns, decl, SECTION_SHARED_KEY) == declared


## @brief A stated document is handed to the loaders unchanged, beating the declaration.
## @return None.
## @version 1
def test_a_stated_document_beats_the_declaration_and_reaches_the_loader() -> None:
    """The end of the wire, checked rather than assumed: `_declared_or_flag` must pass a
    stated MAPPING through instead of calling `Path()` on it, and the real loader must parse
    it. Without both halves the option validates cleanly and then crashes the build (or
    worse, is quietly ignored).

    @brief A stated document wins and parses.
    @version 1
    """
    from clew.cli import _declared_or_flag
    from clew.declaration import SECTION_SHARED_KEY
    from clew.shared_key_edges import load_shared_key_patterns

    decl = {SECTION_SHARED_KEY: {"writers": [{"name_prefix": "FROM_DECL_"}]}}
    args = _args()
    bo.apply_options(
        args,
        {"shared_key_patterns": {"writers": [{"name_prefix": "STATED_"}]}},
        Path("/repo"),
    )

    resolved = _declared_or_flag(args.shared_key_patterns, decl, SECTION_SHARED_KEY)
    writers, readers = load_shared_key_patterns(resolved)

    assert [w.prefix for w in writers] == ["STATED_"]
    assert readers == []


## @brief Every accepted key is reachable, so the sketch and the code cannot drift.
## @param tmp_path pytest temp dir, holding real files for the must-exist path options.
## @return None.
## @version 3
def test_every_accepted_option_can_actually_be_applied(tmp_path: Path) -> None:
    """A key listed as accepted and then unhandled would raise "unknown" for a name this
    module itself advertises — the contradiction a reader has no way to diagnose. Driving
    the whole advertised set through the real function is the only check that cannot
    disagree with the advertisement.

    @brief The accepted set is exactly the appliable set.
    @version 2
    """
    ## DERIVED from `INLINE_LIST_OPTIONS` rather than listed, because listing them made this
    ## gate fail on the NEXT one added rather than on the defect it exists to catch: `vendored`
    ## arrived as an accepted option with no sample here, and the assertion reported "the
    ## advertised set must be complete" — true, but about this fixture rather than about the
    ## code. Every list-shaped option now gets a sample for free.
    values: dict[str, object] = {name: ["X"] for name in bo.INLINE_LIST_OPTIONS}
    values["event_tags"] = {"emits": "producer"}
    for key in (*bo.PATH_OPTIONS, *bo.MANIFEST_OPTIONS):
        values[key] = f"{key}.yaml"
    ## gh#382's category. A stated SECTION is the whole declaration document, so the sample
    ## is a mapping — and it deliberately carries a LIST value, which is what caught
    ## `_checked_mapping` being borrowed here: that validator requires every value to be an
    ## event ROLE and raised `TypeError: unhashable type: 'list'` on a valid section.
    for key in bo.SECTION_DOCUMENT_OPTIONS:
        values[key] = {"predefined": ["X"]} if key == "preprocessor" else {"path": "Kconfig"}

    assert sorted(values) == list(bo.accepted_options()), "the advertised set must be complete"

    ## THE MUST-EXIST OPTIONS GET A REAL FILE, derived from the set for the same reason the
    ## list samples above are derived: a hardcoded list makes this gate fail on the NEXT
    ## must-exist option rather than on the defect it exists to catch. `doxyfile` refuses a
    ## path that is not a file, because falling through would index the whole repo instead and
    ## report success — so the fixture has to supply a repo root that really holds one.
    repo_root = tmp_path
    for key in bo.PATH_OPTIONS_MUST_EXIST:
        (repo_root / f"{key}.yaml").write_text("", encoding="utf-8")

    args = _args()
    assert bo.apply_options(args, values, repo_root) == list(bo.accepted_options())


## @brief A lock declaration is accepted on BOTH routes, or the two disagree in silence.
## @param tmp_path pytest temp dir.
## @return None.
## @version 1
def test_a_lock_declaration_with_releases_is_accepted_on_both_routes(tmp_path: Path) -> None:
    """TWO DOCUMENTS DISAGREEING ABOUT ONE FACT, for the third time in this area. The loader
    `locks._declared_lock_pattern` reads `releases`, and this module's entry schema omitted it —
    so the SAME declaration was accepted from a `.clew.yaml` file and REFUSED as an
    inline build option.

    `releases` is not optional decoration. Without it `_section_for` finds no release token and
    every critical-section extent stays NULL, so the declaration that makes mbedtls's 48 lock
    sites harvestable is exactly the one the inline route rejected.

    ASSERTED ON BOTH ROUTES AND WITH THE SAME DOCUMENT, because either half alone is
    satisfiable the wrong way: a file-route-only test passes today, and an inline-only test
    could pass against a schema that accepts a key the loader then ignores.

    @brief The same locks document validates inline and loads from a file.
    @version 1
    """
    from clew.locks import load_lock_patterns

    ## The mbedtls declaration, and the reason this task exists: a call-form primitive pair.
    document = {
        "locks": [
            {
                "name": "mbedtls_mutex_lock",
                "form": "call",
                "releases": "mbedtls_mutex_unlock",
                "kind": "mutex",
                "mode": "exclusive",
                "role": "scoped",
                "operand_index": 0,
            }
        ]
    }

    ## ROUTE 1 — inline, as `index(options={...})` and `--declare` deliver it.
    assert bo._checked_document("locks", document) == document, (
        "the inline route must accept every key the loader reads"
    )

    ## ROUTE 2 — the same document through the loader, which is what actually consumes it.
    patterns = {p.name: p for p in load_lock_patterns(document)}
    declared = patterns["mbedtls_mutex_lock"]
    assert declared.releases == "mbedtls_mutex_unlock", (
        "without a release token every critical-section extent stays NULL"
    )
    assert declared.form == "call"
    assert declared.operand_index == 0
    ## And the built-in RAII defaults survive the merge rather than being replaced wholesale.
    assert "lock_guard" in patterns


## @brief Every key an entry schema advertises is one the schema itself accepts.
## @return None.
## @version 1
def test_every_advertised_entry_key_is_accepted_by_its_own_schema() -> None:
    """The structural half. The `releases` hole was a key the LOADER read and the SCHEMA
    refused; this checks the reverse direction across every section at once — a key advertised
    in a schema that the schema's own validator then rejects.

    It cannot catch a loader/schema divergence by itself (nothing here reads the loaders), which
    is why the test above exists for the case that actually bit. Together they cover both
    directions for `locks` and one direction for everything else, and a new section gets the
    reverse check for free.

    @brief Each ManifestSchema accepts a document using all of its own advertised keys.
    @version 1
    """
    for key, schema in bo.MANIFEST_SCHEMAS.items():
        document: dict[str, object] = {}
        for entry_schema in schema.entries:
            ## Every allowed key, with a value whose TYPE cannot be the thing under test.
            document[entry_schema.list_key] = [dict.fromkeys(entry_schema.allowed, "x")]
        for doc_key in schema.document:
            document.setdefault(doc_key, [])
        assert bo._checked_document(key, document) is not None, (
            f"section {key!r} advertises a key its own validator rejects"
        )


## @brief A stated `preprocessor` section must reach TIER 1, like its documented alias.
## @return None.
## @version 1
def test_a_stated_preprocessor_section_reaches_tier_one() -> None:
    """`--declare`'s OWN HELP MAKES THE PROMISE THIS BREAKS: "It is applied at TIER 1 through
    exactly the same validated route as the `options` argument ... and is recorded and replayed by
    later builds of the same database." Measured on the live mbedtls index, built from a single
    declaration file carrying both sections: `locks.tier` is `explicit` and appears in
    `stated_options`, while `predefined.tier` is `declared`. Same file, same flag, two tiers — and
    only the tier-1 one survives a later plain refresh.

    THE MECHANISM IS AN ACCEPTED-BUT-UNREAD KEY, the class this project keeps finding. A stated
    `preprocessor:` is a SECTION_DOCUMENT option, so `apply_options` sets `args.preprocessor`;
    the tier-1 resolver for macros reads `args.predefined`. Both spellings are documented and
    only the alias is wired, so the section form parses, validates, is reported as applied — and
    then resolves from the declaration at tier 2 as though nobody had stated anything.

    WHY IT MATTERS MORE THAN A TIER LABEL: `--declare` is documented "for a repository you do not
    own and must leave byte-identical", so the declaration file lives OUTSIDE the target. Tier 2
    means "the target's own file says so", and the next build re-reads that file — which does not
    exist. The statement is silently gone, and for `predefined` that means the macro-guarded half
    of a codebase drops out of the index while the build reports success.

    ASSERTS THE ALIAS TOO, because a fix that promoted the section while breaking the alias would
    trade one silent loss for another.

    @brief A stated preprocessor section resolves at tier 1, as the alias does.
    @return None.
    @version 1
    """
    import argparse

    from clew.cli import _recorded_predefined

    macros = ["MBEDTLS_THREADING_C", "MBEDTLS_THREADING_PTHREAD"]

    alias = argparse.Namespace(predefined=list(macros))
    assert _recorded_predefined(alias, Path("/nonexistent.db")) == macros, (
        "the documented alias must resolve at tier 1 — the control on the fix"
    )

    section = argparse.Namespace(predefined=None, preprocessor={"predefined": list(macros)})
    assert _recorded_predefined(section, Path("/nonexistent.db")) == macros, (
        "a stated `preprocessor: {predefined: [...]}` is the SAME statement in the section "
        "spelling and must reach tier 1 too; landing at tier 2 means it is not replayed and "
        "vanishes on the next refresh of a target that does not carry the file"
    )

    silent = argparse.Namespace(predefined=None, preprocessor={})
    assert _recorded_predefined(silent, Path("/nonexistent.db")) is None, (
        "a stated section with no macros states nothing, and must not fabricate an empty "
        "tier-1 statement that would then be replayed"
    )
