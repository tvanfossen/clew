# SPDX-License-Identifier: MIT
"""Per-flow lanes: the lanes a flow's DIAGRAM is drawn on (UX review A-2, owner Q/A 2026-11-22).

MEASURED on clew's own 36 master flows (be732054, the derived Flow of each page): drawn on the
map's block lanes, 85-95% of arrows were self-calls — the dossier flow 218 of 243, the CLI's 366
of 400. Drawn on files the same flows have 2-15x more calls between lanes (dossier 90 vs 26), and
directory levels collapse to one lane (everything is under `clew/`).

So each flow takes whichever of BLOCKS or FILES shows more calls between lanes; a tie keeps the
blocks (coarser, and the map's own words). File lanes are capped at seven: the six files the flow
touches most keep a lane, the rest share one "other files" lane.

THE DRAWING ONLY. `clew wiki flow` (its JSON is under semver) and the diagram exports keep the
lanes `derive_flow` gave; nothing here reads the index.

@brief Choose a flow diagram's lanes.
@version 1
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from .flow import Flow, Lane, Step

## The lane the quietest files share.
OTHER = "other files"
## Most lanes a file-laned diagram draws (OTHER included).
_MAX_LANES = 7


## @brief The flow redrawn on its files when that shows more calls between lanes, else unchanged.
## @param flow The derived flow.
## @return The flow to draw (the same object when its lanes stay).
## @version 1
## @utility
def per_flow_lanes(flow: Flow) -> Flow:
    """@brief Per-flow lanes. @return Flow."""
    sides = [_sides(s) for s in flow.steps]
    keep = _kept(sides)
    pairs = [tuple(f if f in keep else OTHER for f in pair) for pair in sides]
    cross_files = sum(a != b for a, b in pairs)
    cross_now = sum(s.from_lane != s.to_lane for s in flow.steps)
    if cross_files <= cross_now:
        return flow
    order = list(dict.fromkeys(x for pair in pairs for x in pair if x != OTHER))
    if any(OTHER in pair for pair in pairs):
        order.append(OTHER)
    steps = tuple(
        replace(s, from_lane=a, to_lane=b) for s, (a, b) in zip(flow.steps, pairs, strict=True)
    )
    lanes = tuple(Lane(x, x) for x in order)
    return replace(flow, lanes=lanes, steps=steps, lane_strategy="files")


## @brief A step's (caller file, callee file); a stub stays in its caller's file.
## @param step The step.
## @return The pair.
## @version 1
## @utility
def _sides(step: Step) -> tuple[str, str]:
    """@brief Files. @return Pair."""
    caller = step.site_file or "(unknown file)"
    return caller, (step.file or caller) if step.callee else caller


## @brief The files that keep their own lane: all of them, or the six busiest.
## @param sides (caller, callee) file per step.
## @return Files with a lane.
## @version 1
## @utility
def _kept(sides: list[tuple[str, str]]) -> set[str]:
    """@brief Kept files. @return Set."""
    counts = Counter(f for pair in sides for f in pair)
    if len(counts) <= _MAX_LANES:
        return set(counts)
    return {f for f, _n in counts.most_common(_MAX_LANES - 1)}
