# SPDX-License-Identifier: MIT
"""HOW OFTEN DOES `dossier` RETURN NOTHING, AND WHY — counted, with no judge and no grading.

WHY IT EXISTS. Answer completeness needs a judge: 3,348 calls for one pass over the 1.1.0 grid.
Whether a tool call came back empty does not. It is a fact sitting in the frozen session
transcripts, so this measures it for free — which is the only reason the 1.2.0 claim about wasted
calls is cheap to make and cheap to re-check.

WHAT IT MEASURED ON THE 1.1.0 GRID (144 cells, `acceptance/runs/2026-10-19-n3`):
`index_only` 70 of 244 dossier calls returned nothing (28.7%); the blended arm 22 of 101 (21.8%);
`baseline` made zero dossier calls, which is the arm fence holding and the reason the rest is
trustworthy. Per missed SUBJECT — 237 across 92 calls, because a batched call carries several —
121 were a bare name the index does not hold, 54 a qualified name passed as `subject`, 48 a file
path passed as `subject`, and 14 a `qualified` that could never match.

**IT REPORTED 0.0% ON ITS FIRST RUN, AND THAT WAS THIS SCRIPT'S OWN DEFECT.** It passed the reply
through `json.dumps` before matching, which escapes the quotes, so `"found": false` became
`\\"found\\": false` and the substring check could not fire. It also truncated the reply to 4,000
characters. A broken detector read as a perfect score on the very axis under test — the most
flattering possible failure. `_is_miss` is now spelling-tolerant, nothing is truncated, and
`reply_mentions_found` is counted beside it so a zero can be told from a detector matching
nothing at all. `tests/test_selector_waste.py` pins all of it.

ABSENCE IS NOT EMPTINESS. A cell whose transcript cannot be read is reported in `unreadable`,
never as a cell with zero waste. Zero is the best possible result here and must not be handed out
for a missing file.

COUNTED BY `tool_use` ID, NOT BY BLOCK, for the reason `acceptance/execute.py` records: one 1.1.0
cell's JSONL held 30 `tool_use` blocks against SIXTEEN distinct ids, so counting blocks reported
nearly double. The inflation was uniform across arms, which is the hardest kind to notice.

Usage:
    .venv/bin/python scripts/selector_waste.py acceptance/runs/<date>/
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"

ARMS = ("baseline", "index_only", "index")

## Extensions that mean the model passed a FILE where a symbol was wanted. Not an exhaustive list
## of source types — only the ones that actually appeared as a `subject` on the 1.1.0 grid, so the
## classifier stays a report of what was observed rather than a guess about what might be.
_PATHISH = (".c", ".h", ".cpp", ".hpp", ".cc", ".py", ".rs", ".md", ".txt", ".yaml", ".yml")


def result_text(content: object) -> str:
    """Flatten a `tool_result`'s content into the reply text, WHOLE.

    Never `json.dumps`, and never truncated — both were this script's original defects and both
    produced a clean zero. A measurement must not reshape or clip the thing it measures.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        return "\n".join(parts)
    return "" if content is None else str(content)


def missed_subjects(reply: str, requested: list[str]) -> list[str]:
    """Which of a call's subjects came back unanswered — PER ENTRY, never per call.

    **THE SECOND VERSION OF THIS SCRIPT OVERSTATED EVERY NUMBER IT PRODUCED, and the cause is one
    key.** A batch reply's top-level `found` is a COUNT OF HITS, not a boolean: measured on the
    real surface, `dossier(["execute", "absent"])` returns `found: 1` with `results[1].found ==
    False`. A substring search for `"found":false` therefore fired on any batch with a single bad
    name, so:

      - the call-level rate counted a partial miss as a total one, and
      - the per-subject breakdown then classified every subject in that call as missed, INCLUDING
        the ones that hit.

    That is how 121 subjects came to be labelled "a bare name the index does not hold" while
    `memberdef` held them as functions all along. The names were fine; the attribution was not.

    So the reply is PARSED, and each entry is attributed by its own `found`. A single reply has no
    `results` array: top-level `found is False` is the whole call missing, and a hit carries no
    `found` key at all.
    """
    try:
        payload = json.loads(reply)
    except ValueError:
        ## UNPARSEABLE IS UNKNOWN, NOT CLEAN. Returning [] here would credit a reply we cannot
        ## read as a full hit, which is the flattering reading on the axis under test.
        ##
        ## BACKSLASHES STRIPPED, because the spelling that lands here is the escaped one:
        ## `json.dumps` turns `"found": false` into `\\"found\\": false`, which is not valid JSON
        ## and so arrives in this branch. Matching without stripping is how the first version of
        ## this script reported a clean 0.0% miss rate.
        squashed = reply.replace(" ", "").replace("\\", "")
        return ["<unparseable>"] if '"found":false' in squashed else []
    if not isinstance(payload, dict):
        return []
    entries = payload.get("results")
    if isinstance(entries, list):
        return [
            str(entry.get("name") or "<unnamed>")
            for entry in entries
            if isinstance(entry, dict) and entry.get("found") is False
        ]
    if payload.get("found") is False:
        return [requested[0]] if requested else ["<unnamed>"]
    return []


