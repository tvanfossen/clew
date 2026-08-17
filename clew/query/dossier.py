# SPDX-License-Identifier: MIT
"""The composite per-function dossier.

Ports the retired walkthrough dossier composer
(identity/liveness/reqs/tests/callers/callees/
writes/reads) into dataclass form and ADDS the R1 fields: thread
membership, external-boundary terminus status, and the dispatch/thread
semantics that already ride on the KeyEdge builder. Returns a `Dossier`,
never HTML — R4 renders it.

THE ONE-SHOT (2026-08-11). It also carries the panels a model was measured
fetching separately straight afterwards — the bounded body excerpt, the critical
sections the function opens, the locks already held when it is called, and the
callee names that resolve to nothing in the index. `dossier` is the tool the
served guidance tells a model to call FIRST; every follow-up it provokes about
the symbol it just described is a cost the index pays and raw source reading does
not.

@brief Composite function dossier (identity + fan-out + R1 semantics + body/locks/externals).
@version 2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ._common import (
    DbSource,
    candidate_rows,
    connect,
    extract_version,
    function_candidates,
    identity_rowids,
    is_overloaded,
    strip_xml,
    symbol_provenance,
    table_exists,
)
from .externcalls import external_callees
from .kconfig import gates_covering
from .locks import locks_held_for_rowids, sections_for_rowids
from .macros import MACRO_KIND, macro_definitions_conn
from .models import BodyExcerpt, Dossier, ExternalCallee, MacroDef, ReqRef
from .source import DEFAULT_BODY_LINES, body_excerpt
from .symbols import (
    _call_edges,
    key_edges,
    overridden_by,
    overrides_of,
    threads_for_rowids,
)
from .traversal import termini_for


## @brief The prose a function's DOCUMENTED sibling row carries, if any.
## @param conn Open connection.
## @param fn Function name being described.
## @return (brief, version) from the identity's documented row, or ('', '') when none has prose.
## @version 1
## @req REQ-DDB-INDEX-004
def _sibling_prose(conn: sqlite3.Connection, fn: str) -> tuple[str, str]:
    """THE ONE PLACE gh#11 COULD HAVE LOST DOCUMENTATION, and did in its first cut.

    A public function documented in an indexed header and DEFINED inside an
    unsatisfied `#if` gives doxygen a declaration row with a brief and no body, and
    gives the parser a definition row with a body and no brief. Both are the same
    function — `qualified_name_of` keys them identically, so `identity_rowids`
    already unions them — but `function_candidates` orders body rows first, so the
    dossier's chosen row is the parser's, and reading the brief from that row alone
    reported a documented mbedtls function as having no documentation at all.

    So the prose is read from the identity's rows rather than from the chosen row:
    the FIRST sibling that actually carries a brief or a version wins. The chosen
    row still supplies the location, which is correct — the parser is the only thing
    that knows where the body is.

    This is why a `Dossier` may truthfully carry `provenance: 'ast'` AND a non-empty
    `brief`. It is not a contradiction: doxygen documented the declaration, the
    parser recovered the definition.

    @brief Read the brief/version from a function identity's documented row.
    @return (brief, version), each '' when no sibling carries one.
    @version 1
    """
    for rowid in identity_rowids(conn, fn):
        row = conn.execute(
            "SELECT briefdescription, detaileddescription FROM memberdef WHERE rowid=?",
            (rowid,),
        ).fetchone()
        brief, version = (strip_xml(row[0]), extract_version(row[1])) if row else ("", "")
        if brief or version:
            return brief, version
    return "", ""


## How much `@details` prose a dossier carries before it says it stopped.
##
## MEASURED RATHER THAN GUESSED, on mbedtls: 4,268 rows carry detail, averaging 1,052 characters,
## and 4,195 of them (98%) are under 6,000. A dossier describes ONE subject and already returns a
## full function body, so ~1 KB of prose is not the cost risk; the 14,804-character tail is.
_DETAIL_CAP = 4000

## What a truncated detail says, with the length it stopped at. NEVER a silent cut: this repo's
## standing rule is that a bounded answer must say what was dropped, because a silently truncated
## reply reads as a complete one — the failure mode that makes "covered everything" a lie.
_DETAIL_CUT = (
    "… [detail truncated at {cap} of {total} characters — read the declaration for the rest]"
)


## @brief Bound the detail prose, saying so when it is cut.
## @param text The stripped detail prose.
## @return The prose, or its first `_DETAIL_CAP` characters plus an explicit notice.
## @version 1
## @dg_internal
def _capped_detail(text: str) -> str:
    """@brief Cap detail prose with an explicit truncation notice.
    @return Possibly-truncated prose; never silently cut.
    @version 1
    """
    if len(text) <= _DETAIL_CAP:
        return text
    return text[:_DETAIL_CAP] + _DETAIL_CUT.format(cap=_DETAIL_CAP, total=len(text))


## @brief Fetch identity fields (name/signature/file/lines/brief/detail/version/static).
## @return A dict of the function's identity columns, or None if the rowid has no memberdef row.
## @version 3
## @dg_internal
def _identity(conn: sqlite3.Connection, rowid: int) -> dict | None:
    """@brief Read one function's identity columns (definition row already chosen).

    @version 2
    """
    row = conn.execute(
        "SELECT m.name, m.definition, m.argsstring, COALESCE(p.name,''), "
        "m.bodystart, m.bodyend, m.briefdescription, m.detaileddescription, "
        "m.kind, m.static FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
        "WHERE m.rowid=?",
        (rowid,),
    ).fetchone()
    if row is None:
        return None
    brief, version = strip_xml(row[6]), extract_version(row[7])
    ## THE DETAIL PROSE, which was fetched and thrown away. `row[7]` has always been selected and
    ## only `extract_version` read from it, so a function's `@details` text was in hand on every
    ## dossier and never returned. Measured on mbedtls 2026-08-14: the deprecation warning about
    ## reaching past `MBEDTLS_ALLOW_PRIVATE_ACCESS` lives in
    ## `mbedtls_ssl_handshake_step`'s detaileddescription, two graded Q2 marks turn on it, and the
    ## agent found it by grepping and then READING `include/mbedtls/ssl.h` — twice — because the
    ## dossier returned one sentence of brief.
    detail = _capped_detail(strip_xml(row[7]))
    if not brief and not version:
        # The chosen row has no prose. Fall back to a sibling declaration row of the
        # SAME function before concluding the function is undocumented — see
        # `_sibling_prose`. Guarded on emptiness so the common path costs no query.
        brief, version = _sibling_prose(conn, row[0])
    return {
        "name": row[0],
        "signature": f"{row[1] or ''}{row[2] or ''}",
        "file": row[3],
        "line_start": row[4],
        "line_end": row[5],
        "brief": brief,
        "detail": detail,
        "version": version,
        "kind": row[8],
        "static": bool(row[9]),
    }


## @brief Requirements (with titles) + covering tests for one function.
## @return A (ReqRef list, covering-test-name list) tuple; both empty when the req tables are absent or unmatched.
## @version 2
## @req REQ-DDB-QUERY-004
def _reqs_and_tests(conn: sqlite3.Connection, fn: str) -> tuple[list[ReqRef], list[str]]:
    """@brief Build the requirement refs + covering-test names for a function."""
    if not table_exists(conn, "req_edges"):
        return [], []
    reqs = [
        ReqRef(req_id=rid, title=title or "")
        for rid, title in conn.execute(
            "SELECT DISTINCT r.req_id, COALESCE(req.title,'') FROM req_edges r "
            "LEFT JOIN requirements req ON req.id = r.req_id "
            "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
            "WHERE m.name=? ORDER BY r.req_id",
            (fn,),
        )
    ]
    tests: list[str] = []
    if reqs and table_exists(conn, "req_test_edges"):
        tests = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT m.name FROM req_test_edges t "
                "JOIN memberdef m ON m.rowid = t.test_memberdef_rowid "
                "WHERE t.req_id IN (SELECT DISTINCT r2.req_id FROM req_edges r2 "
                "JOIN memberdef m2 ON m2.rowid = r2.memberdef_rowid WHERE m2.name=?) "
                "ORDER BY m.name",
                (fn,),
            )
        ]
    return reqs, tests


## @brief Liveness status for a resolved rowid ('' when unknown).
## @return The symbol_liveness status string for the rowid, or '' when unknown or the table is absent.
## @version 1
## @dg_internal
def _liveness(conn: sqlite3.Connection, rowid: int) -> str:
    """@brief Read one rowid's symbol_liveness status, or ''."""
    if not table_exists(conn, "symbol_liveness"):
        return ""
    row = conn.execute(
        "SELECT status FROM symbol_liveness WHERE memberdef_rowid=?",
        (rowid,),
    ).fetchone()
    return row[0] if row else ""


