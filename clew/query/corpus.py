# SPDX-License-Identifier: MIT
"""Repo-shape queries: the file corpus, the prose corpus, and compounds.

These answer "what IS this repo" rather than "what does this function do":
`list_files` (the indexed file inventory), `search_prose` (full-text over the
ingested markdown), `lookup_class` (a class/struct with its members and
immediate hierarchy), `file_doc_rows` (the file-level documentation `search`
matches over, gh#10) and `index_scope` (the shape and provenance of the
indexed file set, which is what an EMPTY answer has to name — gh#21).

Two noise sources are handled here, and neither is a hardcoded repo
convention: doxygen synthesises a single `[STL]` path row for everything it
pulls out of system headers, and it registers hundreds of `std::` compounds
against that row. `[STL]` is therefore excluded from the file inventory and
demoted (never dropped — a caller may genuinely ask about `std::vector`)
when ranking class candidates.

@brief File inventory, prose full-text search, class lookup, file docs and scope.
@version 2
"""

from __future__ import annotations

import fnmatch
import re
import sqlite3

from ..vocabulary import EXTERNAL_ROOT_COLUMN
from ._common import MAX_CANDIDATES, DbSource, connect, has_columns, strip_xml, table_exists
from .models import (
    ClassCandidate,
    ClassEntry,
    ClassMember,
    DirectoryEntry,
    DirectoryInventory,
    FileEntry,
    IndexScope,
    ProseHit,
    ProseSearch,
)

# Doxygen's synthetic path row for symbols harvested from system headers.
# It brackets every synthetic marker the same way ('[STL]', '[generated]'),
# so the shape — not any one literal — is what gets filtered.
SYNTHETIC_PATH = re.compile(r"^\[.*\]$")
PATH_TYPE_FILE = 1
CLASS_KINDS = ("class", "struct", "union", "interface")


## @brief Whether a repo-relative path matches a `*`-glob pattern.
## @param path Repo-relative path from the `path` table.
## @param pattern fnmatch pattern; matched against the full path and the basename.
## @return True when either the whole path or its basename matches.
## @version 1
## @dg_internal
def _matches(path: str, pattern: str) -> bool:
    """Match the FULL repo-relative path first (so `app/src/*` and `*.cpp`
    both work), then fall back to the basename (so a bare `Battery*` finds a
    nested file). Case-sensitive, like the paths themselves.

    @brief Glob-match a path or its basename.
    @return Whether the pattern matches.
    @version 1
    """
    return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(
        path.rsplit("/", 1)[-1], pattern
    )


## @brief Collapse whitespace runs in a prose snippet (markup is NOT stripped).
## @param text Snippet text from FTS5.
## @return Single-spaced text.
## @version 1
## @dg_internal
def _collapse(text: str | None) -> str:
    """Prose is markdown, not doxygen markup: a `<stdio.h>` or a generic
    `<T>` inside a documentation snippet is CONTENT, so only whitespace runs
    (the newlines a multi-line chunk carries) are collapsed here — deliberately
    not `strip_xml`, which would delete it.

    @brief Whitespace-collapse a prose snippet.
    @return Single-spaced snippet text.
    @version 1
    """
    return re.sub(r"\s+", " ", text or "").strip()


## @brief The indexed source files, with documented-symbol counts.
## @param db Database path or open connection.
## @param pattern Optional `*`-glob filter (full path or basename).
## @return List of FileEntry in path order; the synthetic '[STL]' row is never included.
## @version 2
## @req REQ-DDB-QUERY-001
def list_files(db: DbSource, pattern: str | None = None) -> list[FileEntry]:
    """Inventory every real source file the database knows about, with the
    number of distinct documented symbols located in it, and which nested git tree
    owns it. Excludes doxygen's synthetic `[STL]` entry and directory rows.

    EXTERNAL FILES ARE LISTED, ANNOTATED, NEVER FILTERED (gh#335). The tag exists so
    that AGGREGATES can report first party by default; an inventory is not an
    aggregate, and a `list_files` that quietly omitted a submodule would be the exact
    failure the emptiness notes exist to prevent — an answer that is short because it
    was filtered, presented as an answer that is short because the repo is.

    @brief List indexed files (optionally glob-filtered) with symbol counts.
    @return List of FileEntry.
    @version 2
    """
    with connect(db) as conn:
        ## A LITERAL, NOT A QUALIFIED NAME, on an index predating the tag: `p.''` is
        ## a syntax error, so the absent-column branch has to substitute the whole
        ## select expression rather than the column name inside it.
        owner = (
            f"p.{EXTERNAL_ROOT_COLUMN}" if has_columns(conn, "path", EXTERNAL_ROOT_COLUMN) else "''"
        )
        rows = conn.execute(
            f"SELECT p.name, COUNT(DISTINCT m.name), {owner} FROM path p "
            "LEFT JOIN memberdef m ON m.file_id = p.rowid "
            "WHERE p.type = ? AND p.name <> '' "
            "GROUP BY p.rowid ORDER BY p.name",
            (PATH_TYPE_FILE,),
        ).fetchall()
    return [
        FileEntry(path=name, symbol_count=count, external_root=owner_root or "")
        for name, count, owner_root in rows
        if not SYNTHETIC_PATH.match(name) and (pattern is None or _matches(name, pattern))
    ]


