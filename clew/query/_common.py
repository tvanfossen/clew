# SPDX-License-Identifier: MIT
"""Shared connection + resolution helpers for the R2 query library.

Every public query module depends on this one (DRY): a single connection
normalizer (accepts `Path | str | sqlite3.Connection`), the DEFINITION-
PREFERRING name→rowid resolution (the decl/def duality correction, ported
from the retired walkthrough dbview helpers), rowid→name lookup, table
existence guards (mini/partial DBs lack later layers), and the doxygen
description scrubbers (`strip_xml` / `extract_version`, ported from
the same retired helpers).

It also owns the FUNCTION IDENTITY rule (`qualified_name_of` /
`identity_rowids`, gh#26): which memberdef rows are the same function. That rule
lives here, once, because three surfaces need it — edge attribution, thread
membership and overload reporting — and two independent copies of it is what let
three unrelated `_classify` helpers share one graph node.

Since gh#37 that rule is also the SELECTOR a consumer passes back
(`matching_identity`): every resolution helper here takes an optional `qualified`
argument, and the accessors above them forward it. The identity key and the
disambiguator are deliberately the same string, so "which rows are one function"
and "which function did you mean" cannot answer differently.

@brief Connection + name/rowid resolution helpers for the query package.
@version 3
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from ..vocabulary import SYMBOL_SOURCE_AST, SYMBOL_SOURCE_COLUMN, SYMBOL_SOURCE_DOXYGEN

if TYPE_CHECKING:  # pragma: no cover — annotation only, kept out of the runtime graph
    from .models import Candidate

DbSource = str | Path | sqlite3.Connection

## Cap the overload-candidate list a resolution surfaces: enough rows to
## disambiguate by file, never so many (react = 37) that the payload balloons.
## Lives here so resolve_symbol and dossier share ONE cap (DRY).
MAX_CANDIDATES = 8


## @brief Yield an open sqlite connection; close it only if we opened it.
## @return An open sqlite3.Connection; a caller-supplied one is yielded as-is, a path-opened one is closed on exit.
## @version 2
## @req REQ-DDB-QUERY-001
@contextlib.contextmanager
def connect(db: DbSource) -> Iterator[sqlite3.Connection]:
    """Normalize a `Path | str | sqlite3.Connection` into an open
    connection. A caller-supplied Connection is yielded as-is (never
    closed here); a path is opened read-only-ish and closed on exit.

    @brief Connection normalizer for every query entry point.
    @version 2
    """
    if isinstance(db, sqlite3.Connection):
        yield db
        return
    conn = sqlite3.connect(str(db))
    try:
        yield conn
    finally:
        conn.close()


## @brief True when a table exists (partial/mini DBs lack later layers).
## @return True if a user table of the given name exists, else False.
## @version 1
## @req REQ-DDB-QUERY-003
def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Return whether a user table of the given name exists."""
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


## @brief True when a table exists AND carries every named column.
## @param conn Open connection.
## @param table Table to inspect.
## @param cols Column names that must all be present.
## @return True only if the table exists and every column does.
## @version 2
## @req REQ-DDB-QUERY-003
def has_columns(conn: sqlite3.Connection, table: str, *cols: str) -> bool:
    """`table_exists` is not enough once a schema GROWS a column. A database
    built by an older clew has the table but not the later columns, and
    selecting one raises a raw `OperationalError` — verified live on a
    build_version-2 target whose `shared_key_edges` has 7 columns, where FIVE
    tier-1 tools died on `no such column: s.dispatch_mode` rather than degrading.
    That is the same graceful-degradation contract `table_exists` already gives
    a MISSING table, extended one level down to a missing column.

    `pragma_table_info` is the table-valued form, so the table name is BOUND
    rather than interpolated into the statement text.

    @brief Guard a query against a column a stale database predates.
    @version 2
    """
    if not table_exists(conn, table):
        return False
    present = {r[0] for r in conn.execute("SELECT name FROM pragma_table_info(?)", (table,))}
    return set(cols) <= present