## @brief The body + external-callee panels, which both need the working tree.
## @param conn Open connection.
## @param rowid The resolved identity's canonical memberdef rowid.
## @param repo_root Working-tree root, or None to skip both panels.
## @param max_body_lines Cap on the body excerpt's line count.
## @return (body excerpt or None, ExternalCallee rows).
## @version 1
## @dg_internal
def _body_and_external(
    conn: sqlite3.Connection,
    rowid: int,
    repo_root: Path | str | None,
    max_body_lines: int,
) -> tuple[BodyExcerpt | None, list[ExternalCallee]]:
    """The two panels that read BYTES rather than rows, kept together because they
    share the same precondition and the same failure: without a working tree neither
    can be produced, and a caller holding only a database file must still get a
    dossier. `repo_root=None` is therefore a supported mode, not a degraded one — it
    is what the R2 library's own tests and any db-only consumer use.

    The external-callee walk reuses the body's OWN recorded extent rather than the
    excerpt's clipped one, so a body truncated for display still reports the calls
    below the cut. Getting that backwards would have made the truncation silently
    lose facts, which is the failure the `truncated` flag exists to prevent.

    @brief Build the body excerpt and the external-callee list.
    @version 1
    """
    if repo_root is None:
        return None, []
    body = body_excerpt(conn, rowid, repo_root, max_lines=max_body_lines)
    if body is None:
        return None, []
    externals = external_callees(
        conn, repo_root, body.file, body.start_line, body.start_line + body.total_lines - 1
    )
    return body, externals