## @brief File-level documentation rows matching EVERY token, or [] when unindexed.
## @param conn Open connection.
## @param tokens Lower-cased query tokens; all must appear in the path or the documentation.
## @return List of (repo-relative path, documentation) pairs in path order.
## @version 2
## @req REQ-DDB-QUERY-007
def file_doc_rows(conn: sqlite3.Connection, tokens: list[str]) -> list[tuple[str, str]]:
    """The gh#10 half of `search`: a module docstring or a file-level `@file`
    comment is a searchable unit, and the FILE is the hit.

    Deliberately NOT an FTS5 query even though the same text is also in
    `supplementary_docs`. `search` promises a CONJUNCTION over tokens with its own
    ranking, and reusing FTS5 here would give one tool two different matching
    semantics depending on which half of it answered — the sort of split that
    makes a result impossible to reason about. `file_docs` is one row per file, so
    a LIKE scan over it is cheap.

    An older index has no `file_docs` table; [] is the honest answer and the
    caller's note says the corpus was absent rather than that nothing matched.

    @brief Match file-level documentation against all query tokens.
    @return List of (path, documentation) pairs.
    @version 2
    """
    if not tokens or not table_exists(conn, "file_docs"):
        return []
    clause = " AND ".join(["(LOWER(file_path) LIKE ? OR LOWER(doc) LIKE ?)"] * len(tokens))
    params: list[str] = []
    for token in tokens:
        params += [f"%{token}%", f"%{token}%"]
    return conn.execute(
        f"SELECT file_path, doc FROM file_docs WHERE {clause} ORDER BY file_path",
        params,
    ).fetchall()


## @brief Member documentation rows matching EVERY token, or [] when unavailable.
## @param conn Open connection.
## @param tokens Lower-cased query tokens; all must appear in the name or either description.
## @param limit Maximum rows to return.
## @return List of (repo-relative path, symbol name, documentation) triples.
## @version 1
## @req REQ-DDB-QUERY-007
def member_doc_rows(
    conn: sqlite3.Connection, tokens: list[str], limit: int = 10
) -> list[tuple[str, str, str]]:
    """gh#404 — THE PROSE THAT ANSWERS "WHY" AND WAS NEVER SEARCHED. The prose corpus is
    markdown plus FILE-level doc comments. A doc comment attached to a MEMBER — a macro, a
    function, a field — went nowhere, and that is where C libraries put their explanations.

    MEASURED ON MBEDTLS: `search_prose("MBEDTLS_ALLOW_PRIVATE_ACCESS")` returned zero and called
    it definitive, while `memberdef.detaileddescription` held the paragraph "Although structs
    defined in header files are publicly available, their members are private and should not be
    accessed by the user" — which is verbatim the answer to a graded question. The text was
    already stored; nothing needed harvesting. A benchmark cell was told the miss was definitive
    and ran three greps to find what the index was holding.

    A LIKE SCAN, NOT FTS5, for exactly the reason `file_doc_rows` gives one line up: `search`
    promises a conjunction over tokens, and answering half a corpus with bm25 and the other half
    with a conjunction gives one tool two matching semantics depending on which half replied.

    GUARDED ON COLUMNS, not only on the table. The description columns are part of doxygen's
    schema but this repo's own minimal test indexes omit them, and `has_columns` is the
    graceful-degradation contract that keeps a thin database answering thinly rather than raising.

    LIMITED, because unlike `file_docs` this is one row per SYMBOL — mbedtls has 10,652 — and an
    unbounded prose reply is the payload this surface budgets elsewhere.

    @brief Match member documentation against all query tokens.
    @return List of (path, name, documentation) triples.
    @version 1
    """
    if not tokens or not table_exists(conn, "memberdef"):
        return []
    columns = [
        c for c in ("briefdescription", "detaileddescription") if has_columns(conn, "memberdef", c)
    ]
    if not columns:
        return []
    doc = "COALESCE(" + ", ".join(f"NULLIF(m.{c},'')" for c in columns) + ", '')"
    ## The token must appear in the symbol's NAME or in its documentation. Including the name is
    ## what makes `search_prose("MBEDTLS_ALLOW_PRIVATE_ACCESS")` reach the macro whose comment
    ## explains it, since the flag is named in the `#if` and described in the prose beside it.
    term = f"(LOWER(m.name) LIKE ? OR LOWER({doc}) LIKE ?)"
    clause = " AND ".join([term] * len(tokens))
    params: list[str] = []
    for token in tokens:
        params += [f"%{token}%", f"%{token}%"]
    return conn.execute(
        f"SELECT COALESCE(p.name,''), m.name, {doc} FROM memberdef m "  # noqa: S608
        f"LEFT JOIN path p ON p.rowid = m.file_id "
        f"WHERE {clause} AND {doc} != '' ORDER BY LENGTH({doc}) DESC, m.name LIMIT ?",
        [*params, max(1, limit)],
    ).fetchall()


## @brief Whether this index carries an ingested markdown corpus at all.
## @param db Database path or open connection.
## @return True when the `supplementary_docs` FTS5 table exists.
## @version 1
## @req REQ-DDB-QUERY-007
def has_prose_corpus(db: DbSource) -> bool:
    """The prose counterpart of `has_file_docs`, and it exists for the identical reason one corpus
    over: an empty prose reply must be able to distinguish "the documentation was read and does not
    say this" from "this index has no documentation to read". Only the first is a fact about the
    repository; the second is a fact about the build, and the caller's cue is to rebuild.

    Without it the prose corpus asserted the strong "definitive empty result" wording in both
    cases — measured on mbedtls, about a token the same index held in three `memberdef` rows.

    @brief Report presence of the ingested markdown corpus.
    @return Whether `supplementary_docs` exists.
    @version 1
    """
    with connect(db) as conn:
        return table_exists(conn, "supplementary_docs")


