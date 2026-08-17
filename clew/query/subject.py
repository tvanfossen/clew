# SPDX-License-Identifier: MIT
"""Subject-agnostic lookup: point the composite dossier at ANYTHING the index holds.

THE DEFECT THIS MODULE EXISTS FOR, measured live against the public mbedtls index:
`dossier("mbedtls_mutex_lock")` answered `found: false` while `search("mutex")` listed
that exact name as `kind: variable`. The composite dossier resolved through
`function_candidates`, which filters `kind='function'`, so every subject that is not a
function was unreachable from the tool a model is told to call first — and mbedtls's
entire locking API is four function POINTERS, i.e. variables.

That single restriction is why the MCP surface had nineteen tools. `lookup_class`,
`req_trace`, `runs_under_lock`, `kconfig` and `thread_roster` are not five capabilities;
they are one capability — "tell me about this thing and what is adjacent to it" — split
five ways because the composite could not be pointed at their subjects. Give the
composite a subject KIND and the five collapse into it.

WHAT THIS MODULE IS NOT. It is not a new query layer. Every section it returns is built
by the R2 function that already built it (`dossier`, `lookup_class`, `req_trace`,
`runs_under_lock`, `kconfig_space`, `thread_roster`, `chain_trace`), and those functions
keep their signatures because the HTML view and the tests call them directly. What is
new is the CLASSIFIER — one cheap probe per corpus that says which of them to call.

@brief Resolve a name to its subject kind and build that kind's dossier.
@version 1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ._common import (
    DbSource,
    connect,
    extract_version,
    function_candidates,
    has_columns,
    strip_xml,
    symbol_provenance,
    table_exists,
)
from .corpus import CLASS_KINDS, lookup_class
from .dossier import _dossier_conn, _macro_dossier
from .kconfig import kconfig_space
from .locks import lock_roster, runs_under_lock
from .macros import MACRO_KIND, macro_definitions_conn
from .models import (
    SUBJECT_KINDS,
    Chain,
    Dossier,
    KconfigSpace,
    LockSubject,
    SubjectDossier,
    Thread,
    VariableSite,
    VariableSubject,
)
from .source import DEFAULT_BODY_LINES, declaration_excerpt
from .symbols import CONFIG_SYMBOL_KIND, req_trace, thread_roster
from .traversal import chain_trace

## The deepest `depth` a subject dossier will traverse, and a REFUSAL rather than a
## clamp. Depth is the argument most able to turn a bounded payload into an unbounded
## one — `dossier('size')` on a real C++ index measured 125,559 bytes at depth ONE — and
## a silently clamped depth reports a 3-hop answer to a caller who asked for 6.
##
## Six matches `chain_trace`'s own default `max_depth`, so this bound narrows nothing
## that traversal already allows; it only stops `dossier` from becoming a second,
## unbounded route to the same walk.
MAX_SUBJECT_DEPTH = 6


## @brief True when a name is a function in this index.
## @param conn Open connection.
## @param name Bare symbol name.
## @return True when at least one `kind='function'` memberdef row carries the name.
## @version 1
## @dg_internal
def _is_function(conn: sqlite3.Connection, name: str) -> bool:
    """Through `function_candidates` rather than its own SQL, so "what counts as a
    function here" has ONE definition. A second copy of that predicate is the drift
    condition that produced gh#26.

    @brief Probe the function corpus.
    @return True when the name names a function.
    @version 1
    """
    return bool(function_candidates(conn, name))


## @brief True when a name defines a macro in this index.
## @param conn Open connection.
## @param name Bare symbol name.
## @return True when the name has at least one `#define` row.
## @version 1
## @dg_internal
def _is_macro(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Probe the macro corpus.
    @return True when the name names a macro.
    @version 1
    """
    return bool(macro_definitions_conn(conn, name))