## @brief A dossier whose subject is a MACRO rather than a function.
## @param macros Every definition site of the name, from `macro_definitions_conn`.
## @return A Dossier carrying the macro identity and an otherwise-empty function payload.
## @version 2
## @req REQ-DDB-QUERY-012
def _macro_dossier(macros: list[MacroDef]) -> Dossier:
    """gh#373. The name defines a macro and no function, so every function-shaped
    layer is EMPTY BY CONSTRUCTION rather than unmeasured: there is no body to
    excerpt, no liveness row, no thread membership, no caller and no callee, because
    all of those filter `kind='function'` and a `#define` is not one. `kind` says
    `'macro definition'` so a consumer can see that at a glance instead of reading an
    empty `callers` list as a finding.

    The FIRST site supplies the identity fields and `macros` carries all of them. The
    identity has to come from somewhere — a Dossier has one `file` and one `line` —
    and picking the first in file/line order is at least deterministic; the full set
    is one field away and the payload does not pretend otherwise. On the motivating
    case that ordering puts `library/common.h` first, which is the library-side
    definition and the one a reader wants, but that is luck and is not relied on.

    `signature` is spelled as the `#define` line rather than as a C declaration,
    because a macro has no type and rendering one would be an invention.

    `gated_by` HERE DESCRIBES THE FIRST SITE AND NOTHING ELSE, copied off that site rather
    than recomputed, so it means exactly what it means on a function dossier: the gates
    covering this record's own `file`:`line_start`. The per-site lists on `macros` are the
    complete answer — that is where the two branches of a conditional `#define` differ, and
    a dossier-level list could describe only one of them. Copying keeps the two consistent
    by construction; computing it again from the same position would be a second chance to
    disagree.

    @brief Build the macro-subject dossier from a name's definition sites.
    @version 2
    """
    first = macros[0]
    return Dossier(
        name=first.name,
        rowid=first.rowid,
        signature=f"#define {first.name}{first.params}",
        file=first.file,
        line_start=first.line,
        line_end=first.line,
        ## The first site that carries prose wins, exactly as `_sibling_prose` does for
        ## a decl/def pair: one of several `#define`s may be documented and the others
        ## bare, and reporting the chosen row's empty brief would call a documented
        ## macro undocumented.
        brief=next((m.brief for m in macros if m.brief), ""),
        version="",
        kind=MACRO_KIND,
        static=False,
        liveness="",
        macros=macros,
        gated_by=list(first.gated_by),
        gates_unplaceable=first.gates_unplaceable,
    )