## @brief Whether this index carries a file-level documentation corpus at all.
## @param db Database path or open connection.
## @return True when the `file_docs` table exists.
## @version 1
## @req REQ-DDB-QUERY-007
def has_file_docs(db: DbSource) -> bool:
    """Exists so an empty `search` can distinguish "the documentation was searched
    and does not contain this" from "there is no documentation corpus in this
    index". Those are different claims and the second one is the caller's cue to
    rebuild, not to give up.

    @brief Report presence of the file-level documentation corpus.
    @return Whether `file_docs` exists.
    @version 1
    """
    with connect(db) as conn:
        return table_exists(conn, "file_docs")


## A `has_gate_layer` helper lived here for gh#393 and is deliberately gone with the
## verdict change it existed to serve. `graph_stats.layer_states` already reports a layer as
## `absent` / `empty` / `populated`, so a second reader of the same fact would be a
## duplicated source of truth on a distinction this project cares a great deal about.


## @brief The shape and provenance of the indexed file set.
## @param db Database path or open connection.
## @param cap Maximum distinct top-level directories and extensions to report.
## @return IndexScope; the provenance fields are "" on an index built before build 17.
## @version 1
## @req REQ-DDB-QUERY-007
def index_scope(db: DbSource, cap: int = 12) -> IndexScope:
    """gh#21. An empty answer used to assert a definitive negative without naming
    the scope that produced it: `list_files("*.c")` reported "the database records
    none" from a checkout containing 53 `.c` files, every clause true of the
    database and the whole effect a false statement about the repository.

    What the caller needed was the scope, which `build_meta` has carried since
    build 17 — and which only `status` read, a separate call the caller had no
    reason to make. This is the SUMMARY form: counts, top-level directories and
    extensions, capped. `status` keeps its own raw read (`state._scope_meta`)
    because the two answer different questions — status reports the decision
    verbatim, and an empty answer needs a compact statement of what was covered.
    Ninety root paths in an empty-result note would be a token bomb.

    @brief Summarise what was indexed and why.
    @return IndexScope.
    @version 1
    """
    with connect(db) as conn:
        meta = _scope_provenance(conn)
        paths = _indexed_paths(conn)
    tops = sorted({p.split("/", 1)[0] for p in paths if "/" in p})
    return IndexScope(
        source=meta.get("source", ""),
        reason=meta.get("reason", ""),
        file_count=len(paths),
        top_levels=tuple(tops[:cap]),
        extensions=_extensions(paths)[:cap],
    )


## @brief Every file extension present in the indexed set, uncapped.
## @param db Database path or open connection.
## @return Sorted, dot-prefixed, lower-cased extensions.
## @version 1
## @req REQ-DDB-QUERY-007
def indexed_extensions(db: DbSource) -> tuple[str, ...]:
    """Separate from `IndexScope.extensions`, which is CAPPED for display, because
    the caller that decides whether `*.c` can possibly match must not read a
    truncated list as a complete one. That mistake would manufacture exactly the
    false certainty gh#21 is about — a definite "no `.c` file is indexed" derived
    from a list that stopped at twelve.

    @brief List all indexed file extensions.
    @return Sorted extension tuple.
    @version 1
    """
    with connect(db) as conn:
        return _extensions(_indexed_paths(conn))


## @brief Distinct dot-prefixed extensions of a path list.
## @param paths Repo-relative paths.
## @return Sorted extension tuple.
## @version 1
## @dg_internal
def _extensions(paths: list[str]) -> tuple[str, ...]:
    """Splits on the BASENAME's last dot, so a dotted directory
    (`.github/workflows/ci.yml`) contributes `.yml` and not `.github/workflows/ci`.

    @brief Derive the extension set of a path list.
    @return Sorted extensions.
    @version 1
    """
    names = [p.rsplit("/", 1)[-1] for p in paths]
    return tuple(sorted({"." + n.rsplit(".", 1)[1].lower() for n in names if "." in n[1:]}))


## @brief The `scope.*` build_meta rows, without their prefix.
## @param conn Open connection.
## @return Mapping of scope key to value; {} when build_meta is absent or older.
## @version 1
## @dg_internal
def _scope_provenance(conn: sqlite3.Connection) -> dict[str, str]:
    """{} rather than an exception on an older index, matching the query layer's
    standing rule that a degraded database answers thinly instead of failing.

    @brief Read the stored scope provenance.
    @return Prefix-stripped mapping.
    @version 1
    """
    if not table_exists(conn, "build_meta"):
        return {}
    rows = conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'scope.%'").fetchall()
    return {key.split(".", 1)[1]: value for key, value in rows}


## @brief Every indexed, non-synthetic file path.
## @param conn Open connection.
## @return Repo-relative path list.
## @version 1
## @dg_internal
def _indexed_paths(conn: sqlite3.Connection) -> list[str]:
    """@brief List the real indexed file paths.
    @return Repo-relative paths.
    @version 1
    """
    if not table_exists(conn, "path"):
        return []
    rows = conn.execute(
        "SELECT name FROM path WHERE type = ? AND name <> ''", (PATH_TYPE_FILE,)
    ).fetchall()
    return [name for (name,) in rows if not SYNTHETIC_PATH.match(name)]


