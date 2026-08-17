# SPDX-License-Identifier: MIT
"""Verbatim source retrieval for one function — the "show me the code" query.

The database records a function's body EXTENT (`bodystart`/`bodyend` +
`bodyfile_id`), not its text, and `build_meta` does not carry a repo root —
so the working tree must be supplied by the caller (R3 takes it from the
active target's registry entry; nothing here hardcodes a path).

The listing is CAPPED on purpose. A comparison query layer shipped an
unbounded equivalent and a single call returned 26 KB of source, which
distorted its own token accounting; an uncapped tool is a tool that quietly
buys back the cost the index was supposed to remove.

@brief Verbatim, line-capped function body retrieval.
@version 1
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from ._common import (
    DbSource,
    candidate_rows,
    connect,
    function_candidates,
    is_overloaded,
    symbol_provenance,
)
from .models import BodyExcerpt, SourceListing

logger = logging.getLogger(__name__)

DEFAULT_MAX_LINES = 200

## The dossier's body cap, deliberately lower than `source`'s. `source` is a call a
## caller made ON PURPOSE to read code; the dossier's body is one panel of a composite
## payload, and the whole point of the one-shot is to stop paying for a second call —
## which a dossier that returns a 400-line function undoes from the other direction.
DEFAULT_BODY_LINES = 120


## How many of a body excerpt's leading lines may carry the function's name for the excerpt to
## count as anchored. THREE, and the number comes from a measurement rather than from taste
## (`.claude/tmp/body_anchor_probe.py`): across four brace styles — `void f(void) { }`, brace on
## its own line, a signature wrapped over three lines, and a C++ out-of-line `int Probe::value()
## const` — doxygen's `bodystart` pointed at the SIGNATURE line every time, so ONE line would
## already have sufficed for every shape tested.
##
## The extra two are headroom for a storage class or return type on a line of its own, which is
## legal and which the probe did not cover. Widening costs detection of a one-or-two-line shift,
## and that is the right trade: a small shift returns nearly the right body, while the harmful
## case — the one measured, 55 lines of an unrelated function — moves by hundreds and is caught
## by any window. A guard that fires on ordinary code would be worse than no guard.
_ANCHOR_WINDOW = 3


## @brief Whether an excerpt's opening lines still name the function they are filed under.
## @param name The function's name as the index records it.
## @param lines The excerpt's lines, in order.
## @return True when the name appears within the first `_ANCHOR_WINDOW` lines.
## @version 1
## @dg_internal
def _anchored(name: str, lines: list[str]) -> bool:
    """THE BARE NAME, because a qualified one is not what the source line spells. doxygen records
    `Probe::value` while the definition reads `int Probe::value() const` — the bare tail matches
    either spelling, and matching on the qualified form would report every C-style function as
    unanchored the moment a class name entered the picture.

    A SUBSTRING TEST, deliberately, not a parse. The question is "does this text still look like
    the right function", not "is this a valid definition"; a parse here would need to handle every
    declarator shape the grammar allows and would fail closed on the ones it did not, turning a
    disclosure into a false alarm. A name that happens to appear for another reason yields a
    FALSE NEGATIVE — the excerpt is called anchored when it is not — which is the safe direction
    for a check whose true positives are the loud ones.

    An empty name or no lines cannot be judged, so both count as anchored: claiming a mismatch on
    absent evidence is the substitution this whole field exists to prevent, one level down.

    @brief Check an excerpt against the name it is filed under.
    @return True when anchored, or unjudgeable.
    @version 1
    """
    bare = name.split("::")[-1].strip()
    if not bare or not lines:
        return True
    return any(bare in line for line in lines[:_ANCHOR_WINDOW])


## @brief Read the recorded body extent + body file for one memberdef rowid.
## @param conn Open connection.
## @param rowid Canonical memberdef rowid.
## @return (name, repo-relative body file, start, end), or None when no body extent is recorded.
## @version 1
## @dg_internal
def _body_extent(conn: sqlite3.Connection, rowid: int) -> tuple[str, str, int, int] | None:
    """Resolve the body location doxygen recorded. A header-only declaration
    (or a macro-defined symbol) has no body: `bodystart` is 0/NULL and there
    is nothing to read.

    @brief Look up a function's recorded body extent.
    @return (name, file, start, end) or None.
    @version 1
    """
    row = conn.execute(
        "SELECT m.name, COALESCE(bp.name, p.name, ''), m.bodystart, m.bodyend "
        "FROM memberdef m "
        "LEFT JOIN path bp ON bp.rowid = m.bodyfile_id "
        "LEFT JOIN path p ON p.rowid = m.file_id "
        "WHERE m.rowid=?",
        (rowid,),
    ).fetchone()
    if row is None:
        return None
    name, file, start, end = row
    if not file or not start:
        return None
    return name, file, int(start), int(end or start)


## @brief Slice a file's text to a body extent, capped at `max_lines`.
## @param path File to read.
## @param start 1-based first line of the body.
## @param end 1-based last line of the body.
## @param max_lines Maximum number of lines to carry back.
## @return (lines, last included line, truncated) — empty lines when the extent is out of range.
## @version 1
## @dg_internal
def _slice(path: Path, start: int, end: int, max_lines: int) -> tuple[list[str], int, bool]:
    """Read `start`..`end` (1-based, inclusive) out of `path`, keeping at most
    `max_lines` and reporting the last line actually included.

    @brief Extract a capped, 1-based inclusive line range from a file.
    @return (lines, end_line, truncated).
    @version 1
    """
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    body = text[start - 1 : end]
    truncated = len(body) > max_lines
    if truncated:
        body = body[:max_lines]
    return body, start + len(body) - 1, truncated


## @brief Read a body extent from a repo-contained file, capped at max_lines.
## @param root Working-tree root (the trust boundary for the read).
## @param file DB-recorded body file, expected to be relative to root.
## @param start 1-based first line of the body.
## @param end 1-based last line of the body.
## @param max_lines Maximum lines to carry back.
## @return (lines, end_line, truncated), or None when the path escapes root or is unreadable.
## @version 1
## @dg_internal
def _read_body(
    root: Path, file: str, start: int, end: int, max_lines: int
) -> tuple[list[str], int, bool] | None:
    """Resolve `file` under `root` and read it — but only if it stays INSIDE
    `root`. The DB is trusted implicitly by R3, which serves whatever target a
    caller sets; a tampered/foreign db could record an absolute (`/etc/passwd`)
    or `../`-escaping body path, which `root / file` would happily follow
    outside the working tree. Resolve both and refuse anything that is not
    contained — defense in depth for the "read a function's source" tool.

    @brief Read a repo-contained body extent, refusing path escapes.
    @return (lines, end_line, truncated) or None.
    @version 1
    """
    root = root.resolve()
    path = (root / file).resolve()
    if not path.is_relative_to(root):
        logger.warning(
            "source(): recorded body path %r resolves to %s, outside repo root %s — refusing to read",
            file,
            path,
            root,
        )
        return None
    try:
        return _slice(path, start, end, max_lines)
    except OSError:
        return None


## @brief A bounded body excerpt for one ALREADY-RESOLVED rowid.
## @param conn Open connection to the index.
## @param rowid The resolved identity's canonical memberdef rowid.
## @param repo_root Working-tree root the recorded body paths are relative to.
## @param max_lines Cap on the lines carried back.
## @return BodyExcerpt, or None when no body extent is recorded / the file is unreadable.
## @version 2
## @req REQ-DDB-QUERY-001
def body_excerpt(
    conn: sqlite3.Connection,
    rowid: int,
    repo_root: Path | str,
    max_lines: int = DEFAULT_BODY_LINES,
) -> BodyExcerpt | None:
    """The dossier's body panel. Takes a ROWID rather than a name on purpose: the
    dossier has already chosen which of several same-named functions it describes
    (gh#26/gh#37), and re-resolving from the name here would be a second, independent
    notion of identity able to quote a DIFFERENT function's source text under the
    described function's heading — the worst possible version of that bug, because a
    body looks like proof.

    None is a real answer with several distinct causes, all of them "no body to show":
    a header-only declaration, a macro-defined symbol, an unreadable working tree, a
    body path that escapes `repo_root`.

    THE NAME USED TO BE READ AND DISCARDED, one underscore away from the check this function
    most needed. The lines come from the LIVE working tree at the span the INDEX recorded, so a
    file edited since the build yields whatever now occupies those numbers — and the docstring
    above already names quoting another function's text as "the worst possible version of that
    bug, because a body looks like proof" while guarding only the re-resolution route to it. The
    staler route was left open: same rowid, same identity, moved file. `anchor_mismatch` closes
    it by DISCLOSURE, since the lines may still help and hiding them would be worse.

    @brief Read a resolved rowid's bounded body excerpt.
    @return BodyExcerpt or None.
    @version 2
    """
    extent = _body_extent(conn, rowid)
    if extent is None:
        return None
    name, file, start, end = extent
    result = _read_body(Path(repo_root).expanduser(), file, start, end, max(1, max_lines))
    if result is None:
        return None
    lines, end_line, truncated = result
    return BodyExcerpt(
        file=file,
        start_line=start,
        end_line=end_line,
        total_lines=end - start + 1,
        truncated=truncated,
        lines=tuple(lines),
        anchor_mismatch=not _anchored(name, lines),
    )


## How many lines a declaration excerpt will read before giving up on finding the
## statement's end. A declaration is one statement, and the overwhelming majority are one
## line; a few wrap an initializer list or a function-pointer parameter list over several.
## Small on purpose — this panel exists to show a binding, not to quote a table.
DECLARATION_MAX_LINES = 8


## @brief A bounded excerpt of the SOURCE LINE a symbol is declared on.
## @param conn Open connection to the index.
## @param rowid The memberdef rowid whose declaration site to read.
## @param repo_root Working-tree root the recorded paths are relative to.
## @param max_lines Cap on the lines carried back.
## @return BodyExcerpt covering the declaration statement, or None when it cannot be read.
## @version 1
## @req REQ-DDB-QUERY-001
def declaration_excerpt(
    conn: sqlite3.Connection,
    rowid: int,
    repo_root: Path | str,
    max_lines: int = DECLARATION_MAX_LINES,
) -> BodyExcerpt | None:
    """WHAT `body_excerpt` CANNOT DO, AND WHY THAT MATTERS. It reads `bodystart`..
    `bodyend`, and a variable has neither — both columns are 0 for every one of the
    10,498 memberdef rows on the public mbedtls index whose kind is not 'function'. So
    the one panel that would show a variable's binding was unreachable through the
    function-shaped path, and the binding is exactly what a caller asking about a
    function pointer wants.

    The extent is `memberdef.line` through the first line containing a `;`, bounded by
    `max_lines`. THAT IS A HEURISTIC AND IT IS STATED AS ONE: `truncated` is True when
    the bound was reached without finding a terminator, so a caller can see that the
    statement continues rather than reading a clipped excerpt as complete. A `;` inside
    a string literal or a trailing comment would end the excerpt early — the cost of
    that is a short excerpt, never a wrong file or a wrong line.

    Reads the DECLARING file (`file_id`), not the body file: a variable has no body
    file, and falling back to one would quote a different translation unit.

    @brief Read the source statement a symbol is declared on.
    @return BodyExcerpt over the declaration, or None.
    @version 1
    """
    row = conn.execute(
        "SELECT COALESCE(p.name,''), m.line FROM memberdef m "
        "LEFT JOIN path p ON p.rowid = m.file_id WHERE m.rowid=?",
        (rowid,),
    ).fetchone()
    if row is None or not row[0] or not row[1]:
        return None
    file, start = row[0], int(row[1])
    cap = max(1, min(max_lines, DECLARATION_MAX_LINES))
    result = _read_body(Path(repo_root).expanduser(), file, start, start + cap - 1, cap)
    if result is None or not result[0]:
        return None
    lines = _to_terminator(result[0])
    return BodyExcerpt(
        file=file,
        start_line=start,
        end_line=start + len(lines) - 1,
        total_lines=len(lines),
        truncated=len(lines) == cap and ";" not in lines[-1],
        lines=tuple(lines),
    )


## @brief Cut a line window at the first statement terminator.
## @param lines The window read from the declaring file.
## @return The lines up to and including the first one containing a semicolon.
## @version 1
## @dg_internal
def _to_terminator(lines: list[str]) -> list[str]:
    """Kept as its own function so the heuristic has ONE name and one place to be wrong
    in. `declaration_excerpt` reports whether it fired via `truncated`; if this rule
    ever needs to understand string literals, it changes here and the disclosure keeps
    working unaltered.

    @brief Trim a declaration window to its first terminated statement.
    @return The trimmed window; the whole window when no terminator appears.
    @version 1
    """
    for i, line in enumerate(lines):
        if ";" in line:
            return lines[: i + 1]
    return lines


## @brief Verbatim, capped source body for one function.
## @param db Database path or open connection.
## @param function Function name to read.
## @param repo_root Working-tree root the recorded paths are relative to.
## @param max_lines Cap on returned lines (default 200); raise it deliberately.
## @return SourceListing, or None when the function is unknown, has no recorded body, unreadable, or path-escaping.
## @version 4
## @req REQ-DDB-QUERY-001
def source(
    db: DbSource,
    function: str,
    repo_root: Path | str,
    max_lines: int = DEFAULT_MAX_LINES,
    qualified: str | None = None,
) -> SourceListing | None:
    """Return the function's actual source text, read from `repo_root` at the
    body extent the database recorded (definition-preferring resolution, so a
    header declaration never shadows the definition). When the name is a
    genuine overload the body shown is the definition-preferring pick and the
    alternatives ride along in `candidates`.

    None when the name is not indexed, when no body extent exists (header-only
    declaration), when the file cannot be read from `repo_root`, or when the
    recorded body path escapes `repo_root` (a tampered/foreign db — refused).

    `qualified` (gh#37) picks WHICH same-named function to read: pass a
    `candidates[i].qualified` from any prior reply. This is the accessor where the
    bare-name guess is most visibly wrong — it returns a body, so a model reads the
    wrong function's actual source text and has no signal that it did.

    @brief Read one function's verbatim body, capped at `max_lines`.
    @return SourceListing or None.
    @version 5
    """
    with connect(db) as conn:
        cands = function_candidates(conn, function, qualified)
        rowid = cands[0][0] if cands else None
        extent = _body_extent(conn, rowid) if rowid is not None else None
        ## Ambiguity is a property of the NAME, so it is measured over every
        ## same-named row — a narrowed call must still disclose the alternatives.
        all_cands = function_candidates(conn, function) if qualified is not None else cands
        overloads = candidate_rows(conn, function, all_cands) if is_overloaded(all_cands) else []
        provenance = symbol_provenance(conn, rowid) if rowid is not None else None
    if extent is None:
        return None
    name, file, start, end = extent
    result = _read_body(Path(repo_root).expanduser(), file, start, end, max(1, max_lines))
    if result is None:
        return None
    lines, end_line, truncated = result
    return SourceListing(
        name=name,
        file=file,
        start_line=start,
        end_line=end_line,
        lines=lines,
        truncated=truncated,
        candidates=overloads,
        provenance=provenance,
    )
