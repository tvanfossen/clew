# SPDX-License-Identifier: MIT
"""A sequence diagram FORMED from the index: lanes, ordered steps, frames.

1.4.0 Track 4, W3 (#67's fourth consumer: "most of a sequence diagram is already in the index").
From an entry function the flow walks the call graph by IDENTITY (W1's `_identity_call_hops`, so a
namesake's calls never appear as this function's), in each caller's own source ORDER (W2's
`call_sequence`, which also supplies the loop / if / try frames around each call), and puts every
function in a LANE:

  * `files` — the file the function's body is in;
  * `packages` — that file's component, by the map's rule (`graph.component_of`: `clew/query`,
    not `clew`);
  * `threads` — the threads whose membership includes it (`thread_of`), or `unattributed`.

EVERY STEP IS AN INDEX EDGE. A call the index did not resolve to an indexed function (a library
call, an unresolved member call) is not drawn — the step list is what the index KNOWS, and a call
site naming several identities is drawn once with all of them listed in `ambiguous` rather than
guessing one. A callee already expanded earlier in the flow is drawn again as a message but not
expanded twice, which keeps a diagram finite without hiding that the call happens.

@brief Derive a sequence flow from the index.
@version 2
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..query._common import connect, function_candidates, identity_rowids, qualified_name_of
from ..query.callsites import Frame, call_sequence
from ..query.traversal import _definition, _identity_call_hops

## The schema version of the flow JSON `clew wiki flow` prints.
FLOW_VERSION = 1
## Lane strategies.
LANES = ("files", "packages", "threads")


## How deep a call measured as run is followed (round 5), and the default step cap of a measured
## flow; both bound a diagram drawn from coverage, and `Flow.capped` says when the cap stopped it.
MEASURED_LEVELS, MEASURED_STEP_CAP = 12, 400


## @brief One lane of the diagram.
## @version 1
@dataclass(frozen=True)
class Lane:
    """@brief A lane: an id and a human label. @version 1"""

    id: str
    label: str


## @brief One message: a call from one function to another, with its frames.
## v2: `site_file` — the file the call is IN (the caller's), which `line` is a line of; `file`
## stays the callee's file. A link built from `file` and `line` pointed into the wrong file.
## v3 (round 5): `not_run` — a STUB standing for that many of the caller's calls no test ran
## (callee empty); only a measured flow has stubs.
## @version 3
@dataclass(frozen=True)
class Step:
    """@brief A call step in diagram order. @version 2"""

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
    site_file: str = ""
    not_run: int = 0


## @brief A derived flow.
## v2 (round 5): `measured` (expanded by per-test coverage) and `capped` (the step cap stopped it).
## @version 2
@dataclass(frozen=True)
class Flow:
    """@brief Lanes and ordered steps from one entry. @version 2"""

    entry: str
    entry_qualified: str
    depth: int
    lane_strategy: str
    lanes: tuple[Lane, ...] = ()
    steps: tuple[Step, ...] = ()
    flow_version: int = FLOW_VERSION
    measured: bool = False
    capped: bool = False


## @brief Derive the flow from an entry function.
## @param db The index.
## @param repo_root The working tree (source is read for call order and frames).
## @param entry The entry function's bare name.
## @param qualified Optional identity selector for the entry.
## @param depth How many call levels to expand (1 = the entry's own calls).
## @param lanes One of LANES.
## @param stop_at Bare names whose calls are not expanded.
## @param file Only the entry identity whose body is in this file (two `main`s share a name).
## @return The Flow.
## v2: `file` — select the entry by its file; its first hops use only that file's rowids.
## v3: the FILE chooses the identity (`_entry_rowids`); found in CI, where doxygen 1.9.8 gave two
## same-named mains distinct definitions and the default guess picked the other one.
## @param executed Lines any test ran, per file (round 5): a call that ran expands past `depth`;
## a measured caller's calls that never ran fold into one `not_run` stub.
## @param max_steps Stop after this many steps (`capped` says so); default 400 when measured.
## v4 (OWNER 2026-11-17, round 5): master flows expand what tests ran.
## @version 4
## @req REQ-DDB-WIKI-001
## @req REQ-DDB-WIKI-041
def derive_flow(
    db: Path | str,
    repo_root: Path | str,
    entry: str,
    *,
    qualified: str | None = None,
    depth: int = 3,
    lanes: str = "files",
    stop_at: tuple[str, ...] = (),
    file: str | None = None,
    executed: dict[str, set[int]] | None = None,
    max_steps: int | None = None,
) -> Flow:
    """REFUSES BY NAME an entry the index does not hold and a lane strategy it does not know, so a
    typo never yields an empty diagram that looks like a function with no calls.

    @brief Build a Flow.
    @return The flow.
    @version 2
    """
    if lanes not in LANES:
        raise ValueError(f"unknown lane strategy {lanes!r}; known: {', '.join(LANES)}")
    with connect(db) as conn:
        walker = _Walker(conn, Path(repo_root), lanes, frozenset(stop_at))
        walker.executed = executed
        walker.max_steps = max_steps or (MEASURED_STEP_CAP if executed is not None else 0)
        rowids = _entry_rowids(conn, walker, entry, qualified, file)
        if not rowids:
            raise ValueError(
                f"no function {entry!r} in this index (qualified={qualified!r}, file={file!r})"
            )
        full = qualified_name_of(entry, _definition(conn, rowids[0]))
        walker.walk(entry, full, min(rowids), depth, 1, frozenset({full}), rowids if file else None)
        ordered = tuple(walker.lane_order)
        return Flow(
            entry=entry,
            entry_qualified=full,
            depth=depth,
            lane_strategy=lanes,
            lanes=tuple(Lane(id=lane, label=lane) for lane in ordered),
            steps=tuple(walker.steps),
            measured=executed is not None,
            capped=walker.capped,
        )


## @brief The rowids of the entry: its identity, chosen by file when one is given.
## @param conn Open connection.
## @param walker The walker (for each row's file).
## @param entry The function name.
## @param qualified An identity selector, or None.
## @param file The entry's file, or None.
## @return Rowids; [] when nothing matches.
## @version 1
## @dg_internal
def _entry_rowids(
    conn: sqlite3.Connection, walker: _Walker, entry: str, qualified: str | None, file: str | None
) -> list[int]:
    """THE FILE CHOOSES THE IDENTITY. Filtering the default identity by file found nothing when
    two same-named functions were distinct identities and the guess picked the other one — which
    depended on the doxygen version. With a file and no selector, the identity is the one whose
    row sits in that file; only that file's rows are walked.

    @brief Entry rowids.
    @return Rowids.
    """
    if not file:
        return identity_rowids(conn, entry, qualified)
    if qualified is None:
        rows = [(r, sig) for r, sig, *_rest in function_candidates(conn, entry)]
        hit = next((sig for r, sig in rows if walker.file_of(r) == file), None)
        if hit is None:
            return []
        qualified = qualified_name_of(entry, hit)
    return [r for r in identity_rowids(conn, entry, qualified) if walker.file_of(r) == file]


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
    ## v2 (round 5): coverage (`executed`), the step cap and whether it was hit.
    ## @version 2
    ## @dg_internal
    def __init__(
        self, conn: sqlite3.Connection, repo_root: Path, lanes: str, stop_at: frozenset[str]
    ) -> None:
        self.conn, self.repo_root, self.lanes, self.stop_at = conn, repo_root, lanes, stop_at
        self.steps: list[Step] = []
        self.lane_order: list[str] = []
        self.expanded: set[str] = set()
        self._lane_cache: dict[int, str] = {}
        ## Round 5: lines any test ran (None = unmeasured), the step cap (0 = none), whether hit.
        self.executed: dict[str, set[int]] | None = None
        self.max_steps = 0
        self.capped = False

    ## @brief Emit the steps of one caller, recursing into callees in call order.
    ## @param name The caller's bare name.
    ## @param qual Its full qualified name.
    ## @param rowid Its canonical rowid.
    ## @param remaining Levels left to expand.
    ## @param level This caller's call level (1 for the entry).
    ## @param path Identities on the current path (cycle guard).
    ## @param rowids The entry's selected rows, or None for the whole identity.
    ## @return None.
    ## v2: passes the caller's file to each step.
    ## v3: `rowids` (an entry selected by file).
    ## v4 (round 5): a measured caller emits only the calls that ran, then one `not_run` stub; a
    ## caller whose FILE the coverage does not hold was not measured and is walked statically.
    ## @version 4
    ## @dg_internal
    def walk(
        self,
        name: str,
        qual: str,
        rowid: int,
        remaining: int,
        level: int,
        path: frozenset[str],
        rowids: list[int] | None = None,
    ) -> None:
        """A SELECTED ENTRY (`rowids`) hops from exactly those rows: an identity shared by several
        files (every `def main`) would otherwise merge their calls.

        @brief Walk one caller.
        @return None.
        """
        self.expanded.add(qual)
        caller = (self.lane(rowid), self._file(rowid))
        sequence = call_sequence(self.conn, self.repo_root, name, qual, rowids) or []
        targets: dict[str, list[tuple[str, int]]] = {}
        hop_rows = rowids or identity_rowids(self.conn, name, qual)
        for nname, nqual, nrowid, _hop in _identity_call_hops(self.conn, name, hop_rows, True):
            targets.setdefault(nname, []).append((nqual, nrowid))
        ran = None if self.executed is None else self.executed.get(caller[1])
        missed = 0
        for site in sequence:
            found = targets.get(site.callee)
            if not found:
                continue
            if self.max_steps and len(self.steps) >= self.max_steps:
                self.capped = True
                return
            if ran is not None and site.line not in ran:
                missed += 1
                continue
            self._emit(name, qual, caller, site, found, (remaining, level, path, ran is not None))
        if missed:
            self._stub(name, qual, caller, level, missed)

    ## @brief One step standing for the calls of a measured caller that no test ran.
    ## @param name Caller name.
    ## @param qual Caller qualified.
    ## @param caller (lane, file) of the caller.
    ## @param level The caller's call level.
    ## @param missed How many calls.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _stub(self, name: str, qual: str, caller: tuple[str, str], level: int, missed: int) -> None:
        """@brief Record a not-run stub. @return None."""
        if self.max_steps and len(self.steps) >= self.max_steps:
            self.capped = True
            return
        self.steps.append(
            Step(
                caller=name,
                caller_qualified=qual,
                callee="",
                callee_qualified="",
                from_lane=caller[0],
                to_lane=caller[0],
                file=caller[1],
                line=0,
                depth=level,
                site_file=caller[1],
                not_run=missed,
            )
        )

    ## @brief Emit one step and, when it may, expand the callee.
    ## @param name Caller name.
    ## @param qual Caller qualified.
    ## @param caller (lane, file) of the caller.
    ## @param site The call site.
    ## @param found The callee identities the caller's edges name for this site's callee.
    ## @param walk_state (remaining, level, path, whether the call was measured as run).
    ## @return None.
    ## v2: records the call site's file.
    ## v3 (round 5): a call measured as run expands past the depth, up to MEASURED_LEVELS.
    ## @version 3
    ## @dg_internal
    def _emit(
        self,
        name: str,
        qual: str,
        caller: tuple[str, str],
        site: object,
        found: list[tuple[str, int]],
        walk_state: tuple[int, int, frozenset[str]],
    ) -> None:
        """@brief Record a step; recurse once per identity. @return None."""
        remaining, level, path, measured = walk_state
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
                from_lane=caller[0],
                to_lane=self.lane(nrowid),
                file=self._file(nrowid),
                line=site.line,
                depth=level,
                frames=site.frames,
                ambiguous=ambiguous,
                expanded_above=already and not ambiguous,
                site_file=caller[1],
            )
        )
        shallow = level >= MEASURED_LEVELS if measured else remaining <= 1
        if ambiguous or already or shallow or site.callee in self.stop_at or nqual in path:
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
    ## v2: `packages` lanes are the map's components (round 3, P1e): a flow inside one top-level
    ## package drew a single lane.
    ## @version 2
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
            from .graph import component_of

            return component_of(rel) if rel else "(root)"
        return rel or "(unknown file)"

    ## @brief The file a function's body is in (public: the entry selection uses it).
    ## @param rowid The function's rowid.
    ## @return Repo-relative path, or "".
    ## @version 1
    ## @dg_internal
    def file_of(self, rowid: int) -> str:
        """@brief File of a function. @return Path or ""."""
        return self._file(rowid)

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