## @brief Run one FTS5 MATCH, retrying the raw text as a quoted phrase.
## @param conn Open connection.
## @param text Caller's query text.
## @param limit Maximum rows.
## @return Result rows (file_path, heading, snippet).
## @version 2
## @dg_internal
def _fts_match(conn: sqlite3.Connection, text: str, limit: int) -> list[tuple]:
    """Execute the MATCH query. FTS5 rejects unbalanced quotes and bare
    operators with an OperationalError, so a failed query is retried once with
    the whole text quoted as a literal phrase rather than surfacing a syntax
    error to a model.

    @brief Execute an FTS5 MATCH with a quoted-phrase fallback.
    @return Result rows.
    @version 2
    """
    sql = (
        "SELECT file_path, heading, "
        "snippet(supplementary_docs, 2, '>>', '<<', '…', 20) "
        "FROM supplementary_docs WHERE supplementary_docs MATCH ? "
        "ORDER BY rank LIMIT ?"
    )
    try:
        return conn.execute(sql, (text, limit)).fetchall()
    except sqlite3.OperationalError:
        phrase = '"' + text.replace('"', " ") + '"'
        return conn.execute(sql, (phrase, limit)).fetchall()


## @brief The query's tokens, stripped of FTS5 operator syntax.
## @param text Caller's query text.
## @return Lower-cased tokens, empty ones dropped.
## @version 1
## @dg_internal
def _query_tokens(text: str) -> tuple[str, ...]:
    """Each token is re-quoted as a literal phrase before it reaches FTS5, so the
    characters stripped here are the ones that would otherwise be read as OPERATORS
    (`*` prefix, `^` anchor, `-` NOT, parentheses, colons) or terminate the quoting.
    Dropping them is not a loss: FTS5's `unicode61` tokenizer already splits on every
    one of them when it builds the index, so a stripped token matches exactly what a
    stored token can be.

    @brief Split a query into FTS5-safe literal tokens.
    @return Sanitised tokens in query order.
    @version 1
    """
    cleaned = "".join(ch if ch.isalnum() or ch in "_'" else " " for ch in text)
    ## A token of pure punctuation ("_", "'") survives the split but tokenizes to NOTHING,
    ## and an empty FTS5 phrase is a syntax error rather than a harmless no-op.
    return tuple(token for token in cleaned.lower().split() if any(c.isalnum() for c in token))


## @brief Full-text search over the ingested prose, widening to OR when the AND is empty.
## @param db Database path or open connection.
## @param text FTS5 query text (plain words work; a bad expression is retried as a phrase).
## @param limit Maximum hits to return.
## @return ProseSearch carrying the hits and whether the query had to be widened.
## @version 2
## @req REQ-DDB-QUERY-001
def search_prose_graded(db: DbSource, text: str, limit: int = 10) -> ProseSearch:
    """THE DEFECT THIS FIXES, MEASURED ON MBEDTLS. FTS5 joins a bare token list with an
    implicit AND, so a phrase is only found when the author used every one of the reader's
    words. `private accessor` returns `docs/3.0-migration-guide.md`; `private members
    accessor` returns NOTHING, because that document says "fields". Both describe the same
    section. A graded agent tried five such phrasings in one cell, was told each empty
    result was definitive, and fell back to `Read`, `Glob` and `grep` on the very file the
    corpus already held.

    THE WIDENING IS STRICTLY A LAST RESORT — only when the AND returns ZERO, and only when
    more than one token could have emptied it. A partial result is left alone: widening a
    query that already found something would bury the exact hits under loose ones, which is
    the opposite failure and just as hard to see. bm25 (`ORDER BY rank`) then puts the
    documents matching the most, and rarest, terms first, so the OR degrades gracefully
    rather than returning the corpus.

    THE CALLER IS TOLD. `widened` is returned, not hidden, because "these matched SOME of
    your terms" is a weaker claim than "these matched all of them" and a reader who cannot
    tell the two apart has traded a false negative for a false positive.

    @brief Search prose, falling back from AND to OR and reporting which answered.
    @return Hits plus the matching mode.
    @version 2
    """
    tokens = _query_tokens(text)
    with connect(db) as conn:
        rows: list[tuple] = []
        widened = False
        if table_exists(conn, "supplementary_docs"):
            rows = _fts_match(conn, text, max(1, limit))
            if not rows and len(tokens) > 1:
                widened = True
                rows = _fts_match(conn, " OR ".join(f'"{t}"' for t in tokens), max(1, limit))
        ## THE THIRD SOURCE (gh#404), and it is not a fallback — it is searched whenever the
        ## markdown half leaves room, because a member's doc comment is prose that happens to
        ## live in a `.c` file. Appended AFTER the FTS rows rather than interleaved: bm25 ranks
        ## the markdown half against itself and a LIKE match carries no comparable score, so
        ## merging them by a fabricated rank would assert an ordering neither half computed.
        ## STRIPPED, because doxygen stores these columns as XML. The first live check returned
        ## `<para>Allow library to access its structs' private members.</para>` — tags a reader pays
        ## for and cannot use. `strip_xml` is the same helper every other description path uses.
        members = [
            (path, f"{name} — member documentation", strip_xml(doc))
            for path, name, doc in member_doc_rows(conn, list(tokens), max(1, limit))
        ]
    seen = {(row[0], row[1]) for row in rows}
    rows = [*rows, *(m for m in members if (m[0], m[1]) not in seen)][: max(1, limit)]
    return ProseSearch(
        hits=[
            ProseHit(file_path=file_path, heading=heading or "", snippet=_collapse(snip))
            for file_path, heading, snip in rows
        ],
        ## `widened` describes the MARKDOWN query only, and stays false when the markdown half
        ## found nothing but a member doc answered: nothing was relaxed in that case, so
        ## reporting a relaxation would be a disclosure of something that did not happen.
        widened=widened and bool(rows),
        tokens=tokens,
    )