## The disclosure a function-subject dossier carries when its identity may not be a function
## at all. SPELLED ONCE, and as a whole sentence rather than a flag: the measured failure was
## a reader acting on `kind: function` + `file: include/mbedtls/aes.h` and going to source,
## so what has to change is what that reader is told, not a boolean it would have to know to
## interpret.
##
## WHY DISCLOSURE AND NOT RE-RANKING. The structural rule available here — "a bodiless
## `kind='function'` row whose name is also `#define`d is a doxygen artefact of the macro
## appearing in a declarator" — FIRES ON A LEGITIMATE CASE, and the C standard library is
## built on it: a header that declares `int isalpha(int);` and also `#define isalpha(c) …`
## produces exactly this shape, as does any mbedtls-style `#define mbedtls_calloc calloc`
## beside a declaration of the same name. `function_candidates` prefers definition rows, so
## the chosen row is bodiless precisely when NO definition of that name is indexed — which
## is true of the artefact AND of every declared-but-not-defined function. A demotion would
## therefore replace a documented declaration's dossier with a macro payload on the ordinary
## case, which is the mistake this repo already made once by re-ranking a test fixture below
## a shipping type and had to withdraw.
##
## The note is safe where the demotion is not, because it is true in BOTH readings: the name
## really does denote a macro and a bodiless row, and it says so instead of choosing.
MACRO_COLLISION_NOTE = (
    "this identity's row has no body extent AND this name is #define'd — doxygen writes a "
    "kind='function' memberdef row for a macro appearing in a declarator (one per wrapped "
    "struct field), so the file and line above may describe such a row rather than a "
    "function definition; read `macros` for the definition sites and their gating branches"
)


## @brief The collision disclosure, when this function identity may be a macro artefact.
## @param macros The name's macro definition sites.
## @param line_start The chosen identity's recorded body start, or None when it has none.
## @return The note, or '' when the shape does not apply.
## @version 1
## @dg_internal
def _macro_collision(macros: list[MacroDef], line_start: int | None) -> str:
    """TWO DATABASE FACTS AND NO HEURISTIC. The name is `#define`d somewhere in this index,
    and the row this dossier chose records no body extent. Both are read off columns; neither
    inspects a signature, a path or any spelling, so there is nothing here for a repository's
    conventions to defeat.

    Empty for every ordinary function — a defined function has a body extent — and the MCP
    layer elides an empty one, so the common payload is unchanged.

    @brief Build the macro-collision note when both conditions hold.
    @return The note, or ''.
    @version 1
    """
    return MACRO_COLLISION_NOTE if macros and not line_start else ""


