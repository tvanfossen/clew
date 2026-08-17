# SPDX-License-Identifier: MIT
"""Layer 5: `shared_key_edges` — dataflow through a shared symbolic key.

Call-graph layers (see `call_edges.py`) only capture direct invocation.
Many embedded/IoT codebases route control flow through a shared symbolic
key instead: one function writes a value via an accessor macro/function,
a different function elsewhere reads that same key with no direct call
between them. This module builds a fifth, independent edge table capturing
that relationship, from two sources:

  Source A — `import_shared_key_edges_inferred`:
      Walks the same tree-sitter AST pass `import_ast_call_edges` uses
      (same file set from the `path` table, same per-file parse), from
      TWO reader sources that feed the same collector:
        - Accessor CALLS: call/macro-invocation names matched against a
          caller-supplied list of writer and reader accessor patterns
          (`--shared-key-patterns`, a YAML file — see
          `load_shared_key_patterns`).
        - Switch/case DISPATCH: every `case <value>:` label in the file,
          always a candidate reader site regardless of pattern config —
          `switch (key) { case KEY_X: ...; }` is a real-world dispatch
          shape with no accessor call to match at all. Scanning every
          switch unconditionally stays fail-closed on noise because a
          case label only produces an edge when its literal ALSO matches
          some writer's key (the intersection below) — an unrelated
          switch on an unrelated enum simply never intersects.
      Only a literal key value (a string literal or a bare
      identifier/enum constant — never a computed expression) is
      accepted from either source; anything else is counted as
      "unresolved" and no edge is emitted (fail-closed, per the
      proposal's explicit risk note). Writer/reader sites are grouped by
      key name; every (writer, reader) pair sharing a key becomes one
      edge, unless the key's fan-out exceeds `_MAX_KEY_PARTICIPANTS`, in
      which case the key's edges are suppressed entirely (avoids an
      O(n^2) noise blob from generic status-flag-style keys).
      confidence='medium', declared=0, source='shared_key_inferred'.
      edge_kind='unknown' — NOT 'state': a data-model-style accessor value can be
      read anywhere (a raw local, an `if`, a loop, arithmetic, another
      call), so a switch/case dispatch is just one of many read shapes
      AST discovery can see, and the discovery shape tells you nothing
      about whether the underlying thing is a persistent state key or a
      transient one-shot occurrence (a queue item, say) — that is a
      property of the key itself, only known from an authoritative
      declaration. Inferring state-vs-event from syntax would be a guess
      dressed up as a fact; 'unknown' says plainly that this source
      cannot tell.

  Source B — `import_shared_key_edges_declared`:
      Ingests an optional `--data-model` TOML manifest — an authoritative
      key declaration, e.g. from an ingot-style data-model tool —
      naming each key's writer/reader functions directly (no AST inference
      needed). Keys marked `event = true` produce `edge_kind='event'`
      edges (a causal write-then-fire relationship); all others produce
      `edge_kind='state'`. This is the ONLY source that ever asserts
      state-vs-event, because it comes from a declaration, not a guess.
      confidence='high' (an authoritative declaration, not a guess),
      declared=1, source='shared_key_declared'.

Expected TOML shape (see `_parse_data_model_toml`)::

    [[keys]]
    name = "ROBOT_SOUND_EVENT_TYPE"
    persistent = false
    event = true
    writers = ["handle_ping_cmd"]
    readers = ["handle_sound_event_findme"]

Both sources write into the same `shared_key_edges` table (created by
whichever stage runs first via `CREATE TABLE IF NOT EXISTS`, so either
can be skipped/omitted independently and the other still works). The
authoritative column list is `_ensure_shared_key_edges_table` below, and every
enumerated column's allowed values come from `vocabulary.COLUMNS` — this
docstring used to carry a hand-copied CREATE TABLE that had already drifted
(it was missing `dispatch_mode`, `edge_triggered`, `crosses_thread` and
`to_thread_id`).

Both stages are graceful no-ops when their optional input isn't supplied,
or (for the TOML path) when neither `tomllib` (3.11+) nor `tomli` is
importable — mirroring `import_ast_call_edges`'s optional-dependency
pattern.

R1 additions: inferred/declared edges now carry `dispatch_mode` (accessor-class
provenance / declared synchrony class), the declared path reads a per-key
`edge_triggered` flag (NULL unless declared), and an optional keyed-dispatch
source C (`import_mqtt_dispatch_edges`, `--mqtt-dispatch`) records topic→handler
routing. Thread-boundary columns (`crosses_thread`/`to_thread_id`) are added by
the CREATE body here but populated by `threads.annotate_thread_boundaries`.

@brief Shared-key (Layer 5) dataflow edge importers.
@version 5
"""

from __future__ import annotations

import fnmatch
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import logger
from .call_edges import (
    _ast_caller_at_line,
    _build_function_indexes,
)
from .declaration import SECTION_SHARED_KEY
from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .pyast import (
    SELF_NAMES,
    dotted_name,
    is_python_tree,
    positional_argument,
    string_value,
    tail_name,
)
from .tiers import LayeredResolution, resolve_layered
from .tomlcompat import require_toml_module
from .treescan import manifest_key
from .vocabulary import (
    DISPATCH_MODE,
    EXTERNAL_ROOT_COLUMN,
    STAGE_MQTT,
    STAGE_SHARED_KEY,
    bool_check,
    check,
    declaration_origin,
)

# The anti-noise ceiling, expressed in EDGES rather than participants (gh#28).
#
# The rule this replaces suppressed a key with more than `_MAX_KEY_PARTICIPANTS`
# distinct writers OR readers, tested on each side independently. Its stated
# purpose is avoiding an O(n^2) noise blob from a generic status-flag key — but a
# key contributes `writers x readers` edges, and a quadratic blob needs BOTH sides
# to be large. Testing the sides separately therefore discards the two LINEAR
# shapes with the highest information content per edge:
#
#   | shape       | writers | readers | edges | old rule | verdict          |
#   |-------------|---------|---------|-------|----------|------------------|
#   | status flag |      20 |      20 |   400 | suppress | correct          |
#   | funnel      |      34 |       1 |    34 | suppress | WRONG            |
#   | broadcast   |       1 |      30 |    30 | suppress | WRONG            |
#
# A funnel — every writer in the codebase converging on ONE reader — is the most
# valuable thing this layer can find, because the single reader is where the
# meaning is. A broadcast is its dual. Both were being thrown away while the
# quadratic case they were collateral to was correctly suppressed.
#
# 64 is not a new tolerance: it is EXACTLY the old ceiling. The previous rule
# admitted at most 8 writers x 8 readers, so every key it admitted has a product
# of 64 or less and is still admitted here. What changes is only that the budget
# may now be spent on a lopsided shape. Nothing needs a separate min-side test
# on top of this — `min(w, r) > 8` implies both sides exceed 8, which implies a
# product above 64, so the product gate already subsumes it.
_MAX_KEY_EDGES = 64


## @brief One accessor-pattern rule: a name pattern + the key-argument index.
## @version 1
class AccessorPattern:
    """One writer or reader accessor-pattern rule for the ARGUMENT-based
    accessor convention: a shared function/macro taking the key as a
    literal argument (`ACCESSOR(key, ...)`).

    `pattern` is matched against callee names with `fnmatch` (so `*` and
    `?` glob normally; a literal name with no wildcard matches exactly).
    `key_arg_index` is the 0-indexed position of the literal key argument
    in the call's argument list. `dispatch_mode` is the accessor-class
    provenance carried onto matched WRITER edges (see R1: QUEUESEND-family
    → 'queued', DATAMODEL_SET-family → 'inline'); defaults to 'unknown'.

    @brief Accessor-pattern rule (name pattern + key-argument position).
    @version 2
    """

    __slots__ = ("dispatch_mode", "key_arg_index", "pattern")

    ## @brief Store the name glob, key-argument index, and dispatch-mode provenance.
    ## @version 1
    ## @dg_internal
    def __init__(self, pattern: str, key_arg_index: int, dispatch_mode: str = "unknown") -> None:
        self.pattern = pattern
        self.key_arg_index = key_arg_index
        self.dispatch_mode = dispatch_mode


## @brief One accessor-pattern rule for the key-in-callee-name convention.
## @version 1
class NamePrefixPattern:
    """One writer or reader accessor-pattern rule for the NAME-based
    accessor convention: one generated function PER KEY, with no key
    argument at all — the key is the remainder of the callee name after
    a fixed prefix (`STORE_SET_ROBOT_SOUND_EVENT_SET(value)`,
    `STORE_GET_ROBOT_SOUND_EVENT_SET()`). Confirmed live against a real
    generated-data-model codebase where no argument-based accessor form
    exists at all.

    `prefix` is a literal string match (not a glob) — the key is
    `callee_name[len(prefix):]`, so a callee that is EXACTLY the prefix
    (empty remainder) never matches: there is no key to extract.
    `dispatch_mode` is the accessor-class provenance carried onto matched
    WRITER edges (see `AccessorPattern`); defaults to 'unknown'.

    @brief Name-prefix accessor rule (key = name remainder after prefix).
    @version 2
    """

    __slots__ = ("dispatch_mode", "prefix")

    ## @brief Store the literal callee-name prefix and dispatch-mode provenance.
    ## @version 1
    ## @dg_internal
    def __init__(self, prefix: str, dispatch_mode: str = "unknown") -> None:
        self.prefix = prefix
        self.dispatch_mode = dispatch_mode


# Built-in accessor conventions applied when NO --shared-key-patterns file is
# given, exactly parallel to reachability.DEFAULT_ENTRY_PATTERNS and
# threads.DEFAULT_SPAWN_PATTERNS: a sensible default + a declared override, never
# a baked-in assumption. This is the INGOT code generator's per-key accessor
# naming (`DataModel_Set_<KEY>(v)` / `DataModel_Get_<KEY>()`) — a generator
# convention, not any one repo's shape. It produces edges ONLY where those
# accessors actually exist, so a non-ingot repo yields zero and pays no noise.
# A repo that names its accessors differently overrides via --shared-key-patterns.
DEFAULT_SHARED_KEY_WRITERS: list[NamePrefixPattern] = [
    NamePrefixPattern("DataModel_Set_"),
]
DEFAULT_SHARED_KEY_READERS: list[NamePrefixPattern] = [
    NamePrefixPattern("DataModel_Get_"),
]
# A TIER-4 KNOWN-ECOSYSTEM SIGNATURE (gh#319), so a declared list ACCUMULATES over
# it rather than replacing it. This is the ingot generator's own enum-constant
# prefix — a fact about that generator, not a name-shape guess about anybody's
# codebase — and under the precedence rule you can correct a guess but you cannot
# un-discover a fact.
#
# It used to REPLACE (`tuple(declared) or DEFAULT_KEY_ALIAS_PREFIXES`), which made
# the SAME generator's defaults combine two different ways one screenful apart: its
# writers and readers below already accumulate (`declared + DEFAULTS`). A repo
# declaring `APP_KEY_` therefore kept `DataModel_Set_` and lost `DM_KEY_`, so an
# ingot repo that also has its own aliases silently stopped normalising the ingot
# half — and the symptom is the orphan write-half the dispatch SPEC calls out,
# which looks like a missing declaration rather than a discarded default.
#
# The ingot generator names its key ENUM constants `DM_KEY_<KEY>` while its
# per-key accessors are `DataModel_Set_<KEY>` — so one generator emits the SAME
# key under two spellings, and which one a call site uses depends only on whether
# the key travels as an argument or as part of a function name. An argument-keyed
# wrapper (`store_bool_on_delta(DM_KEY_WIDGET_ENABLED, v)`)
# therefore yields a key that CANNOT intersect the name-embedded readers of the
# same key, and the declaration that recovers the write half produces an orphan
# with no read half — the exact failure the dispatch SPEC calls out.
#
# Stripping the alias is a built-in DEFAULT extended by a declaration
# (`key_alias_prefixes`), never a hardcoded-only assumption; it pairs with the
# `DataModel_Set_`/`Get_` defaults above and comes from the same generator.
# Measured no-op on every current build: no repo's resolved keys begin with it.
DEFAULT_KEY_ALIAS_PREFIXES: tuple[str, ...] = ("DM_KEY_",)
# Cache key for the built-in defaults (no manifest file to hash). Bump when the
# default pattern set changes, so a cached inferred pass invalidates.
DEFAULT_SHARED_KEY_PATTERNS_VERSION = "ingot-default-v2"
## The manifest field carrying a declared override of the alias prefixes.
KEY_ALIAS_FIELD = "key_alias_prefixes"


