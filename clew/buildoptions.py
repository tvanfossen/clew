# SPDX-License-Identifier: MIT
"""TIER 1, REACHABLE — one structured `options` argument for an embedding caller.

`.clew.yaml` is TIER 2 and has been reachable since a declaration became
discoverable from `--repo-root`. Tier 1 — an operator STATING a value at call time —
never was: `build_or_refresh` exposed `force`/`doxyfile`/`scope`/`exclude`/`target`, and
`build_index` five more, so through MCP the built-in defaults WERE the whole policy. A
five-tier precedence rule whose top tier no consumer can reach makes tier 5 the ceiling
rather than the floor.

THE VOCABULARY IS THE DECLARATION FILE'S. An operator who learns `shared_key_patterns`
here has learned the key they would write into `.clew.yaml`, and the diagnostics
(gh#320) name their findings in the same words. That closes the loop: the tool says what
it could not see, in the vocabulary you use to tell it.

AND IT IS NOW 14 OF 14, MEASURED — every declaration section is statable, with the one
remaining ASYMMETRY named rather than left to be discovered (gh#382).
`test_every_declaration_section_has_a_matching_option` asserts the difference in both
directions, so a new section arrives with an option or breaks a test:

  * `predefined` is an option with no SECTION, kept as a documented alias for
    `preprocessor.predefined`: the acceptance harness and every existing caller name it, and
    a bare macro list is the common case. The section form is what can also state
    `config_header:`, which the alias cannot express at all.

THE COUNT MOVED 11 → 13 BECAUSE THE CLI COLLAPSED, NOT BECAUSE TWO FEATURES WERE ADDED.
`requirements` and `enrich` were argparse flags with no declaration home at all: statable
only by an operator with a shell, which is the exact shape this module's own reasoning below
rejects for the caller it exists for. Folding the 22-argument build surface to 6 made them
sections and options like everything else, so the sentence "the option name is the section
name" now has no exceptions but the documented `predefined` alias.

`doxyfile` IS THE FOURTEENTH, AND IT REVERSES A CLAIM THIS DOCSTRING USED TO MAKE (gh#420).
The paragraph below listed `--doxyfile` beside `--scope`, `--index-cache` and `--rebuild` as
build MECHANICS that "have no section and never should". That was wrong about this one, and
the counter-example was already in this module: `kconfig:` is a section for exactly the same
reason — its discovery follows a convention, and a repo whose file sits outside that
convention needs a way to SAY so. Where a repository keeps its own documentation target is a
standing property of that repository, not a fact about one run.

Measured: `discover_doxyfile` matches the NAME `Doxyfile` in the root, `docs/` and `doc/` and
refuses to guess beyond it — it was once caught selecting a test FIXTURE's Doxyfile to index a
whole project. Mbed-TLS ships `doxygen/mbedtls.doxyfile`, wrong directory AND wrong filename,
so `scope.doxyfile_*` stayed EMPTY on the one acceptance target whose rubric asks about it
while `_doxyfile_scope` sat fully built and unreachable. `--doxyfile` could name it on one
command line, which is precisely the shape the mandate calls not-a-declaration: unrecorded,
unreplayed, and invisible from the MCP surface.

Stating it does NOT choose what gets indexed — since gh#333 a Doxyfile's INPUT, EXCLUDE* and
FILE_PATTERNS are all replaced — so the reversal costs nothing in scope semantics. And unlike
every other path option it must EXIST when stated (`PATH_OPTIONS_MUST_EXIST`), because
resolution otherwise falls through to whole-repo synthesis, which is a legitimate build: the
result would be a well-formed index of a different thing, reporting success.

WHAT DID *NOT* BECOME A DECLARATION, and the distinction is worth stating because it is the
one a reader will test this claim against. `--scope`, `--index-cache` and
`--rebuild` are build MECHANICS — facts about one run, not about the repository — so they
have no section and never should. `--guard-config` was DELETED in favour of discovery rather
than folded, because `discover_guard_config` already finds it from the repo root alone and
carrying a declaration is what `--declare` now does directly. `--verbose` changes the CLI's
own stderr and nothing that reaches the index.

`index_scope` was the last gap and took its own route rather than the merge. It is resolved by
`derive_scope_logged` BEFORE the declaration the stages read is loaded, so the injection point
below cannot reach it; the stated document is threaded down to `scope._declared_index_scope`
instead and built through the SAME construction a written one takes. Only the reported `reason`
differs — it says "stated by the caller (tier 1)" rather than naming a file — and it must, or an
owner would go and edit a file that says nothing. Pairing a stated `index_scope` with any
`--scope` other than `from-guard` REFUSES, because that path never reads it and would build a
different boundary while reporting success.

Before gh#382 the two unreachable sections were `preprocessor` and `kconfig`, and the plan
that scheduled this work named neither correctly — it listed `config_header`, which is a KEY
INSIDE `preprocessor` rather than a section of its own. Counting them was one query; the
list in the plan was three items and two of them were wrong.

TWO CONVENTIONS IN ONE ARGUMENT, deliberately (owner decision, 2026-08-10):

  * INLINE for the values that are a list or a small mapping. `event_tags` is the case
    that proves the need — it has no CLI flag at all, by an explicit earlier decision
    that a bus vocabulary is a standing property of a repo, so before this there was no
    route to state it other than editing the target's own tree.
  * BY PATH for the six manifest-shaped documents. Every loader takes a `Path`; giving
    each a second input type to save an operator a file is a poor trade, and a recorded
    path is reproducible where a recorded structure is a frozen copy.

THAT SECOND BULLET IS REVERSED (gh#360, owner decision 2026-08-11) AND THE REASONING
ABOVE IS KEPT RATHER THAN DELETED, because it is still correct about the case it was
about: AN OPERATOR WITH A SHELL. For them a path IS the better input — reproducible,
diffable, and already written down. It does not hold for the caller this surface exists
for. An AGENT mid-session has no shell and must not write into the target: a third-party
repo stays byte-identical, so `.clew.yaml` is unavailable, and a YAML file at some
absolute path outside the tree is untracked, unreproducible, and deleted by the acceptance
harness's own `git clean`. "Save an operator a file" was never the trade; the trade is
whether a declaration is REACHABLE at all from a caller with no filesystem to write to —
the same shape as the recorded lesson that a declaration reachable only from argv is not a
declaration. So each manifest option now accepts EITHER form, and the path form is
untouched: an operator's recorded path keeps being a recorded path.

THE INLINE FORM IS VALIDATED HARDER THAN THE FILE FORM, and that asymmetry is deliberate.
`MANIFEST_SCHEMAS` below refuses an unknown key at the ENTRY level, which is the level
this repo has recorded as the quiet one: `key_arg_idx` for `key_arg_index` parses to a
perfectly valid mapping, every loader reads the misspelling as absent, and the dataflow is
then keyed off argument 0 with the build reporting success. The loaders' own `entry.get(…,
default)` cannot see that, and tightening them would change what an existing target's
committed declaration means — a separate decision, not this one's to make. Stricter on the
new route costs an author one error message; laxer on it would have shipped the defect.

FAIL CLOSED AT BOTH LEVELS, because the quieter one is the entry level. A misspelled
SECTION is refused by name against the allowed set — the `load_declaration_located`
precedent. But `{"broadcasts": "produce"}` for `producer` would parse as a perfectly valid
mapping that no consumer reads, silently leaving the bus undeclared while the call
reported success. So role values are checked against the vocabulary too.

@brief Validate and apply an embedding caller's tier-1 build options.
@version 5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .event_edges import CONSUMER, PRODUCER

## Keys whose value is a LIST OF STRINGS, applied inline. Each names an argparse dest that
## already exists, so a stated value lands exactly where the equivalent flag would.
## `vendored` is a plain list of repo-relative paths, exactly the shape `entry_patterns` is,
## so it rides the same inline route. It has to be statable at TIER 1 for the case it exists
## for: a third-party target whose tree must stay byte-identical cannot carry a
## `.clew.yaml`, so an agent or an acceptance harness states it on the call.
INLINE_LIST_OPTIONS: tuple[str, ...] = ("entry_patterns", "predefined", "vendored")

## Keys whose value is a MAPPING, applied inline. `event_tags` maps a tag name to a role.
INLINE_MAPPING_OPTIONS: tuple[str, ...] = ("event_tags",)

## Keys whose value is a PATH and only ever a path.
##
## `data_model` is the one MANIFEST that is NOT YAML — an ingot/UDM TOML document, named by
## a repo-relative path in the declaration too — so there is no equivalent inline structure
## to accept.
##
## `requirements` and `enrich` are here because a path is ALL either one ever was: each
## names a document in the target's own tree whose format belongs to that repo, not to this
## tool. There is deliberately no inline form. A requirements catalog has no universal shape
## (this repo's own rule: "there is NO universal requirements.yaml format", one flat list and
## one nested `domains:` tree, read additively), so accepting one inline would mean this
## module choosing a shape the mandate forbids it to assume. Same for an enrichment topics
## document. Both were CLI flags with no declaration home, which is why a repo could not
## state either one through the surface an agent uses.
##
## `doxyfile` joins them for gh#420, and it is the one whose absence changes WHICH SOURCE is
## indexed rather than which metadata is attached. `discover_doxyfile` matches the NAME
## `Doxyfile` in the repo root, `docs/` and `doc/`, and REFUSES to guess beyond that — it once
## took `sorted(repo.glob("*/Doxyfile"))[0]` and selected a test FIXTURE's Doxyfile to index a
## whole project. Mbed-TLS/mbedtls ships `doxygen/mbedtls.doxyfile`: wrong directory AND wrong
## filename, so no discovery reaches it and, before this key, nothing could state it either.
## Widening the glob would trade a fixable gap for an unfixable class of wrong answer; a
## DECLARATION is the answer the no-hardcoding mandate already prescribes.
PATH_OPTIONS: tuple[str, ...] = ("data_model", "requirements", "enrich", "doxyfile")

## Of the path options, the ones whose stated path must EXIST when it is stated.
##
## THE DISTINCTION IS METADATA VERSUS FILE SET, not caution. A missing `requirements` catalog
## degrades to empty metadata over the same rows — honest, recoverable, and each loader says so
## in its own words, which is why `_checked_path` deliberately does not check existence. A
## missing `doxyfile` changes WHICH SOURCE IS COMPILED INTO THE INDEX: resolution falls through
## to whole-repo synthesis, which is a legitimate build, so the result is a well-formed index of
## a different thing. `_resolve_doxyfile_and_root` warns in that case and is deliberately
## non-fatal for the `--doxyfile` FLAG (`--repo-root` alone is sufficient), and a warning is
## exactly what this project has repeatedly found to be gone by query time.
##
## So the refusal lives at the boundary where the DECLARATION is made, matching the entry-level
## rule this repo learned the hard way: a document-level slip is loud, and an entry-level one is
## quiet enough to build green and be believed.
PATH_OPTIONS_MUST_EXIST: frozenset[str] = frozenset({"doxyfile"})

## Keys accepting EITHER a path to a YAML document OR that document inline (gh#360). Every
## loader behind these already takes `Path | dict`, because a `.clew.yaml` section
## arrives as a mapping — so the inline form needs no new parser, only a validated route in.
MANIFEST_OPTIONS: tuple[str, ...] = (
    "shared_key_patterns",
    "thread_patterns",
    "locks",
    "dispatch",
    "mqtt_dispatch",
)

## Keys naming a DECLARATION SECTION whose whole document is stated inline (gh#382). These
## have NO argparse dest and never did — they were tier-2 only, readable from a checked-in
## `.clew.yaml` and unreachable from the MCP surface, which is the exact shape
## CLAUDE.md forbids: "a declaration reachable only from argv is not a declaration", read the
## other way round.
##
## THE OPTION NAME IS THE SECTION NAME, which is the owner's 1:1 ruling made literal. They are
## applied by MERGING INTO THE DECLARATION the stages already read, rather than by adding three
## more dests and three more resolution orders — one injection point, and every consumer of
## `decl` gets the stated value for free.
##
## `predefined` REMAINS as a convenience alias for `preprocessor.predefined` because the
## acceptance harness and every existing caller name it, and because a bare macro list is the
## common case. It is the one option whose name is not a section, and it is documented as such
## rather than quietly tolerated.
SECTION_DOCUMENT_OPTIONS: tuple[str, ...] = ("preprocessor", "kconfig", "index_scope")


## @brief One list-of-entries key inside a manifest, and the keys its entries may carry.
## @version 1
@dataclass(frozen=True)
class EntrySchema:
    """The ENTRY-LEVEL allow-list, which is the level the loaders cannot police for
    themselves. Every one of them reads its fields with `entry.get(name, default)`, so a
    misspelled field is indistinguishable from an omitted one and silently takes the
    default — `key_arg_idx` keys a whole dataflow layer off argument 0.

    `any_of` rather than `required` where a shape is a genuine either/or: a shared-key
    entry is the argument-based convention (`pattern`) or the name-based one
    (`name_prefix`), never both and never neither.

    @brief Allowed and required keys for one manifest list's entries.
    @version 1
    """

    list_key: str
    allowed: frozenset[str]
    required: tuple[str, ...] = ()
    any_of: tuple[str, ...] = field(default_factory=tuple)


## @brief One inline manifest's whole shape: its top-level keys and its entry lists.
## @version 1
@dataclass(frozen=True)
class ManifestSchema:
    """`document` is the DOCUMENT-level allow-list and is not derivable from `entries`:
    `shared_key_patterns` legitimately carries a `key_alias_prefixes` list of strings
    beside its two entry lists, so deriving the allowed set from the entry schemas would
    refuse a correct declaration. Two levels, stated separately, matching
    `declaration.KNOWN_SECTIONS` above them and `dispatch._reject_unknown` beside them.

    @brief The allowed shape of one inline manifest.
    @version 1
    """

    document: frozenset[str]
    entries: tuple[EntrySchema, ...]


## What an inline manifest may contain, per option. The KEYS ARE THIS PROJECT'S OWN
## FORMAT, not any target's convention, so writing them down here is not the hardcoding
## the mandate forbids — it is the same document-level allow-list `declaration.py` keeps
## for section names, one level in.
##
## `dispatch` IS ABSENT ON PURPOSE and validated by `load_dispatch_manifest`, which already
## refuses an unknown key at the document level AND in each of its three entry shapes
## (`dispatch._reject_unknown`). Restating its schema here would be a second copy free to
## drift from the parser that reads it; no schema means "its own loader is stricter than
## anything this module would write", and `_checked_manifest` says so rather than treating
## the absence as permission to skip checking.
MANIFEST_SCHEMAS: dict[str, ManifestSchema] = {
    "shared_key_patterns": ManifestSchema(
        document=frozenset({"writers", "readers", "key_alias_prefixes"}),
        entries=(
            EntrySchema(
                "writers",
                frozenset({"pattern", "key_arg_index", "name_prefix", "dispatch_mode"}),
                any_of=("pattern", "name_prefix"),
            ),
            EntrySchema(
                "readers",
                frozenset({"pattern", "key_arg_index", "name_prefix", "dispatch_mode"}),
                any_of=("pattern", "name_prefix"),
            ),
        ),
    ),
    "thread_patterns": ManifestSchema(
        document=frozenset({"spawns"}),
        entries=(
            EntrySchema(
                "spawns",
                frozenset(
                    {
                        "name",
                        "entry_arg_index",
                        "name_arg_index",
                        "kind",
                        "entry_kwarg",
                        "name_kwarg",
                    }
                ),
                required=("name",),
            ),
        ),
    ),
    "locks": ManifestSchema(
        document=frozenset({"locks"}),
        entries=(
            EntrySchema(
                "locks",
                ## `releases` WAS MISSING, and it is the one key a call-form primitive cannot
                ## work without. `locks._declared_lock_pattern` has always read it, so the same
                ## declaration was accepted from a `.clew.yaml` file and REFUSED here —
                ## two documents disagreeing about one fact, which is the third instance of that
                ## shape in this area (see #404's three-way disagreement and #407's prompt vs
                ## parser). Without a release token `_section_for` finds nothing to close the
                ## extent, so every critical section stays NULL: the declaration that makes
                ## mbedtls's 48 lock sites harvestable was exactly the one this route rejected.
                frozenset({"name", "form", "kind", "mode", "role", "operand_index", "releases"}),
                required=("name",),
            ),
        ),
    ),
    "mqtt_dispatch": ManifestSchema(
        document=frozenset({"subscribe_functions"}),
        entries=(
            EntrySchema(
                "subscribe_functions",
                frozenset({"fn_name", "topic_arg_index", "handler_arg_index"}),
                required=("fn_name",),
            ),
        ),
    ),
}

## DERIVED, and refused with a reason rather than reported as unknown. `key_alias_prefixes`
## is resolved FROM the shared-key document plus the tier-4 ecosystem defaults, so accepting
## a stated value here would let it disagree with the patterns it is supposed to describe.
## Naming it explicitly matters: "unknown option" would send a caller looking for a typo in
## a key that is spelled correctly and simply is not theirs to set.
DERIVED_OPTIONS: dict[str, str] = {
    "key_alias_prefixes": (
        "derived from shared_key_patterns plus the built-in ecosystem prefixes — state "
        "shared_key_patterns instead, and read the resolved value back from "
        "status.options"
    ),
}

## The roles `event_tags` may assign. Imported from the importer that consumes them rather
## than restated, so a role this accepts is a role something reads.
EVENT_ROLES: frozenset[str] = frozenset({PRODUCER, CONSUMER})


## @brief Raised when an options mapping names something unknown or is shaped wrongly.
## @version 1
class BuildOptionError(ValueError):
    """A REFUSAL, not a warning. An option that is silently dropped produces a build whose
    policy is not what the caller stated and which reports success — the failure mode this
    whole surface exists to remove, reintroduced at its own front door.

    @brief Invalid build options.
    @version 1
    """


## @brief Every option key this surface accepts, for an error message and for a caller.
## @return Sorted tuple of accepted key names.
## @version 3
## @req REQ-DDB-CONFIG-008
def accepted_options() -> tuple[str, ...]:
    """@brief The accepted option names.

    @return Sorted key names.
    @version 2
    """
    return tuple(
        sorted(
            (
                *INLINE_LIST_OPTIONS,
                *INLINE_MAPPING_OPTIONS,
                *PATH_OPTIONS,
                *MANIFEST_OPTIONS,
                *SECTION_DOCUMENT_OPTIONS,
            )
        )
    )


## @brief Refuse a key that is not settable, naming why.
## @param key The offending option name.
## @return None; always raises.
## @version 1
## @dg_internal
def _refuse(key: str) -> None:
    """Split from the validation loop so the DERIVED case gets its own sentence. Reporting
    a correctly-spelled derived key as "unknown" is worse than useless — it sends the reader
    hunting a typo that is not there, which is this repo's recorded phantom-hunt shape.

    @brief Raise the right refusal for an unsettable key.
    @version 1
    """
    if key in DERIVED_OPTIONS:
        raise BuildOptionError(f"option {key!r} cannot be stated: {DERIVED_OPTIONS[key]}")
    raise BuildOptionError(
        f"unknown build option {key!r} — accepted: {', '.join(accepted_options())}"
    )


## @brief Validate one inline mapping option's entries.
## @param key The option name, for the message.
## @param value The mapping supplied.
## @return The mapping, unchanged, when every entry is valid.
## @version 1
## @dg_internal
def _checked_mapping(key: str, value: Any) -> dict[str, str]:
    """THE ENTRY-LEVEL GATE, and the reason it exists is that this level is the quiet one.
    A document-level slip is loud; `{"broadcasts": "produce"}` is a valid mapping that no
    consumer reads, so the build would succeed, the bus would stay undeclared, and the
    diagnostics would report the tag as unclaimed while the caller believed they had
    claimed it.

    @brief Check an inline mapping's keys and role values.
    @return The validated mapping.
    @version 1
    """
    if not isinstance(value, dict) or not value:
        raise BuildOptionError(
            f"option {key!r} must be a non-empty mapping, got {type(value).__name__}"
        )
    bad = {tag: role for tag, role in value.items() if role not in EVENT_ROLES}
    if bad:
        raise BuildOptionError(
            f"option {key!r} has {len(bad)} entr{'y' if len(bad) == 1 else 'ies'} with an "
            f"unrecognised role ({', '.join(f'{t}={r!r}' for t, r in sorted(bad.items()))}) "
            f"— accepted roles: {', '.join(sorted(EVENT_ROLES))}"
        )
    return dict(value)


## @brief Validate one inline list option.
## @param key The option name, for the message.
## @param value The list supplied.
## @return The list as strings.
## @version 1
## @dg_internal
def _checked_list(key: str, value: Any) -> list[str]:
    """A bare string is the likely slip and is refused rather than accepted as a
    one-character-per-item list, which is what `list("app_main")` would silently produce.

    @brief Check an inline list option.
    @return The validated list.
    @version 1
    """
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise BuildOptionError(
            f"option {key!r} must be a list of strings, got {type(value).__name__}"
        )
    return [str(item) for item in value]


## @brief Validate a stated declaration SECTION document.
## @param key The option/section name, for the message.
## @param value The document supplied.
## @return The document, unchanged.
## @version 1
## @dg_internal
def _checked_section_document(key: str, value: Any) -> dict:
    """A MAPPING AND NOTHING MORE, deliberately, and it is NOT `_checked_mapping`. That one
    is the `event_tags` validator: it requires every value to be an event ROLE and refuses an
    empty document. Reusing it here raised `TypeError: unhashable type: 'list'` on a perfectly
    valid `preprocessor: {predefined: [...]}` — a validator borrowed for a shape it was never
    written for, which is the same family as one option taking another's decoder.

    THE SECTION'S OWN LOADER POLICES ITS KEYS. `load_declaration_located` refuses an unknown
    section by name, and each reader validates its own entries — `preprocessor` its macro
    list and config header, `kconfig` its path. A second validator here would give one
    document two authorities free to disagree, and the entry level is exactly where a
    silent slip (`key_arg_idx` for `key_arg_index`) does its damage.

    AN EMPTY DOCUMENT IS ALLOWED because `{}` is the withdrawal spelling every other option
    uses. `_checked_mapping` rejects it, which would have made a stated section impossible to
    retract without deleting the database.

    @brief Check that a stated section is a mapping.
    @return The document.
    @version 1
    """
    if not isinstance(value, dict):
        raise BuildOptionError(
            f"option {key!r} states the whole `{key}:` declaration section, so it must be a "
            f"mapping, got {type(value).__name__}"
        )
    return value


## @brief Resolve one path option against the repo root.
## @param key The option name, for the message.
## @param value The path supplied.
## @param repo_root Root to resolve a relative path against, or None.
## @return Absolute path as a string.
## @version 2
## @dg_internal
def _checked_path(key: str, value: Any, repo_root: Path | None) -> str:
    """Relative paths resolve against the REPO, not the process's working directory: a
    caller states the path they would write in the declaration file, and an MCP server's
    cwd is not the target repo. Existence is NOT checked for most of them — each loader
    reports its own missing document with the context to say what it was for.

    THE EXCEPTION IS `PATH_OPTIONS_MUST_EXIST`, and the line the exception is drawn on is
    metadata versus file set. A missing `requirements` catalog degrades to empty metadata over
    the same rows, so the loader's own message is both sufficient and better-informed. A missing
    `doxyfile` sends resolution through to whole-repo synthesis, which is a LEGITIMATE build —
    so there is no loader left to complain, and the result is a well-formed index of a different
    variant of the repository, reporting success.

    @brief Resolve a path option.
    @return Absolute path string.
    @version 2
    """
    if not isinstance(value, (str, Path)):
        raise BuildOptionError(
            f"option {key!r} must be a path to a YAML document, got {type(value).__name__}"
        )
    path = Path(value).expanduser()
    if not path.is_absolute() and repo_root is not None:
        path = Path(repo_root) / path
    if key in PATH_OPTIONS_MUST_EXIST and not path.is_file():
        raise BuildOptionError(
            f"option {key!r} names {path}, which is not a file. Refusing rather than "
            f"continuing: this option decides WHICH SOURCE is indexed, so falling back "
            f"would build a well-formed index of something else and report success. "
            f"State a path relative to the repo root, or remove the option to let "
            f"discovery and synthesis decide."
        )
    return str(path)


## @brief Validate one inline manifest document against its schema.
## @param key The option name, for the message.
## @param value The mapping supplied.
## @return The mapping, unchanged, when the whole document is valid.
## @version 1
## @dg_internal
def _checked_document(key: str, value: dict[str, Any]) -> dict[str, Any]:
    """The DOCUMENT half of the two-level gate. A manifest with no schema here is one whose
    own loader refuses unknown keys at both levels (`dispatch`), so it passes through — but
    it passes through NAMED, rather than by falling off the end of a lookup, because "no
    schema" and "not checked" must not share a code path.

    @brief Check an inline manifest's top-level keys.
    @return The validated document.
    @version 1
    """
    schema = MANIFEST_SCHEMAS.get(key)
    if schema is None:
        return value  # dispatch: validated wholly by load_dispatch_manifest
    unknown = sorted(str(k) for k in value if k not in schema.document)
    if unknown:
        raise BuildOptionError(
            f"option {key!r} names unknown key(s) {', '.join(repr(k) for k in unknown)} "
            f"— allowed: {', '.join(sorted(schema.document))}. Nothing reads an unknown "
            f"key, so the build would have used built-in defaults while reporting that "
            f"your statement was honoured."
        )
    for entry_schema in schema.entries:
        _checked_entries(key, value, entry_schema)
    return dict(value)


## @brief Validate every entry of one list inside an inline manifest.
## @param key The option name, for the message.
## @param document The manifest document.
## @param schema The entry schema for one of its lists.
## @return None; raises on the first offending entry.
## @version 1
## @dg_internal
def _checked_entries(key: str, document: dict[str, Any], schema: EntrySchema) -> None:
    """THE QUIET LEVEL, and the whole reason the inline route is validated harder than the
    file route. `key_arg_idx` for `key_arg_index` is a valid mapping that every loader reads
    as "absent", so the dataflow is keyed off argument 0 and the build reports success —
    this repo's recorded example of an entry-level slip. Same family as
    `entry.get("name")` returning None and the loader skipping the entry silently.

    @brief Check one manifest list's entries.
    @version 1
    """
    entries = document.get(schema.list_key)
    if entries is None:
        return
    if not isinstance(entries, list):
        raise BuildOptionError(
            f"option {key!r}: {schema.list_key!r} must be a list of entries, got "
            f"{type(entries).__name__}"
        )
    for position, entry in enumerate(entries, start=1):
        _checked_entry(key, f"{schema.list_key}[{position}]", entry, schema)


## @brief Validate one entry mapping against its schema.
## @param key The option name, for the message.
## @param where Which list and position the entry sits at.
## @param entry The entry supplied.
## @param schema The entry schema.
## @return None; raises when the entry is shaped wrongly.
## @version 1
## @dg_internal
def _checked_entry(key: str, where: str, entry: Any, schema: EntrySchema) -> None:
    """@brief Check one manifest entry's keys against the allowed and required sets.
    @version 1
    """
    if not isinstance(entry, dict):
        raise BuildOptionError(
            f"option {key!r}: {where} must be a mapping, got {type(entry).__name__}"
        )
    unknown = sorted(str(k) for k in entry if k not in schema.allowed)
    if unknown:
        raise BuildOptionError(
            f"option {key!r}: {where} names unknown key(s) "
            f"{', '.join(repr(k) for k in unknown)} — allowed: "
            f"{', '.join(sorted(schema.allowed))}. A misspelled field reads as an absent "
            f"one, so it would silently take its default."
        )
    missing = [name for name in schema.required if not entry.get(name)]
    if missing:
        raise BuildOptionError(
            f"option {key!r}: {where} is missing required key(s) "
            f"{', '.join(repr(m) for m in missing)}"
        )
    if schema.any_of and not any(entry.get(name) for name in schema.any_of):
        raise BuildOptionError(
            f"option {key!r}: {where} declares none of "
            f"{', '.join(repr(name) for name in schema.any_of)} — it would match nothing"
        )


## @brief Resolve one manifest option, which may be a path or the document inline.
## @param key The option name, for the message.
## @param value A path string/Path, or the manifest document as a mapping.
## @param repo_root Root to resolve a relative path against, or None.
## @return An absolute path string, or the validated mapping.
## @version 1
## @dg_internal
def _checked_manifest(key: str, value: Any, repo_root: Path | None) -> str | dict[str, Any]:
    """BOTH FORMS REACH THE SAME PARSER. Every loader behind these options already accepts
    `Path | dict`, because a `.clew.yaml` section arrives as a mapping — so the
    inline form adds a route, not a format, and `treescan.manifest_key` hashes a mapping
    canonically, which is what keeps gh#358's per-stage cache invalidation intact: stating
    one manifest recomputes the stages that manifest feeds and no others.

    @brief Resolve a manifest option from either input form.
    @return Path string or validated document.
    @version 1
    """
    if isinstance(value, dict):
        return _checked_document(key, value)
    if not isinstance(value, (str, Path)):
        raise BuildOptionError(
            f"option {key!r} must be a path to a YAML document, or that document inline "
            f"as a mapping, got {type(value).__name__}"
        )
    return _checked_path(key, value, repo_root)


## @brief Apply a validated options mapping onto a parsed argument namespace.
## @param args Namespace from the build argument parser, mutated in place.
## @param options Caller-stated options, or None to change nothing.
## @param repo_root Root that relative path options resolve against.
## @return The names actually applied, sorted, for logging.
## @version 3
## @req REQ-DDB-CONFIG-008
def apply_options(args: Any, options: dict[str, Any] | None, repo_root: Path | None) -> list[str]:
    """VALIDATES EVERYTHING BEFORE ASSIGNING ANYTHING, so a mapping with one bad entry
    leaves the namespace untouched rather than half-applied. A partially-applied policy
    would build with a mixture of what the caller asked for and what they did not, and
    report success — the same class of defect as a partially-reloaded pipeline.

    `None` and `{}` both change nothing, and neither is an error: a caller that forwards
    its own optional argument gets the inheriting behaviour by default. An empty document
    for ONE manifest option (`shared_key_patterns: {}`) is the per-option equivalent — it
    states nothing, so that manifest falls back to the target's own declaration, matching
    the absent/empty/replaces convention `--exclude` and `--entry-patterns` already keep.

    @brief Validate and apply tier-1 options.
    @return Applied option names.
    @version 2
    """
    if not options:
        return []
    if not isinstance(options, dict):
        raise BuildOptionError(f"options must be a mapping, got {type(options).__name__}")
    staged: dict[str, Any] = {}
    for key, value in options.items():
        if key in INLINE_LIST_OPTIONS:
            staged[key] = _checked_list(key, value)
        elif key in INLINE_MAPPING_OPTIONS:
            staged[key] = _checked_mapping(key, value)
        elif key in MANIFEST_OPTIONS:
            staged[key] = _checked_manifest(key, value, repo_root)
        elif key in PATH_OPTIONS:
            staged[key] = _checked_path(key, value, repo_root)
        elif key in SECTION_DOCUMENT_OPTIONS:
            staged[key] = _checked_section_document(key, value)
        else:
            _refuse(key)
    for key, value in staged.items():
        setattr(args, key, value)
    return sorted(staged)
