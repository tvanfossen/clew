# SPDX-License-Identifier: MIT
"""A sequence diagram FORMED from the index: lanes, ordered steps, frames.

1.4.0 Track 4, W3 (#67's fourth consumer: "most of a sequence diagram is already in the index").
From an entry function the flow walks the call graph by IDENTITY (W1's `_identity_call_hops`, so a
namesake's calls never appear as this function's), in each caller's own source ORDER (W2's
`call_sequence`, which also supplies the loop / if / try frames around each call), and puts every
function in a LANE:

  * `files` — the file the function's body is in;
  * `packages` — that file's top-level directory;
  * `threads` — the threads whose membership includes it (`thread_of`), or `unattributed`.

EVERY STEP IS AN INDEX EDGE. A call the index did not resolve to an indexed function (a library
call, an unresolved member call) is not drawn — the step list is what the index KNOWS, and a call
site naming several identities is drawn once with all of them listed in `ambiguous` rather than
guessing one. A callee already expanded earlier in the flow is drawn again as a message but not
expanded twice, which keeps a diagram finite without hiding that the call happens.

@brief Derive a sequence flow from the index.
@version 1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..query._common import connect, identity_rowids, qualified_name_of
from ..query.callsites import Frame, call_sequence
from ..query.traversal import _definition, _identity_call_hops

## The schema version of the flow JSON `clew wiki flow` prints.
FLOW_VERSION = 1
## Lane strategies.
LANES = ("files", "packages", "threads")


## @brief One lane of the diagram.
## @version 1
@dataclass(frozen=True)
class Lane:
    """@brief A lane: an id and a human label. @version 1"""

    id: str
    label: str


## @brief One message: a call from one function to another, with its frames.
## @version 1
@dataclass(frozen=True)
class Step:
    """@brief A call step in diagram order. @version 1"""

    caller: str
    caller_qualified: str
    callee: str
    callee_qualified: str
    from_lane: str
    to_lane: str
    file: str
    line: int
    depth: int
    frames: tuple[Frame, ...] = ()
    ambiguous: tuple[str, ...] = ()
    expanded_above: bool = False


## @brief A derived flow.
## @version 1
@dataclass(frozen=True)
class Flow:
    """@brief Lanes and ordered steps from one entry. @version 1"""

    entry: str
    entry_qualified: str
    depth: int
    lane_strategy: str
    lanes: tuple[Lane, ...] = ()
    steps: tuple[Step, ...] = ()
    flow_version: int = FLOW_VERSION


## @brief Derive the flow from an entry function.
## @param db The index.
## @param repo_root The working tree (source is read for call order and frames).
## @param entry The entry function's bare name.
## @param qualified Optional identity selector for the entry.
## @param depth How many call levels to expand (1 = the entry's own calls).
## @param lanes One of LANES.
## @param stop_at Bare names whose calls are not expanded.
## @return The Flow.
## @version 1
## @req REQ-DDB-WIKI-001
def derive_flow(
    db: Path | str,
    repo_root: Path | str,
    entry: str,
    *,
    qualified: str | None = None,
    depth: int = 3,
    lanes: str = "files",
    stop_at: tuple[str, ...] = (),
) -> Flow:
    """REFUSES BY NAME an entry the index does not hold and a lane strategy it does not know, so a
    typo never yields an empty diagram that looks like a function with no calls.

    @brief Build a Flow.
    @return The flow.
    @version 1
    """
    if lanes not in LANES:
        raise ValueError(f"unknown lane strategy {lanes!r}; known: {', '.join(LANES)}")
    with connect(db) as conn:
        rowids = identity_rowids(conn, entry, qualified)
        if not rowids:
            raise ValueError(f"no function {entry!r} in this index (qualified={qualified!r})")
        full = qualified_name_of(entry, _definition(conn, rowids[0]))
        walker = _Walker(conn, Path(repo_root), lanes, frozenset(stop_at))
        walker.walk(entry, full, min(rowids), depth, 1, frozenset({full}))
        ordered = tuple(walker.lane_order)
        return Flow(
            entry=entry,
            entry_qualified=full,
            depth=depth,
            lane_strategy=lanes,
            lanes=tuple(Lane(id=lane, label=lane) for lane in ordered),
            steps=tuple(walker.steps),
        )


## @brief The depth-first walk that emits steps in call order.
## @version 1
class _Walker:
    """ONE OBJECT PER FLOW, holding the steps, the lanes in first-seen order, the identities
    already expanded and a per-function lane cache.

    @brief Flow walk state.
    @version 1
    """

    ## @brief Prepare a walk.
    ## @param conn Open connection.
    ## @param repo_root The working tree.
    ## @param lanes Lane strategy.
    ## @param stop_at Names not to expand.
    ## @version 1
    ## @dg_internal
    def __init__(
        self, conn: sqlite3.Connection, repo_root: Path, lanes: str, stop_at: frozenset[str]
    ) -> None:
        self.conn, self.repo_root, self.lanes, self.stop_at = conn, repo_root, lanes, stop_at
        self.steps: list[Step] = []
        self.lane_order: list[str] = []
        self.expanded: set[str] = set()
        self._lane_cache: dict[int, str] = {}

    ## @brief Emit the steps of one caller, recursing into callees in call order.
    ## @param name The caller's bare name.
    ## @param qual Its full qualified name.
    ## @param rowid Its canonical rowid.
    ## @param remaining Levels left to expand.
    ## @param level This caller's call level (1 for the entry).
    ## @param path Identities on the current path (cycle guard).
    ## @return None.
    ## @version 1
    ## @dg_internal
    def walk(
        self, name: str, qual: str, rowid: int, remaining: int, level: int, path: frozenset[str]
    ) -> None:
        """@brief Walk one caller. @return None."""
        self.expanded.add(qual)
        caller_lane = self.lane(rowid)
        sequence = call_sequence(self.conn, self.repo_root, name, qual) or []
        targets: dict[str, list[tuple[str, int]]] = {}
        for nname, nqual, nrowid, _hop in _identity_call_hops(
            self.conn, name, identity_rowids(self.conn, name, qual), True
        ):
            targets.setdefault(nname, []).append((nqual, nrowid))
        for site in sequence:
            found = targets.get(site.callee)
            if not found:
                continue
            self._emit(name, qual, caller_lane, site, found, (remaining, level, path))

    ## @brief Emit one step and, when it may, expand the callee.
    ## @param name Caller name.
    ## @param qual Caller qualified.
    ## @param caller_lane Caller lane.
    ## @param site The call site.
    ## @param found The callee identities the caller's edges name for this site's callee.
    ## @param walk_state (remaining, level, path).
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _emit(
        self,
        name: str,
        qual: str,
        caller_lane: str,
        site: object,
        found: list[tuple[str, int]],
        walk_state: tuple[int, int, frozenset[str]],
    ) -> None:
        """@brief Record a step; recurse once per identity. @return None."""
        remaining, level, path = walk_state
        nqual, nrowid = found[0]
        ambiguous = tuple(sorted(q for q, _r in found)) if len(found) > 1 else ()
        callee_qual = "" if ambiguous else nqual
        already = nqual in self.expanded
        self.steps.append(
            Step(
                caller=name,
                caller_qualified=qual,
                callee=site.callee,
                callee_qualified=callee_qual,
                from_lane=caller_lane,
                to_lane=self.lane(nrowid),
                file=self._file(nrowid),
                line=site.line,
                depth=level,
                frames=site.frames,
                ambiguous=ambiguous,
                expanded_above=already and not ambiguous,
            )
        )
        if ambiguous or already or remaining <= 1 or site.callee in self.stop_at or nqual in path:
            return
        self.walk(site.callee, nqual, nrowid, remaining - 1, level + 1, path | {nqual})

    ## @brief The lane a function belongs to, recorded in first-seen order.
    ## @param rowid The function's rowid.
    ## @return The lane id.
    ## @version 1
    ## @dg_internal
    def lane(self, rowid: int) -> str:
        """@brief Lane for a function. @return Lane id."""
        if rowid not in self._lane_cache:
            self._lane_cache[rowid] = self._lane_for(rowid)
        lane = self._lane_cache[rowid]
        if lane not in self.lane_order:
            self.lane_order.append(lane)
        return lane

    ## @brief Compute a function's lane under the chosen strategy.
    ## @param rowid The function's rowid.
    ## @return The lane id.
    ## @version 1
    ## @dg_internal
    def _lane_for(self, rowid: int) -> str:
        """@brief Lane by strategy. @return Lane id."""
        if self.lanes == "threads":
            from ..query.symbols import thread_of

            name = self.conn.execute(
                "SELECT name FROM memberdef WHERE rowid = ?", (rowid,)
            ).fetchone()
            threads = sorted({t.name for t in thread_of(self.conn, str(name[0]))}) if name else []
            return "|".join(threads) or "unattributed"
        rel = self._file(rowid)
        if self.lanes == "packages":
            return rel.split("/", 1)[0] if "/" in rel else "(root)"
        return rel or "(unknown file)"

    ## @brief The file a function's body is in.
    ## @param rowid The function's rowid.
    ## @return Repo-relative path, or "".
    ## @version 1
    ## @dg_internal
    def _file(self, rowid: int) -> str:
        """@brief File of a function. @return Path or ""."""
        row = self.conn.execute(
            "SELECT p.name FROM memberdef m JOIN path p "
            "ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.rowid = ?",
            (rowid,),
        ).fetchone()
        return str(row[0]) if row else ""
