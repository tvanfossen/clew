# SPDX-License-Identifier: MIT
"""EARS: which Easy Approach to Requirements Syntax pattern a requirement statement follows (S9).

S9 (owner-approved 2026-11-17): an EARS badge, OPT-IN and NEVER A GATE. EARS (Mavin et al., RE'09)
is a writing style a repository chooses, so `wiki.check.ears` turns it on, requirement pages then
show the pattern, and `clew wiki check` lists the statements that follow none as NOTES — its exit
code does not move.

The five patterns and their combination:

| pattern | shape |
|---|---|
| ubiquitous | The <system> shall <response> |
| event-driven | When <trigger>, the <system> shall <response> |
| state-driven | While <state>, the <system> shall <response> |
| unwanted | If <condition>, then the <system> shall <response> |
| optional | Where <feature>, the <system> shall <response> |
| complex | two or more of the keyword clauses above, then the shall clause |

A SHAPE CHECK, NOT A PARSE. It reads the leading keyword clauses and requires one `shall` clause
after them; it does not judge whether the <system> is named well or the response is testable.

@brief EARS pattern classification for requirement statements.
@version 1
"""

from __future__ import annotations

import re

## The leading keyword of each conditional pattern, in EARS's own order.
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("while", "state-driven"),
    ("when", "event-driven"),
    ("where", "optional"),
    ("if", "unwanted"),
)
_CLAUSE = re.compile(r"^\s*(while|when|where|if)\b[^,]*,\s*", re.I)
_SHALL = re.compile(r"^(?:then\s+)?(?:the\s+)?[\w\s'-]+?\bshall\b\s+\S", re.I)


## @brief The EARS pattern a statement follows, or None when it follows none.
## @param statement The requirement's statement.
## @return One of the pattern names in the module table, or None.
## @version 1
## @req REQ-DDB-WIKI-042
def ears_pattern(statement: str) -> str | None:
    """`If` needs its `then`: EARS's unwanted-behaviour form is "If …, then the … shall …", and a
    bare "If …, the … shall" is a common slip the badge should not bless.

    @brief Classify one statement.
    @return Pattern name or None.
    """
    text = " ".join(str(statement or "").split())
    found: list[str] = []
    while match := _CLAUSE.match(text):
        found.append(match.group(1).lower())
        text = text[match.end() :]
    if "if" in found and not text.lower().startswith("then "):
        return None
    if not _SHALL.match(text):
        return None
    names = dict(_KEYWORDS)
    return "complex" if len(found) > 1 else names[found[0]] if found else "ubiquitous"


## @brief The statement EARS is judged on: the acceptance text, else the title.
## @param acceptance The requirement's acceptance criteria, or "".
## @param title Its title, or "".
## @return The statement.
## @version 1
## @req REQ-DDB-WIKI-042
def statement_of(acceptance: object, title: object) -> str:
    """A catalogue's title is usually a label ("Load the data"); the acceptance text is where a
    requirement is stated, so it is read first.

    @brief Pick the statement.
    @return Text.
    """
    return str(acceptance or title or "")


## @brief The badge a requirement page carries when EARS is on.
## @param statement The requirement's statement.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-042
def ears_badge(statement: str) -> str:
    """@brief Pattern, or "not EARS". @return HTML."""
    pattern = ears_pattern(statement)
    label = f"EARS: {pattern}" if pattern else "not EARS"
    return f'<span class="ears ears-{pattern or "none"}">{label}</span>'


## @brief `clew wiki check`'s EARS notes: each indexed requirement whose statement follows none.
## @param db The index.
## @param enabled `wiki.check.ears`.
## @return One note per requirement; [] when off or all follow a pattern.
## @version 1
## @req REQ-DDB-WIKI-042
def ears_notes(db, enabled: bool) -> list[str]:  # noqa: ANN001
    """NOTES, NOT PROBLEMS: the caller prints them and leaves the exit code alone, because S9 is
    never a gate. The full statement is printed, so a writer can see what to rephrase.

    @brief List the requirements in no EARS pattern.
    @return Notes.
    """
    if not enabled:
        return []
    from ..query._common import connect

    with connect(db) as conn:
        rows = conn.execute("SELECT id, acceptance, title FROM requirements ORDER BY id").fetchall()
    return [
        f"note: {req} is in no EARS pattern: {statement_of(acc, title)!r}"
        for req, acc, title in rows
        if ears_pattern(statement_of(acc, title)) is None
    ]
