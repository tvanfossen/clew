# SPDX-License-Identifier: MIT
"""THE CODE-TEXT CORPUS: full-text over every indexed function's body.

WHY IT EXISTS. An agent with only clew's tools has no grep, so a fact that lives in a function
BODY and is named by no symbol is unreachable however it asks. Measured on mattermost-mobile in
the 1.3.0 grid: whether a failed post is retried is decided by a literal,
`retryPolicyConfiguration: {..., retryLimit: 3}`, inside `NetworkManagerSingleton.createClient`;
the index-only arm never found it, and a shell agent found it with one grep. `search` read names
and briefs only.

A ROW IS A FUNCTION, keyed by its memberdef rowid, so a hit's `kind` goes straight back to
`dossier` for the verbatim body and both edge directions. Every language is covered — a body is
lines between `bodystart` and `bodyend` whichever front end wrote the row. Module-level text
(a constants object, HOC wiring) is in the corpus through each JS/TS file's `__module__` row.

IDENTIFIERS STAY WHOLE: the tokenizer keeps `_` and `$`, so `POST_TIME_TO_FAIL` and `retryLimit`
match as written, not as fragments.

A POST-BUILD PASS, NOT A HARVEST STAGE: the body text is derived from rows and files the build
has already settled, so it is rebuilt whole each build, like the self-declared generated scan.
CREATED EVEN WHEN EMPTY, so "no function contains these words" and "this index has no code
corpus" stay distinguishable.

@brief Full-text search over function bodies.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .jsast import MODULE_CALLER
from .synth import DECL_EXTENT

## The FTS5 table, and its tokenizer: identifiers keep `_` and `$`.
TABLE = "code_text"
## PORTER STEMMING over it, so the word a reader types finds the inflection the code uses: one
## 1.3.0 agent searched `retries` where every identifier says `retry`.
_TOKENIZE = "porter unicode61 tokenchars '_$'"

## A body longer than this is indexed only up to it: a generated table or a minified file would
## otherwise dominate the corpus without being anything a reader asks about.
MAX_BODY_LINES = 2_000


## @brief One function whose body matched.
## @version 1
@dataclass(frozen=True)
class CodeHit:
    """@brief Code-corpus hit.
    @version 1
    """

    name: str
    definition: str
    kind: str
    file: str
    line: int
    snippet: str


## Version 3: indexes parse-built constants and typedefs by their recorded extent.
## Version 2: indexes each compound identifier's parts too.
##
## @brief Rebuild the code-text corpus from the index's function rows and the source files.
## @param db_path The database under construction.
## @param repo_root Repository root the indexed paths are relative to.
## @return Number of function bodies indexed.
## @version 3
## @utility
def record_code_text(db_path: Path, repo_root: Path) -> int:
    """READS EACH FILE ONCE, however many functions it holds, and indexes each function's own
    lines. A file that cannot be read is skipped: its functions are simply absent from this
    corpus, which the symbol corpus still covers.

    @brief Build the code corpus.
    @return Bodies indexed.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.execute(
            f'CREATE VIRTUAL TABLE {TABLE} USING fts5(body, tokenize = "{_TOKENIZE}", '
            "content = '', detail = none)"
        )
        rows = conn.execute(
            "SELECT m.rowid, p.name, m.bodystart, m.bodyend, m.name FROM memberdef m "
            "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
            "WHERE m.kind = 'function' AND m.bodystart > 0 AND m.bodyend >= m.bodystart "
            "ORDER BY p.name"
        ).fetchall() + _binding_rows(conn)
        lines_of: dict[str, list[str] | None] = {}
        covered: dict[str, set[int]] = {}
        for _rowid, rel, start, end, name in rows:
            if name != MODULE_CALLER:
                covered.setdefault(str(rel), set()).update(range(int(start), int(end) + 1))
        batch = []
        for rowid, rel, start, end, name in rows:
            if rel not in lines_of:
                lines_of[rel] = _lines(repo_root / str(rel))
            lines = lines_of[rel]
            if not lines:
                continue
            if name == MODULE_CALLER:
                ## ONLY WHAT NO FUNCTION HOLDS: a module's own text — constants, wiring — and not
                ## a second copy of every function in the file, which doubled the corpus.
                skip = covered.get(str(rel), set())
                body = [ln if i + 1 not in skip else "" for i, ln in enumerate(lines)]
            else:
                body = lines[int(start) - 1 : min(int(end), int(start) - 1 + MAX_BODY_LINES)]
            text = "\n".join(body)
            ## AND EACH COMPOUND IDENTIFIER'S PARTS: `retryLimit` also indexes `retry limit`, so
            ## the word a reader types finds the identifier that holds it. The table is
            ## contentless, so the parts cost index entries and nothing is ever shown.
            batch.append((int(rowid), text + "\n" + " ".join(_identifier_parts(text))))
        conn.executemany(f"INSERT INTO {TABLE} (rowid, body) VALUES (?, ?)", batch)
        conn.commit()
        return len(batch)
    finally:
        conn.close()