## @brief Resolve the writer/reader patterns to use, merging any declared source
##        over the built-in ingot defaults.
## @param path Optional --shared-key-patterns YAML/mapping, or None for defaults only.
## @param extra A second declared document merged after `path` (the dispatch manifest's key wrappers).
## @return (writers, readers, key alias prefixes) after merging every source.
## @version 5
## @req REQ-DDB-SCHEMA-005
## @req REQ-DDB-CONFIG-006
def resolve_shared_key_patterns(
    path: Path | dict | None,
    extra: Path | dict | None = None,
) -> tuple[
    list[AccessorPattern | NamePrefixPattern],
    list[AccessorPattern | NamePrefixPattern],
    tuple[str, ...],
]:
    """Start from the built-in ingot accessor defaults and extend with any
    declared source (parallel to how threads merge declared spawn patterns over
    the built-in primitives). The defaults fire only where matching accessors
    exist, so merging is safe on repos that use a different convention.

    `extra` exists so `dispatch.shared_key_wrappers` — which IS the argument-keyed
    half of this manifest, just written where the rest of the indirection story
    lives — feeds the same parser and the same matcher rather than growing a
    second one.

    DECLARED PATTERNS COME FIRST, and the order is the whole fix. `_match_accessor` is
    FIRST-MATCH, and this function used to append declared patterns AFTER the built-in
    defaults — so a declared pattern whose prefix collides with a default could never
    match, and the default's `dispatch_mode` was used instead. Silently: the edge still
    appeared, carrying the wrong accessor-class provenance, which is worse than no edge
    because it is a plausible answer.

    That inverted this repo's precedence rule — a DECLARATION always beats a built-in
    default (`scope.py`'s declaration > guard > Doxyfile, the CLI flag winning over
    `.clew.yaml`). The merge here was the single place that had it backwards.

    ORDER IS NOT THE SAME QUESTION AS MEMBERSHIP, and conflating them is what the
    gh#319 audit found. Declared patterns come FIRST because `_match_accessor` is
    first-match and a declaration must be able to correct a default's `dispatch_mode`.
    They do not come INSTEAD: the built-ins stay in the list, because they fire only
    where their accessors exist and removing them could only lose edges. That is
    precisely the tier-4 accumulate rule, arrived at here before it had a name — and
    the alias prefixes, from the SAME generator, were doing the opposite one screenful
    away until `resolve_key_alias_prefixes` took over.

    A shadowed default is also WARNED about, because an owner who declares
    `Store_Set` without realising a built-in already claims that prefix should be told
    which one won rather than left to infer it from edge counts.

    @brief Merge declared shared-key patterns ahead of the ingot defaults.
    @return (writers, readers, alias prefixes).
    @version 6
    """
    declared_w: list[AccessorPattern | NamePrefixPattern] = []
    declared_r: list[AccessorPattern | NamePrefixPattern] = []
    for source in (path, extra):
        if source is None:
            continue
        w, r = load_shared_key_patterns(source)
        declared_w += w
        declared_r += r
    _warn_shadowed_defaults(declared_w, DEFAULT_SHARED_KEY_WRITERS, "writer")
    _warn_shadowed_defaults(declared_r, DEFAULT_SHARED_KEY_READERS, "reader")
    return (
        declared_w + list(DEFAULT_SHARED_KEY_WRITERS),
        declared_r + list(DEFAULT_SHARED_KEY_READERS),
        resolve_key_alias_prefixes(path, extra).values,
    )


## @brief Resolve the key-alias prefixes through the five-tier precedence rule.
## @param path The --shared-key-patterns manifest (a Path) or declaration section (a dict), or None.
## @param extra The dispatch manifest's key-wrapper document, or None.
## @return The resolution: the prefixes plus the stated tier that won.
## @version 1
## @req REQ-DDB-CONFIG-006
## @req REQ-DDB-SCHEMA-005
def resolve_key_alias_prefixes(
    path: Path | dict | None,
    extra: Path | dict | None = None,
) -> LayeredResolution:
    """THE SECOND CONSUMER of `tiers.resolve_layered`, and the only other constant
    the gh#319 audit found combining wrongly.

    `DEFAULT_KEY_ALIAS_PREFIXES` is TIER 4 — a known-ecosystem signature — so it
    accumulates and a declaration can add to it but not remove it. There is no
    tier-3 and no tier-5 layer for this option: nothing about a repo's enum naming
    is a language fact, and there are no name-shape guesses here to displace. A
    target stating nothing therefore resolves to the ingot defaults alone, and the
    recorded tier reads `heuristic` — which for an option with an EMPTY tier-5
    layer means "nothing was stated", not "a guess was used".

    THE TWO SOURCES ARE ONE STATED LAYER, and the source type only LABELS the tier.
    `path` and `extra` are different SECTIONS of a target's declaration — the
    accessor manifest and the dispatch manifest's key-wrapper half — not competing
    statements of the same thing, and they have always contributed additively here
    (as they still do for writers and readers). Making them compete because one
    arrived as a flag would drop a repo's `shared_key_wrappers` prefixes the moment
    an operator passed `--shared-key-patterns`, which is a second silent collapse of
    exactly the shape gh#319 exists to remove. A test asserting the opposite is what
    caught the first draft doing it.

    So the tier is a LABEL over the union: `cli._declared_or_flag` hands back a
    `Path` for an explicit `--shared-key-patterns` and the parsed mapping for a
    declaration, so tier 1 is distinguishable without a second argument to keep in
    sync. Only a source that actually CONTRIBUTED a prefix can set it — a manifest
    passed by flag that declares no `key_alias_prefixes` has stated nothing about
    them, and recording `explicit` there would be a provenance record that is
    checkable and wrong.

    PURE, and deliberately so: `cli` calls this a second time to stamp the winning
    tier, because the resolution is computed deep inside the inferred pass where the
    stamping stage cannot reach it. Two calls on identical arguments cannot disagree
    — which is a weaker guarantee than holding one value, so
    `tests/test_tiers.py` pins the two against each other rather than trusting it.

    @brief Resolve the alias prefixes and their provenance.
    @return The LayeredResolution for `key_alias_prefixes`.
    @version 1
    """
    stated: list[str] = []
    by_flag = False
    for source in (path, extra):
        if source is None:
            continue
        contributed = _declared_alias_prefixes(source)
        stated += contributed
        by_flag = by_flag or (bool(contributed) and not isinstance(source, dict))
    return resolve_layered(
        facts=(),
        ecosystem=DEFAULT_KEY_ALIAS_PREFIXES,
        explicit=stated if by_flag else None,
        declared=None if by_flag else (stated or None),
    )


## @brief Warn when a declared pattern shadows a built-in default (or vice versa).
## @param declared The declared patterns for one role.
## @param defaults The built-in patterns for that role.
## @param role 'writer' or 'reader', for the message.
## @return None.
## @version 1
## @dg_internal
def _warn_shadowed_defaults(
    declared: list[AccessorPattern | NamePrefixPattern],
    defaults: Sequence[AccessorPattern | NamePrefixPattern],
    role: str,
) -> None:
    """Reports a collision rather than resolving it silently. Now that declared patterns
    win, a collision means a built-in is UNREACHABLE — which is the intended outcome, but
    an owner should learn it from a log line and not from wondering why `dispatch_mode`
    reads differently than the manifest says.

    Compares only the name-prefix convention: an `AccessorPattern` is an fnmatch glob, and
    deciding whether two globs overlap is a different and much harder question than
    comparing two prefixes. Reporting the easy half honestly beats claiming to check both.

    @brief Log any declared pattern that makes a built-in default unreachable.
    @return None.
    @version 1
    """
    default_prefixes = {p.prefix for p in defaults if isinstance(p, NamePrefixPattern)}
    for pattern in declared:
        if isinstance(pattern, NamePrefixPattern) and pattern.prefix in default_prefixes:
            logger.info(
                "shared_key: declared %s prefix %r shadows a built-in default — the "
                "DECLARED pattern wins (dispatch_mode=%s)",
                role,
                pattern.prefix,
                pattern.dispatch_mode,
            )


## @brief The `key_alias_prefixes` a manifest source declares, if any.
## @param source A patterns manifest path or an already-parsed mapping.
## @return The declared prefixes, or [] when the source declares none.
## @version 2
## @dg_internal
def _declared_alias_prefixes(source: Path | dict) -> list[str]:
    """Reads the raw declaration only; the COMBINATION is
    `resolve_key_alias_prefixes`' job and lives there alone.

    This used to say a declared list REPLACES the built-in default, "because a repo
    that names its enum constants differently is stating that ours does not apply".
    That reasoning does not survive the case it has to cover: an ingot repo with its
    own aliases has BOTH, and the two are not alternatives. Nor did it match the
    writers and readers from the same generator, which have always accumulated.

    @brief Read a declared key-alias prefix list.
    @version 2
    """
    data = source if isinstance(source, dict) else _read_patterns_yaml(source)
    return [str(p) for p in (data.get(KEY_ALIAS_FIELD) or []) if str(p)]


## @brief Parse a patterns manifest file into a mapping.
## @param path Path to the YAML file.
## @return The parsed mapping, or {} when the file is empty.
## @version 2
## @dg_internal
def _read_patterns_yaml(path: Path) -> dict:
    """@brief Read one accessor-patterns YAML file.

    @version 2
    """
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


## @brief Parse a --shared-key-patterns YAML file into (writers, readers).
## @param path Path to the YAML config file.
## @return (writer_patterns, reader_patterns), both possibly empty.
## @version 7
## @req REQ-DDB-SCHEMA-005
def load_shared_key_patterns(
    path: Path | dict,
) -> tuple[
    list[AccessorPattern | NamePrefixPattern],
    list[AccessorPattern | NamePrefixPattern],
]:
    """Load the writer/reader accessor-pattern config. Each entry is EITHER
    the argument-based convention (`pattern` + `key_arg_index`) OR the
    name-based convention (`name_prefix`) — never both.

    Expected shape::

        writers:
          - pattern: "STORE_SET_*"      # argument-based: shared accessor
            key_arg_index: 0
          - name_prefix: "STORE_SET_"    # name-based: one func per key
        readers:
          - pattern: "STORE_GET_*"
            key_arg_index: 0
          - name_prefix: "STORE_GET_"

    No target-repo-specific pattern names are ever hardcoded in this
    module — they are supplied entirely by this external config file.

    Accepts an already-parsed mapping as well as a path, so the same document
    can arrive either as a standalone `--shared-key-patterns` file or as the
    `shared_key_patterns` section of the repo's `.clew.yaml` — one format,
    one parser, two delivery routes.

    @brief Load writer/reader accessor patterns from YAML.
    @version 6
    """
    data = path if isinstance(path, dict) else _read_patterns_yaml(path)
    origin = declaration_origin(path, SECTION_SHARED_KEY)
    return (
        [_parse_pattern_entry(e, f"{origin}: writers") for e in data.get("writers", []) or []],
        [_parse_pattern_entry(e, f"{origin}: readers") for e in data.get("readers", []) or []],
    )


## @brief Parse one YAML pattern entry into an AccessorPattern or NamePrefixPattern.
## @param entry One `writers:`/`readers:` list entry from an accessor manifest.
## @param origin Where the entry was declared, for a fail-closed error message.
## @return A NamePrefixPattern when the entry has a name_prefix, else an AccessorPattern.
## @version 3
## @dg_internal
def _parse_pattern_entry(
    entry: dict,
    origin: str = "shared-key patterns",
) -> AccessorPattern | NamePrefixPattern:
    """Dispatch one writers:/readers: list entry to the matching pattern class by
    which key it contains, validating the declared `dispatch_mode` against the
    schema vocabulary.

    An unknown `dispatch_mode` RAISES rather than normalizing to `'unknown'`:
    the modes are the synchrony axis a consumer reasons about, so silently
    relabelling `queud` as "we do not know" reads identically to a genuinely
    undetermined hand-off.

    @brief Parse one accessor-pattern YAML entry (validating dispatch_mode).
    @version 3
    """
    dispatch_mode = DISPATCH_MODE.validated(
        str(entry.get("dispatch_mode", "unknown")),
        owner=origin,
        field="dispatch_mode",
    )
    if "name_prefix" in entry:
        return NamePrefixPattern(entry["name_prefix"], dispatch_mode)
    return AccessorPattern(entry["pattern"], int(entry.get("key_arg_index", 0)), dispatch_mode)


