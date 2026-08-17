# SPDX-License-Identifier: MIT
"""R2 accessor over the preprocessor-definition rows doxygen already writes.

gh#373. `memberdef` carries a `kind='macro definition'` row per `#define`, with
the expansion in `initializer` and the parameter list in `argsstring`. Every
other query surface in this package filters `kind='function'` — deliberately and
correctly, since a macro has no body, no callers, no thread membership and no
liveness — with the effect that the macro layer was indexed and unreachable.

That is not a hypothetical. mbedtls's Q2 acceptance question is ABOUT a macro
(`MBEDTLS_PRIVATE`), and the graded run measured what happens: `search` for the
gating macro `MBEDTLS_ALLOW_PRIVATE_ACCESS` returned a definitive-sounding zero
while three rows for it were in `memberdef`, and `dossier('MBEDTLS_PRIVATE')`
answered about a STRUCT MEMBER, because doxygen records each wrapped field as
`int mbedtls_aes_context::MBEDTLS_PRIVATE(nr)` with `kind='function'` — 2,000-odd
rows that shadow the one macro row the caller wanted.

So the macro path CANNOT be a fallback for "the name resolves to no function".
On the one name that motivated it, the name DOES resolve to a function. Macros
are looked up independently and reported alongside.

@brief Preprocessor-definition lookup: expansion, parameters, definition sites.
@version 1
"""

from __future__ import annotations

import sqlite3

from ._common import DbSource, connect, has_columns, strip_xml, symbol_provenance, table_exists
from .kconfig import gates_covering
from .models import MacroDef

## The `memberdef.kind` doxygen writes for a `#define`. Spelled once: it is a
## doxygen vocabulary string, not ours, and a second literal copy is the drift that
## silently empties one caller while the other keeps working.
MACRO_KIND = "macro definition"

## Cap on the cross-reference names carried per definition site. A widely-used
## macro can be referenced from hundreds of bodies, and this rides inside a dossier
## that is already budgeted; the point of the field is "here is who reaches for it",
## which a sample answers and an exhaustive list does not.
MAX_MACRO_REFERENCES = 20


## @brief Names doxygen recorded as referencing one macro-definition row.
## @param conn Open connection.
## @param rowid The macro definition's memberdef rowid.
## @return Up to MAX_MACRO_REFERENCES referencing symbol names, alphabetical.
## @version 1
## @dg_internal
def _referenced_by(conn: sqlite3.Connection, rowid: int) -> tuple[str, ...]:
    """EMPTY IS THE COMMON CASE AND IT IS NOT "UNUSED". doxygen writes an `xrefs`
    row when it sees a reference from inside a documented BODY, so a macro used in
    struct declarations, in `#if` conditions or in another macro's expansion has
    none. Measured on mbedtls: 871 of 2,504 macro rows have an inbound reference,
    and `MBEDTLS_PRIVATE` — used ~2,000 times, in declarations — has zero.

    The field is still worth carrying for the 871, and the docstring on `MacroDef`
    says plainly what an empty one means, so a consumer cannot read it as a measured
    negative. That disclosure is the whole reason this is not silently omitted.

    @brief List the symbols doxygen recorded referencing this macro.
    @return Referencing names, capped and alphabetical.
    @version 1
    """
    if not table_exists(conn, "xrefs"):
        return ()
    rows = conn.execute(
        "SELECT DISTINCT s.name FROM xrefs x JOIN memberdef s ON s.rowid = x.src_rowid "
        "WHERE x.dst_rowid=? ORDER BY s.name LIMIT ?",
        (rowid, MAX_MACRO_REFERENCES),
    ).fetchall()
    return tuple(r[0] for r in rows)


## @brief The parameter list of one function-like macro, as it is written.
## @param conn Open connection.
## @param rowid The macro definition's memberdef rowid.
## @return `(a, b)` for a function-like macro; '' when doxygen recorded no parameters.
## @version 1
## @dg_internal
def _macro_params(conn: sqlite3.Connection, rowid: int) -> str:
    """NOT `memberdef.argsstring`, which is NULL on every macro row — that column
    holds a FUNCTION's argument text and a `#define`'s parameters go to the `param`
    table instead. Reading `argsstring` is the obvious first guess and it silently
    returns nothing, which reports every function-like macro as object-like.

    READS `defname` AND NOTHING ELSE, deliberately. doxygen's sqlite3 generator
    de-duplicates `param` rows with a loose match that treats a NULL field as
    matching any value, so a macro's one-field parameter row can be UNIFIED with an
    unrelated function parameter that happens to share its `defname` — measured here:
    `MBEDTLS_PRIVATE`'s `member` came back carrying `type='unsigned char'`,
    `declname='mac'`, `array='[16]'` from some function's buffer argument. The
    `defname` is the macro's own and is correct; every other column on that row may
    belong to a different symbol. Rendering the type would print a fabricated
    signature with total confidence.

    @brief Read a macro's parameter names in declaration order.
    @return Parenthesised parameter list, or ''.
    @version 1
    """
    if not table_exists(conn, "memberdef_param") or not table_exists(conn, "param"):
        return ""
    names = [
        r[0]
        for r in conn.execute(
            "SELECT COALESCE(p.defname, p.declname, '') FROM memberdef_param mp "
            "JOIN param p ON p.rowid = mp.param_id WHERE mp.memberdef_id=? ORDER BY mp.rowid",
            (rowid,),
        )
    ]
    return f"({', '.join(names)})" if names else ""