## @brief Parse-built constants and typedefs with a recorded extent, as corpus rows.
## @param conn Open connection.
## @return (rowid, path, first line, last line, name) rows; empty without `decl_extent`.
## @version 1
## @dg_internal
def _binding_rows(conn: sqlite3.Connection) -> list[tuple]:
    """A HIT INSIDE A CONSTANT NAMES THE CONSTANT: mattermost's retry policy sits in the class
    field `DEFAULT_CONFIG`, and the corpus answered with the whole file's `__module__`.

    @brief Binding rows.
    @return Rows.
    """
    if not _has_table(conn, DECL_EXTENT):
        return []
    return conn.execute(
        "SELECT m.rowid, p.name, m.line, e.end_line, m.name FROM memberdef m "
        f"JOIN {DECL_EXTENT} e ON e.memberdef_rowid = m.rowid "
        "JOIN path p ON p.rowid = m.file_id WHERE m.line > 0 AND e.end_line >= m.line"
    ).fetchall()


## @brief Whether a table exists.
## @version 1
## @dg_internal
def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Table presence. @return True when present."""
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone())


## TEST CODE RANKS LAST: production code is what a reader asks about, and the e2e helper named
## `retry` outranked every real match by being one line long. Absent table, nothing is test.
## Chosen in Python, not by `EXISTS`: SQLite resolves table names when it prepares a statement, so
## a guarded subquery over a missing `test_scope` still fails rather than ranking.
_TEST_LAST = "(p.rowid IN (SELECT path_rowid FROM test_scope))"

## A compound identifier: camelCase, PascalCase, snake_case or SCREAMING_CASE.
_COMPOUND = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|[a-z]+[A-Z][A-Za-z0-9]*|[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*"
)
_PART = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")
## One query word, as the tokenizer cuts it: letters, digits, `_` and `$`.
_QUERY_WORD = re.compile(r"[\w$]+")


## @brief The distinct word parts of every compound identifier in a body.
## @param text A function body.
## @return Lower-cased parts, e.g. `retry`, `limit` for `retryLimit`.
## @version 1
## @dg_internal
def _identifier_parts(text: str) -> list[str]:
    """@brief Split compound identifiers. @return Parts."""
    parts: set[str] = set()
    for ident in _COMPOUND.findall(text):
        for chunk in ident.split("_"):
            parts.update(p.lower() for p in _PART.findall(chunk))
    return sorted(parts)


## @brief A file's lines, or None when it cannot be read as text.
## @version 1
## @dg_internal
def _lines(path: Path) -> list[str] | None:
    """@brief Read lines. @return Lines or None."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