## @brief One namespaced `build_meta` section, read without its key prefix.
## @param db Path to a clew.db, which need not exist or hold any table.
## @param prefix Section name (`scope`, `coverage`, `refresh`), without the dot.
## @return Mapping of unprefixed key to value; {} when absent or unreadable.
## @version 1
## @req REQ-DDB-MCP-001
def meta_section(db: str | Path, prefix: str) -> dict[str, str]:
    """ONE reader for every `build_meta` section, and it lives HERE rather than in
    `mcp_server/state.py` — where it was born — because gh#7 needed a second caller.
    Its own docstring already argued the point: there had been two byte-identical
    copies and a third was about to be pasted in. A fourth in the query layer would
    have made that four.

    NOT routed through `connect`, deliberately. `connect` calls
    `sqlite3.connect(str(db))`, which CREATES an empty file for a path that does not
    exist; this reader is called on databases that may be absent, mid-build or
    tableless, and manufacturing one would be a side effect in a status path. The
    read-only URI plus a fail-soft `{}` is the contract `status` has always had, and
    an absent key honestly reads as "not recorded" — the true answer on an index
    built before the section existed.

    The prefix is INTERPOLATED into a LIKE pattern rather than bound, because SQLite
    cannot parameterize inside a literal it has to concatenate; it is a
    module-controlled constant at every call site, never caller input.

    @brief Read one namespaced build_meta section.
    @return Mapping without the key prefix, or {}.
    @version 1
    """
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM build_meta WHERE key LIKE ?", (f"{prefix}.%",)
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return {key.split(".", 1)[1]: value for key, value in rows}


## @brief Definition-preferring function name→rowid (decl/def duality).
## @param conn Open connection.
## @param name Bare function name.
## @param qualified Optional identity selector; see `matching_identity`.
## @return The definition-preferring memberdef rowid, or None if no such function (or none of that identity).
## @version 7
## @req REQ-DDB-QUERY-003
## @req REQ-DDB-QUERY-010
def resolve_rowid(conn: sqlite3.Connection, name: str, qualified: str | None = None) -> int | None:
    """Resolve a function NAME to its canonical memberdef rowid, preferring
    the row that CARRIES A BODY over a pure declaration,
    then the lowest rowid. Ported from the retired walkthrough dbview helper.

    The bare-name path keeps its own SQL rather than routing through
    `function_candidates`, deliberately: it is the hot path (every dataflow
    neighbour calls it once) and `LIMIT 1` in SQLite beats materializing every
    same-named row in Python. The two orderings are the same key — body rows
    first, then lowest rowid — so the disambiguated branch names the same row the
    bare branch would have, for the subset it keeps.

    @brief Resolve a function name to its definition-preferring rowid.
    @version 7
    """
    if not table_exists(conn, "memberdef"):
        return None
    if qualified is not None:
        cands = function_candidates(conn, name, qualified)
        return cands[0][0] if cands else None
    row = conn.execute(
        "SELECT rowid FROM memberdef WHERE name=? AND kind='function' "
        "ORDER BY (file_id = bodyfile_id) DESC, "
        "(COALESCE(bodyfile_id, 0) > 0 AND COALESCE(bodystart, 0) > 0) DESC, "
        "rowid LIMIT 1",
        (name,),
    ).fetchone()
    return row[0] if row else None