## @brief Full-text search over the ingested supplementary prose.
## @param db Database path or open connection.
## @param text FTS5 query text (plain words work; a bad expression is retried as a phrase).
## @param limit Maximum hits to return.
## @return List of ProseHit ranked by FTS5 relevance; empty when the corpus table is absent.
## @version 2
## @req REQ-DDB-QUERY-001
def search_prose(db: DbSource, text: str, limit: int = 10) -> list[ProseHit]:
    """Search the markdown corpus ingested into the `supplementary_docs`
    FTS5 table, returning a `snippet()` around each match. Older databases
    predate the corpus — the absent table yields an empty list, not an error.

    KEPT AS THE LIST-RETURNING API because it is the published R2 signature and a dozen
    call sites read it as a plain sequence. It now delegates to `search_prose_graded`, so
    it inherits the AND→OR widening; what it cannot carry is `widened`, which is why the
    MCP layer calls the graded form and this one stays for library callers who only want
    rows.

    @brief Search supplementary prose, returning snippets.
    @return List of ProseHit.
    @version 2
    """
    return search_prose_graded(db, text, limit=limit).hits


## @brief Compound rows matching EVERY token, or [] when compounds are unindexed.
## @param conn Open connection.
## @param tokens Lower-cased query tokens; all must appear in the compound name or its brief.
## @return List of (name, kind, repo-relative file, brief) in name order; STL compounds excluded.
## @version 1
## @req REQ-DDB-QUERY-007
def class_rows(conn: sqlite3.Connection, tokens: list[str]) -> list[tuple[str, str, str, str]]:
    """gh#315, THE THIRD SEARCH CORPUS. `search` read function `memberdef` rows and
    file-level documentation, and nothing else — so a class name produced a confident
    EMPTY result, which a caller cannot distinguish from a measured negative. That is
    the worst failure mode this project has, and it is the one the graded agent hits:
    `search("WritePlan")` on this repository returned the `mcp_config.py` file doc and
    not the class defined in it.

    Classes were ABSENT from the searched set rather than outranked or filtered, so
    the fix is a corpus and not a weight. Matching is the same conjunction over name
    and brief the other two corpora use, so one query keeps one meaning whichever
    half answers it.

    STL COMPOUNDS ARE EXCLUDED HERE, unlike in `lookup_class` where they are merely
    demoted, and the asymmetry is deliberate. doxygen registers hundreds of `std::`
    compounds against its synthetic path row; ranking those into a DISCOVERY surface
    lets system headers crowd out the repository the caller asked about — the same
    reasoning that already excludes them from `list_files`. Demotion-not-exclusion
    still holds wherever a caller can name what they want: `lookup_class` answers for
    a `std::` name.

    @brief Match compound names and briefs against all query tokens.
    @return List of (name, kind, file, brief) tuples.
    @version 1
    """
    if not tokens or not table_exists(conn, "compounddef"):
        return []
    placeholders = ",".join("?" * len(CLASS_KINDS))
    clause = " AND ".join(
        ["(LOWER(c.name) LIKE ? OR LOWER(COALESCE(c.briefdescription,'')) LIKE ?)"] * len(tokens)
    )
    params: list[str] = list(CLASS_KINDS)
    for token in tokens:
        params += [f"%{token}%", f"%{token}%"]
    rows = conn.execute(
        "SELECT c.name, c.kind, COALESCE(p.name,''), COALESCE(c.briefdescription,'') "
        "FROM compounddef c LEFT JOIN path p ON p.rowid = c.file_id "
        f"WHERE c.kind IN ({placeholders}) AND {clause} ORDER BY c.name",
        params,
    ).fetchall()
    return [
        (name, kind, file, strip_xml(brief))
        for name, kind, file, brief in rows
        if not SYNTHETIC_PATH.match(file)
    ]


## @brief Gating-symbol rows matching EVERY token, with their gate-site counts.
## @param conn Open connection.
## @param tokens Lower-cased query tokens; all must appear in the symbol name.
## @return List of (symbol, site count, first file, origin) in symbol order.
## @version 1
## @req REQ-DDB-QUERY-007
def gate_symbol_rows(
    conn: sqlite3.Connection, tokens: list[str]
) -> list[tuple[str, int, str, str]]:
    """gh#394, THE EIGHTH SEARCH CORPUS, and the fourth instance of one recurring defect:
    a layer present in the index that `search` never read, so its names came back a
    confident zero rather than being outranked. Variables were gh#372, macros gh#373,
    typedefs and enumerations gh#374; this is the CONFIGURATION SPACE.

    THE MEASUREMENT. After gh#390 the mbedtls index holds 10,861 gating sites over 1,327
    symbols, and `search("MBEDTLS_THREADING_PTHREAD")` still returned NOTHING — `dossier`
    answered only if you already knew the name. The graded agent searched for those symbols
    BY NAME nine times across one benchmark run and was refused every time, which is the
    discovery half of the same question: "is this compiled in, and under what flag".

    NO BRIEF COLUMN, so matching is on the NAME alone. A gate row is a location, not a
    documented entity — its meaning lives in the Kconfig help text or the config header's
    comment, which `search_prose` and `kconfig_symbols` already carry. Inventing a prose
    column here would let a two-token conceptual query match a bare identifier on one word
    and rank it beside a documented symbol.

    AGGREGATED PER SYMBOL. One row per symbol with its site count, never one row per site:
    `MBEDTLS_THREADING_C` gates 151 lines, and 151 identical-looking hits would bury every
    other corpus in the reply for a query that means one thing.

    @brief Match gating symbols by name, aggregated with their site counts.
    @return (symbol, sites, first file, origin) tuples.
    @version 1
    """
    if not tokens or not table_exists(conn, "kconfig_gates"):
        return []
    origin = "origin" if has_columns(conn, "kconfig_gates", "origin") else "''"
    clause = " AND ".join(["LOWER(symbol) LIKE ?"] * len(tokens))
    rows = conn.execute(
        f"SELECT symbol, COUNT(*), MIN(file_path), MIN({origin}) FROM kconfig_gates "  # noqa: S608
        f"WHERE {clause} GROUP BY symbol ORDER BY symbol",
        [f"%{token}%" for token in tokens],
    ).fetchall()
    return [(symbol, sites, file, org) for symbol, sites, file, org in rows]


