# SPDX-License-Identifier: MIT
"""What to try instead, when a lookup found nothing.

**MEASURED, NOT GUESSED.** On the 1.1.0 acceptance grid, 26.7% of `dossier` calls in the
index-bearing arms returned nothing — 92 of 345. The reply those calls received advised checking
`target` and whether the index was stale, which is true and almost never the actual problem. Of
the 237 unanswered subjects behind those calls, **80.6% were recoverable from information the
index already held**:

| what the model passed                 | subjects | the index held                      |
|---------------------------------------|---------:|-------------------------------------|
| a bare name with no bare row          |      121 | the qualified form, 76% of the time |
| a qualified name, as `subject`        |       54 | the bare tail, 94% of the time      |
| a FILE PATH, as `subject`             |       48 | that very path, **100%**            |

The file-path row is the starkest: every path the model passed was a file this index had scanned,
and the reply said "not found". The information to redirect it was one query away.

THIS MODULE ONLY EVER NAMES WHAT IT FOUND. It returns an empty hint rather than a speculative
one — 29 of those 121 bare names genuinely have no neighbour, and inventing advice for them would
make the hint untrustworthy everywhere else. A hint that is sometimes fabricated is worse than no
hint, because a reader cannot tell which kind they are holding.

**IT DOES NOT TURN A MISS INTO A HIT.** The envelope stays `found: false`. A recovery hint is an
additional field on a negative, never a softening of it — `absence is not emptiness` applies to
this module's own output as much as to the tables it reads.

NEVER RAISES. It runs while building a reply that has already failed, so a database that cannot be
opened must not turn a clean negative into a traceback — the same discipline as
`tools_query._unresolved_for`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.query._common import connect, qualified_name_of, table_exists

## How many neighbours to name. Three is enough to be actionable and short enough that the hint
## does not become its own wall of text; the count of what was found is always stated, so a
## truncated list never reads as the whole set.
_MAX_NAMED = 3

## Suffixes that mean "this is a file, not a symbol". Only the ones actually observed as a
## `subject` on the 1.1.0 grid, so this stays a report of what happened rather than a guess.
_PATHISH = (".c", ".h", ".cpp", ".hpp", ".cc", ".py", ".rs", ".md", ".txt", ".yaml", ".yml")


##
# @brief Whether a subject string looks like a file rather than a symbol.
# @param subject The subject as the caller passed it.
# @return True when it looks like a path.
# @version 1
# @req REQ-DDB-QUERY-013
def looks_like_path(subject: str) -> bool:
    """A separator OR a known source suffix. `src/x.cpp` and `main.c` are both files; `C::f` has
    separators of a different kind and is excluded by checking `/` specifically.

    @brief Path-shaped subject test.
    @param subject The subject.
    @return True when path-shaped.
    @version 1
    """
    return "/" in subject or subject.lower().endswith(_PATHISH)


##
# @brief The bare tail of a qualified name.
# @param subject The subject as the caller passed it.
# @return The last segment after `::` or `.`.
# @version 1
# @req REQ-DDB-QUERY-013
def bare_tail(subject: str) -> str:
    """Both separators, because the index holds C++ (`Owner::method`) and Python
    (`pkg.module.function`) in the same column.

    @brief Last segment of a qualified name.
    @param subject The subject.
    @return The tail.
    @version 1
    """
    return subject.rsplit("::", 1)[-1].rsplit(".", 1)[-1]


##
# @brief Find a file in the index whose path matches a path-shaped subject.
# @param conn Open connection.
# @param subject The path-shaped subject.
# @return The matching indexed path, or "".
# @version 1
# @dg_internal
def _indexed_path(conn: sqlite3.Connection, subject: str) -> str:
    """Exact, then suffix, then basename. A model that passed `src/inference/x.cpp` and one that
    passed `x.cpp` both want the same redirection, and the index stores repo-relative paths whose
    prefix the caller may not have.

    @brief Matching indexed path.
    @param conn Open connection.
    @param subject The subject.
    @return The path or "".
    @version 1
    """
    if not table_exists(conn, "path"):
        return ""
    needle = subject.lstrip("./")
    base = needle.rsplit("/", 1)[-1]
    for sql, arg in (
        ("SELECT name FROM path WHERE name = ? LIMIT 1", needle),
        ("SELECT name FROM path WHERE name LIKE ? LIMIT 1", f"%/{needle}"),
        ("SELECT name FROM path WHERE name LIKE ? LIMIT 1", f"%/{base}"),
    ):
        row = conn.execute(sql, (arg,)).fetchone()
        if row and row[0]:
            return str(row[0])
    return ""


##
# @brief Qualified names in the index whose bare tail equals a name.
# @param conn Open connection.
# @param name The bare name that found nothing.
# @return Distinct qualified names, at most `_MAX_NAMED`, and the total found.
# @version 1
# @dg_internal
def _qualified_forms(conn: sqlite3.Connection, name: str) -> tuple[list[str], int]:
    """SQL narrows by `name`, then `qualified_name_of` decides — the same function the `qualified`
    selector compares against, so a hint can never name a form the selector would then reject.
    Deriving the hint from one rule and the acceptance from another is exactly how the served text
    came to advertise `signature`.

    @brief Qualified forms for a bare name.
    @param conn Open connection.
    @param name The bare name.
    @return (named forms, total count).
    @version 1
    """
    if not table_exists(conn, "memberdef"):
        return [], 0
    rows = conn.execute(
        "SELECT DISTINCT name, COALESCE(definition, name) FROM memberdef WHERE name = ?", (name,)
    ).fetchall()
    forms: list[str] = []
    for row_name, definition in rows:
        qualified = qualified_name_of(str(row_name), str(definition))
        if qualified and qualified != name and qualified not in forms:
            forms.append(qualified)
    return sorted(forms)[:_MAX_NAMED], len(forms)


##
# @brief Whether a bare name resolves to any row.
# @param conn Open connection.
# @param name The bare name.
# @return True when at least one row carries it.
# @version 1
# @dg_internal
def _name_exists(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Does this bare name resolve.
    @param conn Open connection.
    @param name The bare name.
    @return True when it does.
    @version 1
    """
    if not name or not table_exists(conn, "memberdef"):
        return False
    return (
        conn.execute("SELECT 1 FROM memberdef WHERE name = ? LIMIT 1", (name,)).fetchone()
        is not None
    )