## @brief All same-named function rows (definition-first) for overload disambiguation.
## @param conn Open connection.
## @param name Bare function name (`memberdef.name`).
## @param qualified Optional identity selector; see `matching_identity`. None keeps every same-named row.
## @return List of (rowid, signature, file, line_start, has_body) tuples, definition rows first then by rowid; empty when the name is unknown or no row carries that identity.
## @version 6
## @req REQ-DDB-QUERY-003
## @req REQ-DDB-QUERY-010
def function_candidates(
    conn: sqlite3.Connection, name: str, qualified: str | None = None
) -> list[tuple[int, str, str, int | None, bool]]:
    """Return every `kind='function'` memberdef row for a name, definition
    rows first (a row that carries a body), each carrying the doxygen
    `definition` signature that distinguishes overloads a bare name cannot.
    This is the raw material for both `resolve_rowid` (which takes the first)
    and the ambiguity signal a consumer surfaces.

    THE `name` ARGUMENT STAYS BARE (gh#37). The SQL matches `memberdef.name`, and
    that is the only column holding the unqualified spelling — a caller who
    passed `Harvester.harvest` here would match NOTHING, which is precisely the
    trap gh#37 recorded. Selection among the rows is `qualified`'s job, applied in
    Python against `qualified_name_of`, so a qualified spelling never has to be
    matched against `definition` with `LIKE`. That was the alternative and it is
    the one gh#37 forbids: whole-signature comparison was measured to tear 122
    entropic decl/def pairs in half.

    Filtering AFTER the fetch rather than in SQL, deliberately. `qualified_name_of`
    is a token scan over `definition`, not an expression SQLite can evaluate, and
    the row set for one bare name is small (11 for the worst case on this repo's
    own index, 37 on entropic) — so this costs nothing measurable and keeps ONE
    identity rule in ONE place instead of a second, SQL-shaped copy of it.

    @brief List same-named function rows, definition-preferring, with signatures.
    @version 6
    """
    if not table_exists(conn, "memberdef"):
        return []
    rows = conn.execute(
        "SELECT m.rowid, COALESCE(m.definition, m.name), COALESCE(p.name,''), "
        "m.bodystart, (COALESCE(m.bodyfile_id, 0) > 0 AND COALESCE(m.bodystart, 0) > 0) AS has_body "
        "FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
        "WHERE m.name=? AND m.kind='function' "
        "ORDER BY (m.file_id = m.bodyfile_id) DESC, has_body DESC, m.rowid",
        (name,),
    ).fetchall()
    cands = [(r[0], r[1], r[2], r[3], bool(r[4])) for r in rows]
    return cands if qualified is None else matching_identity(name, cands, qualified)


## @brief Keep only the candidate rows whose IDENTITY is the named qualified one.
## @param name Bare function name the rows were fetched by.
## @param cands Rows from `function_candidates`.
## @param qualified The qualified-name identity to select (as published in `Candidate.qualified`).
## @return The subset of `cands` whose `qualified_name_of` equals `qualified`; empty when none does.
## @version 1
## @req REQ-DDB-QUERY-010
def matching_identity(
    name: str, cands: list[tuple[int, str, str, int | None, bool]], qualified: str
) -> list[tuple[int, str, str, int | None, bool]]:
    """THE DISAMBIGUATOR gh#37 IS ABOUT, and the reason it is a QUALIFIED NAME
    rather than the `file` substring `Candidate` used to promise or the `rowid` it
    already carried.

    Against `rowid`: a rowid is a sqlite row number that a rebuild reassigns, so a
    model that read `candidates`, reasoned, and re-queried after an intervening
    `build_or_refresh` would silently address a DIFFERENT function. It is also the
    one field on the payload that means nothing outside this database.

    Against a `file` substring: it cannot separate two same-named identities in ONE
    file, which is the ordinary Python shape (two classes in a module, a method and
    a module-level helper) and the exact case gh#26 was filed about. It would have
    resolved gh#37's motivating example and failed the general one.

    For the qualified name: it is ALREADY the identity key. `qualified_name_of` is
    what gh#26 chose to decide which memberdef rows are the same function, so
    selecting on it means a disambiguated call gets the same identity the edge
    attribution and thread membership already use — one rule, three surfaces, no
    second definition of "same function" to drift. It survives a rebuild, and it is
    published verbatim on every `Candidate`, so a consumer constructs it by copying
    a string rather than by parsing a signature.

    WHAT IT DELIBERATELY CANNOT SELECT: genuine overloads. `Owner::run(int)` and
    `Owner::run(double)` share a qualified name and `identity_rowids` unions them by
    design — keying on `argsstring` too would split a declaration from its
    definition whenever a default argument differs. So this selects an IDENTITY, not
    a signature, and a caller wanting one arm of a same-class overload still has
    only `candidates` to read. That is a real boundary and it is stated on the tools.

    RETURNS EMPTY ON NO MATCH, never falls back to every row. A disambiguator that
    silently degrades to the bare-name union would be worse than none: the caller
    would believe it had narrowed the answer. A typo must read as "no such
    identity", which the accessors surface as their ordinary not-found envelope.

    @brief Select the candidate rows belonging to one qualified identity.
    @return The matching subset, possibly empty.
    @version 1
    """
    return [c for c in cands if qualified_name_of(name, c[1]) == qualified]


