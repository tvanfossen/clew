# SPDX-License-Identifier: MIT
"""DOMINATED-FUZZY SUPPRESSION (gh#26) — delete the name fan-out the AST layers
publish when a stronger layer already named the real callee.

THE DEFECT THIS CLOSES. `_ast_record_call_edge` resolves a call site's callee by
NAME. When several indexed functions share that name it cannot tell which one the
call meant, so it fans one edge out to EVERY namesake and marks each `fuzzy`.
That is honest about the individual row and dishonest in aggregate: this repo's
own index has four module-private `_table_exists` helpers, so
`callers('_table_exists')` reported functions in three modules that cannot see
it. `9ca9671` stopped those rows being LAUNDERED as `exact`; it could not remove
them, because the query layer cannot invent the absence of a row the pipeline
wrote. This stage removes them.

THE RULE. For a caller C and a bare callee name N, let the ANCHORS be the
qualified identities that some NON-FUZZY layer attributes to (C, N). If there is
at least one anchor, a `fuzzy` row from C to a same-named function that is NOT an
anchor is a fan-out artefact and is deleted. A stronger layer looked at this exact
call site and named a different function; the guess is dominated by the evidence.

WHAT IT DELIBERATELY DOES NOT DELETE, each exemption measured rather than assumed:

  * **A group with no anchor.** Nothing dominates the guess, so the fan-out is the
    only evidence there is and `fuzzy` already says what it is worth. This is why
    the pass is not a general "prefer non-fuzzy" rule, which would have emptied
    large parts of a C++ graph: on entropic 25,162 of 29,880 rows are fuzzy, and
    only 539 of them sit in a group an anchor dominates.
  * **A row whose identity IS an anchor.** Same function, weaker layer — the row
    names the relationship the anchor already names, so it is not a fan-out
    artefact at all. The first draft of this pass deleted them as redundant
    duplicates, which removes real rows from a layer's own record of what it
    found and moves `row_inflation` without any fabrication being deleted.
  * **A virtual OVERRIDE of an anchor**, per doxygen's own `reimplements` relation.
    A base class's `generate()` calling the protected virtual `do_generate()` is a
    template-method dispatch whose real dynamic target is the derived override, and
    the fan-out row is the only edge that reaches it. 48 rows on entropic, all of
    that shape.
  * **Any source but `ast` / `ast_member`.** `declared_dispatch` and `fnptr` emit
    `fuzzy` to encode a MULTI-CANDIDATE dispatch on purpose; those rows are the
    answer, not a name guess, and deleting them would break declared dispatch.

IDENTITY IS THE QUALIFIED NAME, reusing `query._common.qualified_name_of` rather
than re-deriving it. Two copies of the identity rule would drift, and drift here
means this stage deletes rows the query layer still believes are distinct
functions. It also makes decl/def duality safe for free: doxygen emits a memberdef
per documented declaration as well as one for the definition, and both carry the
same qualified name, so a declaration row is never mistaken for a namesake.

MEASURED BEFORE LANDING, on both public targets and this repo's self-index:

  | target   | fan-out fuzzy | deleted | share |
  |----------|---------------|---------|-------|
  | entropic |         5,614 |     539 | 9.60% |
  | mbedtls  |             4 |       0 | 0.00% |
  | self     |         3,028 |     287 | 9.48% |

Each figure comes from applying the pass to a COPY of one index rather than diffing
two builds. That is not fussiness: the two-build diff reported the self-index's
non-fuzzy edge count moving by +1, which a delete-only pass cannot cause — two
doxygen/tree-sitter runs over one tree are not bit-identical, and on a self-indexing
repo the source moves as well, because the pipeline IS the source.

Eight groups totalling 51 deleted rows were read against the source by hand and
all 51 were fabrications — `save_snapshot`'s only `execute` call is `db_.execute`,
`run_streaming`'s two `flush` calls are both `filter.flush()`, and two of the rows
named an anonymous-namespace function in another translation unit, which internal
linkage makes structurally unreachable.

LIVENESS AND TERMINI CANNOT MOVE. Only `fuzzy` rows are deleted, and both
`mark_reachability`'s seeded BFS and the thread-membership closure traverse
non-fuzzy edges only. That is a property to check after a build, not a hope: the
seeding heuristic keys on zero non-fuzzy INCOMING edges, so a pass that touched
non-fuzzy rows would move the seed set and with it every liveness verdict.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

## The PACKAGE logger, not `getLogger(__name__)`. Every other stage takes it from
## here, and the CLI attaches its handler to this one name — a per-module child would
## reach the build log only by propagation, which is one accident away from a stage
## whose verdict is invisible in the very log a reader checks it in.
from ._common import logger
from .query._common import qualified_name_of
from .vocabulary import (
    CALL_MATCH_FUZZY,
    CALL_SOURCE_AST,
    CALL_SOURCE_AST_MEMBER,
)

## The layers whose `fuzzy` grade means "a function of this name exists and the
## specific one was never confirmed" — the only grade this pass is entitled to
## second-guess. Every OTHER source that emits `fuzzy` (`declared_dispatch`,
## `fnptr`) is encoding a deliberate multi-candidate dispatch.
FANOUT_SOURCES = (CALL_SOURCE_AST, CALL_SOURCE_AST_MEMBER)


## @brief rowid → (bare name, qualified identity) for every function in the index.
## @param conn Open connection to the database being built.
## @return Mapping of memberdef rowid to its (name, qualified identity) pair.
## @version 1
## @dg_internal
def _identity_index(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """Built once per build; the classification below needs an identity for both
    endpoints of every edge and a per-row query would be thousands of lookups.

    DEGRADES to the bare name when `memberdef` has no `definition` column — the
    same graceful-degradation contract `call_edges._definition_index` states, and
    for the same reason: several test fixtures hand-build a minimal `memberdef`
    with only the columns their own assertion needs, and a bare
    `SELECT definition` turns one of those into an `OperationalError` raised from a
    layer the test was not exercising. With no definitions every namesake collapses
    to one identity, so no group ever has a non-anchor member and the pass deletes
    NOTHING. Failing closed on a thin schema is the right direction for a
    destructive stage.

    @brief Map every function rowid to its bare name and qualified identity.
    @return {rowid: (name, qualified_identity)}.
    @version 1
    """
    columns = {r[0] for r in conn.execute("SELECT name FROM pragma_table_info('memberdef')")}
    if "definition" not in columns:
        return {
            rowid: (name, name) for rowid, name in conn.execute("SELECT rowid, name FROM memberdef")
        }
    return {
        rowid: (name, qualified_name_of(name, definition))
        for rowid, name, definition in conn.execute("SELECT rowid, name, definition FROM memberdef")
    }


## @brief Unordered pairs of qualified identities linked by doxygen's `reimplements`.
## @param conn Open connection to the database being built.
## @param identity rowid → (name, qualified identity) map.
## @return Set of frozensets, each holding the two identities of one override relation.
## @version 1
## @dg_internal
def _override_pairs(
    conn: sqlite3.Connection,
    identity: dict[int, tuple[str, str]],
) -> set[frozenset[str]]:
    """Read as IDENTITIES, not rowids, so a base declaration and its definition
    both match — the override exemption has to survive decl/def duality or it would
    protect a virtual dispatch through one row of a function and not the other.

    Returns an empty set when the table is absent (doxygen versions that do not
    emit it, and every hand-built fixture), which makes the exemption inert rather
    than fatal. That direction is deliberate but it is NOT free: with no
    `reimplements` rows a genuine template-method dispatch loses its exemption and
    the derived override's edge is deleted. It is the correct trade only because
    the alternative — skipping the whole pass without the table — would leave the
    fabrications this stage exists to remove.

    @brief Identity pairs doxygen records as override relations.
    @return Unordered identity pairs; empty when `reimplements` is absent.
    @version 1
    """
    try:
        rows = conn.execute(
            "SELECT memberdef_rowid, reimplemented_rowid FROM reimplements"
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    pairs = set()
    for derived, base in rows:
        if derived in identity and base in identity:
            pairs.add(frozenset((identity[derived][1], identity[base][1])))
    return pairs


## @brief Non-fuzzy qualified identities per (caller, bare callee name) group.
## @param rows Every call edge as (caller, callee, source, confidence).
## @param identity rowid → (name, qualified identity) map.
## @return {(caller_rowid, callee_name): {anchor identities}}.
## @version 1
## @dg_internal
def _anchors(
    rows: list[tuple[int, int, str, str]],
    identity: dict[int, tuple[str, str]],
) -> dict[tuple[int, str], set[str]]:
    """Keyed on the BARE name because that is the key the fan-out was built from:
    `_ast_record_call_edge` looked the callee up in a name→rowids index, so the
    set of rows that must be judged together is exactly the set sharing a bare
    name. Keying on the qualified identity instead would put each namesake in its
    own group, every group would contain its own row, and the pass would delete
    nothing.

    @brief Group non-fuzzy evidence by caller and bare callee name.
    @return Anchor identities per group.
    @version 1
    """
    anchors: dict[tuple[int, str], set[str]] = {}
    for caller, callee, _source, confidence in rows:
        if confidence == CALL_MATCH_FUZZY or callee not in identity:
            continue
        anchors.setdefault((caller, identity[callee][0]), set()).add(identity[callee][1])
    return anchors


## @brief The fan-out rows a non-fuzzy anchor dominates, and why each was spared or doomed.
## @param rows Every call edge as (caller, callee, source, confidence).
## @param identity rowid → (name, qualified identity) map.
## @param overrides Identity pairs from doxygen's `reimplements`.
## @return (doomed (caller, callee, source) triples, verdict tally).
## @version 2
## @req REQ-DDB-PIPE-009
def classify_dominated(
    rows: list[tuple[int, int, str, str]],
    identity: dict[int, tuple[str, str]],
    overrides: set[frozenset[str]],
) -> tuple[list[tuple[int, int, str]], Counter]:
    """Pure over its arguments so the rule can be tested without a built index —
    the measurement scripts and the tests exercise this function, and the SQL
    around it only supplies rows and deletes what comes back.

    The tally counts every fan-out row in an anchored group under one of four
    verdicts, so the log can state what was spared alongside what was deleted. A
    pass that reports only its deletions gives a reader no way to see that the
    same-identity and override exemptions actually fired.

    @brief Decide which fuzzy fan-out rows a non-fuzzy anchor dominates.
    @return (doomed edge triples, verdict counter).
    @version 2
    """
    anchors = _anchors(rows, identity)
    doomed: list[tuple[int, int, str]] = []
    tally: Counter = Counter()
    for caller, callee, source, confidence in rows:
        if confidence != CALL_MATCH_FUZZY or source not in FANOUT_SOURCES:
            continue
        if callee not in identity:
            continue
        name, qualified = identity[callee]
        anchored = anchors.get((caller, name))
        if not anchored:
            tally["unanchored_kept"] += 1
        elif qualified in anchored:
            tally["same_identity_kept"] += 1
        elif any(frozenset((qualified, a)) in overrides for a in anchored):
            tally["override_kept"] += 1
        else:
            tally["dominated_deleted"] += 1
            doomed.append((caller, callee, source))
    return doomed, tally


## @brief Delete the dominated fan-out rows, one statement for the whole set.
## @param conn Open connection to the database being built.
## @param doomed (caller, callee, source) triples to remove.
## @return Number of rows actually deleted.
## @version 2
## @dg_internal
def _delete(conn: sqlite3.Connection, doomed: list[tuple[int, int, str]]) -> int:
    """Deletes on the full `(caller_rowid, callee_rowid, source)` key — the table's
    own UNIQUE key — so one triple can never match a row from a different layer.
    Targeting `(caller, callee)` alone would take the non-fuzzy anchor row down
    with the guess.

    @brief Remove the doomed fan-out rows.
    @return Rows deleted.
    @version 2
    """
    if not doomed:
        return 0
    return conn.executemany(
        "DELETE FROM call_edges WHERE caller_rowid = ? AND callee_rowid = ? AND source = ?",
        doomed,
    ).rowcount


## @brief Report what the pass deleted and, as importantly, what it spared.
## @param tally Verdict counter from `classify_dominated`.
## @param deleted Rows actually removed.
## @return None.
## @version 2
## @dg_internal
def _log_verdict(tally: Counter, deleted: int) -> None:
    """Names all four verdicts every time, including the zeros. A silent exemption
    is indistinguishable from an exemption that never fires, and both of this
    pass's exemptions exist because the unexempted version was wrong.

    @brief Log the dominated-fuzzy verdict breakdown.
    @return None.
    @version 2
    """
    logger.info(
        "call_edges: dominated-fuzzy suppression — deleted %d fan-out row(s) a non-fuzzy "
        "anchor dominated; KEPT %d same-identity (same function, weaker layer), "
        "%d virtual override(s) of an anchor, %d unanchored (no stronger evidence exists)",
        deleted,
        tally["same_identity_kept"],
        tally["override_kept"],
        tally["unanchored_kept"],
    )


## @brief Delete AST name-fan-out call edges that a non-fuzzy anchor dominates (gh#26).
## @param conn Open connection to the database being built.
## @return Number of call_edges rows deleted.
## @version 1
## @req REQ-DDB-PIPE-009
def prune_dominated_fuzzy_edges(conn: sqlite3.Connection) -> int:
    """Run as its own pipeline stage AFTER every call-edge layer, unlike the
    self-edge guard which is embedded in Layer 3. The placement is the whole
    reason this is a separate stage: an anchor may come from `macro_hop`,
    `fnptr` or `declared_dispatch`, so judging the fan-out before those layers
    have run would spare rows a later layer disproves. It still sits ABOVE
    `extract_threads` and `mark_reachability`, which is free — deleting only
    fuzzy rows cannot change a traversal that skips fuzzy rows.

    Non-raising on a thin index: a database with no `call_edges` table at all
    returns 0 rather than failing a build, matching how every other augmentation
    stage treats a missing predecessor.

    @brief Delete the dominated fuzzy fan-out rows from call_edges.
    @return Rows deleted.
    @version 1
    """
    try:
        rows = conn.execute(
            "SELECT caller_rowid, callee_rowid, source, confidence FROM call_edges"
        ).fetchall()
    except sqlite3.OperationalError:
        logger.info("call_edges: dominated-fuzzy suppression — no call_edges table, skipping")
        return 0
    identity = _identity_index(conn)
    doomed, tally = classify_dominated(rows, identity, _override_pairs(conn, identity))
    deleted = _delete(conn, doomed)
    _log_verdict(tally, deleted)
    return deleted


## @brief Pipeline stage: open the built database and run the suppression pass.
## @param db_path Path to the database being built.
## @return Number of call_edges rows deleted.
## @version 1
## @req REQ-DDB-PIPE-009
def prune_dominated_fuzzy_call_edges(db_path: Path) -> int:
    """The Path-taking form every other stage in `_build_stages` has, kept separate
    from the connection-taking rule above so a test can exercise the rule against a
    hand-built `memberdef` without a real build.

    @brief Run dominated-fuzzy suppression against a database path.
    @return Rows deleted.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    try:
        deleted = prune_dominated_fuzzy_edges(conn)
        conn.commit()
    finally:
        conn.close()
    return deleted