## @brief Rank one class candidate: project-first, then exactness, then brevity.
## @param row Candidate row (rowid, name, kind, file, line, brief).
## @param wanted The name the caller asked for.
## @return Sort key tuple; lower sorts first.
## @version 1
## @dg_internal
def _class_rank(row: tuple, wanted: str) -> tuple:
    """Rank so a project class always outranks the `std::` noise doxygen
    harvests from system headers, an exact name beats a qualified tail match,
    and a tail match beats an incidental substring.

    @brief Sort key for class-lookup candidates.
    @return (is_stl, match tier, name length, name).
    @version 1
    """
    name, file = row[1], row[3]
    tail = name.rsplit("::", 1)[-1]
    if name == wanted:
        tier = 0
    elif tail == wanted:
        tier = 1
    elif tail.lower() == wanted.lower():
        tier = 2
    else:
        tier = 3
    return (bool(SYNTHETIC_PATH.match(file)), tier, len(name), name)


## @brief Members of one compound, ordered by declaration line.
## @param conn Open connection.
## @param rowid compounddef rowid.
## @return List of ClassMember; empty when the `member` relation is absent.
## @version 1
## @dg_internal
def _members(conn: sqlite3.Connection, rowid: int) -> list[ClassMember]:
    """@brief Build the ClassMember rows for one compound.
    @return List of ClassMember.
    @version 1
    """
    if not table_exists(conn, "member"):
        return []
    rows = conn.execute(
        "SELECT m.name, m.kind, COALESCE(m.type,''), COALESCE(m.argsstring,''), m.line "
        "FROM member mm JOIN memberdef m ON m.rowid = mm.memberdef_rowid "
        "WHERE mm.scope_rowid=? ORDER BY m.line, m.name",
        (rowid,),
    ).fetchall()
    return [
        ClassMember(
            name=name,
            kind=kind,
            signature=f"{mtype} {name}{args}".strip(),
            line=line,
        )
        for name, kind, mtype, args, line in rows
    ]


## @brief Immediate base and derived compound names for one compound.
## @param conn Open connection.
## @param rowid compounddef rowid.
## @return (bases, derived) name lists; both empty when `compoundref` is absent.
## @version 2
## @dg_internal
def _hierarchy(conn: sqlite3.Connection, rowid: int) -> tuple[list[str], list[str]]:
    """@brief Read the inheritance neighbours of one compound.
    @return (base names, derived names).
    @version 2
    """
    if not table_exists(conn, "compoundref"):
        return [], []
    sql = (
        "SELECT c.name FROM compoundref r JOIN compounddef c ON c.rowid = r.{other}_rowid "
        "WHERE r.{focal}_rowid=? ORDER BY c.name"
    )
    bases = [r[0] for r in conn.execute(sql.format(other="base", focal="derived"), (rowid,))]
    derived = [r[0] for r in conn.execute(sql.format(other="derived", focal="base"), (rowid,))]
    return bases, derived


## @brief The capped candidate list for an ambiguous class lookup, empty when unambiguous.
## @param ranked Candidate rows already sorted best-first by `_class_rank`.
## @return Up to MAX_CANDIDATES ClassCandidate rows, or [] when one compound matched.
## @version 1
## @dg_internal
def _compound_candidates(ranked: list[tuple]) -> list[ClassCandidate]:
    """Collapses on the QUALIFIED NAME, which is a compound's identity the way a
    signature is a function's — and is also the string a consumer passes back to
    `lookup_class` to select one. Two rows with the same qualified name are the same
    class seen twice (a decl/def duality of doxygen's making), not an ambiguity, and
    listing both would invite a caller to disambiguate between two identical strings.

    Named `_compound_candidates` and not `_class_candidates` on purpose: `symbols.py`
    already has a `_class_candidates`, and this repo's own index collapses same-named
    module-private helpers into one node (gh#26). Colliding here would have added a
    fabricated-neighbour pair to the very index this change exists to make honest.

    @brief Build the capped class-candidate list.
    @return ClassCandidate rows, best-ranked first.
    @version 1
    """
    seen: dict[str, ClassCandidate] = {}
    for _rowid, name, kind, file, line, _brief in ranked:
        if name not in seen:
            seen[name] = ClassCandidate(qualified=name, kind=kind, file=file, line=line or None)
    if len(seen) < 2:
        return []
    return list(seen.values())[:MAX_CANDIDATES]