## @brief The capped, provenance-carrying Candidate list for one ambiguous name.
## @param conn Open connection.
## @param name Bare function name the rows were fetched by, needed to derive each row's identity.
## @param cands Raw rows from `function_candidates`.
## @return Up to MAX_CANDIDATES Candidate rows, each carrying its provenance and its qualified identity.
## @version 3
## @req REQ-DDB-QUERY-003
## @req REQ-DDB-QUERY-010
def candidate_rows(conn: sqlite3.Connection, name: str, cands: list[tuple]) -> list[Candidate]:
    """FOUR surfaces built this list by hand with the same comprehension —
    `resolve_symbol`, `dossier`, `source` and `chain_trace` — which is exactly the
    duplication that let gh#26's identity rule drift into two copies. Adding a
    provenance field would have meant editing four call sites and getting it wrong
    in one, so the comprehension moved here first. gh#37 then added a second field
    and this is why that was a one-line change.

    `name` is a REQUIRED argument rather than a defaulted one even though it is
    recoverable from nothing else here, because `qualified` is the field a consumer
    passes back and a silently-empty one would leave `candidates` advisory again —
    exactly gh#37's defect. A default would have let a call site forget it and still
    typecheck.

    Deliberately does NOT check `is_overloaded`; the caller decides whether an
    ambiguity exists, because `chain_trace` and `dossier` gate it differently.

    @brief Build the capped overload-candidate list.
    @return Candidate rows with provenance and identity.
    @version 3
    """
    from .models import (
        Candidate,
    )

    return [
        Candidate(
            rowid=c[0],
            signature=c[1],
            file=c[2],
            line_start=c[3],
            has_body=c[4],
            provenance=symbol_provenance(conn, c[0]),
            qualified=qualified_name_of(name, c[1]),
        )
        for c in cands[:MAX_CANDIDATES]
    ]


## @brief Whether this index records where its memberdef rows came from.
## @param conn Open connection.
## @return True when `memberdef` carries the provenance column.
## @version 1
## @req REQ-DDB-INDEX-004
def records_provenance(conn: sqlite3.Connection) -> bool:
    """False for an index built before build version 19, where the column does not
    exist AND every row is doxygen's by construction — so the honest answer to
    "which rows are parsed?" on such a database is "none", not an error.

    @brief Report whether symbol provenance is recorded.
    @return True when the column is present.
    @version 1
    """
    return has_columns(conn, "memberdef", SYMBOL_SOURCE_COLUMN)


## @brief The provenance a symbol row should REPORT, or None when it says nothing.
## @param conn Open connection.
## @param rowid memberdef rowid to describe.
## @return 'ast' for a parser-recovered row; None for a doxygen row or an index that predates the column.
## @version 2
## @req REQ-DDB-INDEX-004
def symbol_provenance(conn: sqlite3.Connection, rowid: int) -> str | None:
    """RETURNS None FOR A DOXYGEN ROW, deliberately, and this is the one design
    decision on this surface worth arguing with.

    `wire._absent` elides an empty field from every ROW, and the elision doctrine
    there is "a field is present only when it says something". Every symbol in a
    healthy index is doxygen's, so emitting a `'doxygen'` provenance on all of them
    would add ~24 B to a measured-135 B call row — an 18% inflation of the exact
    payload that module was written to shrink — to restate the norm. So the field
    is present exactly when the answer is surprising.

    The consequence a consumer must know, and which the tool descriptions state:
    an ABSENT provenance means doxygen documented this symbol. A provenance of
    'ast' means the tree-sitter parser recovered it from the source text because
    doxygen never emitted it, and it therefore has NO brief, NO documented
    parameters and NO `@req` tags — a preprocessor that skipped the code skipped
    its doc comment too. Reading an absent brief on such a row as "undocumented
    function" rather than "unparsed function" is the mistake this field prevents.

    @brief The provenance worth reporting for one symbol row.
    @return 'ast', or None when there is nothing to say.
    @version 2
    """
    if not records_provenance(conn):
        return None
    row = conn.execute(
        f"SELECT {SYMBOL_SOURCE_COLUMN} FROM memberdef WHERE rowid=?",
        (rowid,),
    ).fetchone()
    return SYMBOL_SOURCE_AST if row is not None and row[0] == SYMBOL_SOURCE_AST else None