## @brief Every `kind='variable'` memberdef row for a name, definition-preferring.
## @param conn Open connection.
## @param name Bare symbol name.
## @return Rows of (rowid, type, definition, file, line, static, extern, initializer, brief, detail).
## @version 2
## @dg_internal
def _variable_rows(conn: sqlite3.Connection, name: str) -> list[tuple]:
    """ORDERED DEFINITION-FIRST, by the same rule `function_candidates` uses and for the
    same reason: an `extern` declaration in a header and the definition in a translation
    unit are one variable seen twice, and the definition is the row that carries the
    binding. `extern DESC` puts the non-extern row first; the mbedtls function pointers
    record `extern=0` on both rows, so `file_id = bodyfile_id` is the tiebreak that
    actually separates them there.

    GUARDED ON COLUMNS, NOT ONLY ON THE TABLE, and this one bit immediately. Every other
    subject probe reads columns `memberdef` has always had; this reads six the schema
    grew (`type`, `initializer`, `static`, `extern`, and the two description columns), and
    because `resolve_subject` runs EVERY probe on EVERY dossier call, a database missing
    one took the whole tool down with `no such column: m.type` — not just its variable
    path. Verified against this suite's hand-built minimal indexes, which is the same
    graceful-degradation contract `has_columns` was written for after five tier-1 tools
    died on `s.dispatch_mode`.

    Degrades to the columns that ARE present rather than refusing, because "no variable
    of that name" and "this index cannot describe variables" are different facts and the
    second must not be reported as the first — the standing rule that no rows is a claim
    about the detector.

    @brief Fetch a name's variable rows, definition-preferring.
    @return Raw rows, definition first, with absent columns defaulted.
    @version 2
    """
    if not table_exists(conn, "memberdef"):
        return []
    optional = ("type", "initializer", "briefdescription", "detaileddescription")
    text = {
        c: (f"COALESCE(m.{c},'')" if has_columns(conn, "memberdef", c) else "''") for c in optional
    }
    flags = {
        c: (f"m.{c}" if has_columns(conn, "memberdef", c) else "0") for c in ("static", "extern")
    }
    line = "m.line" if has_columns(conn, "memberdef", "line") else "0"
    ## NULL, NOT `0`, for an absent ORDER BY term. A bare integer in an ORDER BY is an
    ## ORDINAL in SQLite — `ORDER BY 0` raises "1st ORDER BY term out of range" rather than
    ## sorting by a constant, which is a different failure from the missing column it was
    ## meant to paper over and reads nothing like it. The SELECT list keeps `0`, where an
    ## integer is an integer.
    body = (
        "(m.file_id = m.bodyfile_id)" if has_columns(conn, "memberdef", "bodyfile_id") else "NULL"
    )
    extern = flags["extern"] if flags["extern"] != "0" else "NULL"
    return conn.execute(
        f"SELECT m.rowid, {text['type']}, COALESCE(m.definition, m.name), "  # noqa: S608
        f"COALESCE(p.name,''), {line}, {flags['static']}, {flags['extern']}, "
        f"{text['initializer']}, {text['briefdescription']}, {text['detaileddescription']} "
        "FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
        "WHERE m.name=? AND m.kind='variable' "
        f"ORDER BY {extern} ASC, {body} DESC, m.rowid",
        (name,),
    ).fetchall()


## @brief True when a name is an indexed compound (class/struct/union).
## @param conn Open connection.
## @param name Bare or qualified compound name.
## @return True when a class/struct/union/interface matches exactly or as a qualified tail.
## @version 2
## @dg_internal
def _is_compound(conn: sqlite3.Connection, name: str) -> bool:
    """EXACT OR QUALIFIED-TAIL, never `lookup_class`'s substring fallback. That fallback
    is right for a caller who has ASKED for a class and typed a fragment; it is wrong as
    a classifier, because `lock` would then classify as the class `spinlock` and the
    dossier would answer about a compound the caller never named.

    IT MUST FILTER ON `CLASS_KINDS`, and not doing so was a measured defect. doxygen puts
    more than classes in `compounddef`: it registers a row per FILE with `kind='file'`, and
    on mbedtls `resolve_subject("threading.c")` therefore came back `('class',)` while
    `subject_dossier` returned nothing at all — because `lookup_class` DOES filter on
    `CLASS_KINDS` and found no class. Probe and builder must agree or the caller is told
    "this kind exists" and then handed an empty section, which is the same disagreement
    gh#390 produced for config symbols one commit ago.

    A WRONG KIND IS WORSE THAN A MISS. "threading.c is a class" is a confident
    misclassification, and the reply carries no hint that the classifier and the builder
    disagreed — the shape this repo's notes call an arbitrary pick reported as the answer.

    @brief Probe the compound corpus.
    @return True when the name names a class, struct, union or interface.
    @version 2
    """
    if not table_exists(conn, "compounddef"):
        return False
    placeholders = ",".join("?" * len(CLASS_KINDS))
    return (
        conn.execute(
            f"SELECT 1 FROM compounddef WHERE kind IN ({placeholders}) "  # noqa: S608
            "AND (name = ? OR name LIKE '%::' || ?) LIMIT 1",
            (*CLASS_KINDS, name, name),
        ).fetchone()
        is not None
    )