## @brief Assemble the full composite dossier for one function.
## @param db Path, str or open connection to a built index.
## @param fn Bare function name.
## @param qualified Optional identity from a prior `candidates.qualified`, selecting WHICH same-named function to describe.
## @param repo_root Working tree the index was built from; omit to skip the body and external-callee panels.
## @param max_body_lines Cap on the body excerpt (default `DEFAULT_BODY_LINES`).
## @return The populated Dossier, or None when `fn` resolves to no indexed function (or none of that identity).
## @version 11
## @req REQ-DDB-QUERY-004
## @req REQ-DDB-QUERY-009
## @req REQ-DDB-QUERY-010
def function_dossier(
    db: DbSource,
    fn: str,
    qualified: str | None = None,
    repo_root: Path | str | None = None,
    max_body_lines: int = DEFAULT_BODY_LINES,
) -> Dossier | None:
    """Build the complete `Dossier` for `fn`: identity, liveness, thread
    membership, terminus status, requirements + covering tests, and the
    call-graph + shared-key fan-out (both directions). None when `fn`
    resolves to no indexed function. When `fn` is a genuine overload the
    dossier describes the definition-preferring pick and lists the
    alternatives in `candidates` so the pick is never silently arbitrary.

    The neighbour lists are scoped to the resolved IDENTITY, not to the bare name
    (gh#26): a bare name that denotes several unrelated functions no longer
    reports the union of all their edges.

    `qualified` SAYS WHICH IDENTITY (gh#37). Without it the pick is the
    definition-preferring first row, which is arbitrary among namesakes; with it the
    caller names the one it read out of a previous `candidates` list, and the SAME
    string scopes the identity, the neighbour lists, the thread membership and both
    override directions — because it is the identity key those already use, not a
    second notion of sameness bolted alongside. Optional: the bare-name path is
    unchanged, and the vast majority of names are unique.

    Two halves it does NOT narrow, both pre-existing and both name-scoped in the
    layer beneath: `writes`/`reads` (`_key_edge_rows` joins on `memberdef.name`) and
    `requirements`/`covering_tests` (`_reqs_and_tests` matches `m.name=?`). Stated
    here rather than left to be discovered, since an argument that appears to narrow
    a whole payload and narrows most of it is how gh#37 happened in the first place.

    ONE CALL, NOT SEVEN. `repo_root` turns on the two panels that read the working
    tree — the bounded body excerpt and the unresolvable callee names — and the lock
    panels (`sections`, `locks_held`) come from the index unconditionally. The reason
    they live here rather than behind four more tools is measured: on one graded
    question a model called `dossier` twice and then made fifteen further calls, seven
    of them `source`, four of those only to discover which platform primitive a wrapper
    forwards to. Every one of those follow-ups asked about the symbol the dossier had
    just described.

    ALL FOUR ARE KEYED ON THE RESOLVED IDENTITY. The lock panels take
    `identity_rowids`, not `rowids_for_name` as the standalone `sections_in` /
    `locks_held_when` tools do, and the body takes the chosen ROWID rather than the
    name. This is not incidental: gh#26 means one bare name can denote three unrelated
    functions in a single module, and a payload that widened its own scope while
    reporting one identity would quote the wrong body under the right heading.

    @brief Build the composite Dossier for one function.
    @version 11
    """
    with connect(db) as conn:
        return _dossier_conn(conn, fn, qualified, repo_root, max_body_lines)


