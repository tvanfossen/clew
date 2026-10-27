# SPDX-License-Identifier: MIT
"""WHEN `dossier` MISSED, HAD clew JUST SERVED THAT SPELLING? — counted, no judge, no grading.

`scripts/selector_waste.py` counts how often a `dossier` call came back empty and sorts the
missed subjects by SHAPE: a file path, a qualified name, a bare name with no row. This asks the
next question, which is the one that decides whether a miss is clew's fault: **was the string the
caller passed one that clew itself had printed in an earlier reply?**

A bare name the index does not hold is a reader guessing, and no change to this tool prevents it.
A spelling clew put on the wire under a `name` field — and then refused as a `subject` — is a
contract this tool broke with itself, and the measurement separates the two.

WHAT IT MEASURED ON THE 1.1.0 GRID (`acceptance/runs/2026-10-19-n3`): see the printed table. The
finding that drove C7 was that the `threads` corpus serves
`{"name": "HealthMonitor::monitor_loop", "entry": "monitor_loop"}` while subject resolution
matched only the bare `memberdef.name`, so the field a reader is told to hand back was the one
field that could not be handed back.

**IT REPORTED AN INFLATED COUNT ON ITS FIRST RUN, AND THAT WAS THIS SCRIPT'S OWN DEFECT.** The
first version walked every `tool_result` BLOCK rather than pairing blocks by `tool_use` id, so a
transcript that repeats a row counted the same miss several times: 157 missed `index_only`
subjects against `selector_waste.py`'s 92 for the same cells. That is the exact inflation
`selector_waste.py`'s own header records — one cell's JSONL held 30 `tool_use` blocks against 16
distinct ids — reproduced by a second script written with the first one's lesson in front of it.
The numerator and denominator were both inflated, so the RATIO survived roughly intact, which is
the kind of error that reads as harmless and is not: the absolute figure was going into a commit
message. It now reuses `selector_waste._blocks`, so there is one pairing rule rather than two.

ABSENCE IS NOT EMPTINESS. A cell whose transcript cannot be found is reported in `unreadable`,
never as a cell with nothing to attribute.

Usage:
    .venv/bin/python scripts/served_spelling_audit.py acceptance/runs/<date>/
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from selector_waste import _blocks, missed_subjects  # noqa: E402

## Where the CLI keeps a session transcript. The run directory holds only the final result and the
## usage envelope — the per-call blocks live here — which is why this is reachable at all and also
## why it is fragile: a culled transcript takes the measurement with it.
PROJECTS = Path.home() / ".claude" / "projects"

## The reply keys whose value a reader is invited to hand back as a `subject`. `name` is the one
## that matters and the one `search`'s own prose points at; the rest are here because the frozen
## transcripts show the model using them that way.
NAME_KEYS = frozenset({"name", "entry", "spawn_function", "symbol", "qualified", "path", "file"})

_PATHISH = re.compile(r"\.(c|h|cpp|hpp|cc|py|rs|md|txt|ya?ml|pl|pm|mk|json|ts|tsx|sh)$", re.I)


##
# @brief Every string an earlier reply offered under a name-like key.
# @param obj A parsed reply, or any part of one.
# @param out Accumulator mapping key -> the strings served under it.
# @return None; `out` is updated in place.
# @version 1
def harvest_served(obj: object, out: dict[str, set[str]]) -> None:
    """RECURSIVE BECAUSE THE REPLIES ARE NESTED — a batch carries `results[]`, a dossier carries
    `callers[]`, a thread inventory carries `threads[]` — and the key that matters sits at a
    different depth in each. Keyed by the FIELD NAME so a finding can say which surface served
    the rejected spelling, which is what makes it fixable rather than merely counted.

    @brief Collect the spellings a reply put on the wire.
    @return None.
    @version 1
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in NAME_KEYS and isinstance(value, str) and value:
                out.setdefault(key, set()).add(value)
            harvest_served(value, out)
    elif isinstance(obj, list):
        for value in obj:
            harvest_served(value, out)