## @brief Every `#define` of one name, with expansion, parameters, location and gating branch.
## @param conn Open connection.
## @param name Bare macro name.
## @return One MacroDef per definition site, ordered by file then line; empty when the name defines no macro.
## @version 2
## @req REQ-DDB-QUERY-012
def macro_definitions_conn(conn: sqlite3.Connection, name: str) -> list[MacroDef]:
    """ONE ROW PER SITE. A conditionally redefined macro genuinely has several, and
    on the motivating case the several ARE the answer:
    `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined in `library/common.h` and in two
    `programs/ssl/` mains, which is precisely how the library sees the plain field
    names while an application sees the `private_`-prefixed ones. A collapse to one
    row would have deleted the only fact the question was asking for.

    EACH SITE CARRIES THE GATES COVERING ITS OWN LINE (gh#403), which is what turns two
    disagreeing expansions into an answer. `MBEDTLS_PRIVATE` has two sites eleven columns
    apart in one file: line 15 comes back under `[ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS]`
    and line 17 under `[ifdef …]`, so the payload states which translation unit gets which
    spelling instead of leaving a reader to infer it from two rows that contradict.

    Attached PER ROW rather than once for the name, because the sites are in different
    branches and often in different files — a single list could only describe one of them,
    and would describe the others wrongly with complete confidence.

    Takes an open connection so a caller already inside a `with connect(...)` block
    — `dossier` is the one that matters — does not open a second one per call.
    `macro_definitions` is the standalone wrapper.

    @brief List every definition site of a macro name, each with its gating branch.
    @return MacroDef rows, file/line ordered.
    @version 2
    """
    ## Column-level, not table-level. `initializer` and `line` are doxygen's own
    ## columns and a current build always has them, but a database this consumer was
    ## merely POINTED AT may not — and a query layer that raises a raw
    ## `OperationalError` on a partial schema is the failure `has_columns` exists to
    ## prevent. Both are required together: without `initializer` there is no
    ## expansion, which is the entire reason to ask.
    if not has_columns(conn, "memberdef", "kind", "line", "initializer", "briefdescription"):
        return []
    rows = conn.execute(
        "SELECT m.rowid, m.name, COALESCE(p.name,''), m.line, "
        "COALESCE(m.initializer,''), COALESCE(m.briefdescription,'') "
        "FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
        "WHERE m.name=? AND m.kind=? ORDER BY COALESCE(p.name,''), m.line",
        (name, MACRO_KIND),
    ).fetchall()
    return [_macro_def(conn, row) for row in rows]


## @brief Build one MacroDef from a selected row, adding its parameters and gates.
## @param conn Open connection.
## @param row (rowid, name, file, line, expansion, briefdescription) as selected above.
## @return The populated MacroDef.
## @version 1
## @dg_internal
def _macro_def(conn: sqlite3.Connection, row: tuple) -> MacroDef:
    """Split out of `macro_definitions_conn` so the per-site enrichment — parameters,
    cross-references, provenance and gates, four queries against three tables — is not a
    comprehension the reader has to unpick, and so the SELECT list stays adjacent to the
    positional indices it feeds.

    `gates_covering` is called with the site's OWN file and line. A macro whose `line` is
    NULL (an index that recorded no position) is passed 0, which no gate extent covers, so
    it comes back ungated rather than borrowing the first gate in the file.

    @brief Assemble one macro definition site.
    @return MacroDef.
    @version 1
    """
    gates, unplaceable = gates_covering(conn, row[2], int(row[3] or 0))
    return MacroDef(
        name=row[1],
        rowid=row[0],
        file=row[2],
        line=row[3],
        params=_macro_params(conn, row[0]),
        expansion=row[4],
        brief=strip_xml(row[5]),
        referenced_by=_referenced_by(conn, row[0]),
        provenance=symbol_provenance(conn, row[0]),
        gated_by=gates,
        gates_unplaceable=unplaceable,
    )


## @brief Every `#define` of one name, opening the database itself.
## @param db Path, str or open connection to a built index.
## @param name Bare macro name.
## @return One MacroDef per definition site; empty when the name defines no macro.
## @version 1
## @req REQ-DDB-QUERY-012
def macro_definitions(db: DbSource, name: str) -> list[MacroDef]:
    """@brief Look up a macro's definition sites from a database source.
    @return MacroDef rows, file/line ordered.
    @version 1
    """
    with connect(db) as conn:
        return macro_definitions_conn(conn, name)