## @brief Assemble one dossier on an ALREADY-OPEN connection.
## @param conn Open connection to a built index.
## @param fn Bare function name.
## @param qualified Optional identity selector from a prior `candidates.qualified`.
## @param repo_root Working tree, or None to skip the body and external-callee panels.
## @param max_body_lines Cap on the body excerpt.
## @return The populated Dossier, or None when `fn` resolves to nothing.
## @version 5
## @req REQ-DDB-QUERY-004
## @dg_internal
def _dossier_conn(
    conn: sqlite3.Connection,
    fn: str,
    qualified: str | None,
    repo_root: Path | str | None,
    max_body_lines: int,
) -> Dossier | None:
    """SPLIT OUT SO A BATCH SHARES ONE CONNECTION, and for no other reason — the body
    below is `dossier`'s former body verbatim, so the single-symbol path is unchanged.

    The split is what makes `dossiers` cheap: five symbols used to mean five
    `connect()` calls, five sqlite opens and five sets of `table_exists` probes against
    the same file. One connection answers all of them.

    @brief Build one Dossier against an open connection.
    @return The Dossier, or None.
    @version 5
    """
    macros = macro_definitions_conn(conn, fn)
    cands = function_candidates(conn, fn, qualified)
    if not cands:
        ## gh#373. A name that defines a macro and no function used to return
        ## None — indistinguishable from "not indexed" — while the `#define`,
        ## its expansion and its file:line were all sitting in `memberdef`.
        ## Only on a BARE name: an unmatched `qualified` is a request for a
        ## specific function identity, and answering it with a macro would
        ## substitute a different symbol for the one that was asked for.
        return _macro_dossier(macros) if macros and qualified is None else None
    rowid = cands[0][0]
    ident = _identity(conn, rowid)
    if ident is None:
        return None
    reqs, tests = _reqs_and_tests(conn, ident["name"])
    termini = termini_for(conn, rowid)
    ids = identity_rowids(conn, fn, qualified)
    body, externals = _body_and_external(conn, rowid, repo_root, max_body_lines)
    ## Ambiguity is a property of the NAME, so it is measured over every same-named
    ## row: a narrowed dossier must still disclose that alternatives exist, or a
    ## consumer cannot tell a disambiguated answer from a unique one.
    all_cands = function_candidates(conn, fn) if qualified is not None else cands
    overloads = candidate_rows(conn, fn, all_cands) if is_overloaded(all_cands) else []
    ## The gates covering the DEFINITION line. `ident` carries the file and line doxygen
    ## recorded, which is the one position every function has — a body excerpt is optional
    ## (`repo_root` may be None) and a declaration in a header is gated separately from its
    ## definition, so keying off the body would make the field vanish exactly when a caller
    ## asked for the cheap payload.
    gates, unknown = gates_covering(conn, ident["file"], int(ident["line_start"] or 0))
    return Dossier(
        name=ident["name"],
        rowid=rowid,
        signature=ident["signature"],
        file=ident["file"],
        line_start=ident["line_start"],
        line_end=ident["line_end"],
        brief=ident["brief"],
        detail=ident["detail"],
        version=ident["version"],
        kind=ident["kind"],
        static=ident["static"],
        liveness=_liveness(conn, rowid),
        provenance=symbol_provenance(conn, rowid),
        candidates=overloads,
        # Membership is per-rowid, and doxygen splits one function across a
        # declaration row and a definition row — so asking only the chosen
        # rowid reports no thread whenever membership landed on the sibling.
        # Union across the decl/def pair of THIS function; a same-named
        # function in another module or on another class is excluded.
        #
        # gh#26: this used to compare whole `definition` signatures inline. It
        # is now the SHARED `identity_rowids` helper, for two reasons. DRY —
        # the call-edge surface needs the same rule, and two copies of an
        # identity rule in one package is the drift condition that produced
        # gh#26 in the first place. And correctness — whole-signature
        # equality over-splits a single function whose declaration and
        # definition differ by a macro attribute or an inline/static
        # qualifier, measured at 122 such names on entropic and 13 on
        # mbedtls, where the qualified-name key splits none.
        threads=threads_for_rowids(conn, ids),
        is_terminus=bool(termini),
        termini=termini,
        requirements=reqs,
        covering_tests=tests,
        callers=_call_edges(conn, ident["name"], want_callers=True, qualified=qualified),
        callees=_call_edges(conn, ident["name"], want_callers=False, qualified=qualified),
        writes=key_edges(conn, ident["name"], as_writer=True),
        reads=key_edges(conn, ident["name"], as_writer=False),
        # gh#8. doxygen's own `reimplements` relation was populated and read by
        # nothing outside `dispatch_edges.py`, so a consumer could not ask the
        # question C++ polymorphism makes unavoidable -- what runs when this
        # dispatches. Both directions, because they answer different questions: what
        # this replaces when called through a base pointer, and what may run instead
        # of it. Resolved through the IDENTITY like the neighbour lists, so the
        # decl/def duality cannot lose the relation and a bare name shared by two
        # unrelated functions cannot fabricate one.
        overrides=overrides_of(conn, fn, qualified),
        overridden_by=overridden_by(conn, fn, qualified),
        body=body,
        # `sections` is what this function LOCKS; `locks_held` is what is ALREADY
        # locked when it runs. Two different questions with two different join
        # directions (holder_rowid vs critical_section_calls.callee_rowid), which is
        # why they are two fields and not one merged "locks" list.
        sections=sections_for_rowids(conn, ids),
        locks_held=locks_held_for_rowids(conn, ids),
        external_callees=externals,
        # gh#373. Reported even though the SUBJECT here is a function, because on
        # the case that motivated this the two collide: doxygen writes a
        # `kind='function'` memberdef row for every struct field wrapped in
        # `MBEDTLS_PRIVATE(...)`, so ~2,000 member rows share the macro's name and
        # `function_candidates` picks one of them. A macro path conditioned on
        # "no function of this name" would therefore have stayed dark on exactly
        # the symbol it was built for. Empty for every ordinary function, and
        # elided on the wire, so the common payload is unchanged.
        macros=macros,
        # gh#403. The identity above may not be a function at all, and on the one symbol
        # that motivated the macro panel it is not: `MBEDTLS_PRIVATE` resolves to a struct
        # FIELD row in `include/mbedtls/aes.h` with no line, one of ~2,000 doxygen writes
        # for the macro appearing in a declarator. The graded run measured a reader acting
        # on that headline and going to source eight to nine times per run. Re-ranking was
        # refused for the reason `MACRO_COLLISION_NOTE` records: the only structural rule
        # available fires on a legitimate declared-but-undefined function whose name is
        # also a macro, which is a C idiom rather than an edge case.
        macro_collision=_macro_collision(macros, ident["line_start"]),
        # THE PRECONDITION OF THE ANSWER, ON THE ROW rather than in an inventory. Both graded
        # questions on this project's matrix ask "is this compiled in, and under what flag" —
        # `grep mbedtls_mutex_lock` finds the text and cannot tell you it sits behind a flag
        # that is off by default. The configuration space could already say which lines a
        # SYMBOL gates; nothing could say which gates cover THIS function, which is the
        # direction a real question arrives from.
        #
        # A FIELD, NEVER A TOOL. The surface is adjacency: a lock, a shared key and a gate are
        # all things that hold of a function, and one tool per relation is what 19 tools
        # taught. Empty for an ungated function and elided on the wire, so the common payload
        # does not change.
        gated_by=list(gates),
        gates_unplaceable=unknown,
    )