## @brief The `ORDER BY` fragment that makes doxygen's own row win a name collapse.
## @param conn Open connection.
## @param alias Table alias the column is reached through.
## @return A comparison expression ordering doxygen rows first, or '' when unsupported.
## @version 2
## @req REQ-DDB-INDEX-004
def documented_first(conn: sqlite3.Connection, alias: str) -> str:
    """WHY A COLLAPSE MUST PREFER DOCUMENTATION. `search` collapses every
    same-named row to ONE, ordered definition-row-first. A parser-recovered
    row IS a definition row, so without this fragment it would outrank doxygen's
    documented header declaration for the same function — and mbedtls is full of
    exactly that shape: a public function documented in an indexed header and
    defined inside an unsatisfied `#if`. The recovered row would win the collapse
    and the brief would VANISH from a surface that used to carry it.

    That is a documentation REGRESSION caused by a change whose whole purpose is to
    add information, which makes it the failure mode worth naming: preferring the
    documented row keeps every pre-existing row byte-identical and lets recovery add
    only nodes for names doxygen did not know at all.

    Returns '' on an index that predates the column, so the caller's ORDER BY is
    unchanged rather than referencing a column that is not there.

    @brief ORDER BY fragment preferring doxygen-sourced rows.
    @return A comparison expression, or '' when provenance is not recorded.
    @version 2
    """
    if not records_provenance(conn):
        return ""
    return f"({alias}.{SYMBOL_SOURCE_COLUMN} = '{SYMBOL_SOURCE_DOXYGEN}') DESC, "


_IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


## @brief True when a qualified name occurs in a signature at identifier boundaries.
## @param definition Doxygen `definition` signature text.
## @param qualified Qualified name to look for (e.g. "LinkOwner::rx_loop").
## @return True when the name appears bounded by non-identifier characters.
## @version 2
## @dg_internal
def _qualified_match(definition: str, qualified: str) -> bool:
    """Boundary-checked containment: `CoLinkOwner::rx_loop` must NOT match a
    search for `LinkOwner::rx_loop`. Every occurrence is examined, because
    the first one may be a substring hit while a later one is genuine.
    """
    start = 0
    while True:
        idx = definition.find(qualified, start)
        if idx < 0:
            return False
        end = idx + len(qualified)
        before_ok = idx == 0 or definition[idx - 1] not in _IDENT_CHARS
        after_ok = end == len(definition) or definition[end] not in _IDENT_CHARS
        if before_ok and after_ok:
            return True
        start = idx + 1


## @brief EVERY memberdef rowid a name denotes, qualified or bare.
## @param conn Open connection.
## @param name Function name, optionally class-qualified ("Owner::run").
## @return All matching memberdef rowids, ascending; NO definition-preference (see body).
## @version 5
## @req REQ-DDB-QUERY-003
def rowids_for_name(conn: sqlite3.Connection, name: str) -> list[int]:
    """Resolve a name to ALL the functions it denotes, not just one.

    `resolve_rowid` deliberately collapses to a single canonical rowid, which
    is right for "show me this function" but wrong for membership questions:
    `thread_membership` is keyed per rowid, so asking one rowid answers for one
    function. Two failures followed on real C++ source — `thread_roster` emits QUALIFIED
    entry names (`LinkOwner::rx_loop`) that never match the unqualified
    `memberdef.name` at all, so 11 of 12 threads were unresolvable; and a bare
    ambiguous name (`run`, `tick_loop`) silently picked ONE of several real
    functions, dropping the rest.

    A qualified name is matched against the doxygen `definition` signature at
    identifier boundaries; a bare name matches `memberdef.name` directly.

    Deliberately NO definition-preference, unlike `resolve_rowid`. Measured on
    in practice: the rows carrying thread membership are usually DECLARATION rows,
    because a header-declared method has `file_id != bodyfile_id`. For
    `rx_loop` the two real thread entries (LinkOwner, SensorRuntime) are both
    declarations, while the sole definition row is an unrelated
    anonymous-namespace helper with no membership — so preferring definitions
    returned exactly the wrong rowid and answered "no threads". Filtering is
    the qualified-name check's job; a union question wants every candidate.

    @brief Resolve a (possibly qualified) name to every rowid it denotes.
    @return Ascending list of rowids; empty when the name is unknown.
    @version 4
    """
    if not table_exists(conn, "memberdef"):
        return []
    tail = name.rsplit("::", 1)[-1]
    rows = conn.execute(
        "SELECT rowid, COALESCE(definition,'') FROM memberdef WHERE name=? AND kind='function'",
        (tail,),
    ).fetchall()
    if "::" in name:
        rows = [r for r in rows if _qualified_match(r[1], name)]
    return sorted(r[0] for r in rows)