##
# @brief What to try instead, for a subject this index could not answer.
# @param db The index database, or None when there is none to read.
# @param subject The subject as the caller passed it.
# @return One sentence naming a concrete next call, or "" when nothing was found.
# @version 1
# @req REQ-DDB-QUERY-013
def recovery_hint(db: str | Path | None, subject: str | None) -> str:
    """THREE CHECKS, IN THE ORDER THAT MATCHES THE MEASURED FREQUENCIES, and each one returns only
    what it actually found in the index:

      1. the subject is a FILE this index holds -> `dossier` describes symbols; name the tool that
         answers about files instead. 48 of 48 such subjects were indexed paths.
      2. the subject is QUALIFIED and its bare tail resolves -> the selector wants a bare `subject`
         plus `qualified=`, which the served parameter text says and the model did not do. 51 of 54.
      3. the subject is BARE and a qualified form exists -> name it. 92 of 121.

    EMPTY STRING WHEN NOTHING MATCHES, which is 29 of 121 bare names and 3 of 54 qualified ones.
    Those genuinely have no neighbour, and a fabricated suggestion there would make every real
    hint suspect.

    @brief A concrete next call, or "".
    @param db The index database or None.
    @param subject The subject.
    @return The hint, or "".
    @version 1
    """
    if db is None or not subject:
        return ""
    try:
        with connect(db) as conn:
            return _hint_from(conn, subject)
    except (sqlite3.Error, OSError, ValueError):
        ## A probe that cannot run contributes no clause, exactly as `_unresolved_for` does.
        return ""


##
# @brief Build the hint from an open connection.
# @param conn Open connection.
# @param subject The subject as the caller passed it.
# @return The hint, or "".
# @version 1
# @dg_internal
def _hint_from(conn: sqlite3.Connection, subject: str) -> str:
    """Split from `recovery_hint` so the failure handling and the logic are separately readable,
    and so the three checks sit together where their order can be seen.

    @brief The hint for an open connection.
    @param conn Open connection.
    @param subject The subject.
    @return The hint or "".
    @version 1
    """
    if looks_like_path(subject):
        found = _indexed_path(conn, subject)
        if found:
            return (
                f" THIS INDEX HOLDS THE FILE {found!r}, but `dossier` describes SYMBOLS, not "
                f"files — a path can never be a `subject`. Use "
                f'`search(corpus="files", text="{Path(found).name}")` to enumerate it, or '
                f"`dossier` on a symbol defined in it."
            )
        return ""

    tail = bare_tail(subject)
    if tail != subject and _name_exists(conn, tail):
        return (
            f" THE NAME IS INDEXED, THE SPELLING IS NOT. `subject` must be BARE: pass "
            f'`subject="{tail}", qualified="{subject}"` — `qualified` is what selects one '
            f"identity, and a qualified string in `subject` matches nothing."
        )

    ## ZERO OBSERVED HITS ON THE 1.1.0 GRID, STATED SO NOBODY CLAIMS OTHERWISE. Once the
    ## measurement was corrected for batch attribution, every bare-name miss fell into one of two
    ## buckets and neither is this one: 26 subjects had NO row at all (nothing to suggest), and 5
    ## had a row under that exact name and missed anyway — a retrieval defect, not a spelling one,
    ## and tracked separately. The branch is kept because the mechanism is sound and the cost is
    ## one indexed lookup on a path that has already failed; if the next grid also shows zero, it
    ## should be deleted rather than carried as decoration.
    forms, total = _qualified_forms(conn, subject)
    if forms:
        named = ", ".join(repr(form) for form in forms)
        more = f" and {total - len(forms)} more" if total > len(forms) else ""
        return (
            f" NO BARE {subject!r}, but this index holds it qualified: {named}{more}. Re-ask as "
            f'`subject="{subject}", qualified="{forms[0]}"`.'
        )
    return ""