def classify_miss(subject: object, passed_qualified: bool) -> list[str]:
    """Why a miss happened, one entry per subject in the call.

    ONE ENTRY PER SUBJECT, NOT PER CALL. A batched `dossier(subject=[a, b, c])` that misses is one
    wasted round trip but three unanswered names, and the two are different claims about the same
    data. Callers must say which denominator they are quoting.

    `qualified` is checked FIRST because it dominates: if the call passed a selector at all, the
    selector is why it failed, whatever the subject looked like.
    """
    subjects = subject if isinstance(subject, list) else [subject]
    out: list[str] = []
    for one in subjects:
        text = str(one)
        if passed_qualified:
            out.append("passed `qualified` that could not match")
        elif "/" in text or text.endswith(_PATHISH):
            out.append("a FILE PATH as subject")
        elif "::" in text or "." in text:
            out.append("a QUALIFIED name as subject")
        else:
            out.append("a bare name the index does not hold")
    return out


def transcript_for(raw: Path) -> Path | None:
    """Locate the session transcript for one frozen cell, or None.

    The `.raw.json` envelope names the session; `.meta.json` does NOT carry it, which is why this
    reads the envelope. The glob across every project slug is deliberate — a run whose repo path
    moved still resolves, and `acceptance/execute.count_tools` falls back the same way.
    """
    try:
        session = json.loads(raw.read_text("utf-8")).get("session_id")
    except (OSError, ValueError):
        return None
    if not session:
        return None
    hits = sorted(PROJECTS.glob(f"*/{session}.jsonl"))
    return hits[0] if hits else None