## Version 5: a query word also matches as a prefix (`MBEDTLS_ERR_` finds its family).
## Version 4: a binding's span is its declaration line through its recorded extent.
## Version 3: a query is split into words as the tokenizer splits them, so a dotted member
## access matches its parts instead of failing as an unsupported phrase.
##
## Version 2: ranks test-scope code last, guarded against a missing `test_scope`.
##
## @brief Functions whose bodies contain every word, smallest body first; None when no corpus.
## @param conn Open index connection.
## @param text Words to match.
## @param limit Maximum hits.
## @param repo_root Where to read snippet lines from; None leaves snippets empty.
## @return Hits, or None when this index has no code corpus.
## @version 5
## @utility
def search_code(
    conn: sqlite3.Connection, text: str, limit: int, repo_root: Path | None = None
) -> list[CodeHit] | None:
    """EVERY WORD MUST APPEAR IN ONE BODY, as the other text corpora match. The SMALLEST
    containing body ranks first: a nested closure's words are also in its enclosing function, and
    the innermost function that holds them is the answer.

    THE SNIPPET IS READ FROM THE FILE NOW, not stored: the table holds only the inverted index
    (contentless, no positions), which is what kept the corpus from multiplying the database —
    measured on mattermost-mobile, storing the text took the index from 8.4 MB to 45 MB. It also
    means a snippet is the file as it is, not as it was when the index was built.

    @brief Search function bodies.
    @return Hits or None.
    @version 1
    """
    if not _has_table(conn, TABLE):
        return None
    ## A MEMBER ACCESS MATCHES ITS PARTS: the tokenizer splits `props.failed` at the dot, so a
    ## quoted token became a phrase, which a `detail=none` table refuses — inside the tool.
    tokens = _QUERY_WORD.findall(text)
    if not tokens:
        return []
    ## EACH WORD MATCHES WHOLE (through the stemmer, so `retries` finds `retry`) OR AS A PREFIX,
    ## so a family named by its prefix — `MBEDTLS_ERR_`, `mbedtls_ct_` — finds its members. A
    ## prefix term is not stemmed, which is why both forms are asked.
    query = " AND ".join(f'("{t}" OR "{t}"*)' for t in tokens)
    ## A BINDING'S SPAN is its declaration line through its recorded end; a function's is its body.
    start, end, extent = "m.bodystart", "m.bodyend", ""
    if _has_table(conn, DECL_EXTENT):
        start = "(CASE WHEN m.bodystart > 0 THEN m.bodystart ELSE m.line END)"
        end = "COALESCE(e.end_line, m.bodyend)"
        extent = f"LEFT JOIN {DECL_EXTENT} e ON e.memberdef_rowid = m.rowid "
    order = f"({end} - {start})"
    if _has_table(conn, "test_scope"):
        order = f"{_TEST_LAST}, {order}"
    rows = conn.execute(
        f"SELECT m.name, m.definition, m.kind, p.name, {start}, {end} "
        f"FROM {TABLE} JOIN memberdef m ON m.rowid = {TABLE}.rowid {extent}"
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        f"WHERE {TABLE} MATCH ? ORDER BY {order} LIMIT ?",
        (query, max(1, limit)),
    ).fetchall()
    hits = []
    for name, definition, kind, file, start, end in rows:
        line, snippet = _first_match(repo_root, str(file), int(start), int(end), tokens)
        hits.append(
            CodeHit(
                name=str(name),
                definition=str(definition or ""),
                kind=str(kind),
                file=str(file),
                line=line,
                snippet=snippet,
            )
        )
    return hits


## Version 2: finds the snippet line by stem, as the match was made.
##
## @brief The first line in a span containing a token, read from the file.
## @version 2
## @dg_internal
def _first_match(
    repo_root: Path | None, rel: str, start: int, end: int, tokens: list[str]
) -> tuple[int, str]:
    """THE LINE IS FOUND BY STEM, as the match was: `retries` matched through porter stemming,
    and the line says `retry`, so a token is compared by a prefix that drops a short suffix.

    @brief Locate the matching line. @return (line number, stripped line).
    """
    lines = _lines(repo_root / rel) if repo_root is not None else None
    lowered = [t.lower()[: max(4, len(t) - 3)] for t in tokens]
    for number in range(start, min(end, len(lines or [])) + 1):
        text = (lines or [])[number - 1]
        if any(t in text.lower() for t in lowered):
            return number, text.strip()
    return start, ""
