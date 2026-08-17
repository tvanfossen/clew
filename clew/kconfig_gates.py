# SPDX-License-Identifier: MIT
"""symbol → `file:line` — which source lines a `CONFIG_*` symbol gates.

gh#18 part 3. The issue calls this "a first-class relation … not derivable from
either side alone", and that is exactly right: the Kconfig tree knows the symbol
exists and nothing about the code it selects, while the source knows a
preprocessor conditional mentions a token and nothing about what that token means.
Only the join says "this variant is what turns that function on".

## WHY THE PREPROCESSOR AND NOT THE C EXPRESSION

Only PREPROCESSOR CONDITIONALS are harvested — `#ifdef`, `#ifndef`, `#if`,
`#elif` — because those are the sites where the symbol decides whether code
EXISTS. A Zephyr `if (IS_ENABLED(CONFIG_X))` in ordinary C is a runtime branch in
code that is compiled either way, which is a different relation, and filing the two
under one form would tell a consumer that removing the symbol removes the function
when it does not. (An `IS_ENABLED(CONFIG_X)` inside a `#if` IS caught, because
there it really is deciding existence.)

## WHY IT DOES NOT NEED THE KCONFIG TREE

The scan records every `CONFIG_*` token it finds in a conditional, whether or not
the Kconfig tree declares that symbol. Two reasons, both about not hiding a
finding:

  - A gate on a symbol NO Kconfig declares is a defect in the target — dead code
    behind a symbol nobody can set — and filtering to declared symbols would delete
    the evidence of it.
  - The Kconfig parse can fail for an ordinary reason (a Zephyr app indexed outside
    its west workspace). This layer then still works, and a consumer sees the gating
    structure with `kconfig.error` explaining why the space beside it is empty.

The `CONFIG_` prefix is Kconfig's own, fixed, universal convention — it is what
Kconfig's generated headers emit, on every build system that uses it — so matching
it is reading a declaration, not assuming a repo's shape.

@brief Harvest CONFIG_* preprocessor gating sites into kconfig_gates.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .preprocessor import bare_macro_names
from .indexcache import IndexCache
from .vocabulary import (
    GATE_ORIGIN_DECLARED,
    GATE_ORIGIN_KCONFIG,
    GATE_ORIGIN_UNDECLARED,
    KCONFIG_GATE_IF_EXPR,
    KCONFIG_GATE_IFDEF,
    KCONFIG_GATE_IFNDEF,
    STAGE_KCONFIG_GATES,
    check,
)

## The tree-sitter node types that gate code on a condition. `preproc_ifdef` covers
## BOTH `#ifdef` and `#ifndef` in the C and C++ grammars — the directive is the
## node's first child, which is what `_ifdef_form` reads to tell them apart, and
## getting that wrong inverts the variant a reader concludes.
_IFDEF_NODE = "preproc_ifdef"
_EXPR_NODES = ("preproc_if", "preproc_elif")
## The `#else` branch, which the grammar hangs off its conditional as `alternative`. It carries
## no condition of its own, so it is never walked as a gate — its rows are synthesised from the
## parent's symbols with the polarity inverted. See `_else_branch_gates`.
_ELSE_NODE = "preproc_else"

## The polarity of an else branch, per form. `if_expr` maps to itself because it already means
## "this layer does not evaluate the condition", and negating an unevaluated expression yields
## another unevaluated expression rather than a known polarity.
_INVERTED_FORM = {
    KCONFIG_GATE_IFDEF: KCONFIG_GATE_IFNDEF,
    KCONFIG_GATE_IFNDEF: KCONFIG_GATE_IFDEF,
    KCONFIG_GATE_IF_EXPR: KCONFIG_GATE_IF_EXPR,
}

## `#ifndef` as the grammar spells its leading token.
_IFNDEF_TOKEN = "#ifndef"

## A Kconfig-generated macro. `CONFIG_` is Kconfig's own universal prefix, emitted
## by its generated headers on every build system that uses it, so this reads a
## convention rather than assuming one. Anchored with `\b` so a `MY_CONFIG_X` does
## not match — a symbol that is not Kconfig's would attribute a gate to a variant
## space it has nothing to do with.
##
## IT NO LONGER DECIDES WHAT IS HARVESTED, only how a harvested symbol is LABELLED.
## As a filter it made this whole layer inert on the dominant C convention — see the
## module docstring.
_CONFIG_TOKEN = re.compile(r"\bCONFIG_[A-Za-z0-9_]+")

## Any C identifier appearing in a preprocessor condition. This is the harvest set.
_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

## `defined` is an OPERATOR in a `#if` expression, not a symbol, and it appears in
## nearly every conditional a C repository writes — harvesting it would put one
## meaningless row at the top of every gate query, ranked by sheer frequency.
_NOT_A_SYMBOL = frozenset({"defined"})


## @brief Idempotent creation of the kconfig_gates table.
## @param conn Open connection to the index being built.
## @version 3
## @req REQ-DDB-SCHEMA-013
def ensure_kconfig_gates_table(conn: sqlite3.Connection) -> None:
    """Created SEPARATELY from `kconfig_symbols`, next to the harvest that fills it,
    for the reason `ensure_kconfig_tables` records: the two layers fail
    independently — a repo can have a parseable Kconfig and no C sources, or gated C
    and an unparseable Kconfig — and a shared creator would make one layer's absence
    look like the other's.

    `symbol` stores the Kconfig symbol name WITHOUT the `CONFIG_` prefix, so it joins
    `kconfig_symbols.name` directly; `macro` keeps the token as the source wrote it,
    because that is what a reader greps for.

    No foreign key to `kconfig_symbols`: a gate on an undeclared symbol is a finding
    this layer exists to keep, and a REFERENCES would make storing it impossible.

    `origin` says how the symbol's NAME is accounted for — Kconfig's prefix, the target's
    own declared preprocessor configuration, or nothing this build could see. It is a label
    and never a filter: an undeclared gate is a finding about the target (a symbol nobody
    has declared, or dead code behind one nobody can set), and dropping those rows would
    delete the evidence — the same argument this module already makes for a gate on a
    symbol no Kconfig declares.

    `end_line` CLOSES THE RANGE, and the branch it closes is the one the row's own `form`
    describes — NOT the whole conditional. Measured with `.claude/tmp/gate_extent_probe.py`: a
    `preproc_ifdef` node spans lines 3-7 for `#ifdef FEATURE_A ... #else ... #endif`, so a range
    join over the node's own extent reports the code in the `#else` as gated ON `FEATURE_A` when
    it is present exactly when `FEATURE_A` is NOT set. A confidently inverted variant is worse
    than no answer, so the row stops at its alternative and the alternative gets its own row with
    the opposite polarity.

    DEFAULT 0 MEANS "EXTENT UNKNOWN", which is what an index built before this column knew. A
    consumer must not read 0 as "covers nothing" or as "covers everything" — `gates_covering`
    skips those rows and says so, rather than guessing a range for them.

    @brief Create the CONFIG-gating table.
    @version 3
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS kconfig_gates (
            symbol    TEXT NOT NULL,
            macro     TEXT NOT NULL,
            form      TEXT NOT NULL {check("kconfig_gates", "form")},
            file_path TEXT NOT NULL,
            line      INTEGER NOT NULL,
            end_line  INTEGER NOT NULL DEFAULT 0,
            origin    TEXT NOT NULL {check("kconfig_gates", "origin")},
            UNIQUE(symbol, form, file_path, line)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kconfig_gates_symbol ON kconfig_gates(symbol)")
    conn.commit()


## @brief Whether an ifdef node is `#ifdef` or `#ifndef`.
## @param node A `preproc_ifdef` node.
## @return The matching KCONFIG_GATE_* form.
## @version 1
## @dg_internal
def _ifdef_form(node: Any) -> str:
    """The grammar uses ONE node type for both directives, so the sense lives only in
    the leading token. Reading it is not a nicety: `#ifndef CONFIG_X` means the code
    is present when the symbol is NOT set, and a consumer told otherwise describes
    the variant exactly backwards.

    @brief Distinguish `#ifdef` from `#ifndef`.
    @return 'ifdef' or 'ifndef'.
    @version 1
    """
    first = node.children[0].type if node.children else ""
    return KCONFIG_GATE_IFNDEF if first == _IFNDEF_TOKEN else KCONFIG_GATE_IFDEF


## @brief Whether an ifndef node is an INCLUDE GUARD rather than a configuration gate.
## @param node A `preproc_ifdef` node already known to be `#ifndef`.
## @return True when the guarded block immediately defines the same symbol.
## @version 1
## @dg_internal
def _is_include_guard(node: Any) -> bool:
    """STRUCTURAL, NOT A NAME HEURISTIC. `#ifndef FOO_H` / `#define FOO_H` is the C
    idiom for "include me once", and the discriminator is that the guarded block DEFINES
    THE SAME SYMBOL it just tested — which no configuration gate ever does, because a
    config gate reads a symbol somebody else set.

    A `_H`-suffix test was the obvious alternative and it is wrong twice over: mbedtls
    ships `MBEDTLS_THREADING_C`-style feature macros that a suffix rule cannot see, and
    plenty of real guards do not end in `_H` at all (`MBEDTLS_CHECK_CONFIG_H_INCLUDED`,
    or any project that spells them differently). Reading the grammar's own shape is the
    same principle as `child_by_field_name("body")` in the gh#11 recovery: the parse
    already knows, so do not guess.

    WHY IT MATTERS NOW. Widening the harvest past `CONFIG_` (gh#390) admitted these:
    201 of mbedtls's 1,327 gating symbols, and 10 of 10 in this repo's own C fixture.
    Nobody asks "what turns COMMAND_HANDLER_H on", so once they reached `search` (gh#394)
    they ranked EXACT on their own names and became pure noise in a discovery surface.

    @brief Detect the ifndef/define include-guard idiom.
    @return True for an include guard.
    @version 1
    """
    name_field = node.child_by_field_name("name")
    if name_field is None:
        return False
    guarded = name_field.text.decode("utf-8", errors="replace")
    for child in node.children:
        if child.type != "preproc_def":
            continue
        defined = child.child_by_field_name("name")
        if defined is not None and defined.text.decode("utf-8", errors="replace") == guarded:
            return True
    return False


## @brief The CONFIG tokens, form and line range one conditional node contributes.
## @param node A preproc_ifdef / preproc_if / preproc_elif node.
## @return List of (symbol, macro, form, line, end_line) tuples; empty when it names none.
## @version 4
## @dg_internal
def _gates_from_node(node: Any) -> list[tuple[str, str, str, int, int]]:
    """Reads the DIRECTIVE's own text, not the guarded block's. A `preproc_ifdef`
    node spans everything up to its `#endif`, so matching `CONFIG_` over
    `node.text` would attribute every mention inside the block — including ordinary
    code — to the gate. The condition is taken from the `name`/`condition` field
    instead, which is the directive and nothing else.

    A `#if` naming SEVERAL symbols yields one row per symbol, because each of them
    genuinely participates in deciding whether the line exists.

    EVERY IDENTIFIER, NOT JUST `CONFIG_*`. Matching one prefix here made the layer
    inert on any repository that does not use Kconfig — mbedtls gates on
    `MBEDTLS_THREADING_C` and produced ZERO rows. Which vocabulary accounts for a
    name is decided at STORE time, where the declaration is known; deciding it here
    would bake a target's convention into a cached per-file harvest.

    AN INCLUDE GUARD IS NOT A GATE and is dropped here rather than stored and labelled.
    This table answers "which source lines does a configuration symbol decide", and
    `#ifndef FOO_H` decides nothing about a variant — it tests a symbol the very next line
    defines. Storing it would push the filtering onto every consumer, and the one that
    matters got it wrong immediately: 201 of mbedtls's 1,327 symbols and 10 of 10 in this
    repo's C fixture are guards, and they ranked EXACT in `search` on their own names.
    Excluded by STRUCTURE (`_is_include_guard`), never by a `_H` suffix.

    THE RANGE STOPS AT THE ALTERNATIVE, and one row per branch carries its own polarity. This
    is the half a range join gets wrong silently: measured with `.claude/tmp/gate_extent_probe.py`,
    `#ifdef FEATURE_A / #else / #endif` parses as a `preproc_ifdef` spanning the WHOLE construct
    with the `#else` as its `alternative` child, so joining a function's line against the node's
    own extent reports the else-branch function as present when the symbol is SET — the exact
    inverse of the truth. So an `#ifdef` row ends where its `#else` begins, and the else branch
    becomes a SECOND row with the form inverted, which is what the vocabulary's `form` field is
    for ("must not be collapsed to a boolean").

    An `#elif` is already visited as a node in its own right, so it needs no synthesised row —
    only the same truncation, since it too can carry an alternative. An `#else` under an
    expression conditional inherits `if_expr`, which already means "polarity unknown to this
    layer": the branch's presence genuinely depends on an expression nothing here evaluates.

    @brief Extract the gates one preprocessor conditional declares.
    @return (symbol, macro, form, line, end_line) tuples.
    @version 4
    """
    line = node.start_point[0] + 1
    alternative = node.child_by_field_name("alternative")
    end = (alternative.start_point[0] if alternative is not None else node.end_point[0]) + 1
    if node.type == _IFDEF_NODE:
        field, form = node.child_by_field_name("name"), _ifdef_form(node)
        if form == KCONFIG_GATE_IFNDEF and _is_include_guard(node):
            return []
    else:
        field, form = node.child_by_field_name("condition"), KCONFIG_GATE_IF_EXPR
    if field is None:
        return []
    text = field.text.decode("utf-8", errors="replace")
    seen = dict.fromkeys(t for t in _IDENTIFIER.findall(text) if t not in _NOT_A_SYMBOL)
    rows = [(_bare_symbol(macro), macro, form, line, end) for macro in seen]
    return rows + _else_branch_gates(alternative, form, seen)


## @brief The inverted-polarity rows an `#else` branch contributes, if there is one.
## @param alternative The conditional's `alternative` child, or None.
## @param form The parent conditional's form.
## @param macros The macro tokens the parent condition named.
## @return (symbol, macro, form, line, end_line) tuples for the else branch.
## @version 1
## @dg_internal
def _else_branch_gates(alternative: Any, form: str, macros: Any) -> list[tuple]:
    """AN `#else` IS A GATE, WITH THE POLARITY THE OTHER WAY. Without these rows the else
    branch reads as ungated — an under-report — and with the parent's own extent it reads as
    gated the wrong way, which is worse. This is the third option: same symbols, inverted form,
    the else branch's own range.

    ONLY A `preproc_else` IS HANDLED HERE. A `preproc_elif` is visited as a node in its own
    right by the harvester's walk and carries its own condition, so synthesising a row for it
    would duplicate the rows that walk produces — with a condition it does not have.

    `if_expr` INVERTS TO `if_expr`, deliberately. The form already means "polarity unknown to
    this layer", and an expression's negation is no more evaluated than the expression was.

    @brief Rows for the else branch of a conditional.
    @return Gate rows, empty when there is no `#else`.
    @version 1
    """
    if alternative is None or alternative.type != _ELSE_NODE:
        return []
    inverted = _INVERTED_FORM.get(form, form)
    line, end = alternative.start_point[0] + 1, alternative.end_point[0] + 1
    return [(_bare_symbol(macro), macro, inverted, line, end) for macro in macros]


## @brief The join key for a gating macro: Kconfig's prefix stripped, anything else as-is.
## @param macro The token as the source wrote it.
## @return The symbol name.
## @version 1
## @dg_internal
def _bare_symbol(macro: str) -> str:
    """`kconfig_gates.symbol` joins `kconfig_symbols.name`, which stores the symbol WITHOUT
    Kconfig's `CONFIG_` prefix — so the prefix is stripped for exactly the names that carry
    it, and only those. Stripping unconditionally would have no prefix to remove; leaving
    it on a `CONFIG_` name would break the one join this column exists for.

    @brief Reduce a gating macro to its join key.
    @return Symbol name.
    @version 1
    """
    return macro[len("CONFIG_") :] if macro.startswith("CONFIG_") else macro


## @brief Per-file harvester for `CONFIG_*` preprocessor gating sites.
## @version 1
class _GateHarvester(Harvester):
    """Rowid-free by construction — it records symbol names, a form and a line —
    so it caches on the file's content sha like every other stage.

    Runs over EVERY indexed file, including Python ones, which simply have no
    `preproc_*` nodes and contribute nothing. That costs one already-cached parse
    and avoids a per-language special case that would need updating for every
    grammar added.

    @brief `CONFIG_*` gating-site per-file harvester.
    @version 1
    """

    stage = STAGE_KCONFIG_GATES
    ## 1 -> 2: the harvest widened from `CONFIG_*` to every gating identifier. A cached
    ## payload from version 1 holds the OLD, near-empty set, and on a repo that uses no
    ## Kconfig it is empty outright — so an unbumped version would leave every previously
    ## built index reporting the defect this change fixes, with a warm cache hiding it.
    ## 2 -> 3: include guards excluded. A version-2 payload holds them, and a warm cache
    ## would keep serving guard rows into the search corpus this exclusion exists to clean.
    ## 3 -> 4: every entry gained an `end_line`, and an `#else` gained a row of its own with the
    ## polarity inverted. A version-3 payload has four fields where the reader now unpacks five,
    ## so this bump is load-bearing rather than hygienic — and it is what makes "which gates cover
    ## this function" answerable at all, since a gate recorded as a single line covers nothing.
    stage_version = 4
    label = "kconfig gates"

    ## @brief Harvest one file's CONFIG gating sites.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's raw bytes (unused; the tree carries the text).
    ## @return List of [symbol, macro, form, line] entries.
    ## @version 1
    ## @req REQ-DDB-PIPE-007
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """Returns LISTS rather than tuples because the payload is JSON-serialised
        into the cache, where a tuple comes back as a list anyway — so producing
        lists here keeps a cache hit and a fresh parse structurally identical, which
        is the invariant `run_harvest`'s docstring depends on.

        @brief Walk one file's preprocessor conditionals.
        @return Gate entries for this file.
        @version 1
        """
        found: list[list[Any]] = []
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == _IFDEF_NODE or node.type in _EXPR_NODES:
                found.extend(list(gate) for gate in _gates_from_node(node))
            stack.extend(node.children)
        return found


## @brief The kconfig-gate stage's harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-PIPE-007
def gate_harvester() -> Harvester:
    """Public factory so the gh#358 shared parse pass can warm this stage's cache
    rows without importing a private class — and so there is ONE construction
    site, which is what makes the pass's key and the stage's key equal by
    construction rather than by two matching edits.

    @brief Build this stage's harvester.
    @version 1
    """
    return _GateHarvester()


## @brief How a gating symbol's name is accounted for.
## @param symbol The bare symbol name.
## @param macro The token as the source wrote it.
## @param declared Macro names the target's preprocessor declaration supplies.
## @return A GATE_ORIGIN_* value.
## @version 1
## @dg_internal
def _origin(symbol: str, macro: str, declared: frozenset[str]) -> str:
    """Kconfig's prefix wins first because it is a UNIVERSAL convention rather than a
    per-repo statement — a `CONFIG_X` is Kconfig's whatever else a target declares, and
    reading it the other way would relabel a Zephyr tree the moment it also shipped a
    config header.

    Both spellings are checked against the declaration because a declared list holds
    the macro as the build states it, which for a config header is the full name and
    for a Kconfig-style entry may be the bare one.

    @brief Classify one gating symbol's provenance.
    @return GATE_ORIGIN_KCONFIG / _DECLARED / _UNDECLARED.
    @version 1
    """
    if _CONFIG_TOKEN.fullmatch(macro):
        return GATE_ORIGIN_KCONFIG
    if macro in declared or symbol in declared:
        return GATE_ORIGIN_DECLARED
    return GATE_ORIGIN_UNDECLARED


## @brief The macro NAMES a preprocessor declaration supplies, without their values.
## @param macros Declared entries, doxygen PREDEFINED style (`NAME` or `NAME=value`).
## @return The bare names.
## @version 2
## @dg_internal
def declared_macro_names(macros: Iterable[str]) -> frozenset[str]:
    """PREDEFINED entries carry an optional `=value`, and a value is not part of the
    identity a gate is matched on: a header defining `MBEDTLS_X 1` and a conditional
    asking `#if defined(MBEDTLS_X)` are the same symbol, and comparing the raw strings
    would classify every valued macro as undeclared.

    IT ALSO STRIPS THE QUOTING NOW, AND NOT DOING SO WAS A REAL DEFECT. `macros` holds RENDERED
    doxygen tokens — `'"NAME"'`, quotes included — so removing only the value left
    `'"MBEDTLS_THREADING_C"'`, which matches no bare symbol: every macro a build actually
    declared was labelled `undeclared`, i.e. `origin` reported an entire configuration as absent
    from the build that declared it. `PreprocessorConfig.defined_names` had been doing it
    correctly all along and its docstring warned in as many words that a second caller respelling
    the two operations would drift on one — which is what happened here.

    So this now DELEGATES to `preprocessor.bare_macro_names` rather than being fixed in place.
    Two correct implementations of one rule is the state that produced this bug.

    @brief Reduce declared macro entries to their names.
    @return Set of macro names.
    @version 2
    """
    return bare_macro_names(macros)


## @brief Harvest and store every preprocessor gating site, labelled by its origin.
## @param db_path Path to the index being built.
## @param repo_root Repo root the indexed paths are relative to.
## @param cache Optional incremental index cache; None disables caching.
## @param declared Macro names the target's preprocessor declaration supplies.
## @return Number of gate rows written.
## @version 4
## @req REQ-DDB-PIPE-007
def import_kconfig_gates(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
    declared: Iterable[str] = (),
) -> int:
    """CREATES THE TABLE UNCONDITIONALLY once tree-sitter is available, even at zero
    rows, and does NOT create it when tree-sitter is missing. That asymmetry is the
    point: an empty table means "we walked the tree and this repo gates nothing",
    an absent one means "this layer never ran", and a consumer distinguishing a
    correct negative from a detector failure needs both. Writing down the wrong one
    is the mistake this repo has made three times.

    Runs INDEPENDENTLY of whether a Kconfig was found — see the module docstring on
    why a gate is recorded for an undeclared symbol. `declared` only LABELS the rows, so
    a target that has declared nothing still gets a complete layer.

    @brief Fill kconfig_gates from the indexed source tree.
    @return Row count.
    @version 4
    """
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.warning(
            "kconfig gates: tree-sitter unavailable — no gating sites harvested, and "
            "kconfig_gates is deliberately NOT created so its absence is visible"
        )
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_kconfig_gates_table(conn)
        harvested = run_harvest(conn, repo_root, gate_harvester(), ts_classes, cache)
        names = declared_macro_names(declared)
        rows = [
            (symbol, macro, form, path, line, end, _origin(symbol, macro, names))
            for symbol, macro, form, path, line, end in _rows_from_harvest(conn, harvested)
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO kconfig_gates"
            "(symbol, macro, form, file_path, line, end_line, origin) VALUES(?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(
        "kconfig gates: %d gating site(s) over %d distinct symbol(s) "
        "(%d kconfig, %d declared, %d undeclared)",
        len(rows),
        len({row[0] for row in rows}),
        sum(1 for row in rows if row[6] == GATE_ORIGIN_KCONFIG),
        sum(1 for row in rows if row[6] == GATE_ORIGIN_DECLARED),
        sum(1 for row in rows if row[6] == GATE_ORIGIN_UNDECLARED),
    )
    return len(rows)


## @brief Flatten a harvest result into insertable gate rows.
## @param conn Open connection (for the path table).
## @param harvested (path_rowid, payload) pairs from run_harvest.
## @return (symbol, macro, form, file_path, line, end_line) tuples.
## @version 2
## @dg_internal
def _rows_from_harvest(
    conn: sqlite3.Connection, harvested: list[tuple[int, Any]]
) -> list[tuple[str, str, str, str, int, int]]:
    """Resolves each payload's `path` rowid back to the repo-relative name the `path`
    table stores. Storing the NAME rather than the rowid is deliberate: doxygen
    reassigns rowids on every run, so a stored rowid would silently re-point at a
    different file after a rebuild — the same hazard `ast_symbols` records for
    `memberdef.rowid`.

    A CACHED PAYLOAD FROM AN EARLIER STAGE VERSION HAS FOUR FIELDS, NOT FIVE, and this unpack
    would raise on one. That is why `stage_version` moved to 4: a version bump invalidates the
    cached payloads, so the widened shape and the widened reader arrive together. Tolerating both
    shapes here would keep serving rows with no extent from a warm cache, which is the failure
    the bump exists to prevent — silently, since a missing extent reads as `0`.

    @brief Turn harvested payloads into gate rows.
    @return Insertable tuples.
    @version 2
    """
    names = dict(conn.execute("SELECT rowid, name FROM path").fetchall())
    return [
        (
            str(symbol),
            str(macro),
            str(form),
            str(names.get(path_rowid, "")),
            int(line),
            int(end),
        )
        for path_rowid, payload in harvested
        for symbol, macro, form, line, end in payload or ()
    ]