##
# @brief The shape of a missed subject, as a reader would have written it.
# @param subject The subject that missed.
# @return One of 'file path', 'qualified', 'bare'.
# @version 1
def shape(subject: str) -> str:
    """SHAPE, NOT CAUSE. It says what the caller typed, which is all this function can know; why
    the index did not hold it is `selector_waste.classify_miss`'s question.

    A path is tested FIRST because a path contains a `.` and would otherwise read as a Python
    qualification — `src/app.ts` is not `src/app` dot `ts`.

    @brief Classify a missed subject by spelling.
    @return The shape.
    @version 1
    """
    if "/" in subject or _PATHISH.search(subject):
        return "file path"
    if "::" in subject or ("." in subject and not subject.startswith(".")):
        return "qualified"
    return "bare"


##
# @brief Attribute one cell's missed subjects to the keys that served their spellings.
# @param path The session transcript.
# @return (totals, by served key, by shape).
# @version 1
def audit_cell(path: Path) -> tuple[Counter, Counter, Counter]:
    """TWO PASSES OVER ONE PAIRING. Every reply in the cell is harvested for served spellings
    first, then every missed subject is looked up in that set — so a spelling served LATER than
    the miss still counts. That is deliberate and it is the conservative direction for the claim
    being made: it can only overstate how much clew served, and the finding is that clew served
    too much of it.

    @brief Attribute a cell's misses.
    @return The three counters.
    @version 1
    """
    uses, results = _blocks(path)
    served: dict[str, set[str]] = {}
    for reply in results.values():
        try:
            parsed = json.loads(reply)
        except ValueError:
            continue
        harvest_served(parsed, served)

    totals: Counter = Counter()
    by_key: Counter = Counter()
    by_shape: Counter = Counter()
    for call_id, block in uses.items():
        if "dossier" not in str(block.get("name") or ""):
            continue
        raw = (block.get("input") or {}).get("subject")
        requested = [str(s) for s in (raw if isinstance(raw, list) else [raw])]
        for name in missed_subjects(results.get(call_id, ""), requested):
            totals["missed"] += 1
            by_shape[shape(name)] += 1
            keys = sorted(k for k, vals in served.items() if name in vals)
            if keys:
                totals["served_by_clew"] += 1
                by_key[", ".join(keys)] += 1
    return totals, by_key, by_shape


##
# @brief Audit every index-bearing cell of a run.
# @param run The run directory.
# @return Process exit status.
# @version 1
def main(run: Path) -> int:
    """@brief Print the attribution table for one run.
    @return 0, or 2 when the run holds no readable transcript.
    @version 1
    """
    totals: Counter = Counter()
    by_key: Counter = Counter()
    by_shape: Counter = Counter()
    unreadable: list[str] = []

    for target in sorted(p.name for p in run.iterdir() if (p / "answers").is_dir()):
        for raw in sorted((run / target / "answers").glob("*.raw.json")):
            if "_baseline_" in raw.name:
                continue
            session = json.loads(raw.read_text("utf-8")).get("session_id")
            hits = sorted(PROJECTS.glob(f"*/{session}.jsonl")) if session else []
            if not hits:
                unreadable.append(f"{target}/{raw.stem}")
                continue
            t, k, s = audit_cell(hits[0])
            totals += t
            by_key += k
            by_shape += s

    missed = totals["missed"]
    if not missed and unreadable:
        print(f"no readable transcript for {len(unreadable)} cell(s); nothing measured")
        return 2
    served = totals["served_by_clew"]
    print(f"run: {run}")
    print(f"missed dossier subjects (index-bearing arms, de-duplicated by tool_use id): {missed}")
    if missed:
        print(
            f"of those, the spelling was SERVED by an earlier clew reply: {served} "
            f"({served / missed * 100:.1f}%)"
        )
    print("\nby spelling the caller used:")
    for name, n in by_shape.most_common():
        print(f"  {n:4d}  {name}")
    print("\nby the reply key that carried the rejected spelling:")
    for key, n in by_key.most_common():
        print(f"  {n:4d}  {key}")
    ## NAMED, NEVER COUNTED AS ZERO WASTE. A culled transcript is a cell this run cannot speak
    ## for, and reporting it as clean would be the flattering reading.
    print(f"\nunreadable transcripts: {len(unreadable)}")
    for cell in unreadable[:10]:
        print(f"  {cell}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(Path(sys.argv[1])))
