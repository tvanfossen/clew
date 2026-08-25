# SPDX-License-Identifier: MIT
"""Measure the judge's per-decision FLIP RATE against answers a run already froze.

WHY IT STAYS. The grading architecture rests on one number: how often does the judge change its
mind about the same (mark, answer) pair? Measured 2026-08-21 at 0 flips in 40 pairs x 3 reps,
which bounds it at roughly <=7.5% at 95% confidence (rule of three) — not zero, and not the 15%
that would have forced heavy deterministic scaffolding into the schema.

THAT BOUND HAS A SHELF LIFE. Each rubric names its judge by a dated model id, but a rubric can
be repointed and a different model behaves differently. Re-run this against a fresh run to
confirm the bound still holds: the number is a property of a judge, not of the design.

NO AGENT RUNS. Inputs are the `.grade.json` and `.md` files a `generate` + `grade` pass already
wrote. Re-judging those pairs costs judge calls only.

SCOPE: VERDICT DECISIONS ONLY — `retrieval` and `conclusion` marks. Set decisions come from an
EXTRACTION call rather than a verdict call, and extraction variance is a different question with
a different failure mode. Measuring them together reports one blended rate for two mechanisms.

Usage:
    .venv/bin/python scripts/judge_variance.py sample --answers <dir> --n 40 --seed 7
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
sys.path.insert(0, str(REPO))

from acceptance.grader import judge  # noqa: E402

OUT = REPO / "acceptance" / "operational" / "judge-variance"
MANIFEST = OUT / "sample.json"
RESULTS = OUT / "verdicts.jsonl"

## Parallel judge calls. Small on purpose: these are `claude -p` subprocesses against a
## subscription, and the flakiness this exists to characterise is CAUSED by exhausting session
## capacity. A wide fan-out would manufacture the errors it is counting.
WORKERS = 4

## An answer shorter than this is a stub, not prose. The first version of this file read a
## sidecar field that held a FILENAME, and spent 120 judge calls asking whether a 19-character
## string demonstrated each mark. It answered MISS to most, producing a clean 55% "drift" that
## was 100% one-way — confident enough to have been reported as a finding about the judge, and
## entirely an artefact. A length floor cannot be phrased around the way "did we read the right
## field" can.
MIN_ANSWER_CHARS = 400

VERDICT_KINDS = ("retrieval", "conclusion")


## @brief Every ruled verdict decision in a run, paired with its answer prose.
## @param answers Directory holding a run's frozen artifacts.
## @return Candidate dicts.
## @version 2
def _candidates(answers: Path) -> list[dict]:
    """A decision whose `hit` is null was never ruled — including it would measure the transport
    rather than the judge.

    @brief Judged pairs from a run.
    @return Candidates.
    @version 2
    """
    out: list[dict] = []
    for sidecar in sorted(answers.glob("*.grade.json")):
        prose = answers / f"{sidecar.name.removesuffix('.grade.json')}.md"
        if not prose.is_file():
            continue
        answer = prose.read_text(encoding="utf-8")
        if len(answer) < MIN_ANSWER_CHARS:
            continue
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
        for i, decision in enumerate(doc.get("decisions") or []):
            if decision.get("kind") not in VERDICT_KINDS or decision.get("hit") is None:
                continue
            out.append(
                {
                    "cell": doc.get("cell", sidecar.stem),
                    "index": i,
                    "kind": decision["kind"],
                    "mark": decision.get("mark", ""),
                    "recorded": "HIT" if decision["hit"] else "MISS",
                    "model": doc.get("judge_model", ""),
                    "answer": answer,
                }
            )
    return out


## @brief Choose a stratified sample and write the manifest.
## @param answers Run directory.
## @param n Total pairs.
## @param seed Recorded seed.
## @return Exit code.
## @version 2
def cmd_sample(answers: Path, n: int, seed: int) -> int:
    """Stratified by mark kind, because the split IS the finding. An unstratified sample is
    dominated by whichever kind is commoner and reports one blended rate — the number least
    useful for deciding what the schema must carry.

    @brief Write a stratified sample.
    @return Exit code.
    @version 2
    """
    pool = _candidates(answers)
    if not pool:
        print(f"REFUSING: no ruled verdict decisions under {answers}", file=sys.stderr)
        return 2
    rng = random.Random(seed)
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for item in pool:
        by_kind[item["kind"]].append(item)

    half = max(1, n // len(VERDICT_KINDS))
    chosen: list[dict] = []
    for kind in VERDICT_KINDS:
        bucket = by_kind.get(kind) or []
        rng.shuffle(bucket)
        take = bucket[:half]
        chosen.extend(take)
        if len(take) < half:
            print(f"NOTE: only {len(take)} {kind} pairs available, wanted {half} — disclosed")

    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(
            {
                "answers": str(answers),
                "seed": seed,
                "requested": n,
                "pool": {k: len(v) for k, v in by_kind.items()},
                "sample": chosen,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"pool: {len(pool)} ruled verdict decisions  { ({k: len(v) for k, v in by_kind.items()}) }"
    )
    print(f"sampled: {len(chosen)} -> {MANIFEST.relative_to(REPO)}")
    return 0


## @brief Re-judge every sampled pair k times, appending as results land.
## @param k Independent calls per pair.
## @return Exit code.
## @version 2
def cmd_run(k: int) -> int:
    """Append-only JSONL, so an interrupted run keeps everything already paid for. Each call is
    a fresh tool-less process with no memory of the last, which is what makes repeats a variance
    measurement rather than a conversation.

    @brief Re-judge the sample.
    @return Exit code.
    @version 2
    """
    if not MANIFEST.is_file():
        print(f"REFUSING: no manifest at {MANIFEST} — run `sample` first", file=sys.stderr)
        return 2
    sample = json.loads(MANIFEST.read_text(encoding="utf-8"))["sample"]
    done: set[str] = set()
    if RESULTS.is_file():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add(f"{row['cell']}#{row['index']}#{row['rep']}")

    jobs = [
        (item, rep)
        for item in sample
        for rep in range(k)
        if f"{item['cell']}#{item['index']}#{rep}" not in done
    ]
    print(f"{len(sample)} pairs x {k} reps = {len(sample) * k} calls; {len(jobs)} remaining")

    def one(job: tuple[dict, int]) -> dict:
        item, rep = job
        reply = judge.ask(
            judge.verdict_prompt(item["mark"], judge.anonymise(item["answer"])), item["model"]
        )
        verdict = None if reply.error else judge.read_verdict(reply.text)
        return {
            "cell": item["cell"],
            "index": item["index"],
            "kind": item["kind"],
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


## @brief Report the flip rate, split by mark kind, errors separate.
## @return Exit code.
## @version 2
def cmd_report() -> int:
    """A pair FLIPPED if its successful verdicts are not unanimous. Errors are excluded from the
    unanimity test and counted on their own line — treating an error as a verdict turns flaky
    infrastructure into a result.

    DIRECTION IS PRINTED, because it is the whole interpretation. A symmetric drift against the
    recorded verdicts is judge noise; a ONE-WAY drift is a CHANGE — the prompt, the model or the
    input differs from whatever produced the recorded verdict, and the number is not variance at
    all. That distinction is what caught this file's own first version.

    @brief Report judge variance.
    @return Exit code.
    @version 2
    """
    if not RESULTS.is_file():
        print(f"REFUSING: no results at {RESULTS} — run `run` first", file=sys.stderr)
        return 2
    rows = [json.loads(x) for x in RESULTS.read_text(encoding="utf-8").splitlines() if x]
    by_pair: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_pair[(row["cell"], row["index"])].append(row)

    stats: dict[str, Counter] = defaultdict(Counter)
    errors = sum(1 for r in rows if not r.get("verdict"))
    for reps in by_pair.values():
        kind = reps[0]["kind"]
        good = [r["verdict"] for r in reps if r["verdict"]]
        if not good:
            stats[kind]["all_errored"] += 1
            continue
        stats[kind]["pairs"] += 1
        if len(set(good)) > 1:
            stats[kind]["flipped"] += 1
        majority = Counter(good).most_common(1)[0][0]
        recorded = reps[0]["recorded"]
        if majority != recorded:
            stats[kind][f"{recorded}->{majority}"] += 1

    rate = errors / max(1, len(rows))
    print(f"calls: {len(rows)}   transport/parse errors: {errors} ({rate:.1%})")
    print(f"\n{'kind':<12} {'pairs':>6} {'flipped':>8} {'flip rate':>10}")
    for kind in VERDICT_KINDS:
        s = stats.get(kind) or Counter()
        if not s["pairs"]:
            print(f"{kind:<12} {0:>6}   — no pairs measured")
            continue
        print(f"{kind:<12} {s['pairs']:>6} {s['flipped']:>8} {s['flipped'] / s['pairs']:>9.1%}")
        if s["MISS->HIT"] or s["HIT->MISS"]:
            print(f"{'':<12} vs recorded: MISS->HIT {s['MISS->HIT']}  HIT->MISS {s['HIT->MISS']}")
        if s["all_errored"]:
            print(f"{'':<12} {s['all_errored']} pair(s) errored on every rep — NOT flips")
    pairs = sum(s["pairs"] for s in stats.values())
    flips = sum(s["flipped"] for s in stats.values())
    if pairs and not flips:
        print(
            f"\n0 flips in {pairs} pairs bounds the rate at ~<={3 / pairs:.1%} at 95% confidence "
            f"(rule of three). It does NOT show the rate is zero."
        )
    return 0


## @brief CLI entry point.
## @return Exit code.
## @version 2
def main() -> int:
    """@brief Dispatch subcommands.
    @return Exit code.
    @version 2
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--answers", type=Path, required=True)
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--seed", type=int, default=7)
    r = sub.add_parser("run")
    r.add_argument("--k", type=int, default=3)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.cmd == "sample":
        return cmd_sample(args.answers, args.n, args.seed)
    if args.cmd == "run":
        return cmd_run(args.k)
    return cmd_report()


if __name__ == "__main__":
    raise SystemExit(main())