## @brief The QUALIFIED name a bare name + doxygen `definition` denotes.
## @param name Bare function name (`memberdef.name`).
## @param definition Doxygen `definition` text, shaped "<return-type tokens> <qualified name>".
## @return The qualified name, or `name` itself when no qualified form is identifiable.
## @version 1
## @req REQ-DDB-QUERY-003
def qualified_name_of(name: str, definition: str | None) -> str:
    """The IDENTITY key for a function (gh#26). doxygen puts the qualified name
    in the LAST whitespace-separated token of `definition` and the argument list
    in a separate `argsstring` column, so scanning tokens from the right for one
    whose tail is `name` at a `::` or `.` boundary yields
    `pkg.guidance._classify` or `LinkOwner::rx_loop` without parsing C++.

    Chosen over comparing the WHOLE `definition` string, which was measured to
    over-split real decl/def pairs on both public C/C++ targets: a declaration
    and its definition can differ by a macro attribute
    (`ATTRIBUTE_TARGET_POPCNT void fuzzer::TracePC::HandleCmp` vs
    `void fuzzer::TracePC::HandleCmp`) or an `inline`/`static` qualifier, which
    splits ONE function into two identities. Whole-signature equality yielded
    2,819 identities on entropic where the qualified name yields 2,694, and
    every one of the 122 differing names was a single function torn in half.
    This is the same failure the lock layer already suffered when a pointer
    sigil leaked into its scope string, so the key deliberately excludes the
    return type — the part that carries the sigil.

    Falls back to the bare `name` rather than inventing an identity: an operator,
    or a signature doxygen mis-parsed from a macro (one real entropic row reads
    `if((Val|Vals[Idx])< TwoIn32) fuzzer else fuzzer::TPC HandleCmp`), degrades
    to today's name-keyed behaviour instead of fabricating a distinct function.

    @brief Extract a function's qualified-name identity from its signature.
    @return Qualified name, else the bare name.
    @version 1
    """
    for token in reversed((definition or "").split()):
        if token == name:
            return token
        tail = len(token) - len(name) - 1
        if tail >= 0 and token.endswith(name) and token[tail] in ":.":
            return token
    return name


## @brief Every memberdef rowid belonging to the SAME function a name resolves to.
## @param conn Open connection.
## @param name Function name to resolve.
## @param qualified Optional identity selector, replacing the definition-preferring guess; see `matching_identity`.
## @return Ascending rowids of the canonical identity (decl + def rows of ONE function); empty when unknown.
## @version 2
## @req REQ-DDB-QUERY-003
## @req REQ-DDB-QUERY-010
def identity_rowids(conn: sqlite3.Connection, name: str, qualified: str | None = None) -> list[int]:
    """The seam gh#26 was missing. `resolve_rowid` picks ONE canonical rowid and
    `rowids_for_name` returns EVERY rowid the name denotes — including unrelated
    functions that merely share it. Neither is right for attributing edges: the
    first loses a function's declaration rows (doxygen emits one memberdef per
    documented header declaration, and edges attach to whichever row the layer
    saw), the second unions three unrelated `_classify` helpers into one node.

    This returns the middle thing: the rowids of the ONE function the name
    canonically resolves to, keyed by `qualified_name_of`. So a C++ function's
    decl/def pair stays together while `pkg.guidance._classify` and
    `pkg.scope._classify` become separate identities.

    Deliberately does NOT separate genuine overloads — `Owner::run(int)` and
    `Owner::run(double)` share a qualified name and remain one identity. Keying
    on `argsstring` too would split them, but default arguments legitimately
    differ between a declaration and its definition, which reintroduces exactly
    the over-split this key was chosen to avoid. Overloads stay served by
    `candidates`; see the module note in `symbols._direct_call_edges`.

    `qualified` REPLACES THE GUESS RATHER THAN FILTERING AFTER IT (gh#37). Without
    it the target identity is read off `cands[0]` — the definition-preferring row —
    which is a reasonable default and an arbitrary one when several identities share
    the bare name. Supplying it names the identity outright, so the union this
    returns is the one the caller picked instead of the one the ordering happened to
    put first. An unmatched selector yields `[]`, and every caller already treats an
    empty rowid list as "not found".

    @brief Resolve a name to the rowids of one function (decl + def), not one row.
    @return Ascending rowids of the canonical identity; empty when the name is unknown.
    @version 2
    """
    cands = function_candidates(conn, name)
    if not cands:
        return []
    target = qualified if qualified is not None else qualified_name_of(name, cands[0][1])
    return sorted(r for r, sig, _f, _ls, _hb in cands if qualified_name_of(name, sig) == target)