## @brief Look up a class/struct by name, preferring project over STL noise.
## @param db Database path or open connection.
## @param name Class name, bare or qualified (`PolygonWidget` or `demo::shape::PolygonWidget`).
## @return The best-ranked ClassEntry (carrying the rejected candidates), or None when nothing matches.
## @version 4
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-010
def lookup_class(db: DbSource, name: str) -> ClassEntry | None:
    """Resolve a class/struct/union name to its definition, members, and
    immediate hierarchy. Matching is exact-first then substring, and every
    project compound outranks the `std::` compounds doxygen registers against
    its synthetic `[STL]` file — so a bare project name never loses to a
    system-header namesake.

    RETURNS THE REJECTS TOO (gh#315). This function has always fetched every
    substring match and returned exactly one, discarding the rest in a `min()` —
    so a caller asking for `PolygonWidget` in a repo that also defines
    `RoundedPolygonWidget` was told about one class and given no signal that the
    other existed. Every other disambiguating surface here — `resolve_symbol`,
    `dossier`, `chain_trace`, `source` — reports its rejected candidates, and the
    inconsistency was the defect: a silent pick is only safe when the caller can
    tell a pick was made. `candidates` is capped and stays empty when the name is
    unambiguous.

    @brief Look up one class/struct with members, hierarchy and rejected candidates.
    @return ClassEntry or None.
    @version 3
    """
    with connect(db) as conn:
        if not table_exists(conn, "compounddef"):
            return None
        placeholders = ",".join("?" * len(CLASS_KINDS))
        rows = conn.execute(
            "SELECT c.rowid, c.name, c.kind, COALESCE(p.name,''), c.line, c.briefdescription "
            "FROM compounddef c LEFT JOIN path p ON p.rowid = c.file_id "
            f"WHERE c.kind IN ({placeholders}) AND c.name LIKE ?",
            (*CLASS_KINDS, f"%{name}%"),
        ).fetchall()
        if not rows:
            return None
        ranked = sorted(rows, key=lambda r: _class_rank(r, name))
        best = ranked[0]
        bases, derived = _hierarchy(conn, best[0])
        return ClassEntry(
            name=best[1],
            kind=best[2],
            file=best[3],
            line=best[4] or None,
            brief=strip_xml(best[5]),
            members=_members(conn, best[0]),
            bases=bases,
            derived=derived,
            candidates=_compound_candidates(ranked),
        )


## Top-level directories listed before the reply says it stopped. Generous because a rollup is a
## dozen rows on a real repo (mbedtls: 10) — the cap is a backstop, not a policy.
_DIR_CAP = 40


## @brief Say what the per-directory counts are, and what they are NOT.
## @param indexed Total indexed files across all directories.
## @param shown How many directory rows the reply carries.
## @param total How many directories exist in the indexed set.
## @return The sentence; never empty when anything was indexed.
## @version 1
## @req REQ-DDB-QUERY-002
def rollup_meaning(indexed: int, shown: int, total: int) -> str:
    """THE COUNT IS OF INDEXED FILES AND A READER WILL TAKE IT FOR THE DIRECTORY'S SIZE. On
    mbedtls those differ enough to invert the answer: `tests/` holds 310 tracked files and 44
    indexed ones, because most are `.function` / `.data` fixtures no grammar handles, so the
    largest directory HERE is `library` (174) while the largest in the REPOSITORY is `tests`.
    A rollup offering the first as the second would argue for a wrong answer — the same class as
    the two false-count rosters and the config payload, and the reason this sentence is not
    optional.

    So it says what was counted, that files a grammar does not handle are absent, and where to
    settle a question about the repository itself.

    @brief Explain what the directory rollup counts.
    @return The sentence, or "" when nothing was indexed.
    @version 1
    """
    if not indexed:
        return ""
    parts = [
        f"{indexed} INDEXED file(s) across {total} top-level directory(ies). These are files this "
        "index HOLDS, not a census of the tree: a file whose extension no grammar handles is not "
        "indexed at all, so a directory can be large in the repository and small here."
    ]
    if shown < total:
        parts.append(f"Only the {shown} largest are listed; {total - shown} more are not shown.")
    parts.append(
        "So 'the largest directory in this index' and 'the largest directory in the repository' "
        "are different questions, and this answers only the first. For the second, count the "
        "tree. Pass a glob as `text` (e.g. `tests/*`) to list the indexed files themselves."
    )
    ## AND IT SAYS WHY IT DISAGREES WITH THE OTHER FILE COUNT IN THIS TOOL, without claiming an
    ## arithmetic it does not have. `coverage.indexed_files` is 443 where this is 527 on mbedtls,
    ## and two same-sounding figures differing for no stated reason is how a reader concludes one is
    ## wrong. It is NOT a single subtraction: coverage counts first-party RESOLVED files and also
    ## drops prose and documentation, and those categories OVERLAP — I wrote the subtraction two
    ## ways (527-41, then 527-41-259) and neither reconciled, which is exactly why this states the
    ## definitions rather than a sum.
    parts.append(
        "This counts every file row the index holds, so it is LARGER than "
        "`coverage.indexed_files`, which is a narrower set: first-party, resolved, and excluding "
        "prose and documentation. The two figures differ by construction and the difference is "
        "not one subtraction — `unresolved_files` and `external_files` below are contributors, "
        "not the whole of it."
    )
    return " ".join(parts)