## @brief True when a name is a requirement id this index knows.
## @param conn Open connection.
## @param name Candidate requirement id.
## @return True when the id appears in the catalog or on any tag edge.
## @version 1
## @dg_internal
def _is_requirement(conn: sqlite3.Connection, name: str) -> bool:
    """BOTH TABLES, because they populate independently and this repo has already been
    caught reading one of them: `req_edges` come from TAGS and the catalog comes from a
    declared YAML file, so a tagged-but-uncatalogued id is real and a catalogued-but-
    untagged one is a coverage finding. Either is a requirement subject.

    NO PATTERN MATCHING. The id shape is a per-repo declaration (`REQ-0621` in one repo,
    `REQ-PROJ-NAV-002` in another) and baking one in here is exactly what the
    no-hardcoding mandate forbids. Asking the tables costs one indexed lookup and cannot
    be wrong about a spelling it has never seen.

    @brief Probe the requirement corpus.
    @return True when the name names a requirement.
    @version 1
    """
    for table, column in (("requirements", "id"), ("req_edges", "req_id")):
        if not table_exists(conn, table):
            continue
        sql = f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1"  # noqa: S608
        if conn.execute(sql, (name,)).fetchone() is not None:
            return True
    return False


## @brief True when a name is a lock identity in this index.
## @param conn Open connection.
## @param name Lock name as written in the source.
## @return True when the locks table holds a row of that name.
## @version 1
## @dg_internal
def _is_lock(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Probe the lock corpus.
    @return True when the name names a lock.
    @version 1
    """
    if not table_exists(conn, "locks"):
        return False
    return conn.execute("SELECT 1 FROM locks WHERE name=? LIMIT 1", (name,)).fetchone() is not None


## @brief True when a name is a thread in this index.
## @param conn Open connection.
## @param name Thread name or entry-function name.
## @return True when the threads table holds a row of that name.
## @version 1
## @dg_internal
def _is_thread(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Probe the thread corpus.
    @return True when the name names a thread.
    @version 1
    """
    if not table_exists(conn, "threads"):
        return False
    return (
        conn.execute("SELECT 1 FROM threads WHERE name=? LIMIT 1", (name,)).fetchone() is not None
    )


## @brief True when a name is a declared configuration symbol.
## @param conn Open connection.
## @param name CONFIG symbol name.
## @return True when the symbol is declared, or gated on anywhere in the tree.
## @version 2
## @dg_internal
def _is_config(conn: sqlite3.Connection, name: str) -> bool:
    """GATED-ON SYMBOLS ARE SUBJECTS TOO, since gh#390. This used to read "DECLARED
    symbols only ... a gate naming a symbol no Kconfig declares is not a subject, because
    there is nothing to describe", and that was right when a gate row was a bare name from
    a Kconfig-less corner of a Kconfig repo.

    It stopped being right when the gate harvest widened past the `CONFIG_` prefix. A gate
    row now says WHERE a symbol decides that code exists, in how many files, and in which
    form — `#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS` at `private_access.h:14` IS the answer to
    "why does this struct member have two names", and `MBEDTLS_THREADING_C` gating 151
    sites across 31 files IS the answer to "is the locking compiled in". Refusing those as
    subjects left `dossier` returning a definitive negative for the exact symbols two
    benchmark questions were about.

    An undeclared gate remains a FINDING — dead code behind a symbol nobody can set — and
    `origin` on each row says so. That is a label on the answer, not a reason to withhold it.

    @brief Probe the configuration corpus.
    @return True when the name is a declared config symbol or is gated on.
    @version 2
    """
    for table, column in (("kconfig_symbols", "name"), ("kconfig_gates", "symbol")):
        if not table_exists(conn, table):
            continue
        sql = f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1"  # noqa: S608
        if conn.execute(sql, (name,)).fetchone() is not None:
            return True
    return False


## One probe per subject kind, keyed by kind. A MAPPING and not a chain of `if`s so that
## `SUBJECT_KINDS` is the only place the order lives — a probe added without a kind, or a
## kind declared without a probe, fails the parity test rather than shipping a subject
## nothing can resolve.
_PROBES = {
    "function": _is_function,
    "macro": _is_macro,
    "variable": lambda conn, name: bool(_variable_rows(conn, name)),
    "class": _is_compound,
    "requirement": _is_requirement,
    "lock": _is_lock,
    "thread": _is_thread,
    "config": _is_config,
}


## @brief Every subject kind one name resolves to, in probe order.
## @param db Path, str or open connection to a built index.
## @param name The name to classify.
## @return Kinds this name is, best-first; empty when the index holds no such subject.
## @version 1
## @req REQ-DDB-QUERY-001
def resolve_subject(db: DbSource, name: str) -> tuple[str, ...]:
    """ALL OF THEM, NOT THE FIRST. One string genuinely can be several subjects — a
    macro and the member it wraps, a lock and the variable that declares it — and a
    classifier that returned the first match would make the arbitrary pick invisible.
    That is the gh#26 failure one level up: an arbitrary resolution reported as the
    answer, with nothing on the wire saying a choice was made.

    EVERY PROBE IS ONE INDEXED LOOKUP against a table that is small or keyed, so
    classifying costs a handful of microseconds and the hot path — a name that is a
    function — is unchanged in what it then builds.

    @brief Classify a name across every subject corpus.
    @return The kinds it resolves to, in `SUBJECT_KINDS` order.
    @version 1
    """
    with connect(db) as conn:
        return tuple(k for k in SUBJECT_KINDS if _PROBES[k](conn, name))


## @brief Build the variable section for a name.
## @param conn Open connection.
## @param name Bare variable name.
## @param repo_root Working tree, or None to skip the declaration excerpts.
## @return The VariableSubject, or None when the name names no variable.
## @version 1
## @dg_internal
def _variable_subject(
    conn: sqlite3.Connection, name: str, repo_root: Path | str | None
) -> VariableSubject | None:
    """EVERY SITE, not the chosen one. The header's `extern` row and the translation
    unit's definition answer different questions, and on the case this exists for they
    are 10 lines apart in two different files: `include/mbedtls/threading.h:113` declares
    `mbedtls_mutex_lock` and `library/threading.c:103` binds it. A payload naming one
    file would have been wrong half the time and unfalsifiable either way.

    The BRIEF is taken from the first site that carries one, exactly as `_sibling_prose`
    does for a decl/def function pair: a variable documented in its header and bare at
    its definition is documented, and reading the chosen row alone would report
    otherwise.

    @brief Assemble a variable subject from all of a name's declaration sites.
    @return VariableSubject or None.
    @version 1
    """
    rows = _variable_rows(conn, name)
    if not rows:
        return None
    sites = tuple(
        VariableSite(
            file=r[3],
            line=int(r[4] or 0),
            signature=r[2],
            static=bool(r[5]),
            extern=bool(r[6]),
            initializer=r[7],
            declaration=(None if repo_root is None else declaration_excerpt(conn, r[0], repo_root)),
        )
        for r in rows
    )
    brief = next((strip_xml(r[8]) for r in rows if strip_xml(r[8])), "")
    version = next((extract_version(r[9]) for r in rows if extract_version(r[9])), "")
    return VariableSubject(
        name=name,
        rowid=rows[0][0],
        type=rows[0][1],
        brief=brief,
        version=version,
        provenance=symbol_provenance(conn, rows[0][0]),
        sites=sites,
    )


## @brief Build the lock section for a name.
## @param db Path, str or open connection to a built index.
## @param name Lock name as written in the source.
## @return The LockSubject, or None when no lock carries the name.
## @version 1
## @dg_internal
def _lock_subject(db: DbSource, name: str) -> LockSubject | None:
    """Composed from `lock_roster` and `runs_under_lock`, the two functions that already
    answer the two halves — this adds no SQL. The roster row is what keeps the identity
    caveat attached: a bare lock name can denote several `(name, scope, kind)` rows, and
    `siblings` says so rather than letting the first one stand for the mutex.

    @brief Assemble a lock subject from the roster and its sections.
    @return LockSubject or None.
    @version 1
    """
    matches = [entry for entry in lock_roster(db).locks if entry.name == name]
    if not matches:
        return None
    return LockSubject(
        lock=matches[0],
        sections=tuple(runs_under_lock(db, name)),
        siblings=tuple(matches[1:]),
    )


## What `search` PUTS ON A ROW mapped to the subject kind that follows it (gh#404). `search`'s
## `kind` and `dossier`'s `kind` grew independently — the search label comes from four unlinked
## places (`SEARCHED_MEMBERDEF_KINDS`, the bare `file` literal, `CLASS_KINDS`, `CONFIG_SYMBOL_KIND`)
## while this module's vocabulary is `SUBJECT_KINDS` — and only `function`, `variable` and `class`
## happened to spell the same thing in both.
##
## MEASURED COST OF THE DIVERGENCE: a benchmark cell read `kind: "macro definition"` off a search
## row, passed it straight back exactly as `search`'s own description instructs, and got
## `Unknown subject kind`. One whole round trip, spent on our inconsistency, twice in three runs.
##
## ALIASED HERE RATHER THAN BY WIDENING `SUBJECT_KINDS`, deliberately: that tuple's ORDER is
## load-bearing (it is the best-first probe order for a bare name), every one of its values must
## appear in `dossier.json` and must own a `_PROBES` and a `_BUILDERS` entry. An alias is additive
## and touches none of that.
##
## `config symbol` -> `config` is the one pair the code already knew about: `CONFIG_SYMBOL_KIND`'s
## own comment says "NOT 'config', which is `resolve_subject`'s kind for the same thing". That
## deliberate split is preserved on the wire and reconciled only here, at the boundary.
_KIND_ALIASES: dict[str, str] = {
    MACRO_KIND: "macro",
    "struct": "class",
    "union": "class",
    "interface": "class",
    CONFIG_SYMBOL_KIND: "config",
}

## Search kinds that name no subject at all, with what to do instead. These are NOT aliasable —
## there is no typedef subject, no enumeration subject and no file subject to build — so the
## honest fix is a refusal that names the route rather than a mapping that pretends.
##
## SAYING "unknown kind" AND STOPPING IS WHAT COST THE ROUND TRIP. A refusal that names the
## alternative costs the same message and ends the search.
_KIND_NO_SUBJECT: dict[str, str] = {
    "file": "a file has no dossier — its documentation is `search(corpus='prose')`",
    "typedef": "a typedef has no dossier — the `search` row already carries all the index holds",
    "enumeration": (
        "an enumeration has no dossier — the `search` row already carries all the index holds"
    ),
}


## @brief The chosen subject kind, validated against what the name actually resolves to.
## @param kinds Every kind the name resolves to.
## @param wanted The caller's explicit kind, or None to take the best-first pick.
## @return The kind to build, or None when the name resolves to nothing usable.
## @version 2
## @dg_internal
def _chosen_kind(kinds: tuple[str, ...], wanted: str | None) -> str | None:
    """AN EXPLICIT KIND IS A FILTER, NOT AN OVERRIDE. Asking for `kind='variable'` on a
    name that is only a function returns nothing, rather than the function relabelled —
    a caller that disambiguated deliberately must not be handed the thing it ruled out.

    A SEARCH ROW'S `kind` IS ACCEPTED HERE (gh#404), because `search`'s description promises it
    is: "READ `kind` ON EVERY ROW: it is what you pass back". `_KIND_ALIASES` makes that promise
    true for the five kinds that name a subject, and `_KIND_NO_SUBJECT` makes the refusal useful
    for the three that do not. The alias is applied BEFORE the filter, so aliasing cannot smuggle
    in a kind the name does not actually resolve to.

    @brief Select which resolved kind to build.
    @return The kind, or None.
    @version 2
    """
    if wanted is None:
        return kinds[0] if kinds else None
    wanted = _KIND_ALIASES.get(wanted, wanted)
    if wanted in _KIND_NO_SUBJECT:
        raise ValueError(
            f"Subject kind {wanted!r} names no dossier subject: {_KIND_NO_SUBJECT[wanted]}."
        )
    if wanted not in SUBJECT_KINDS:
        raise ValueError(
            f"Unknown subject kind {wanted!r}. Known kinds: {', '.join(SUBJECT_KINDS)}."
        )
    return wanted if wanted in kinds else None


## @brief The bounded traversal a depth>1 request asks for, when the subject has a seed.
## @param db Path, str or open connection to a built index.
## @param kind The resolved subject kind.
## @param name The subject name.
## @param depth Requested hop depth.
## @param direction 'forward' (downstream) or 'backward' (upstream).
## @param max_neighbors Fan-out cap at depth 1.
## @return The Chain, or None when depth is 1 or the subject has no traversal seed.
## @version 1
## @dg_internal
def _chain_for(
    db: DbSource, kind: str, name: str, depth: int, direction: str, max_neighbors: int
) -> Chain | None:
    """REUSES `chain_trace` RATHER THAN WALKING AGAIN. Its fan-out taper, its cycle
    handling and its non-fuzzy-edges-only rule are the bounds that keep a depth-3 walk
    from returning a hub's whole component, and a second traversal here would be a
    second set of bounds to get wrong.

    ONLY A FUNCTION HAS A SEED. `chain_trace` starts from a function name and follows
    call and shared-key edges; a lock, a requirement and a config symbol are not
    endpoints of those edges, so there is nothing to walk from. Returning None is the
    honest answer and the MCP layer discloses it — a depth argument that silently did
    nothing would be worse than one that refused.

    @brief Traverse from the subject when it has a traversal seed.
    @return Chain or None.
    @version 1
    """
    if depth <= 1 or kind != "function":
        return None
    return chain_trace(db, name, direction=direction, max_depth=depth, max_neighbors=max_neighbors)


## @brief The full subject dossier for a name of ANY indexed kind.
## @param db Path, str or open connection to a built index.
## @param subject The name to describe.
## @param kind Restrict to one subject kind, or None to take the best-first resolution.
## @param qualified Optional identity selector from a prior `candidates.qualified` (functions only).
## @param repo_root Working tree the index was built from; omit to skip every panel that reads bytes.
## @param max_body_lines Cap on the function body excerpt.
## @param depth Hops to traverse; 1 is adjacency only, up to MAX_SUBJECT_DEPTH.
## @param direction Traversal direction when depth > 1.
## @param max_neighbors Fan-out cap for the traversal.
## @return The SubjectDossier, or None when the index holds no subject of that name.
## @version 1
## @req REQ-DDB-QUERY-004
## @req REQ-DDB-QUERY-009
## @req REQ-DDB-QUERY-010
def subject_dossier(
    db: DbSource,
    subject: str,
    kind: str | None = None,
    qualified: str | None = None,
    repo_root: Path | str | None = None,
    max_body_lines: int = DEFAULT_BODY_LINES,
    depth: int = 1,
    direction: str = "forward",
    max_neighbors: int = 8,
) -> SubjectDossier | None:
    """ONE SUBJECT, ONE POPULATED SECTION, AND THE OTHER KINDS NAMED. See
    `SubjectDossier` for why absence rather than an empty field carries "does not apply".

    THE FUNCTION PATH IS THE OLD PATH, byte for byte: `_dossier_conn` is called with the
    same arguments the function-only `dossier` passed it, so nothing about the common
    case changes except that it now travels inside an envelope that says what kind of
    thing it described.

    `depth` IS REFUSED ABOVE `MAX_SUBJECT_DEPTH` rather than clamped, for the reason
    every cap on this surface refuses: a clamped depth answers three hops to a request
    for eight and reports no difference, which is the silent-degradation failure the
    `_limited` disclosures exist to convert into a measurement.

    @brief Describe one subject of any kind, with its adjacency.
    @return SubjectDossier or None.
    @version 1
    """
    if depth < 1 or depth > MAX_SUBJECT_DEPTH:
        raise ValueError(
            f"depth must be between 1 and {MAX_SUBJECT_DEPTH}; {depth} was requested. "
            "Depth 1 is the subject and its immediate adjacency; deeper walks are "
            "bounded because an unbounded one on a hub symbol returns its whole "
            "component."
        )
    kinds = resolve_subject(db, subject)
    chosen = _chosen_kind(kinds, kind)
    if chosen is None:
        return None
    with connect(db) as conn:
        section = _BUILDERS[chosen](
            _BuildContext(conn, db, subject, qualified, repo_root, max_body_lines)
        )
    ## A builder that came back empty after its probe fired is NOT a resolved subject.
    ## The probe and the builder can legitimately disagree — a compound whose ranked
    ## lookup rejected every match, a lock row whose sections were all excluded — and
    ## returning an envelope naming a kind with nothing under it would claim a
    ## description that was never produced.
    if next(iter(section.values())) is None:
        return None
    return SubjectDossier(
        subject=subject,
        kind=chosen,
        also=tuple(k for k in kinds if k != chosen),
        chain=_chain_for(db, chosen, subject, depth, direction, max_neighbors),
        **section,
    )


## @brief Subject dossiers for several names over ONE connection.
## @param db Path, str or open connection to a built index.
## @param subjects The names to describe, in the order the caller asked for them.
## @param kind Restrict every subject to one kind, or None for best-first resolution.
## @param repo_root Working tree the index was built from; omit to skip the byte-reading panels.
## @param max_body_lines Cap on each function body excerpt.
## @param depth Hops to traverse; 1 is adjacency only.
## @return One entry per requested name, positionally aligned, None where a name resolves to nothing.
## @version 1
## @req REQ-DDB-QUERY-004
def subject_dossiers(
    db: DbSource,
    subjects: list[str],
    kind: str | None = None,
    repo_root: Path | str | None = None,
    max_body_lines: int = DEFAULT_BODY_LINES,
    depth: int = 1,
) -> list[SubjectDossier | None]:
    """ONE CONNECTION, N SUBJECTS, and the sharing is free rather than engineered:
    `connect` yields a caller-supplied `Connection` as-is, so passing the open connection
    down as `db` makes every nested `connect` inside `subject_dossier` a no-op. Five
    subjects used to mean five sqlite opens and five sets of `table_exists` probes
    against the same file.

    POSITIONAL, INCLUDING THE MISSES, for the same reason `dossiers` is: a dropped miss
    silently re-labels every answer after it.

    NO `qualified`, for the same reason `dossiers` refuses it: one identity selector
    cannot say which of five names it disambiguates.

    @brief Describe several subjects of any kind in one pass.
    @return One SubjectDossier-or-None per requested name, in request order.
    @version 1
    """
    with connect(db) as conn:
        return [
            subject_dossier(
                conn,
                name,
                kind=kind,
                repo_root=repo_root,
                max_body_lines=max_body_lines,
                depth=depth,
            )
            for name in subjects
        ]


## @brief The single thread row a name names, or None.
## @param conn Open connection.
## @param name Thread name.
## @return The Thread, or None when the roster holds no row of that name.
## @version 1
## @dg_internal
def _thread_subject(conn: sqlite3.Connection, name: str) -> Thread | None:
    """Filters the roster rather than querying `threads` directly, so a thread subject
    carries the same `member_count`, origin tag and spawn site the roster reports. A
    second query would be a second definition of what a thread row IS.

    @brief Pick one thread out of the roster by name.
    @return Thread or None.
    @version 1
    """
    return next((t for t in thread_roster(conn).threads if t.name == name), None)


## @brief The configuration space, narrowed to one declared symbol's gates.
## @param conn Open connection.
## @param name CONFIG symbol name.
## @return The KconfigSpace, or None when the symbol is neither declared nor gated on.
## @version 2
## @dg_internal
def _config_subject(conn: sqlite3.Connection, name: str) -> KconfigSpace | None:
    """Returns the WHOLE envelope, gates narrowed to this symbol, because
    `KconfigSpace`'s `found`/`source`/`error` fields are what separate "this repo has no
    Kconfig" from "its Kconfig would not parse" — and stripping them to return a bare
    symbol row would collapse exactly the three-way distinction that type exists to keep.

    ACCEPTS A GATE-ONLY SYMBOL (gh#390), matching `_is_config`. Requiring a declaration
    here would make the two disagree: the probe would classify the subject as `config` and
    the builder would then hand back None, which presents to a caller as "this kind exists
    but I have nothing" — the same confident emptiness the widened harvest exists to end.

    @brief Build the config subject for one declared or gated-on symbol.
    @return KconfigSpace or None.
    @version 2
    """
    space = kconfig_space(conn, name)
    if any(s.name == name for s in space.symbols):
        return space
    return space if space.gates else None


## @brief The macro dossier for a name, built from its definition sites.
## @param conn Open connection.
## @param name Bare macro name.
## @return The macro Dossier, or None when the name defines no macro.
## @version 1
## @dg_internal
def _macro_subject(conn: sqlite3.Connection, name: str) -> Dossier | None:
    """THE EMPTY-LIST COUPLING MADE EXPLICIT (gh#404). `_macro_dossier` indexes `macros[0]`
    unguarded, and today it cannot be reached with an empty list because `_is_macro` gated the
    kind — a coupling that holds by luck of ordering rather than by construction. Returning None
    here instead is what lets `subject_dossier`'s existing "section is None" branch report a clean
    miss, the same way every other builder does.

    NO `qualified` ARGUMENT, because a `#define` has no qualified spelling to disambiguate: the
    preprocessor has one flat namespace. A caller passing `qualified` with `kind='macro'` is
    already refused upstream.

    @brief Build the macro subject's dossier.
    @return The Dossier, or None.
    @version 1
    """
    macros = macro_definitions_conn(conn, name)
    return _macro_dossier(macros) if macros else None


## One builder per subject kind, returning the KWARG that populates its section.
##
## A MAPPING, not a chain of branches, for the same reason `_PROBES` is: the kind list
## lives once in `SUBJECT_KINDS` and a kind with no builder fails the parity test instead
## of falling through to whatever the last branch happened to be.
##
## `macro` USED TO SHARE THE FUNCTION BUILDER and that was the bug (gh#404). The old comment
## justified it by saying `_dossier_conn` "already resolves a macro-only name to `_macro_dossier`",
## which is true and which quietly names its own exception: MACRO-ONLY. `dossier.py`'s guard is
## `if not cands`, so a name that is ALSO a function never reaches the macro path however
## explicitly the caller asked for one.
##
## MEASURED: `MBEDTLS_PRIVATE` has 473 `kind='function'` memberdef rows — doxygen writes one per
## struct field wrapped in the macro — and NONE has `file_id = bodyfile_id`, so
## `function_candidates`' `ORDER BY has_body DESC, rowid` degenerates to lowest rowid and returns
## `include/mbedtls/aes.h` with `bodystart NULL`. A caller that asked for `kind='macro'` got a
## struct FIELD, under an envelope labelled `subject_kind: macro`, and went and read the file.
##
## THE FILTER WAS NEVER BROKEN — `_chosen_kind` correctly returns `"macro"` — the BUILDER threw the
## answer away. So the fix is here and only here. It deliberately does NOT touch `dossier.py`'s
## guard: that would change what a BARE name resolves to and break the collision tests this repo
## pinned when it withdrew exactly that re-ranking (a note, not a demotion, is the standing
## disposition for the bare case).
_BUILDERS = {
    "function": lambda ctx: {"function": _dossier_conn(*ctx.function_args)},
    "macro": lambda ctx: {"function": _macro_subject(ctx.conn, ctx.subject)},
    "variable": lambda ctx: {"variable": _variable_subject(ctx.conn, ctx.subject, ctx.repo_root)},
    "class": lambda ctx: {"compound": lookup_class(ctx.conn, ctx.subject)},
    "requirement": lambda ctx: {"requirement": req_trace(ctx.conn, ctx.subject)},
    "lock": lambda ctx: {"lock": _lock_subject(ctx.db, ctx.subject)},
    "thread": lambda ctx: {"thread": _thread_subject(ctx.conn, ctx.subject)},
    "config": lambda ctx: {"config": _config_subject(ctx.conn, ctx.subject)},
}


## @brief What every section builder needs, so the builders share one signature.
## @version 1
@dataclass(frozen=True)
class _BuildContext:
    """A RECORD RATHER THAN SEVEN POSITIONAL ARGUMENTS, because the builders are a
    mapping and a mapping's values must be callable the same way. Without it each kind
    would need its own adapter, which is the per-kind wrapper layer that
    `_memberdef_corpora` was written to delete one module over.

    @brief The arguments a section builder is called with.
    @version 1
    """

    conn: sqlite3.Connection
    db: DbSource
    subject: str
    qualified: str | None
    repo_root: Path | str | None
    max_body_lines: int

    ## @brief The positional arguments `_dossier_conn` takes, unchanged.
    ## @return The tuple to splat into `_dossier_conn`.
    ## @version 1
    ## @dg_internal
    @property
    def function_args(self) -> tuple:
        """Spelled out here so the function path's call is VERBATIM what the
        function-only `dossier` passed — the one thing this refactor must not change.

        @brief The function builder's argument tuple.
        @return Arguments for `_dossier_conn`.
        @version 1
        """
        return (self.conn, self.subject, self.qualified, self.repo_root, self.max_body_lines)