def _blocks(path: Path) -> tuple[dict[str, dict], dict[str, str]]:
    """Collect `tool_use` blocks by id and `tool_result` text by the id it answers.

    Read independently and joined by id, because a result block does not name the tool — only the
    call it answers. `setdefault` is what de-duplicates the repeated rows.
    """
    uses: dict[str, dict] = {}
    results: dict[str, str] = {}
    for line in path.read_text("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        content = ((row.get("message") or {}).get("content")) or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("id"):
                uses.setdefault(str(block["id"]), block)
            elif block.get("type") == "tool_result" and block.get("tool_use_id"):
                results.setdefault(str(block["tool_use_id"]), result_text(block.get("content")))
    return uses, results


def count_cell(path: Path) -> tuple[Counter, Counter]:
    """Count dossier behaviour in one session transcript.

    Returns (totals, miss causes). Causes are keyed per SUBJECT and totals per CALL — see
    `classify_miss`.
    """
    uses, results = _blocks(path)
    totals: Counter = Counter()
    causes: Counter = Counter()
    seen: set[str] = set()
    for call_id, block in uses.items():
        if "dossier" not in str(block.get("name") or ""):
            continue
        totals["dossier_calls"] += 1
        args = block.get("input") or {}
        qualified = bool(args.get("qualified"))
        if qualified:
            totals["qualified_passed"] += 1
        raw_subject = args.get("subject")
        requested = [
            str(s) for s in (raw_subject if isinstance(raw_subject, list) else [raw_subject])
        ]
        totals["subjects_requested"] += len(requested)
        key = json.dumps(raw_subject)
        if key in seen:
            totals["repeat_subject"] += 1
        seen.add(key)
        reply = results.get(call_id, "")
        ## COUNTED EVEN WHEN NOTHING MATCHES. If `subjects_missed` is 0 while this is 0 too, the
        ## detector never saw a reply it could read and the run says nothing either way.
        if "found" in reply:
            totals["reply_mentions_found"] += 1

        missed = missed_subjects(reply, requested)
        totals["subjects_missed"] += len(missed)
        if missed:
            ## A CALL IS "PARTIAL" WHEN SOME SUBJECTS ANSWERED. Counting it as a full miss is the
            ## error the previous version made, so the two are now separate rows.
            if len(missed) == len(requested):
                totals["calls_fully_missed"] += 1
            else:
                totals["calls_partly_missed"] += 1
            if qualified:
                totals["qualified_missed"] += 1
            for name in missed:
                causes.update(classify_miss(name, qualified))
        elif qualified:
            totals["qualified_resolved"] += 1
    return totals, causes


def main(argv: list[str]) -> int:
    """Report dossier waste per arm over a frozen run directory."""
    if not argv:
        print("usage: selector_waste.py <run-dir>", file=sys.stderr)
        return 2
    run = Path(argv[0])
    per_arm: dict[str, Counter] = {}
    causes: Counter = Counter()
    cells: Counter = Counter()
    unreadable: list[str] = []

    for raw in sorted(run.glob("*/answers/*.raw.json")):
        arm = next((a for a in ("index_only", "baseline", "index") if f"_{a}_" in raw.name), "?")
        path = transcript_for(raw)
        if path is None:
            unreadable.append(raw.name)
            continue
        cells[arm] += 1
        totals, cell_causes = count_cell(path)
        per_arm.setdefault(arm, Counter()).update(totals)
        causes.update(cell_causes)

    print(f"run: {run}")
    print(
        f"{'arm':<12}{'cells':>6}{'calls':>7}{'subjects':>10}{'subj.miss':>11}"
        f"{'full':>6}{'part':>6}{'qual=':>7}{'q.miss':>8}{'repeat':>8}"
    )
    for arm in ARMS:
        got = per_arm.get(arm)
        if got is None:
            continue
        print(
            f"{arm:<12}{cells[arm]:>6}{got['dossier_calls']:>7}{got['subjects_requested']:>10}"
            f"{got['subjects_missed']:>11}{got['calls_fully_missed']:>6}"
            f"{got['calls_partly_missed']:>6}{got['qualified_passed']:>7}"
            f"{got['qualified_missed']:>8}{got['repeat_subject']:>8}"
        )

    for arm in ("index_only", "index"):
        got = per_arm.get(arm)
        if not got or not got["subjects_requested"]:
            continue
        calls = got["dossier_calls"]
        subjects = got["subjects_requested"]
        ## THE GUARD AGAINST A FLATTERING ZERO, printed rather than assumed.
        seen_field = got["reply_mentions_found"]
        ## TWO DENOMINATORS, BOTH STATED. A batched call that answered 7 of 8 is one partly-missed
        ## call and one unanswered subject; reporting it as a missed call is the error the second
        ## version of this script made.
        print(
            f"\n{arm}: {got['subjects_missed']}/{subjects} SUBJECTS unanswered "
            f"({got['subjects_missed'] / subjects:.1%} of subjects asked); of {calls} calls, "
            f"{got['calls_fully_missed']} answered nothing and {got['calls_partly_missed']} "
            f"answered some. {got['repeat_subject']} repeated a subject; "
            f"{got['qualified_passed']} passed `qualified`, of which {got['qualified_missed']} "
            f"missed. {seen_field} repl(ies) mentioned `found` at all."
        )
        if not seen_field:
            print(
                f"  WARNING: no reply in {arm} mentioned `found`. A 0% miss rate here means the "
                f"detector saw nothing it understands, NOT that nothing failed."
            )

    if causes:
        subjects = sum(causes.values())
        print(f"\nwhy each miss happened ({subjects} subjects across the missed calls):")
        for cause, count in causes.most_common():
            print(f"  {count:5d}  {cause}")

    ## REPORTED EVEN WHEN ZERO: "none unreadable" and "nobody checked" must not read alike.
    print(f"\nunreadable transcripts: {len(unreadable)}")
    for name in unreadable[:10]:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