## The most symbols one `dossiers` call will answer for. A REFUSAL, never a silent
## truncation of the list: a batch that quietly answered for the first eight of twelve
## names would report `count: 8` beside a request for twelve, and a model that did not
## re-count would conclude the missing four are not indexed. That is the same
## silent-degradation failure the `_limited` disclosure exists to prevent, one level up.
##
## EIGHT, because the response budget is what bounds it. The three measured Q1 runs each
## dossiered exactly five distinct symbols, so eight leaves headroom over the observed
## demand; past that each symbol's fair share of the 32,768-byte cap falls under ~4 KB,
## which is thinner than one dossier's identity block plus a usable body excerpt. A cap
## that returns eight useful dossiers beats one that returns twenty unreadable ones.
MAX_BATCH_SYMBOLS = 8


## @brief Assemble dossiers for several functions over ONE connection.
## @param db Path, str or open connection to a built index.
## @param fns Bare function names, in the order the caller asked for them.
## @param repo_root Working tree the index was built from; omit to skip the body and external-callee panels.
## @param max_body_lines Cap on each body excerpt.
## @return One entry per requested name, positionally aligned, None where a name resolves to nothing.
## @version 1
## @req REQ-DDB-QUERY-004
## @req REQ-DDB-QUERY-009
def function_dossiers(
    db: DbSource,
    fns: list[str],
    repo_root: Path | str | None = None,
    max_body_lines: int = DEFAULT_BODY_LINES,
) -> list[Dossier | None]:
    """FOUR TO SIX SEPARATE CALLS, MEASURED. Across three graded mbedtls runs of one
    question the model called `dossier` five times each, one symbol per call, and each
    call cost a whole model turn — the transcripts differ in almost every other respect
    and agree on that. Per-call cost was already below the source arm's; the remaining
    gap was entirely VOLUME, and a batch is the one change that removes turns rather
    than bytes.

    POSITIONAL, INCLUDING THE MISSES. A name that resolves to nothing yields `None` in
    its own slot rather than being dropped, so `len(result) == len(fns)` always holds
    and the caller can pair a miss with the name that caused it. Dropping misses would
    make one unresolvable name silently re-label every dossier after it.

    NO `qualified` HERE, deliberately. It selects ONE identity among namesakes, so it
    has no meaning against a list — a single `qualified` cannot say which of five
    symbols it disambiguates, and a parallel list of them would be a second positional
    correspondence to get wrong. A caller that needs disambiguation calls `dossier` for
    that one symbol; the MCP layer refuses the combination rather than ignoring it.

    Duplicates are NOT removed here. The R2 contract is positional and a caller asking
    twice gets two answers; de-duplication is a wire-economy concern and belongs to the
    surface that has a byte budget.

    @brief Build dossiers for several functions in one pass.
    @return One Dossier-or-None per requested name, in request order.
    @version 1
    """
    with connect(db) as conn:
        return [_dossier_conn(conn, fn, None, repo_root, max_body_lines) for fn in fns]