## @brief True when a name maps to more than one DISTINCT function signature.
## @return True if the same-named rows carry >1 distinct `definition` signature (a genuine overload, not mere decl/def duality).
## @version 1
## @req REQ-DDB-QUERY-003
def is_overloaded(candidates: list[tuple[int, str, str, int | None, bool]]) -> bool:
    """Distinguish a genuine overload from decl/def duality. A single function
    contributes multiple rows (one definition + one per documented header
    declaration) that all share ONE `definition` signature; those must NOT read
    as ambiguous. More than one DISTINCT signature means the bare name really
    does select among different functions.

    @brief Report whether same-named rows are a genuine overload.
    @version 1
    """
    return len({sig for _, sig, _, _, _ in candidates}) > 1


## @brief rowid→function name (DISTINCT-by-name is implicit: rowid is unique).
## @return The function name for the memberdef rowid, or None if absent.
## @version 1
## @req REQ-DDB-QUERY-003
def name_of(conn: sqlite3.Connection, rowid: int) -> str | None:
    """@brief Return the function name for a memberdef rowid, or None."""
    row = conn.execute(
        "SELECT name FROM memberdef WHERE rowid=?",
        (rowid,),
    ).fetchone()
    return row[0] if row else None


## @brief Strip doxygen's XML-ish markup from a description column.
## @return Plain text with XML-ish tags removed and whitespace runs collapsed.
## @version 1
## @req REQ-DDB-QUERY-003
def strip_xml(text: str | None) -> str:
    """@brief Collapse doxygen description markup to plain whitespace-run text."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


## @brief Extract the version value doxygen folded into detaileddescription.
## @return The version token from the detaileddescription, or '' when absent.
## @version 2
## @req REQ-DDB-QUERY-003
def extract_version(detail: str | None) -> str:
    """The words "at-version" are deliberately NOT written as a bare tag anywhere in
    this block. This function's job is to parse that tag, so naming it literally put
    three of them in one comment — doxygen would read each as a tag, and the guard
    correctly reported a duplicate. A doc comment about a tag must not contain the
    tag.

    @brief Pull the <simplesect kind="version"> value, or '' when absent.
    @version 2
    """
    m = re.search(r'<simplesect kind="version"><para>\s*([^\s<]+)', detail or "")
    return m.group(1) if m else ""


## @brief Coerce a 0/1/None integer column into a bool|None.
## @return None when the input is None (unknown), else the value's truthiness as a bool.
## @version 1
## @req REQ-DDB-QUERY-003
def to_bool(value: object) -> bool | None:
    """@brief None stays None (unknown); else the value's truthiness as bool."""
    return None if value is None else bool(value)


## @brief Liveness status for one function name ('' when unknown/absent).
## @return The symbol_liveness status string (e.g. 'live'/'orphan'), or '' when unknown or the table is absent.
## @version 1
## @req REQ-DDB-QUERY-003
def liveness_of(conn: sqlite3.Connection, name: str) -> str:
    """Return 'live'/'orphan' for a function (definition-preferring rowid),
    or '' when there is no symbol_liveness row (or the table is absent).

    @brief Look up one function's symbol-liveness status.
    @version 1
    """
    if not table_exists(conn, "symbol_liveness"):
        return ""
    rowid = resolve_rowid(conn, name)
    if rowid is None:
        return ""
    row = conn.execute(
        "SELECT status FROM symbol_liveness WHERE memberdef_rowid=?",
        (rowid,),
    ).fetchone()
    return row[0] if row else ""
