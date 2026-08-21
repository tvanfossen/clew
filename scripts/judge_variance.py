# SPDX-License-Identifier: MIT
"""Measure the LLM judge's per-mark FLIP RATE against answers already committed.

WHY THIS EXISTS. The grading architecture for the next rubric generation depends on one
number nobody has: how often does the judge change its mind about the same (mark, answer)
pair? Today grading is n=1 per mark with no vote, so the flip rate is unknown and bounded
only at <=~6% by the falsity trios — a bound, not a measurement.

If it is ~1%, the schema needs almost no deterministic scaffolding and mark authoring is
cheap. If it is ~15%, the schema must carry structure and authoring is a different job.
Designing the schema first means guessing which.

NO AGENT RUNS. Every input is a `.grade.json` already in the repository: it carries the
frozen answer prose, the mark text, and the verdict the judge gave at the time. Re-judging
those pairs costs judge calls only.

WHAT IT REPORTS, and the split is the point:
  * flip rate for CONCEPTUAL marks (no declared symbols or refs — the judge is the only
    grader) versus marks that also had an objective channel;
  * agreement with the ORIGINALLY RECORDED verdict, which is a free extra sample;
  * TRANSPORT ERRORS separately. A judge error is not a MISS. Lumping the two is how 102
    marks the judge never ruled on once counted as failures against both arms.

THREE SUBCOMMANDS, deliberately separate. `sample` is free and lets the sample be inspected
before any capacity is spent; `run` appends to JSONL so a kill costs nothing already paid
for; `report` re-reads without re-running.

Usage:
    .venv/bin/python scripts/judge_variance.py sample --n 40 --seed 7
    .venv/bin/python scripts/judge_variance.py run --k 3
    .venv/bin/python scripts/judge_variance.py report
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGETS = REPO / "acceptance" / "targets"
OUT = REPO / "acceptance" / "operational" / "judge-variance"
MANIFEST = OUT / "sample.json"
RESULTS = OUT / "verdicts.jsonl"

## Parallel judge calls. Small on purpose: these are `claude -p` subprocesses against a
## subscription, and the flakiness this measurement exists to characterise is CAUSED by
## exhausting session capacity. A wide fan-out would manufacture the errors it is counting.
WORKERS = 4

## An answer shorter than this is a stub or a path, not prose. See `_candidates`.
MIN_ANSWER_CHARS = 400


## @brief Import the bench harness, which lives outside the package.
## @return (bench_judge, grade_prompts) modules.
## @version 1
def _bench():
    """`acceptance/bench` is not an installed package, so it is imported by path.

    Importing the REAL judge rather than reimplementing the call is the whole point: a
    measurement of a judge that is not the shipped judge measures nothing.

    @brief Load the bench judge modules.
    @return (bench_judge, grade_prompts).
    @version 1
    """
    sys.path.insert(
        0, str(REPO / "acceptance" / "bench")
    )  # NOTE: bench/ was deleted in the 002 overhaul; rewire to the new grader
    import bench_judge
    import grade_prompts

    return bench_judge, grade_prompts


## @brief Every judged (mark, answer) pair in the committed grade sidecars.
## @return List of candidate dicts.
## @version 1
def _candidates() -> list[dict]:
    """Collect pairs the judge ACTUALLY ruled on.

    A mark settled objectively never reached the judge, so including it would dilute the
    flip rate with cases the judge never saw. The filter is `judge.verdict` being present,
    not `conceptual` — an objective mark whose symbols missed still goes to the judge, and
    those are exactly the borderline cases where a flip is most likely.

    @brief Judged pairs from committed sidecars.
    @return Candidates.
    @version 1
    """
    out: list[dict] = []
    for path in sorted(TARGETS.rglob("*.grade.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ## `answer` IS A FILENAME, NOT THE PROSE. The first version of this file used the
        ## field directly and spent 120 judge calls asking whether a 19-character filename
        ## demonstrated each mark. It answered MISS to most, which produced a clean-looking
        ## 55% "drift" that was 100% one-way — a result confident enough to have been
        ## reported, and entirely an artefact of the harness.
        answer_path = doc.get("answer") or ""
        if not answer_path:
            continue
        prose_file = path.parent / answer_path
        if not prose_file.is_file():
            continue
        answer = prose_file.read_text(encoding="utf-8")
        ## THE STRUCTURAL GUARD THAT WAS MISSING. An answer shorter than this is not an
        ## answer, and a judge asked to grade one will return verdicts that look like data.
        ## Refusing by length cannot be phrased around the way "did we read a file" can.
        if len(answer) < MIN_ANSWER_CHARS:
            continue
        for mark in doc.get("marks") or []:
            recorded = (mark.get("judge") or {}).get("verdict")
            if recorded not in ("HIT", "MISS"):
                continue
            out.append(
                {
                    "cell": path.stem.removesuffix(".grade"),
                    "target": path.parent.parent.name,
                    "arm": doc.get("arm", ""),
                    "model": doc.get("model", ""),
                    "mark_index": mark.get("index"),
                    "mark_text": mark.get("text", ""),
                    "conceptual": bool(mark.get("conceptual")),
                    "recorded": recorded,
                    "answer": answer,
                }
            )
    return out


## @brief Choose a stratified sample and write the manifest.
## @param n Total pairs to sample.
## @param seed Deterministic seed, recorded in the manifest.
## @return Exit code.
## @version 1
def cmd_sample(n: int, seed: int) -> int:
    """Stratify by mark shape, half and half, because the split IS the finding.

    An unstratified sample would be dominated by whichever shape is commoner and would
    report one blended rate — which is the number least useful for deciding what the schema
    must carry.

    @brief Write a stratified sample manifest.
    @param n Sample size.
    @param seed RNG seed.
    @return Exit code.
    @version 1
    """
    pool = _candidates()
    if not pool:
        print("REFUSING: no judged marks found in any committed sidecar", file=sys.stderr)
        return 2

    rng = random.Random(seed)
    by_shape: dict[bool, list[dict]] = defaultdict(list)
    for item in pool:
        by_shape[item["conceptual"]].append(item)

    half = max(1, n // 2)
    chosen: list[dict] = []
    for shape in (True, False):
        bucket = by_shape.get(shape) or []
        rng.shuffle(bucket)
        take = bucket[:half]
        chosen.extend(take)
        if len(take) < half:
            print(
                f"NOTE: only {len(take)} pairs available with conceptual={shape}, "
                f"wanted {half} — the sample is smaller than requested and this line is "
                f"the disclosure, not a silent truncation"
            )

    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(
            {
                "seed": seed,
                "requested": n,
                "pool_size": len(pool),
                "pool_conceptual": len(by_shape.get(True) or []),
                "pool_objective": len(by_shape.get(False) or []),
                "sample": chosen,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"pool: {len(pool)} judged pairs across {len({c['cell'] for c in pool})} cells")
    print(
        f"  conceptual={len(by_shape.get(True) or [])}  objective={len(by_shape.get(False) or [])}"
    )
    print(f"sampled: {len(chosen)} -> {MANIFEST.relative_to(REPO)}")
    return 0


## @brief Re-judge every sampled pair k times, appending results as they land.
## @param k Independent judge calls per pair.
## @return Exit code.
## @version 1
def cmd_run(k: int) -> int:
    """Append-only JSONL, so an interrupted run keeps everything already paid for.

    Each call is INDEPENDENT — a fresh tool-less `claude -p` with no memory of the last —
    which is what makes repeated calls a variance measurement rather than a conversation.

    @brief Run the judge k times per sampled pair.
    @param k Repeats.
    @return Exit code.
    @version 1
    """
    if not MANIFEST.is_file():
        print(f"REFUSING: no manifest at {MANIFEST} — run `sample` first", file=sys.stderr)
        return 2
    bench_judge, grade_prompts = _bench()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sample = manifest["sample"]

    done: set[str] = set()
    if RESULTS.is_file():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add(f"{row['cell']}#{row['mark_index']}#{row['rep']}")

    jobs = [
        (item, rep)
        for item in sample
        for rep in range(k)
        if f"{item['cell']}#{item['mark_index']}#{rep}" not in done
    ]
    print(f"{len(sample)} pairs x {k} reps = {len(sample) * k} calls; {len(jobs)} remaining")

    def one(job: tuple[dict, int]) -> dict:
        item, rep = job
        prompt = grade_prompts.mark_prompt(
            item["mark_text"], grade_prompts.anonymise(item["answer"])
        )
        reply = bench_judge.ask(prompt)
        verdict = (
            None
            if reply.error
            else bench_judge.verdict_token(reply.text, "VERDICT", grade_prompts.MARK_VERDICTS)
        )
        return {
            "cell": item["cell"],
            "target": item["target"],
            "mark_index": item["mark_index"],
            "conceptual": item["conceptual"],
            "recorded": item["recorded"],
            "rep": rep,
            "verdict": verdict,
            "error": reply.error or ("unparseable" if verdict is None else ""),
        }

    with RESULTS.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(WORKERS) as pool:
        for i, row in enumerate(pool.map(one, jobs), 1):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(jobs)}")
    print(f"wrote -> {RESULTS.relative_to(REPO)}")
    return 0


## @brief Report the flip rate, split by mark shape, with transport errors separate.
## @return Exit code.
## @version 1
def cmd_report() -> int:
    """A pair FLIPPED if its successful verdicts are not unanimous.

    Errors are excluded from the unanimity test and counted on their own line. Treating an
    error as a verdict is the defect this whole file is careful about: it turns flaky
    infrastructure into a result.

    @brief Report judge variance.
    @return Exit code.
    @version 1
    """
    if not RESULTS.is_file():
        print(f"REFUSING: no results at {RESULTS} — run `run` first", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line]

    by_pair: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_pair[(row["cell"], row["mark_index"])].append(row)

    stats: dict[str, Counter] = {"conceptual": Counter(), "objective": Counter()}
    disagreed_with_recorded: dict[str, Counter] = {
        "conceptual": Counter(),
        "objective": Counter(),
    }
    errors = 0
    calls = 0

    for reps in by_pair.values():
        shape = "conceptual" if reps[0]["conceptual"] else "objective"
        calls += len(reps)
        good = [r["verdict"] for r in reps if r["verdict"]]
        errors += len(reps) - len(good)
        if not good:
            stats[shape]["all_errored"] += 1
            continue
        stats[shape]["pairs"] += 1
        if len(set(good)) > 1:
            stats[shape]["flipped"] += 1
        majority = Counter(good).most_common(1)[0][0]
        recorded = reps[0]["recorded"]
        if majority != recorded:
            disagreed_with_recorded[shape]["differs"] += 1
            ## DIRECTION IS THE WHOLE INTERPRETATION. A symmetric drift is judge noise; a
            ## one-way drift is a CHANGE — the prompt, the model or the input differs from
            ## what produced the committed verdict, and the number is not variance at all.
            disagreed_with_recorded[shape][f"{recorded}->{majority}"] += 1
        disagreed_with_recorded[shape]["compared"] += 1

    print(f"calls: {calls}   transport/parse errors: {errors} ({errors / max(1, calls):.1%})")
    print()
    print(f"{'shape':<12} {'pairs':>6} {'flipped':>8} {'flip rate':>10} {'vs recorded':>13}")
    for shape in ("conceptual", "objective"):
        s = stats[shape]
        d = disagreed_with_recorded[shape]
        pairs = s["pairs"]
        if not pairs:
            print(f"{shape:<12} {0:>6}   — no pairs measured")
            continue
        rate = s["flipped"] / pairs
        drift = d["differs"] / max(1, d["compared"])
        print(f"{shape:<12} {pairs:>6} {s['flipped']:>8} {rate:>9.1%} {drift:>12.1%}")
        if s["all_errored"]:
            print(
                f"{'':<12} {s['all_errored']} pair(s) errored on every rep — NOT counted as flips"
            )
        h2m, m2h = d["HIT->MISS"], d["MISS->HIT"]
        if h2m or m2h:
            print(f"{'':<12} direction: MISS->HIT {m2h}   HIT->MISS {h2m}")
    print()
    print("flip rate  = the same (mark, answer) pair did not get a unanimous verdict across reps")
    print("vs recorded = the new majority disagrees with the verdict in the committed sidecar")
    return 0


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """Dispatch subcommands.

    @brief Entry point.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="choose a stratified sample of judged pairs")
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--seed", type=int, default=7)
    r = sub.add_parser("run", help="re-judge each sampled pair k times")
    r.add_argument("--k", type=int, default=3)
    sub.add_parser("report", help="flip rate, split by mark shape")
    args = parser.parse_args()
    if args.cmd == "sample":
        return cmd_sample(args.n, args.seed)
    if args.cmd == "run":
        return cmd_run(args.k)
    return cmd_report()


if __name__ == "__main__":
    raise SystemExit(main())