## @brief Create the shared_key_edges table if it doesn't already exist.
## @version 4
## @req REQ-DDB-SCHEMA-007
def _ensure_shared_key_edges_table(conn: sqlite3.Connection) -> None:
    """Create shared_key_edges + indexes if absent; never drops existing rows.

    Either the inferred or declared stage may run first (or run alone),
    so table creation uses IF NOT EXISTS rather than the DROP-then-CREATE
    pattern used by single-owner tables like `call_edges`. edge_kind
    accepts 'unknown' alongside 'state'/'event' — AST-inferred edges
    can't tell state from event apart (see `_insert_inferred_edges`).

    R1 richness columns (extended CREATE body — no ALTER, every build is
    from-scratch copy→augment→os.replace):
      - `dispatch_mode` — the synchrony axis the explorer matrix grades:
        'inline' (sync on the writer's thread), 'queued' (buffered to a
        consumer thread), 'keyed' (topic/key routing, e.g. MQTT), 'unknown'.
        Inferred from accessor-class provenance (per-pattern) or declared.
      - `edge_triggered` — DECLARED-ONLY per-bus fire-on-change flag; NULL
        unless a manifest asserts it (setter-body property, AST-infeasible).
      - `crosses_thread` / `to_thread_id` — COMPUTED by
        `threads.annotate_thread_boundaries`; NULL when thread data is
        insufficient. `to_thread_id` forward-references `threads(id)`.

    @brief Idempotent shared_key_edges table/index creation.
    @version 5
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS shared_key_edges (
            writer_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            reader_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            key_name      TEXT NOT NULL,
            edge_kind     TEXT NOT NULL {check("shared_key_edges", "edge_kind")},
            declared      INTEGER NOT NULL {bool_check("declared")},
            source        TEXT NOT NULL {check("shared_key_edges", "source")},
            confidence    TEXT NOT NULL {check("shared_key_edges", "confidence")},
            dispatch_mode  TEXT NOT NULL DEFAULT 'unknown'
                             {check("shared_key_edges", "dispatch_mode")},
            edge_triggered INTEGER {bool_check("edge_triggered")},
            crosses_thread INTEGER {bool_check("crosses_thread")},
            to_thread_id   INTEGER REFERENCES threads(id),
            UNIQUE(writer_rowid, reader_rowid, key_name, source)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shared_key_edges_writer ON shared_key_edges(writer_rowid)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shared_key_edges_reader ON shared_key_edges(reader_rowid)",
    )
    conn.commit()


# ─── Source A: inferred (AST pattern match) ─────────────────────────────────


## @brief Return the resolution mode + dispatch_mode if `name` matches a pattern.
## @param name Callee name to classify.
## @param patterns Writer or reader pattern list (mixed AccessorPattern/NamePrefixPattern).
## @return `(kind, value, dispatch_mode)` where kind∈{"arg","name"}, or None.
## @version 3
## @dg_internal
def _match_accessor(
    name: str,
    patterns: list[AccessorPattern | NamePrefixPattern],
) -> tuple[str, int, str] | tuple[str, str, str] | None:
    """First-match `name` against a mixed writer/reader pattern list.

    An `AccessorPattern` match defers key resolution to the call's
    argument (mode `"arg"`); a `NamePrefixPattern` match resolves the key
    immediately from the name itself (mode `"name"`) — no argument node
    needed, since the key-in-name convention has none. The matched
    pattern's `dispatch_mode` (accessor-class provenance) rides along as
    the third element so a matched writer edge inherits it.

    @brief First-match accessor-pattern lookup (either convention).
    @version 3
    """
    for accessor in patterns:
        if isinstance(accessor, NamePrefixPattern):
            if name.startswith(accessor.prefix) and len(name) > len(accessor.prefix):
                return "name", name[len(accessor.prefix) :], accessor.dispatch_mode
        elif fnmatch.fnmatchcase(name, accessor.pattern):
            return "arg", accessor.key_arg_index, accessor.dispatch_mode
    return None


## @brief Extract the Nth positional argument node from a call_expression.
## @return The AST node for the Nth (0-indexed) named argument, or None when out of range.
## @version 1
## @dg_internal
def _nth_call_argument(call_node: Any, index: int) -> Any | None:
    """Return the AST node for the Nth (0-indexed) argument, or None.

    @brief Fetch the Nth argument node of a call_expression.
    @version 1
    """
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return None
    # `argument_list` children include the punctuation tokens ("(", ",",
    # ")"); named_children skips them, giving just the argument expressions.
    named = args_node.named_children
    if index < 0 or index >= len(named):
        return None
    return named[index]


## @brief Strip a declared enum-alias prefix off a resolved key, if one applies.
## @param text The key text as it appeared in the source.
## @param prefixes Alias prefixes to strip (first match wins).
## @return The key with its alias prefix removed, or `text` unchanged.
## @version 1
## @dg_internal
def _strip_key_alias(text: str, prefixes: tuple[str, ...]) -> str:
    """A prefix that consumes the WHOLE token is refused: `DM_KEY_` alone is the
    enum's namespace, not a key, and stripping it to "" would silently merge
    every such site under one empty key.

    @brief Normalize one enum-spelled key to its accessor-name spelling.
    @version 1
    """
    for prefix in prefixes:
        if text.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix) :]
    return text


## @brief Resolve a call argument node to a literal key name, if possible.
## @param node The argument AST node.
## @param src_bytes The file's raw source bytes.
## @param alias_prefixes Enum-alias prefixes to normalize off an identifier key.
## @return The literal key text, or None if the argument isn't a literal.
## @version 3
## @dg_internal
def _resolve_literal_key(
    node: Any, src_bytes: bytes, alias_prefixes: tuple[str, ...] = ()
) -> str | None:
    """A "literal" key is a string literal (quotes stripped) or a bare
    identifier (an enum constant / #define name) — anything else (a
    variable read, member access, nested call, arithmetic) is a computed
    expression and is NOT resolved, per the fail-closed requirement.

    `alias_prefixes` applies only to the IDENTIFIER form, which is the only one
    that can be an enum constant. A string-literal topic and a queue handle are
    left exactly as written. Defaults to no normalization so the thread-name and
    MQTT-topic callers of this function are untouched.

    @brief Resolve a literal string/identifier key argument.
    @version 2
    """
    # Address-of a named object — `&svc_in_msg_queue` — is a literal
    # reference to that named symbol (a queue/mutex handle passed to a
    # QUEUESEND/QUEUERECEIVE accessor), NOT a computed expression. Unwrap
    # the pointer_expression to its inner identifier so queue-handle keys
    # resolve like any other literal key.
    if node.type == "pointer_expression":
        inner = [c for c in node.named_children if c.type == "identifier"]
        if len(inner) != 1:
            return None
        node = inner[0]
    text = src_bytes[node.start_byte : node.end_byte].decode(
        "utf-8",
        errors="replace",
    )
    if node.type == "string_literal":
        return text.strip('"')
    return _strip_key_alias(text, alias_prefixes) if node.type == "identifier" else None


## @brief One matched writer or reader accessor call site.
## @version 1
class _KeyCallSite:
    """One matched accessor call: which function, which key, and (for
    writer sites) the accessor-class `dispatch_mode` provenance the edge
    inherits. Reader/case sites leave `dispatch_mode='unknown'`.

    @brief A single resolved writer/reader call site.
    @version 2
    """

    __slots__ = ("dispatch_mode", "key_name", "rowid")

    ## @brief Store the caller rowid, resolved key name, and dispatch-mode provenance.
    ## @version 1
    ## @dg_internal
    def __init__(self, rowid: int, key_name: str, dispatch_mode: str = "unknown") -> None:
        self.rowid = rowid
        self.key_name = key_name
        self.dispatch_mode = dispatch_mode


## @brief Counters threaded through the shared-key AST walk.
## @version 1
class _SharedKeyCounters:
    """Counters for the shared-key AST walk: matched vs unresolved.

    @brief Shared-key walk counters.
    @version 1
    """

    __slots__ = ("unresolved",)

    ## @brief Initialize the unresolved-argument counter to zero.
    ## @version 1
    ## @dg_internal
    def __init__(self) -> None:
        self.unresolved = 0


## @brief Bundle of writer/reader accessor-pattern lists.
## @version 1
class _SharedKeyPatterns:
    """Immutable bundle of writer/reader accessor-pattern lists, threaded
    through the AST walk as one parameter instead of two.

    @brief Writer + reader accessor-pattern bundle.
    @version 1
    """

    __slots__ = ("alias_prefixes", "readers", "writers")

    ## @brief Store the writer/reader pattern lists and the key-alias prefixes.
    ## @param writers Writer accessor patterns.
    ## @param readers Reader accessor patterns.
    ## @param alias_prefixes Enum-alias prefixes to normalize off identifier keys.
    ## @version 2
    ## @dg_internal
    def __init__(
        self,
        writers: list[AccessorPattern | NamePrefixPattern],
        readers: list[AccessorPattern | NamePrefixPattern],
        alias_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.writers = writers
        self.readers = readers
        self.alias_prefixes = alias_prefixes


## @brief Mutable output collector for the shared-key AST walk.
## @version 1
class _SharedKeyCollector:
    """Mutable output of the shared-key AST walk: matched call sites plus
    unresolved-argument counters, threaded through as one parameter.

    @brief Shared-key walk output collector.
    @version 1
    """

    __slots__ = ("counters", "reader_sites", "writer_sites")

    ## @brief Initialize empty writer/reader site lists and a fresh counter.
    ## @version 1
    ## @dg_internal
    def __init__(self) -> None:
        self.writer_sites: list[_KeyCallSite] = []
        self.reader_sites: list[_KeyCallSite] = []
        self.counters = _SharedKeyCounters()


## @brief First-match a callee name as writer or reader; None if neither.
## @version 2
## @dg_internal
def _match_writer_or_reader(
    callee_name: str,
    patterns: _SharedKeyPatterns,
) -> tuple[str, tuple[str, int, str] | tuple[str, str, str]] | None:
    """Return ("writer"|"reader", mode), or None if `callee_name` matches
    neither the writer nor the reader pattern list. `mode` is the
    resolution mode from `_match_accessor` — `("arg", index, dispatch_mode)`
    or `("name", key_name, dispatch_mode)`.

    @brief Classify a callee name against the writer/reader pattern lists.
    @version 3
    """
    writer_mode = _match_accessor(callee_name, patterns.writers)
    if writer_mode is not None:
        return "writer", writer_mode
    reader_mode = _match_accessor(callee_name, patterns.readers)
    if reader_mode is not None:
        return "reader", reader_mode
    return None


## @brief Classify one call_expression as a writer/reader hit, if it matches.
## @version 2
## @dg_internal
def _classify_call_site(
    node: Any,
    src_bytes: bytes,
    patterns: _SharedKeyPatterns,
) -> tuple[str, tuple[str, int, str] | tuple[str, str, str]] | None:
    """Return ("writer"|"reader", mode) if the callee name matches a writer
    or reader pattern; None if it matches neither.

    @brief Match one call_expression's callee name against the pattern lists.
    @version 2
    """
    callee_node = node.child_by_field_name("function")
    if callee_node is None or callee_node.type != "identifier":
        return None
    callee_name = src_bytes[callee_node.start_byte : callee_node.end_byte].decode(
        "utf-8",
        errors="replace",
    )
    return _match_writer_or_reader(callee_name, patterns)


## @brief Resolve a call's key from an argument-position mode.
## @param node The call_expression node.
## @param src_bytes The file's raw source bytes.
## @param key_arg_index 0-indexed position of the key argument.
## @param alias_prefixes Enum-alias prefixes to normalize off the resolved key.
## @return The literal key text at the given argument index, or None when missing or non-literal.
## @version 2
## @dg_internal
def _resolve_arg_mode_key(
    node: Any, src_bytes: bytes, key_arg_index: int, alias_prefixes: tuple[str, ...] = ()
) -> str | None:
    """Resolve the key from the Nth call argument (the AccessorPattern
    convention). Returns None (unresolved) if the argument is missing or
    not a literal.

    This is the argument-keyed path the alias normalization exists for: it is
    where a generator's `DM_KEY_<KEY>` enum spelling enters, while the
    name-embedded path never sees the prefix at all.

    @brief Resolve an argument-mode key.
    @version 2
    """
    arg_node = _nth_call_argument(node, key_arg_index)
    if arg_node is None:
        return None
    return _resolve_literal_key(arg_node, src_bytes, alias_prefixes)


## @brief Record one matched call site's literal key (or count it unresolved).
## @param node The matched call_expression node.
## @param src_bytes The file's raw source bytes.
## @param role "writer" or "reader".
## @param mode `(kind, value, dispatch_mode)` from `_classify_call_site`.
## @param out The per-file `{"w","r","u"}` collector.
## @param alias_prefixes Enum-alias prefixes to normalize off an argument key.
## @version 4
## @dg_internal
def _record_call_site(
    node: Any,
    src_bytes: bytes,
    role: str,
    mode: tuple[str, int, str] | tuple[str, str, str],
    out: dict[str, list],
    alias_prefixes: tuple[str, ...] = (),
) -> None:
    """Resolve the matched call's key (from an argument or the callee name
    itself, depending on `mode`) and file it as a writer or reader site keyed
    by SOURCE LINE, or record the line as unresolved when an argument-mode key
    isn't a literal. A writer site carries the matched accessor-class
    `dispatch_mode` provenance; reader sites don't need it.

    @brief Resolve + file one matched writer/reader call site.
    @version 4
    """
    kind, value, dispatch_mode = mode
    line = node.start_point[0] + 1
    if kind == "name":
        key_name: str | None = str(value)
    else:
        key_name = _resolve_arg_mode_key(node, src_bytes, int(value), alias_prefixes)
    if key_name is None:
        out["u"].append(line)
        return
    if role == "writer":
        out["w"].append([line, key_name, dispatch_mode])
    else:
        out["r"].append([line, key_name])


## @brief Record one switch/case label's literal as a reader site.
## @param case_node The case_statement node.
## @param src_bytes The file's raw source bytes.
## @param out The per-file `{"w","r","u"}` collector.
## @param alias_prefixes Enum-alias prefixes to normalize off the case literal.
## @version 3
## @dg_internal
def _record_case_site(
    case_node: Any,
    src_bytes: bytes,
    out: dict[str, list],
    alias_prefixes: tuple[str, ...] = (),
) -> None:
    """Resolve a `case <value>:` label's literal and file it as a reader
    site of the enclosing function — a switch/case dispatch on a symbolic
    key IS a reaction to that key, structurally distinct from a call but
    the same relationship. `default:` has no value field and is skipped
    (not a key match, not something to count unresolved). A `case` value
    that isn't a literal/identifier (a numeric constant, say) is counted
    unresolved rather than guessed at, same as a non-literal call argument.

    A case label is normalized like an argument key: `switch (key_id) { case
    DM_KEY_X: }` is the READ half of exactly the write an argument-keyed wrapper
    performs, and leaving the two spellings apart would keep them from meeting.

    @brief Resolve + file one case-label reader site.
    @version 3
    """
    value_node = case_node.child_by_field_name("value")
    if value_node is None:
        return  # `default:` — not a key match, nothing to resolve
    line = case_node.start_point[0] + 1
    key_name = _resolve_literal_key(value_node, src_bytes, alias_prefixes)
    if key_name is None:
        out["u"].append(line)
        return
    out["r"].append([line, key_name])


## @brief Resolve a Python argument node to a literal key name, if possible.
## @param node The argument AST node.
## @param src_bytes The file's raw source bytes.
## @param alias_prefixes Enum-alias prefixes to normalize off a name key.
## @return The literal key text, or None when the argument is computed.
## @version 4
## @dg_internal
def _resolve_py_literal_key(
    node: Any, src_bytes: bytes, alias_prefixes: tuple[str, ...] = ()
) -> str | None:
    """Python's literal-key shapes differ from C's in two ways that matter.

    A string is a `string` node whose text INCLUDES its quotes and whose quote
    style varies (`'x'`, `"x"`, `f"x"`), so C's `text.strip('"')` would keep the
    quotes on a single-quoted topic; `pyast.string_value` reads `string_content`
    instead and refuses an interpolated f-string rather than recording a template
    as a key.

    An enum member is an `attribute` (`EventType.LOG_ENTRY_ADDED`), not the bare
    identifier C uses for an enum constant — and this is the shape a real repo
    actually uses (measured on a real Python codebase: every keyed `publish`/`subscribe`
    pair keys on `EventType.*`). Accepting only a bare identifier would leave the
    layer empty on a repo that has the dataflow and has declared it.

    A BARE IDENTIFIER IS REFUSED, and that is the load-bearing difference from
    the C resolver. C's bare identifier is genuinely a constant token — an enum
    constant or a `#define`, both compile-time. Python has no such thing: an
    unqualified name is a binding, so `bus.publish(t, 2)` keys on a PARAMETER.
    Accepting it makes every call site that forwards a variable collapse onto one
    fabricated key and cross-products its writers with its readers — the #47
    failure mode by another route (5294 fabricated edges against 549 real ones).
    A `self.`/`cls.`-headed chain is refused for the same reason: it is an
    instance attribute, i.e. a variable that merely happens to contain a dot, and
    the same text in two unrelated classes is two different values.

    Accepted cost, stated plainly: a repo keying on a module-level constant
    (`publish(TOPIC_ALPHA, ...)`) yields no key. That is a false NEGATIVE, which
    this layer prefers by policy — and such a repo can key on the string or an
    enum member instead. A computed chain (`self._topics[i]`) was already refused.

    @brief Resolve a Python string / enum-member key argument (never a variable).
    @return The key text, or None.
    @version 3
    """
    text = string_value(node, src_bytes)
    if text is not None:
        return text
    dotted = dotted_name(node, src_bytes) if node is not None else None
    if dotted is None or "." not in dotted or dotted.partition(".")[0] in SELF_NAMES:
        return None
    return _strip_key_alias(dotted, alias_prefixes)


## @brief Walk one parsed Python file, harvesting writer/reader key sites.
## @param tree The parsed Python tree.
## @param src_bytes The file's raw source bytes.
## @param patterns The active writer/reader accessor patterns.
## @return {"w": [...], "r": [...], "u": [...]} of line-keyed, rowid-free sites.
## @version 4
## @dg_internal
def _walk_py_shared_key_calls(
    tree: Any,
    src_bytes: bytes,
    patterns: _SharedKeyPatterns,
) -> dict[str, list]:
    """Matches an accessor by the callee's TAIL name, so a declared `publish`
    pattern fires on `self._bus.publish(...)` as well as a bare `publish(...)`.
    Tail matching is right here and wrong for thread spawns because the two
    answer different questions: an accessor pattern is a glob the repo DECLARED,
    while a spawn default is shipped by clew and must never match a name it
    was not told about.

    There is deliberately NO built-in Python accessor default. `publish`,
    `subscribe`, `get` and `set` are ordinary method names on countless unrelated
    objects, so defaulting them would manufacture a dataflow graph out of
    coincidence — the #47 failure. A Python codebase's dataflow appears only once it
    declares its convention in `.clew.yaml`.

    Python has no `case_statement`; `match`/`case` exists as `case_clause` but
    neither codebase uses it (measured: 0 case clauses), so no dispatch-site
    source is claimed here rather than one being written blind.

    @brief Walk Python accessor call sites for shared keys.
    @return Per-file writer/reader/unresolved payload.
    @version 4
    """
    out: dict[str, list] = {"w": [], "r": [], "u": []}
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call":
            continue
        dotted = dotted_name(node.child_by_field_name("function"), src_bytes)
        if dotted is None:
            continue
        classification = _match_writer_or_reader(tail_name(dotted), patterns)
        if classification is not None:
            _record_py_call_site(node, src_bytes, classification, out, patterns.alias_prefixes)
    return out


## @brief Record one matched Python accessor call's key (or count it unresolved).
## @param node The matched `call` node.
## @param src_bytes The file's raw source bytes.
## @param classification (role, mode) from `_match_writer_or_reader`.
## @param out The per-file `{"w","r","u"}` collector.
## @param alias_prefixes Enum-alias prefixes to normalize off the key.
## @version 1
## @dg_internal
def _record_py_call_site(
    node: Any,
    src_bytes: bytes,
    classification: tuple[str, tuple],
    out: dict[str, list],
    alias_prefixes: tuple[str, ...] = (),
) -> None:
    """Reads the key from Python's POSITIONAL arguments only. The C helper counts
    every named child, which in an `argument_list` includes `keyword_argument`
    nodes — so `publish(topic, data, qos=0)` would shift indices once a keyword
    appeared before the key.

    @brief Resolve + file one matched Python accessor call site.
    @version 1
    """
    role, mode = classification
    kind, value, dispatch_mode = mode
    line = node.start_point[0] + 1
    if kind == "name":
        key_name: str | None = str(value)
    else:
        arg = positional_argument(node, int(value))
        key_name = (
            _resolve_py_literal_key(arg, src_bytes, alias_prefixes) if arg is not None else None
        )
    if key_name is None:
        out["u"].append(line)
        return
    if role == "writer":
        out["w"].append([line, key_name, dispatch_mode])
    else:
        out["r"].append([line, key_name])


## @brief Walk one parsed file's AST, harvesting writer/reader key sites.
## @return {"w": [...], "r": [...], "u": [...]} of line-keyed, rowid-free sites.
## @version 4
## @dg_internal
def _walk_shared_key_calls(
    tree: Any,
    src_bytes: bytes,
    patterns: _SharedKeyPatterns,
) -> dict[str, list]:
    """Walk the parse tree iteratively, classifying accessor call sites AND
    switch/case dispatch sites.

    Mirrors `call_edges._ast_walk_calls`'s traversal shape. Two site
    sources feed the same writer/reader collector: an explicit accessor
    CALL matched against `patterns` (as before), and a `case <value>:`
    label inside ANY switch statement, always treated as a candidate
    reader — a common real-world dispatch shape (`switch (key) { case
    KEY_X: ...; }`) that has no accessor call to match against at all.
    A case label only produces an edge when its literal ALSO matches some
    writer's key (the existing writer∩reader intersection in
    `_build_inferred_edges`), so scanning every switch unconditionally
    does not need its own pattern config to stay fail-closed on noise.

    `patterns.alias_prefixes` is threaded into BOTH site recorders. It used to be
    stored on the bundle and read by neither, so every `alias_prefixes` parameter
    below it defaulted to `()` and the enum-alias normalization was dead code:
    an argument-keyed write of `DM_KEY_FOO` could never meet a name-embedded read
    of `FOO`. Both halves must normalize or neither should.

    A Python tree is delegated to `_walk_py_shared_key_calls`. Without that
    delegation the pass was structurally BLIND on Python, not merely empty: it
    gates on `call_expression`, a node the Python grammar never emits, so a repo
    could declare its accessor convention and still get zero edges. That is the
    same class of error as the #29 macro blindness recorded in CLAUDE.md — "no
    rows" was a claim about the detector.

    @brief Walk shared-key accessor calls and case-label dispatch sites.
    @version 5
    """
    if is_python_tree(tree):
        return _walk_py_shared_key_calls(tree, src_bytes, patterns)
    out: dict[str, list] = {"w": [], "r": [], "u": []}
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "case_statement":
            _record_case_site(node, src_bytes, out, patterns.alias_prefixes)
            continue
        if node.type != "call_expression":
            continue
        classification = _classify_call_site(node, src_bytes, patterns)
        if classification is None:
            continue
        role, mode = classification
        _record_call_site(node, src_bytes, role, mode, out, patterns.alias_prefixes)
    return out


## @brief Layer 5a's cacheable per-file shared-key site harvester.
## @version 1
class _SharedKeyHarvester(Harvester):
    """Records line-keyed writer/reader/unresolved sites per file. The
    accessor patterns decide what matches at all, so the --shared-key-patterns
    manifest's content hash is folded into the cache key.

    @brief Layer 5a per-file harvester.
    @version 1
    """

    stage = STAGE_SHARED_KEY
    # Bump when _walk_shared_key_calls' extraction changes.
    # 2: alias_prefixes now reach the site recorders, so a cached payload from
    #    before that fix carries un-normalized `DM_KEY_*` keys.
    # 3: Python files are walked at all, so a `.py` path that previously cached
    #    an empty payload can now yield real sites.
    stage_version = 3
    label = "shared-key AST"

    ## @brief Store the accessor-pattern bundle plus the manifest cache key.
    ## @version 1
    ## @dg_internal
    def __init__(self, patterns: _SharedKeyPatterns, extra_key: str) -> None:
        super().__init__(extra_key)
        self.patterns = patterns

    ## @brief Harvest one file's writer/reader key sites.
    ## @return The per-file {"w","r","u"} payload.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-005
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _walk_shared_key_calls(tree, src_bytes, self.patterns)


## @brief Layer 5a's harvester for one resolved accessor vocabulary.
## @param patterns_path The --shared-key-patterns manifest (Path), declaration section (dict), or None.
## @param extra The dispatch manifest's `shared_key_wrappers` half, or None.
## @return A Harvester keyed on both declarations' content hashes.
## @version 1
## @req REQ-DDB-SCHEMA-005
def shared_key_harvester(
    patterns_path: Path | dict | None = None,
    extra: Path | dict | None = None,
) -> Harvester:
    """The ONE construction site. It matters more here than for the other stages
    because `resolve_shared_key_patterns` WARNS about declared prefixes that shadow a
    built-in default: resolving twice per build would print that warning twice and
    invite the reader to look for two declarations.

    @brief Build this stage's harvester.
    @version 1
    """
    writers, readers, alias_prefixes = resolve_shared_key_patterns(patterns_path, extra)
    return _SharedKeyHarvester(
        _SharedKeyPatterns(writers, readers, alias_prefixes),
        _inferred_cache_key(patterns_path, extra),
    )


## @brief Resolve one file's harvested key sites into the cross-file collector.
## @version 1
## @dg_internal
def _fold_shared_key_payload(
    payload: dict[str, list],
    funcs_in_file: list[tuple[int, str, int, int]],
    collector: _SharedKeyCollector,
) -> None:
    """Map each harvested line to its enclosing function's memberdef rowid;
    sites in no indexed function are dropped (and their unresolved-key lines
    are not counted), exactly as the original single-pass walk did.

    @brief Fold one file's shared-key harvest.
    @version 1
    """
    for line, key_name, dispatch_mode in payload["w"]:
        rowid = _ast_caller_at_line(funcs_in_file, line)
        if rowid is not None:
            collector.writer_sites.append(_KeyCallSite(rowid, key_name, dispatch_mode))
    for line, key_name in payload["r"]:
        rowid = _ast_caller_at_line(funcs_in_file, line)
        if rowid is not None:
            collector.reader_sites.append(_KeyCallSite(rowid, key_name))
    for line in payload["u"]:
        if _ast_caller_at_line(funcs_in_file, line) is not None:
            collector.counters.unresolved += 1


## @brief Group call sites by key name into rowid sets.
## @return A dict mapping each key name to the set of caller rowids touching it.
## @version 1
## @dg_internal
def _group_sites_by_key(sites: list[_KeyCallSite]) -> dict[str, set[int]]:
    """Group call sites by key name into rowid sets.

    @brief Group writer/reader call sites by key.
    @version 1
    """
    grouped: dict[str, set[int]] = {}
    for site in sites:
        grouped.setdefault(site.key_name, set()).add(site.rowid)
    return grouped


## @brief Build a (key, writer_rowid) -> dispatch_mode provenance map.
## @return A dict mapping each (key name, writer rowid) pair to its accessor-class dispatch_mode.
## @version 2
## @req REQ-DDB-SCHEMA-002
def _writer_dispatch_map(sites: list[_KeyCallSite]) -> dict[tuple[str, int], str]:
    """Map each (key, writer rowid) to its accessor-class dispatch_mode.

    When the same writer touches the same key through patterns of differing
    dispatch_mode, a non-'unknown' provenance wins over 'unknown' (an
    explicit class is more informative than the default).

    @brief Collapse writer sites into a (key, rowid) -> dispatch_mode map.
    @version 2
    """
    mapping: dict[tuple[str, int], str] = {}
    for site in sites:
        pk = (site.key_name, site.rowid)
        existing = mapping.get(pk)
        if existing is None or existing == "unknown":
            mapping[pk] = site.dispatch_mode
    return mapping


## @brief Build (writer, reader, key, dispatch_mode) tuples, suppressing fan-out.
## @param writer_by_key Key name → rowids that WRITE it.
## @param reader_by_key Key name → rowids that READ it.
## @param writer_dispatch (key, writer rowid) → the writer's accessor dispatch_mode.
## @return (edge tuples, suppressed keys as (name, writers, readers) triples).
## @version 3
## @dg_internal
## @req REQ-DDB-PIPE-010
def _build_inferred_edges(
    writer_by_key: dict[str, set[int]],
    reader_by_key: dict[str, set[int]],
    writer_dispatch: dict[tuple[str, int], str],
) -> tuple[list[tuple[int, int, str, str]], list[tuple[str, int, int]]]:
    """Cross writer x reader rowids sharing a key into edge tuples, each
    tagged with the writer's accessor-class `dispatch_mode`.

    A key is suppressed when it would contribute more than `_MAX_KEY_EDGES`
    edges — `writers x readers`, the actual cost, rather than either side on its
    own. See the constant for why the per-side test discarded exactly the funnel
    and broadcast shapes the layer most wants, and why the product ceiling admits
    every key the per-side test did.

    Returns the suppressed keys as (name, writers, readers) triples rather than a
    bare count. The count alone was actively unhelpful: a reader who asked what a
    key reached, and got nothing, had no way to learn from `6 fan-out keys
    suppressed` that theirs was one of the six, and finding out meant reading this
    module (gh#28).

    @brief Cross writer/reader rowid sets into edges, suppressing quadratic keys.
    @return (edge tuples, suppressed key triples).
    @version 3
    """
    edges: list[tuple[int, int, str, str]] = []
    suppressed: list[tuple[str, int, int]] = []
    shared_keys = set(writer_by_key) & set(reader_by_key)
    for key_name in sorted(shared_keys):
        writer_rowids = writer_by_key[key_name]
        reader_rowids = reader_by_key[key_name]
        if len(writer_rowids) * len(reader_rowids) > _MAX_KEY_EDGES:
            suppressed.append((key_name, len(writer_rowids), len(reader_rowids)))
            continue
        for writer_rowid in writer_rowids:
            dispatch_mode = writer_dispatch.get((key_name, writer_rowid), "unknown")
            for reader_rowid in reader_rowids:
                edges.append((writer_rowid, reader_rowid, key_name, dispatch_mode))
    return edges, suppressed


## @brief Name every suppressed fan-out key and its writer/reader counts.
## @param suppressed (key name, writers, readers) triples that were dropped.
## @return None.
## @version 1
## @dg_internal
## @req REQ-DDB-PIPE-010
def _log_suppressed_keys(suppressed: list[tuple[str, int, int]]) -> None:
    """Silent when nothing was suppressed, so a clean build gains no line — but
    when a key IS dropped its name is said out loud, at INFO, beside the product
    that exceeded the ceiling. The absence of this line is what made gh#28 a
    source-reading exercise: the layer reported how MANY keys it discarded and
    never which, so the one key a reader was asking about looked simply absent.

    @brief Log the name and shape of each suppressed fan-out key.
    @return None.
    @version 1
    """
    for key_name, writers, readers in suppressed:
        logger.info(
            "shared_key_edges: suppressed fan-out key %s — %d writers x %d readers "
            "= %d edges, above the %d-edge ceiling",
            key_name,
            writers,
            readers,
            writers * readers,
            _MAX_KEY_EDGES,
        )


## @brief Insert inferred shared-key edges, ignoring duplicates.
## @version 3
## @dg_internal
def _insert_inferred_edges(
    conn: sqlite3.Connection,
    edges: list[tuple[int, int, str, str]],
) -> int:
    """Insert inferred shared-key edges, ignoring duplicates.

    edge_kind='unknown', not 'state': AST discovery cannot tell a
    persistent state key from a transient one-shot occurrence (a queue
    item, say) — that's a property of the key itself, only known from an
    authoritative declaration (see `import_shared_key_edges_declared`).
    Asserting 'state' here would be a guess dressed up as a fact.
    `dispatch_mode` DOES ride along: it is accessor-class provenance (which
    writer pattern matched), not a syntactic guess. `edge_triggered` stays
    NULL — a fire-on-change property is declared-only.

    @brief Bulk-insert inferred shared_key_edges rows.
    @version 3
    """
    return conn.executemany(
        """
        INSERT OR IGNORE INTO shared_key_edges
            (writer_rowid, reader_rowid, key_name, edge_kind, declared,
             source, confidence, dispatch_mode)
        VALUES (?, ?, ?, 'unknown', 0, 'shared_key_inferred', 'medium', ?)
        """,
        edges,
    ).rowcount


## @brief Walk every indexed file's AST, collecting shared-key call sites.
## @return Cross-file collector of writer/reader sites + unresolved counters.
## @version 3
## @dg_internal
def _walk_all_files_for_shared_keys(
    conn: sqlite3.Connection,
    repo_root: Path,
    harvester: Harvester,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None = None,
) -> _SharedKeyCollector:
    """Drive the content-sha-cached per-file harvest, then fold each file's
    payload against the current build's memberdef rowids.

    It RECEIVES the harvester rather than rebuilding it from the patterns and a
    separately-passed key: gh#358's shared parse pass builds it once (resolving the
    declaration, and warning about shadowed defaults, once) and hands the same object
    here, so the warmed key and the read key are the same key.

    @brief Per-file AST walk collecting shared-key call sites.
    @version 3
    """
    _, file_funcs = _build_function_indexes(conn)
    collector = _SharedKeyCollector()
    for path_rowid, payload in run_harvest(conn, repo_root, harvester, ts_classes, cache):
        funcs_in_file = file_funcs.get(path_rowid, [])
        if funcs_in_file:
            _fold_shared_key_payload(payload, funcs_in_file, collector)
    return collector


## @brief Layer 5a: infer shared-key edges from accessor-pattern AST matches.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param patterns_path Path to the --shared-key-patterns YAML file, or None.
## @param cache Optional incremental index cache; None disables caching.
## @version 3
# A NAME-based accessor: at least one leading token, a `Set`/`Get` verb, then a
# key that starts with an uppercase letter or digit. Two real conventions match:
# snake with a trailing underscore (`DataModel_Set_<KEY>`) and CamelCase with no
# separator (`Store_SetAreaData`, `Telemetry_SetLastSampleId`). group(1) is
# the family prefix (through the verb + any separator), group(2) is the key.
# Requiring a LEADING token separates a data-model family — one function per key,
# sharing a long common prefix — from an object setter (`set_level`), which has
# none. Requiring an UPPERCASE-initial key separates it from a lowercase command
# handler (`handle_get_stage_list_cmd`), whose "key" is a verb phrase.
_ACCESSOR_NAME_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*_(?:[Ss]et|[Gg]et)_?)([A-Z0-9].*)$"
)
# A family needs this many DISTINCT keys to be worth suggesting — a couple of
# prefixed setters is not a data model; a dozen is.
_MIN_ACCESSOR_FAMILY_KEYS = 4

# The memberdef kinds this diagnostic searches, PUBLIC so the count of what was
# examined is taken over the same corpus as the families found in it (gh#320). A
# zero reported against the wrong denominator is worse than no denominator: it
# would state that a large corpus was searched when the search read a different one.
#
# FUNCTIONS AND MACROS both. A repo whose accessor family is macro-defined produces
# ZERO `kind='function'` rows, so reading only functions makes this diagnostic blind
# to the case it exists to catch. `macro definition` is doxygen's own literal — the
# spelling is load-bearing and `define` matches nothing.
ACCESSOR_CORPUS_KINDS: tuple[str, ...] = ("function", "macro definition")


## @brief One undeclared accessor family: its prefix, key count, and whose code it is.
## @version 1
@dataclass(frozen=True)
class AccessorFamily:
    """A SUGGESTION IS ONLY ACTIONABLE IF THE OPERATOR CAN ACT ON IT (gh#352 half 3), and that
    is what `external_root` decides. Measured by probing this detector against both public
    targets: [tvanfossen/entropic](https://github.com/tvanfossen/entropic) examines 17,773
    distinct names and names NINE families, ALL NINE vendored inside `extern/llama.cpp`
    (`ma_*` from miniaudio, `ggml_set_*`); Mbed-TLS/mbedtls examines 5,967 and names TWO, both
    DES key-schedule setters. So the diagnostic named 11 families across two repos and an
    operator should declare NONE of them.

    Undifferentiated, that is a hint that costs an operator real time and yields nothing — the
    same shape as `lock_roster` telling a caller to quote a count that is 57% another
    repository's. Split, the first-party list is the actionable one and the external count is
    context.

    `external_root` is '' for first party, which keeps the wire form quiet on the common case
    (`_absent` prunes empty strings inside rows) and matches `LockEntry`.

    @brief An undeclared accessor family with its origin.
    @version 1
    """

    prefix: str
    keys: int
    external_root: str = ""


## @brief Suggest undeclared name-based accessor families no active pattern covers.
## @param conn Open connection to the built DB.
## @param patterns The active writer+reader patterns (defaults + any declared).
## @return AccessorFamily rows, largest first, for families NOT covered by any active NamePrefixPattern and carrying at least _MIN_ACCESSOR_FAMILY_KEYS keys.
## @version 7
## @req REQ-DDB-SCHEMA-005
## @req REQ-DDB-CONFIG-007
def detect_undeclared_accessor_families(
    conn: sqlite3.Connection,
    patterns: list[Any],
) -> list[AccessorFamily]:
    """Find set/get-shaped accessor FAMILIES (one function per key, sharing a
    long common prefix) that no active `NamePrefixPattern` matches — the
    dataflow a repo has but has not declared, so it silently produces no
    shared_key_edges (as a C/POSIX library's `topics_set_*` accessor family does).
    Purely advisory: it suggests what a `--shared-key-patterns` manifest could
    declare; it never fabricates edges. Object setters (`set_level`) carry no
    leading token and are excluded by construction; argument-based
    `AccessorPattern`s have no prefix and cannot cover a name family, so only
    `NamePrefixPattern` prefixes count as coverage.

    EACH FAMILY NOW CARRIES ITS ORIGIN (gh#352 half 3). A family whose functions live in a
    vendored submodule is not something the operator of THIS repo can declare, and naming it
    beside the ones they can is how a diagnostic trains its reader to ignore it. See
    `AccessorFamily` for the measurement.

    A FAMILY WITH FUNCTIONS ON BOTH SIDES IS FIRST PARTY, the same asymmetry
    `scope._is_dependency_of_parent` and `locks._origin_per_mutex` argue: if any part of the
    family is this repo's, declaring a prefix is an action the operator can take, and
    mislabelling it external would remove it from the list they act on.

    @brief Suggest undeclared name-based accessor families, split by origin.
    @version 7
    """
    covered = tuple(
        p.prefix.lower() for p in patterns if isinstance(p, NamePrefixPattern) and p.prefix
    )
    families: dict[str, set[str]] = {}
    origins: dict[str, set[str]] = {}
    ## The kinds live in `ACCESSOR_CORPUS_KINDS` so that `diagnostics.collect` can count
    ## the corpus this reads WITHOUT restating the predicate. Two spellings of one filter
    ## is how a denominator silently stops describing its numerator.
    for name, owner in conn.execute(_accessor_corpus_sql(conn), ACCESSOR_CORPUS_KINDS):
        match = _ACCESSOR_NAME_RE.match(name or "")
        if match is None:
            continue
        prefix, key = match.group(1), match.group(2)
        if any(prefix.lower().startswith(c) for c in covered):
            continue
        families.setdefault(prefix, set()).add(key)
        origins.setdefault(prefix, set()).add(owner or "")
    out = [
        AccessorFamily(
            prefix=prefix,
            keys=len(keys),
            ## '' wins whenever ANY row is first party — see the both-sides rule above.
            external_root="" if "" in origins[prefix] else sorted(origins[prefix])[0],
        )
        for prefix, keys in families.items()
        if len(keys) >= _MIN_ACCESSOR_FAMILY_KEYS
    ]
    return sorted(out, key=lambda f: (-f.keys, f.prefix))


## @brief The corpus query, joining the external tag only when this index carries it.
## @param conn Open connection.
## @return SQL selecting (name, external_root) over the accessor corpus kinds.
## @version 1
## @dg_internal
def _accessor_corpus_sql(conn: sqlite3.Connection) -> str:
    """`LEFT JOIN`, and `COALESCE(bodyfile_id, file_id)`: a macro definition has no body file,
    and a header declaration's `file_id` is the only site it has. Preferring the BODY file
    matches the decl/def duality rule the rest of the pipeline follows — the definition is the
    row that says where the code actually lives.

    `''` for an index predating gh#335, which reads as "every family is first party" — and that
    is TRUE for such an index, because it excluded nested trees outright rather than tagging
    them.

    @brief Build the accessor-corpus query for this index's schema.
    @return SQL text.
    @version 1
    """
    placeholders = ",".join("?" * len(ACCESSOR_CORPUS_KINDS))
    if not _has_external_column(conn):
        return f"SELECT DISTINCT name, '' FROM memberdef WHERE kind IN ({placeholders})"
    return (
        f"SELECT DISTINCT m.name, COALESCE(p.{EXTERNAL_ROOT_COLUMN}, '') "
        "FROM memberdef m "
        "LEFT JOIN path p ON p.rowid = COALESCE(m.bodyfile_id, m.file_id) "
        f"WHERE m.kind IN ({placeholders})"
    )


## @brief Whether this index's `path` table carries the external-provenance column.
## @param conn Open connection.
## @return True when the column is present.
## @version 1
## @dg_internal
def _has_external_column(conn: sqlite3.Connection) -> bool:
    """@brief Report whether `path` carries the external-root column.
    @return True when present.
    @version 1
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='path'"
    ).fetchone():
        return False
    present = {r[1] for r in conn.execute("PRAGMA table_info(path)")}
    return EXTERNAL_ROOT_COLUMN in present


## @brief Log a hint when undeclared accessor families are present, first party first.
## @param conn Open connection to the built DB.
## @param patterns The active writer+reader patterns.
## @return None.
## @version 2
## @dg_internal
def _log_undeclared_accessor_hint(conn: sqlite3.Connection, patterns: list[Any]) -> None:
    """Turn the correct-but-silent empty/sparse dataflow layer into an
    actionable prompt: name the top undeclared accessor families and their key
    counts so an owner knows what a `--shared-key-patterns` manifest could map.

    ONLY FIRST-PARTY FAMILIES ARE NAMED (gh#352 half 3). An owner cannot declare a prefix for
    code they do not own, so a vendored family in this list is advice that costs time and
    yields nothing — and a hint whose entries are mostly unactionable teaches its reader to
    skip the hint. Measured across both public targets, 11 of 11 named families were vendored
    or otherwise not the operator's to declare.

    THE EXTERNAL ONES ARE COUNTED, NOT SILENCED. Dropping them entirely would leave an owner
    unable to tell "the detector found nothing" from "the detector found nine things in
    somebody else's code", and those call for different next steps.

    @brief Emit the undeclared-accessor-family suggestion to the log, first party first.
    @version 2
    """
    families = detect_undeclared_accessor_families(conn, patterns)
    if not families:
        return
    ours = [f for f in families if not f.external_root]
    theirs = [f for f in families if f.external_root]
    if not ours:
        logger.info(
            "shared_key_edges: %d undeclared accessor famil%s detected, but ALL of them are in "
            "vendored trees (%s) — nothing here is yours to declare, so no manifest would help",
            len(theirs),
            "y" if len(theirs) == 1 else "ies",
            ", ".join(sorted({f.external_root for f in theirs})),
        )
        return
    top = ", ".join(f"{f.prefix}* ({f.keys} keys)" for f in ours[:5])
    logger.info(
        "shared_key_edges: %d undeclared accessor famil%s in THIS repo (%s) — declare a "
        "--shared-key-patterns manifest (name_prefix) to map this dataflow%s",
        len(ours),
        "y" if len(ours) == 1 else "ies",
        top,
        f"; {len(theirs)} more are in vendored trees and are not yours to declare"
        if theirs
        else "",
    )


## @brief Cache key for the inferred pass, covering every pattern source.
## @param patterns_path The --shared-key-patterns manifest, or None.
## @param extra The dispatch manifest's `shared_key_wrappers` document, or None.
## @return The extract_cache key component for this pass.
## @version 1
## @dg_internal
def _inferred_cache_key(patterns_path: Path | dict | None, extra: Path | dict | None) -> str:
    """BOTH manifests decide what the per-file harvest matches, so both belong in
    the key — a dispatch declaration that grew a `shared_key_wrappers` entry must
    re-harvest, exactly as editing the standalone manifest does. Empty
    contributions are dropped rather than joined as `""`, so a build declaring
    neither (or only the standalone manifest) keeps the key it already had and no
    existing cache is invalidated by this parameter merely existing.

    @brief Compose the inferred shared-key pass's cache key.
    @return Cache key string.
    @version 1
    """
    declared = [k for k in (manifest_key(patterns_path), manifest_key(extra)) if k]
    if not declared:
        return DEFAULT_SHARED_KEY_PATTERNS_VERSION
    return f"{'+'.join(declared)}+{DEFAULT_SHARED_KEY_PATTERNS_VERSION}"


def import_shared_key_edges_inferred(
    db_path: Path,
    repo_root: Path,
    patterns_path: Path | dict | None,
    cache: IndexCache | None = None,
    extra: Path | dict | None = None,
    harvester: _SharedKeyHarvester | None = None,
) -> None:
    """Walk the same tree-sitter file set `import_ast_call_edges` uses,
    matching call sites against caller-supplied writer/reader accessor
    patterns AND every switch/case dispatch site (unconditional once this
    pass runs at all — see the module docstring), and emit shared_key_edges
    rows for every (writer, reader) pair sharing a literal key. No-ops
    cleanly when no patterns config is given, or when tree_sitter isn't
    installed.

    `extra` is a SECOND declared patterns document merged over the first — the
    `dispatch` manifest's `shared_key_wrappers` section, which IS the
    argument-keyed half of this manifest written where the rest of a repo's
    indirection story lives. It feeds the same parser and the same matcher
    rather than growing a second one (#37).

    The resolved alias prefixes are now HANDED TO THE MATCHER. They were
    resolved and then dropped, so the `DM_KEY_` normalization was plumbed
    through every walker parameter and enabled by nothing: an argument-keyed
    wrapper yielded key `DM_KEY_FOO` while the name-embedded readers of the same
    key yield `FOO`, the two could never intersect, and a declared wrapper
    produced an orphan write-half — the exact failure the dispatch SPEC calls
    out as the reason #37 needs the normalization at all.

    `harvester` is the one gh#358's shared parse pass built and warmed the cache
    with. It carries the RESOLVED patterns, which is why the resolution no longer
    happens here: doing it in both places would emit the shadowed-default warnings
    twice and would let the warmed cache key drift from the read one.

    @brief Import inferred shared-key edges from an AST pattern + case match.
    @version 11
    @req REQ-DDB-SCHEMA-005
    """
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info(
            "tree_sitter not available — skipping inferred shared-key pass",
        )
        return

    # No --shared-key-patterns given ⇒ fall back to the built-in ingot accessor
    # defaults (they fire only where such accessors exist), rather than skipping
    # the pass entirely and leaving the causal dataflow layer empty.
    if patterns_path is None and extra is None:
        logger.info(
            "shared_key_edges: no --shared-key-patterns given — using built-in "
            "ingot accessor defaults (DataModel_Set_/Get_)",
        )
    harvester = harvester or shared_key_harvester(patterns_path, extra)
    writers = harvester.patterns.writers
    readers = harvester.patterns.readers
    conn = sqlite3.connect(str(db_path))
    _ensure_shared_key_edges_table(conn)

    collector = _walk_all_files_for_shared_keys(
        conn,
        repo_root,
        harvester,
        ts_classes,
        cache,
    )

    writer_by_key = _group_sites_by_key(collector.writer_sites)
    reader_by_key = _group_sites_by_key(collector.reader_sites)
    writer_dispatch = _writer_dispatch_map(collector.writer_sites)
    edges, suppressed = _build_inferred_edges(writer_by_key, reader_by_key, writer_dispatch)
    inserted = _insert_inferred_edges(conn, edges)
    conn.commit()
    logger.info(
        "shared_key_edges: inferred %d edges (of %d raw), %d fan-out keys "
        "suppressed, %d unresolved (non-literal) key arguments",
        inserted,
        len(edges),
        len(suppressed),
        collector.counters.unresolved,
    )
    _log_suppressed_keys(suppressed)
    # Advisory: name any set/get accessor families the active patterns miss, so a
    # repo whose dataflow uses a non-default convention learns what to declare.
    _log_undeclared_accessor_hint(conn, [*writers, *readers])
    conn.close()


# ─── Source B: declared (ingot-style TOML manifest) ─────────────────────
#
# The tomllib/tomli import used to live here as `_import_toml_module`, and it was
# the ONLY correct copy: `py_entrypoints` had a second, bare `import tomllib` with
# no fallback. That asymmetry is why the shim moved to `tomlcompat` — a duplicated
# compatibility helper is how one copy ends up without the compatibility.


## @brief One declared key entry from the data-model TOML manifest.
## @version 1
class _DeclaredKey:
    """One `[[keys]]` entry from the data-model TOML/YAML manifest.

    `dispatch_mode` is the authoritative synchrony class ('inline' /
    'queued' / 'keyed' / 'unknown'); `edge_triggered` is the DECLARED-ONLY
    per-bus fire-on-change flag (True/False, or None when the manifest
    doesn't assert it — the AST-infeasible setter-body property that must
    stay NULL absent a declaration).

    @brief Declared key manifest entry.
    @version 2
    """

    __slots__ = ("dispatch_mode", "edge_triggered", "event", "name", "readers", "writers")

    ## @brief Store the key name, event flag, writer/reader names, and R1 dispatch fields.
    ## @version 1
    ## @dg_internal
    def __init__(
        self,
        name: str,
        event: bool,
        writers: list[str],
        readers: list[str],
        dispatch_mode: str = "unknown",
        edge_triggered: bool | None = None,
    ) -> None:
        self.name = name
        self.event = event
        self.writers = writers
        self.readers = readers
        self.dispatch_mode = dispatch_mode
        self.edge_triggered = edge_triggered


## @brief Parse the data-model TOML manifest into declared-key entries.
## @param toml_mod The tomllib/tomli module to parse with.
## @param data_model_path Path to the TOML manifest.
## @return List of declared keys parsed from `[[keys]]` tables.
## @version 2
## @dg_internal
def _parse_data_model_toml(
    toml_mod: Any,
    data_model_path: Path,
) -> list[_DeclaredKey]:
    """Parse `[[keys]] name / persistent / event / writers / readers`
    entries (plus the R1 `dispatch_mode` / `edge_triggered` fields).
    `persistent` is accepted but not used beyond round-tripping the shape.

    @brief Parse [[keys]] entries from the data-model TOML.
    @version 3
    """
    with data_model_path.open("rb") as fh:
        doc = toml_mod.load(fh)
    return _declared_keys_from_doc(doc, str(data_model_path))


## @brief Map an optional manifest bool to 0/1/None for edge_triggered.
## @return None when the manifest omitted the value (stays SQL NULL); otherwise the value as a bool.
## @version 2
## @req REQ-DDB-SCHEMA-002
def _coerce_edge_triggered(value: Any) -> bool | None:
    """@brief None when the manifest omits it (stays NULL); else the bool."""
    return None if value is None else bool(value)


## @brief Build _DeclaredKey entries from an already-parsed manifest dict.
## @param doc The parsed data-model manifest (TOML or YAML), as a mapping.
## @param origin Manifest path, for a fail-closed error message.
## @return A list of _DeclaredKey entries, one per named `keys` table in the manifest.
## @version 4
## @dg_internal
def _declared_keys_from_doc(doc: dict, origin: str = "data-model manifest") -> list[_DeclaredKey]:
    """Shared shape for the TOML and YAML data-model manifests: a top-level
    `keys` list of {name, event?, writers?, readers?, dispatch_mode?,
    edge_triggered?} tables. `edge_triggered` stays None (→ SQL NULL) when
    the manifest omits it — the declared-only fire-on-change flag is never
    guessed.

    `dispatch_mode` is validated here, which it was NOT before: this path read
    it raw and carried it all the way to the edge INSERT, where it surfaced as a
    bare `IntegrityError` mid-build with no mention of the manifest, the key or
    the token. The accessor path validated and the manifest path did not, so the
    same typo behaved differently depending on which route declared it — and via
    `.clew.yaml`'s `data_model:` this route is reachable through the MCP
    server with no CLI argument at all.

    @brief Map a parsed manifest dict to declared-key entries.
    @version 4
    """
    keys = []
    for entry in doc.get("keys", []) or []:
        name = entry.get("name")
        if not name:
            continue
        keys.append(
            _DeclaredKey(
                name=name,
                event=bool(entry.get("event", False)),
                writers=list(entry.get("writers", []) or []),
                readers=list(entry.get("readers", []) or []),
                dispatch_mode=DISPATCH_MODE.validated(
                    str(entry.get("dispatch_mode", "unknown")),
                    owner=f"{origin}: key {name!r}",
                    field="dispatch_mode",
                ),
                edge_triggered=_coerce_edge_triggered(entry.get("edge_triggered")),
            ),
        )
    return keys


## @brief Parse a YAML data-model manifest into declared-key entries.
##
## Same `keys:` list shape as the TOML manifest — supports data-model-style YAML
## models alongside ingot-style TOML. Returns [] if yaml is unavailable.
## @return A list of _DeclaredKey entries parsed from the YAML manifest ([] when the top level isn't a mapping).
## @version 2
## @dg_internal
def _parse_data_model_yaml(data_model_path: Path) -> list[_DeclaredKey]:
    import yaml

    doc = yaml.safe_load(data_model_path.read_text(encoding="utf-8")) or {}
    return _declared_keys_from_doc(doc if isinstance(doc, dict) else {}, str(data_model_path))


## @brief Load declared keys from a TOML or YAML data-model manifest by suffix.
## @return List of declared keys, or [] when unparseable/unsupported.
## @version 2
## @dg_internal
def _load_declared_keys(data_model_path: Path) -> list[_DeclaredKey]:
    """This path is reached only because an owner DECLARED a data-model manifest,
    so `require_toml_module` rather than the tolerant `toml_module`: it used to
    log a warning and return `[]`, which is indistinguishable from "the manifest
    declared no keys" and drops the entire declared shared-key pass on an
    interpreter missing the backport. An explicit declaration that cannot be read
    is an error, not an empty answer.

    @brief Dispatch a declared manifest to the YAML or TOML parser by suffix.
    @return Declared keys, or [] when the manifest declares none.
    @version 2
    """
    suffix = data_model_path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return _parse_data_model_yaml(data_model_path)
    return _parse_data_model_toml(require_toml_module(), data_model_path)


## @brief Name -> rowids index that prefers definition rows over declarations.
##
## Doxygen emits one memberdef for a function's definition
## (file_id == bodyfile_id) plus one per documented header declaration
## (file_id = header, bodyfile_id = definer). Resolving a declared-manifest
## writer/reader NAME via the raw all-rowids index cross-products decl×def
## into duplicate edge rows (verified: a single manifest edge inserted 4x).
## Per name, keep the definition rowids when any exist; else keep all
## (declaration-only externs still resolve).
## @version 2
## @req REQ-DDB-QUERY-003
def _definition_preferring_name_index(
    conn: sqlite3.Connection,
) -> dict[str, list[int]]:
    by_name: dict[str, list[tuple[int, bool]]] = {}
    for rowid, name, is_def in conn.execute(
        "SELECT rowid, name, (file_id = bodyfile_id) FROM memberdef WHERE kind = 'function'",
    ):
        by_name.setdefault(name, []).append((rowid, bool(is_def)))
    index: dict[str, list[int]] = {}
    for name, entries in by_name.items():
        defs = [r for r, is_def in entries if is_def]
        index[name] = defs if defs else [r for r, _ in entries]
    return index


## @brief Resolve a list of function names to memberdef rowids.
## @param names Function names to resolve.
## @param name_to_rowids Index built from _build_function_indexes.
## @return (resolved_rowids, unresolved_name_count).
## @version 1
## @dg_internal
def _resolve_names(
    names: list[str],
    name_to_rowids: dict[str, list[int]],
) -> tuple[list[int], int]:
    """Resolve each name to its memberdef rowid(s); count names with no match.

    @brief Resolve a list of function names to memberdef rowids.
    @version 1
    """
    rowids: list[int] = []
    unresolved = 0
    for name in names:
        candidates = name_to_rowids.get(name, [])
        if not candidates:
            unresolved += 1
            continue
        rowids.extend(candidates)
    return rowids, unresolved


# A declared edge tuple carries the manifest's dispatch_mode + edge_triggered
# alongside the resolved (writer, reader, key, edge_kind).
_DeclaredEdge = tuple[int, int, str, str, str, "bool | None"]


## @brief Resolve one declared key's writer/reader names into edge tuples.
## @version 2
## @dg_internal
def _resolve_one_declared_key(
    key: _DeclaredKey,
    name_to_rowids: dict[str, list[int]],
) -> tuple[list[_DeclaredEdge], int]:
    """Resolve one key's writer/reader names and cross them into edges,
    stamping the manifest's `dispatch_mode` + `edge_triggered` on each.

    @brief Resolve+cross one declared key's writer/reader names.
    @version 2
    """
    edge_kind = "event" if key.event else "state"
    writer_rowids, writer_unresolved = _resolve_names(key.writers, name_to_rowids)
    reader_rowids, reader_unresolved = _resolve_names(key.readers, name_to_rowids)
    edges: list[_DeclaredEdge] = [
        (
            writer_rowid,
            reader_rowid,
            key.name,
            edge_kind,
            key.dispatch_mode,
            key.edge_triggered,
        )
        for writer_rowid in writer_rowids
        for reader_rowid in reader_rowids
    ]
    return edges, writer_unresolved + reader_unresolved


## @brief Resolve declared writer/reader function names to memberdef rowids.
## @version 2
## @dg_internal
def _resolve_declared_edges(
    keys: list[_DeclaredKey],
    name_to_rowids: dict[str, list[int]],
) -> tuple[list[_DeclaredEdge], int]:
    """Resolve each declared key's writer/reader names to memberdef rowids
    and cross them into edge tuples. Names that don't resolve to any
    indexed function are skipped and counted as unresolved.

    @brief Resolve declared-manifest names into edge tuples.
    @version 2
    """
    edges: list[_DeclaredEdge] = []
    unresolved = 0
    for key in keys:
        key_edges, key_unresolved = _resolve_one_declared_key(key, name_to_rowids)
        edges.extend(key_edges)
        unresolved += key_unresolved
    return edges, unresolved


## @brief Insert declared shared-key edges, ignoring duplicates.
## @version 2
## @dg_internal
def _insert_declared_edges(
    conn: sqlite3.Connection,
    edges: list[_DeclaredEdge],
) -> int:
    """Insert declared shared-key edges, ignoring duplicates. `dispatch_mode`
    and `edge_triggered` come straight from the authoritative manifest;
    edge_triggered is NULL for any key that didn't declare it.

    @brief Bulk-insert declared shared_key_edges rows.
    @version 2
    """
    return conn.executemany(
        """
        INSERT OR IGNORE INTO shared_key_edges
            (writer_rowid, reader_rowid, key_name, edge_kind, declared,
             source, confidence, dispatch_mode, edge_triggered)
        VALUES (?, ?, ?, ?, 1, 'shared_key_declared', 'high', ?, ?)
        """,
        edges,
    ).rowcount


## @brief Layer 5b: ingest an authoritative data-model key manifest (TOML or YAML).
## @param db_path Path to the clew.db being built.
## @param data_model_path Path to the --data-model manifest (.toml/.yaml/.yml), or None.
## @version 4
## @req REQ-DDB-SCHEMA-005
def import_shared_key_edges_declared(
    db_path: Path,
    data_model_path: Path | None,
) -> None:
    """Ingest an optional ingot-style manifest declaring keys and their
    writer/reader functions directly (no AST inference needed). Accepts
    either an ingot-style TOML or a data-model-style YAML manifest (same `keys:`
    list shape), dispatched by file suffix. Keys with `event = true`
    become `edge_kind='event'` edges; others `edge_kind='state'`. No-ops
    cleanly when no manifest is given, the manifest has no keys, or the
    required parser (tomllib/tomli for TOML, PyYAML for YAML) is absent.

    @brief Import declared shared-key edges from a TOML/YAML data-model manifest.
    @version 4
    """
    if data_model_path is None:
        logger.info(
            "shared_key_edges: no --data-model given — skipping declared pass",
        )
        return

    keys = _load_declared_keys(data_model_path)
    if not keys:
        return
    conn = sqlite3.connect(str(db_path))
    _ensure_shared_key_edges_table(conn)
    name_to_rowids = _definition_preferring_name_index(conn)

    edges, unresolved = _resolve_declared_edges(keys, name_to_rowids)
    inserted = _insert_declared_edges(conn, edges)
    conn.commit()
    conn.close()
    logger.info(
        "shared_key_edges: declared %d edges (of %d raw) from %d manifest "
        "keys, %d unresolved writer/reader names",
        inserted,
        len(edges),
        len(keys),
        unresolved,
    )


# ─── Source C: keyed dispatch (MQTT/topic routing, optional D5) ─────────────


## @brief One subscribe-function convention: callee + topic/handler arg indices.
## @version 1
class _SubscribePattern:
    """A topic-subscription registrar to AST-harvest: the callee identifier,
    the 0-indexed topic-string argument, and the 0-indexed handler-fn
    argument. Mirrors the accessor/spawn manifest philosophy.

    @brief Subscribe-function convention (callee + topic/handler indices).
    @version 1
    """

    __slots__ = ("fn_name", "handler_arg_index", "topic_arg_index")

    ## @brief Store the subscribe callee name and topic/handler argument indices.
    ## @version 1
    ## @dg_internal
    def __init__(self, fn_name: str, topic_arg_index: int, handler_arg_index: int) -> None:
        self.fn_name = fn_name
        self.topic_arg_index = topic_arg_index
        self.handler_arg_index = handler_arg_index


## @brief Load a --mqtt-dispatch manifest (path or inline document) into patterns.
## @param source The manifest path, or the already-parsed document as a mapping.
## @return A list of _SubscribePattern rules, one per named entry under `subscribe_functions`.
## @version 3
## @req REQ-DDB-SCHEMA-004
def _load_subscribe_patterns(source: Path | dict) -> list[_SubscribePattern]:
    """Parse the optional `--mqtt-dispatch` manifest::

        subscribe_functions:
          - fn_name: "MqttcCore_Subscribe"
            topic_arg_index: 1
            handler_arg_index: 2

    A MAPPING IS ACCEPTED, and this was a live defect rather than only groundwork for the
    inline statement form (gh#360). `cli._declared_or_flag` has always handed the `.clew.yaml`
    `mqtt_dispatch:` SECTION down as a parsed mapping — every sibling loader takes
    `Path | dict` for exactly that reason — while this one called `.read_text` on it, so a
    repository declaring that section in-tree crashed its own build with an `AttributeError`
    and no test covered the declaration route for this one manifest.

    @brief Load subscribe-function patterns from a path or an inline document.
    @version 3
    """
    if isinstance(source, dict):
        data = source
    else:
        import yaml

        data = yaml.safe_load(Path(source).read_text(encoding="utf-8")) or {}
    patterns: list[_SubscribePattern] = []
    for entry in data.get("subscribe_functions", []) or []:
        fn_name = entry.get("fn_name")
        if not fn_name:
            continue
        patterns.append(
            _SubscribePattern(
                fn_name=fn_name,
                topic_arg_index=int(entry.get("topic_arg_index", 0)),
                handler_arg_index=int(entry.get("handler_arg_index", 1)),
            ),
        )
    return patterns


## @brief One harvested subscribe site: registrar, topic, handler name.
## @version 1
class _SubscribeSite:
    """A resolved subscribe call: the registrar (enclosing fn) rowid, the
    topic literal (or the 'dynamic' sentinel when runtime-built), and the
    handler function's identifier text.

    @brief A resolved topic-subscription call site.
    @version 1
    """

    __slots__ = ("handler_name", "registrar_rowid", "topic")

    ## @brief Store the registrar rowid, topic literal, and handler-fn name.
    ## @version 1
    ## @dg_internal
    def __init__(self, registrar_rowid: int, topic: str, handler_name: str) -> None:
        self.registrar_rowid = registrar_rowid
        self.topic = topic
        self.handler_name = handler_name


## @brief Resolve one subscribe call site, if the handler is an identifier.
## @return [line, topic, handler_name], or None when the handler isn't a bare identifier.
## @version 2
## @dg_internal
def _resolve_subscribe_site(
    call_node: Any,
    src_bytes: bytes,
    pattern: _SubscribePattern,
) -> list[Any] | None:
    """Extract the handler identifier (required) and topic literal (a
    'dynamic' sentinel when the topic is runtime-built, per R1 caveat 1),
    keyed by source line so the harvest stays rowid-free and cacheable.
    Returns None when the handler argument isn't a plain identifier.

    @brief Resolve a matched subscribe call into line/topic/handler.
    @version 2
    """
    handler_arg = _nth_call_argument(call_node, pattern.handler_arg_index)
    if handler_arg is None or handler_arg.type != "identifier":
        return None
    handler_name = src_bytes[handler_arg.start_byte : handler_arg.end_byte].decode(
        "utf-8", errors="replace"
    )
    topic_arg = _nth_call_argument(call_node, pattern.topic_arg_index)
    topic = _resolve_literal_key(topic_arg, src_bytes) if topic_arg is not None else None
    return [call_node.start_point[0] + 1, topic or "dynamic", handler_name]


## @brief Walk one file, harvesting subscribe call sites.
## @return List of [line, topic, handler_name] triples in walk order.
## @version 2
## @dg_internal
def _walk_subscribe_sites(
    tree: Any,
    src_bytes: bytes,
    patterns_by_name: dict[str, _SubscribePattern],
) -> list[list[Any]]:
    """@brief Harvest subscribe call sites from one file's AST."""
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        if callee is None or callee.type != "identifier":
            continue
        callee_name = src_bytes[callee.start_byte : callee.end_byte].decode(
            "utf-8",
            errors="replace",
        )
        pattern = patterns_by_name.get(callee_name)
        if pattern is None:
            continue
        site = _resolve_subscribe_site(node, src_bytes, pattern)
        if site is not None:
            sites.append(site)
    return sites


## @brief Layer 5c's cacheable per-file subscribe-site harvester.
## @version 1
class _SubscribeHarvester(Harvester):
    """Records `[line, topic, handler_name]` triples per file, keyed also on
    the --mqtt-dispatch manifest content that decides what matches.

    @brief Layer 5c per-file harvester.
    @version 1
    """

    stage = STAGE_MQTT
    # Bump when _walk_subscribe_sites' extraction changes.
    stage_version = 1
    label = "mqtt dispatch"

    ## @brief Store the subscribe-pattern map plus the manifest cache key.
    ## @version 1
    ## @dg_internal
    def __init__(self, patterns_by_name: dict[str, _SubscribePattern], extra_key: str) -> None:
        super().__init__(extra_key)
        self.patterns_by_name = patterns_by_name

    ## @brief Harvest one file's subscribe call sites.
    ## @return List of [line, topic, handler_name] triples.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-005
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _walk_subscribe_sites(tree, src_bytes, self.patterns_by_name)


## @brief Layer 5c's harvester, or None when no manifest declares subscribe functions.
## @param mqtt_dispatch_path The --mqtt-dispatch manifest, or None.
## @return A Harvester, or None when this stage will not run at all.
## @version 1
## @req REQ-DDB-SCHEMA-005
def subscribe_harvester(mqtt_dispatch_path: Path | dict | None = None) -> Harvester | None:
    """None means "this stage is inert", and the shared parse pass must be told that
    rather than left to warm a payload nobody will read — an undeclared MQTT
    vocabulary matches nothing, so the cost would be pure waste.

    @brief Build this stage's harvester, or None when it is inert.
    @version 1
    """
    if mqtt_dispatch_path is None:
        return None
    patterns = _load_subscribe_patterns(mqtt_dispatch_path)
    return _SubscribeHarvester({p.fn_name: p for p in patterns}, manifest_key(mqtt_dispatch_path))


## @brief Harvest subscribe sites across all indexed files.
## @return Flat list of _SubscribeSite with registrar rowids resolved.
## @version 3
## @dg_internal
def _harvest_subscribe_sites(
    conn: sqlite3.Connection,
    repo_root: Path,
    harvester: Harvester,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None = None,
) -> list[_SubscribeSite]:
    """@brief Per-file AST walk collecting topic-subscription sites.

    Takes the harvester gh#358's shared parse pass already warmed the cache with,
    rather than rebuilding an equal-but-separate one.

    @version 3
    """
    _, file_funcs = _build_function_indexes(conn)
    sites: list[_SubscribeSite] = []
    for path_rowid, payload in run_harvest(conn, repo_root, harvester, ts_classes, cache):
        funcs_in_file = file_funcs.get(path_rowid, [])
        if not funcs_in_file:
            continue
        for line, topic, handler_name in payload:
            registrar = _ast_caller_at_line(funcs_in_file, line)
            if registrar is not None:
                sites.append(_SubscribeSite(registrar, topic, handler_name))
    return sites


## @brief Cross harvested subscribe sites into keyed shared-key edge tuples.
## @version 2
## @req REQ-DDB-SCHEMA-004
def _build_keyed_edges(
    sites: list[_SubscribeSite],
    name_to_rowids: dict[str, list[int]],
) -> tuple[list[_DeclaredEdge], int]:
    """topic→handler becomes a keyed shared-key row: writer = the registrar
    (the fn that subscribed), reader = the handler, key = topic (or the
    'dynamic' sentinel), edge_kind='event', dispatch_mode='keyed'.
    edge_triggered stays NULL (not a fire-on-change property).

    @brief Cross subscribe sites into keyed shared_key_edges tuples.
    @version 2
    """
    edges: list[_DeclaredEdge] = []
    unresolved = 0
    for site in sites:
        handler_rowids = name_to_rowids.get(site.handler_name, [])
        if not handler_rowids:
            unresolved += 1
            continue
        for handler_rowid in handler_rowids:
            edges.append(
                (
                    site.registrar_rowid,
                    handler_rowid,
                    site.topic,
                    "event",
                    "keyed",
                    None,
                ),
            )
    return edges, unresolved


## @brief Layer 5c (optional): keyed topic→handler dispatch from --mqtt-dispatch.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param mqtt_dispatch_path Path to the --mqtt-dispatch YAML manifest, or None.
## @param cache Optional incremental index cache; None disables caching.
## @param harvester Pre-built harvester from the shared parse pass; built here when omitted.
## @version 5
## @req REQ-DDB-SCHEMA-004
def import_mqtt_dispatch_edges(
    db_path: Path,
    repo_root: Path,
    mqtt_dispatch_path: Path | dict | None,
    cache: IndexCache | None = None,
    harvester: Harvester | None = None,
) -> None:
    """Harvest topic-subscription registrations declared in an optional
    `--mqtt-dispatch` manifest and record them as keyed `shared_key_edges`
    (dispatch_mode='keyed', declared=1). No-ops cleanly when no manifest is
    given or tree_sitter is absent. AST inference of the runtime map-lookup
    dispatch itself remains a documented follow-on (see R1-SPEC §2e).

    @brief Import keyed topic→handler dispatch edges from --mqtt-dispatch.
    @version 4
    """
    if mqtt_dispatch_path is None:
        logger.info(
            "shared_key_edges: no --mqtt-dispatch given — skipping keyed pass",
        )
        return
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info("tree_sitter not available — skipping keyed MQTT pass")
        return

    conn = sqlite3.connect(str(db_path))
    _ensure_shared_key_edges_table(conn)
    name_to_rowids = _definition_preferring_name_index(conn)
    sites = _harvest_subscribe_sites(
        conn,
        repo_root,
        # Never None here: `subscribe_harvester` returns None only for the
        # undeclared manifest this function already returned on, above.
        harvester or subscribe_harvester(mqtt_dispatch_path),  # type: ignore[arg-type]
        ts_classes,
        cache,
    )
    edges, unresolved = _build_keyed_edges(sites, name_to_rowids)
    inserted = _insert_declared_edges(conn, edges)
    conn.commit()
    conn.close()
    logger.info(
        "shared_key_edges: keyed %d topic→handler edges (of %d raw) from "
        "%d subscribe sites, %d unresolved handlers",
        inserted,
        len(edges),
        len(sites),
        unresolved,
    )