## @brief The indexed file set rolled up by top-level directory.
## @param db Index path or open connection.
## @return DirectoryInventory, largest first, with the sentence saying what it counts.
## @version 1
## @req REQ-DDB-QUERY-002
def directory_rollup(db: DbSource) -> DirectoryInventory:
    """WHAT IS IN HERE, BY DIRECTORY. `list_files` has always answered this per FILE and no MCP
    surface could reach it — the `list_files` TOOL was deleted in the four-tool consolidation, so
    a working capability became unreachable. Measured on mbedtls 2026-08-14: Q4 replaced it with
    six `find … | wc -l` shell calls, which is 6 of its 11 fallbacks, and still missed the four
    marks it was computing them for.

    ROLLED UP RATHER THAN LISTED, because 450 file rows is the reply that made the config corpus
    unusable. The glob route (`text`) reaches the files themselves when a caller wants them.

    @brief Roll the indexed files up by top-level directory.
    @return The inventory.
    @version 1
    """
    with connect(db) as conn:
        owner = (
            f"p.{EXTERNAL_ROOT_COLUMN}" if has_columns(conn, "path", EXTERNAL_ROOT_COLUMN) else "''"
        )
        ## `dg_unresolved` is selected only when present, on the same absent-column contract the
        ## external tag uses: an index built before it reads 0, which is what that index knew.
        unresolved = "p.dg_unresolved" if has_columns(conn, "path", "dg_unresolved") else "0"
        rows = conn.execute(
            f"SELECT CASE WHEN instr(p.name, '/') > 0 "
            f"       THEN substr(p.name, 1, instr(p.name, '/') - 1) ELSE '.' END AS dir, "
            f"       COUNT(DISTINCT p.rowid), COUNT(DISTINCT m.name), "
            f"       SUM(CASE WHEN COALESCE({owner}, '') <> '' THEN 1 ELSE 0 END), "
            f"       SUM(CASE WHEN COALESCE({unresolved}, 0) <> 0 THEN 1 ELSE 0 END) "
            "FROM path p LEFT JOIN memberdef m ON m.file_id = p.rowid "
            "WHERE p.type = ? AND p.name <> '' AND p.name NOT LIKE '[%' "
            "GROUP BY dir ORDER BY 2 DESC, dir",
            (PATH_TYPE_FILE,),
        ).fetchall()
    entries = tuple(
        DirectoryEntry(
            directory=name,
            indexed_files=files,
            symbols=symbols,
            external_files=external or 0,
            unresolved_files=unresolved_count or 0,
        )
        for name, files, symbols, external, unresolved_count in rows
    )
    indexed = sum(e.indexed_files for e in entries)
    return DirectoryInventory(
        directories=entries[:_DIR_CAP],
        indexed_files=indexed,
        rollup_meaning=rollup_meaning(indexed, min(len(entries), _DIR_CAP), len(entries)),
    )


## The `scope.*` keys that name a DOCUMENT the repository declares, as opposed to the keys that
## describe what this build indexed. Both live under the same prefix in `build_meta`; only these
## answer "what does the project's own documentation build cover" and "what did it vendor".
_DECLARED_SCOPE_KEYS = (
    "doxyfile_path",
    "doxyfile_input",
    "doxyfile_file_patterns",
    "vendored_declared",
    "vendored_roots",
)


## @brief What the repository DECLARES about its own doc build and its vendored trees.
## @param db Index path or open connection.
## @return Mapping of declared-scope key to value, plus `doc_scope_meaning`; {} when none is stated.
## @version 1
## @req REQ-DDB-QUERY-007
def doc_scope(db: DbSource) -> dict[str, str]:
    """THE INDEX KNEW THIS AND NO QUERY RETURNED IT. `scope.doxyfile_*` has been stamped since the
    `doxyfile:` declaration key landed, and it was reachable only through `index(action='status')`
    on the DERIVED target — which refuses a named one. Measured on mbedtls 2026-08-14: the Q4 cell
    ran `find -iname "Doxyfile*"`, `find -iname "*doxygen*"`, an `ls`, and finally a
    `grep -E "^(INPUT|RECURSIVE|EXCLUDE|FILE_PATTERNS...)"` OF THE DOXYFILE — reading by hand the
    three values sitting in `build_meta` the whole time.

    A PLAIN MAPPING, NOT A MODEL, and deliberately: every value is a string copied verbatim out of
    `build_meta`, the key set is the storage's own, and a dataclass here would add a second place
    for the key names to drift from the writer. `doc_scope_meaning` carries the one thing a reader
    cannot get from the values.

    RETURNS {} WHEN NOTHING IS DECLARED, which is a different fact from "this repo has no Doxyfile"
    — the caller is told which, rather than being left to infer absence from emptiness.

    @brief Read the declared documentation scope and vendored roots.
    @return Declared-scope mapping, empty when the repository states none.
    @version 1
    """
    with connect(db) as conn:
        stated = {k: v for k, v in _scope_provenance(conn).items() if k in _DECLARED_SCOPE_KEYS}
    if not stated:
        return {}
    parts = []
    if "doxyfile_path" in stated:
        parts.append(
            f"`{stated['doxyfile_path']}` is the doc build THIS REPOSITORY declares, and "
            f"`doxyfile_input`/`doxyfile_file_patterns` are ITS scope — which is NOT this index's "
            f"scope. A doc build is a publishing target; the index covers the whole repository."
        )
    if "vendored_roots" in stated:
        parts.append(
            f"`{stated['vendored_roots']}` is declared vendored: committed into this repository "
            f"but not written by it."
        )
    return {**stated, "doc_scope_meaning": " ".join(parts)}
