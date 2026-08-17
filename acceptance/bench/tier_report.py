# SPDX-License-Identifier: MIT
## @brief Does the index let a CHEAPER model do a more expensive model's job?
## @version 2
"""The sharpest claim this matrix can support, and a different analysis from "the index helps".

Within-model comparison asks: does `sonnet+index` beat `sonnet` raw? Useful, and it is what
every previous run measured. The TIER-CROSSING question is stronger: does `haiku+index` reach
or beat `sonnet` or `opus` WITHOUT it? If a cheaper model does a more expensive model's job on
the read-and-digest path, that is a directive-grade result.

TOKENS ARE THE UNIT OF RECORD (owner decision, 2026-07-31). A dollar figure is a direct
conversion from a token count against a price sheet, so recording dollars stores the same
information plus a dependency on rates that drift — and a stale multiplier goes wrong silently,
in prose, which this project has already paid for. Session capacity, the actual binding
constraint, is metered in tokens anyway.

  WITHIN a model    token counts are directly comparable, and that is where the hypothesis
                    lives: does the index arm answer using fewer tokens than the source arm?
                    No normalisation, no price sheet.
  ACROSS tiers      a haiku token and an opus token are different goods. This report prints
                    both counts SIDE BY SIDE rather than dividing them, so a reader applies
                    whatever prices they actually pay instead of inheriting one hardcoded here.

`metrics.csv` still records `cost_usd` from `claude -p` — free to keep, occasionally the
fastest check that a cell ran at all, and not what any claim is stated in.

SPREAD IS REPORTED BESIDE EVERY TOKEN FIGURE. Calibration measured run-to-run CV at 48% on the
source arm and 84% on the INDEX arm — the noisier one, because the agent chose 4 database
queries on one run and 33 on the next. At n=3 a single cell's mean carries a standard error
near 50%, so a per-question ratio is uninterpretable and never carries a verdict here.

Usage:
  .venv/bin/python acceptance/bench/tier_report.py <answers-dir> [--tiers haiku,sonnet,opus]
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

## Both rules live with the module that OWNS the data. A second copy of a de-duplication or a
## fencing rule is a second thing to get backwards, and arm fencing has been inverted twice.
import target_check
from grade_matrix import summarise
from run_matrix import latest_per_cell

## Cheapest first. The claim is about a cheaper model reaching a dearer one, so the ordering
## is load-bearing rather than cosmetic.
DEFAULT_TIERS = ("haiku", "sonnet", "opus")

## Bootstrap resamples for the paired-ratio interval. 2000 is well past the point where the
## percentile bounds stop moving at these sample sizes, and it costs milliseconds.
BOOTSTRAP_SAMPLES = 2000

## Paired observations required before this report will state a VERDICT.
##
## A percentile bootstrap degenerates at small n, and at n=1 it is actively misleading: every
## resample draws the same value, so the interval has zero width and an unrepeated measurement
## prints as a certainty. The first version of this section did exactly that — one opus pair
## announced "index uses 25% FEWER tokens" with a 0.75x-0.75x interval. That is the failure the
## whole paired analysis exists to prevent, reproduced inside the guard against it.
##
## The full matrix supplies 11 questions x 3 runs = 33 pairs per (arm, model, target), so this
## floor only ever suppresses verdicts on partial or calibration data — which is precisely when
## a verdict would be wrong.
MIN_PAIRS_FOR_VERDICT = 10


## @brief Median of a list, or 0.
## @param values Numbers.
## @return Median or 0.0.
## @version 1
## @dg_internal
def _median(values: list[float]) -> float:
    """@brief Empty-safe median.
    @return Median or 0.0.
    @version 1
    """
    return statistics.median(values) if values else 0.0


## @brief Coefficient of variation, as a percentage.
## @param values Numbers.
## @return Standard deviation over the mean, in percent; 0 when undefined.
## @version 1
## @dg_internal
def _cv(values: list[float]) -> float:
    """Run-to-run spread on identical cells, which is the number that says whether an arm
    difference is resolved at all. Measured 48% on the source arm and 84% on the index arm
    during calibration — wide enough to swallow the 0.52x token headline a previous grid
    published as a point estimate.

    @brief Spread of a sample, relative to its mean.
    @return CV in percent.
    @version 1
    """
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    return (statistics.stdev(values) / mean * 100) if mean else 0.0


## @brief Per-question paired token ratios, index arm over source arm.
## @param rows De-duplicated valid metric rows.
## @param model Model alias to pair within.
## @return Ordered list of (question, run, ratio).
## @version 1
## @dg_internal
def _paired_ratios(rows: list[dict], model: str) -> list[tuple[str, str, float]]:
    """PAIRED WITHIN A QUESTION, because question difficulty is the dominant spread term and
    pairing cancels it.

    Comparing two pooled arm means instead would drown the effect in that spread. Across the
    full matrix each (arm, model, target) has 11 questions x 3 runs, so 33 paired differences
    carry the claim. Same question, same run index, both arms.

    @brief Pair index-arm against source-arm tokens within each question.
    @return (question, run, mcp/src ratio) tuples.
    @version 1
    """
    by_cell: dict[tuple[str, str, str], float] = {}
    for r in rows:
        if r["model"] == model:
            by_cell[(r["q"], r["run"], r["arm"])] = float(r["total_tokens"])
    out: list[tuple[str, str, float]] = []
    for q, run, arm in sorted(by_cell):
        if arm != "src":
            continue
        src, mcp = by_cell[(q, run, "src")], by_cell.get((q, run, "mcp"))
        if mcp and src:
            out.append((q, run, mcp / src))
    return out


## @brief Geometric mean of ratios, with a bootstrap percentile interval.
## @param ratios Paired ratios.
## @return (geometric mean, low, high) — all 0.0 when there is nothing to summarise.
## @version 1
## @dg_internal
def _ratio_interval(ratios: list[float]) -> tuple[float, float, float]:
    """GEOMETRIC mean, because these are ratios: the arithmetic mean of 0.5 and 2.0 is 1.25,
    which claims a 25% increase from two measurements that exactly cancel.

    The interval is a bootstrap percentile rather than a t-interval — assumption-free, which
    matters at 84% CV where normality is not something to take on faith. Seeded, so the same
    data always yields the same interval and a reviewer can reproduce the number.

    @brief Summarise paired ratios with an assumption-free interval.
    @return (geometric mean, low, high).
    @version 1
    """
    if not ratios:
        return 0.0, 0.0, 0.0
    logs = [math.log(r) for r in ratios]
    rand = random.Random(20260731)
    means = sorted(
        statistics.mean(rand.choices(logs, k=len(logs))) for _ in range(BOOTSTRAP_SAMPLES)
    )
    lo = means[int(0.025 * BOOTSTRAP_SAMPLES)]
    hi = means[int(0.975 * BOOTSTRAP_SAMPLES)]
    return math.exp(statistics.mean(logs)), math.exp(lo), math.exp(hi)


## @brief Per-(model, arm) quality and grading coverage from the grade sidecars.
## @param roots One or more answer directories — the reusable source baseline and the
##        version's index run live in separate trees.
## @return {(model, arm): (earned, possible, unruled)}.
## @version 3
## @dg_internal
def _quality(*roots: Path) -> dict[tuple[str, str], tuple[float, float, float]]:
    """DELEGATES to `grade_matrix.summarise` rather than re-deriving the score.

    It used to reimplement two rules the grader already owns — the arm-fencing translation
    (`arm_only` names the arm that CAN reach a mark; rubric says raw/db, the harness says
    src/mcp) and the verdict weighting. Both were correct, verified by truth table across
    all six fence/arm combinations. That is not the point: the fencing rule has been INVERTED
    twice in this project's history, it sets the headline number directly, and a second copy
    is a second thing to invert. One implementation cannot disagree with itself.

    Delegating also picks up `judge_errors` for free, which is how coverage becomes visible
    here. A score built from 69% of its marks is a different claim from the same score built
    from all of them, and 102 unruled marks were once counted as failures against both arms.

    @brief Aggregate rubric score and unruled-mark count per model and arm.
    @return Mapping to (earned, possible, unruled).
    @version 3
    """
    earned: dict[tuple[str, str], float] = defaultdict(float)
    possible: dict[tuple[str, str], float] = defaultdict(float)
    unruled: dict[tuple[str, str], float] = defaultdict(float)
    for root in roots:
        for path in sorted(root.glob("*.grade.json")):
            g = json.loads(path.read_text())
            key = (g["model"], g["arm"])
            stats = summarise(g.get("marks", []), g["arm"], g.get("falsity"))
            ## D3'S VETO IS APPLIED HERE, where the headline is computed, and NOT in
            ## `summarise` — which keeps each cell's measured score so a human can confirm the
            ## veto by hand. A vetoed question earns ZERO while its marks stay in the
            ## DENOMINATOR: that is what "quality 0" means, and dropping the denominator too
            ## would make a vetoed cell arithmetically invisible instead of costly.
            ##
            ## The rule the owner set: "99% token reduction with a false answer == failure".
            ## Cheapness cannot offset a falsehood, so the token axis is left untouched and
            ## this axis goes to zero.
            earned[key] += 0.0 if stats["quality_vetoed"] else stats["score"]
            possible[key] += stats["marks_total"]
            unruled[key] += stats["judge_errors"]
    return {k: (earned[k], possible[k], unruled[k]) for k in possible}


if __name__ == "__main__":
    ## ACCEPTS SEVERAL RUN DIRECTORIES, because the two arms no longer share one.
    ##
    ## A source-arm cell reads source with Read/Grep/Bash and never touches the index, so its
    ## result does not depend on the clew version — re-running it every release spends
    ## half a target's capacity to reproduce a number that did not move. The source arm is
    ## therefore a REUSABLE BASELINE stored once per target, and only the index arm is
    ## re-measured per version.
    ##
    ## Metric 2 pairs src against mcp WITHIN a question, so the pairing must see both. Passing
    ## the directories separately keeps that explicit: a caller who forgets one gets "no tier
    ## pairs present" rather than a silently one-armed report.
    roots = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    if not roots:
        raise SystemExit(
            "usage: tier_report.py <baseline-src-dir> <run-mcp-dir> [--tiers haiku,sonnet,opus]"
        )
    tiers = (
        sys.argv[sys.argv.index("--tiers") + 1].split(",")
        if "--tiers" in sys.argv
        else list(DEFAULT_TIERS)
    )

    raw_rows: list[dict] = []
    ## VOID CELLS ARE EXCLUDED FROM EVERY AGGREGATE AND COUNTED IN THE OUTPUT. A cell whose
    ## index answered about another repository has meaningless tokens as well as meaningless
    ## marks — the retracted grid's headline "3.4x cheaper" was measuring bail-outs, because a
    ## cell that discovers the wrong repo and stops costs 0.70x a working one. Dropping them
    ## silently would reproduce that exactly; the count is printed before any figure.
    voids = 0
    unchecked_roots: list[Path] = []
    for root in roots:
        path = root / "metrics.csv"
        if not path.exists():
            raise SystemExit(f"no metrics.csv under {root}")
        if not target_check.records_target_column(root):
            unchecked_roots.append(root)
        with path.open(newline="") as fh:
            for r in csv.DictReader(fh):
                if (r.get("target_ok") or "") == target_check.VOID:
                    voids += 1
                    continue
                if r.get("valid") == "True":
                    raw_rows.append(r)
    if voids:
        print(f"EXCLUDED {voids} VOID cell(s) — index answered about another repository\n")
    for root in unchecked_roots:
        print(f"NOTE: {root} predates the wrong-repository check — UNCHECKED, not clean\n")
    rows, superseded = latest_per_cell(raw_rows)
    if superseded:
        print(f"note: {superseded} superseded row(s) dropped (cells re-run); last attempt wins\n")
    toks: dict[tuple[str, str], list[float]] = defaultdict(list)
    secs: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        key = (r["model"], r["arm"])
        toks[key].append(float(r["total_tokens"]))
        secs[key].append(float(r["duration_ms"]) / 1000)

    quality = _quality(*roots)

    ## SPREAD IS PRINTED BESIDE EVERY TOKEN FIGURE, never a bare median. A ratio printed alone
    ## reads as measured precision, and a previously published token headline sat exactly on the
    ## edge of what this sample size can resolve — the spread is what says so.
    print("=== PER TIER — within-model effect of the index ===")
    print(
        f"{'model':<8}{'arm':<5}{'quality':>9}{'unruled':>9}{'n':>3}"
        f"{'tokens':>12}{'CV':>6}{'range':>24}{'sec':>7}"
    )
    for model in tiers:
        for arm in ("src", "mcp"):
            key = (model, arm)
            if key not in quality and not toks[key]:
                continue
            earned, possible, unruled = quality.get(key, (0.0, 0.0, 0.0))
            values = toks[key]
            ## "—" NOT "0%". A single cell has no measurable spread, and an ungraded cell has
            ## no score — printing 0 for either states a measurement that was never made,
            ## which is how a missing number becomes a bad finding.
            pct = f"{100 * earned / possible:.0f}%" if possible else "—"
            ## Coverage beside the score, never behind it. A mark the judge never ruled on is
            ## an unfinished measurement, not a failure; 102 of them were once counted as
            ## failures against both arms when a grading run hit a session limit.
            unmarked = f"{100 * unruled / possible:.0f}%" if possible else "—"
            cv = f"{_cv(values):.0f}%" if len(values) > 1 else "—"
            rng = f"{min(values):,.0f}–{max(values):,.0f}" if len(values) > 1 else "—"
            print(
                f"{model:<8}{arm:<5}{pct:>9}{unmarked:>9}{len(values):>3}{_median(values):>12,.0f}"
                f"{cv:>6}{rng:>24}{_median(secs[key]):>7.0f}"
            )

    ## METRIC 2, THE WAY IT WAS PRE-REGISTERED. Paired within a question, geometric mean of
    ## the ratios, bootstrap interval. An interval spanning 1.00 is PARITY and says so —
    ## against the owner's bar (two of three metrics improve, the third at parity minimum)
    ## parity is a real outcome, not a failed measurement.
    print("\n=== METRIC 2 — tokens, paired within question (index arm / source arm) ===")
    ## COLUMN RENAMED FROM "verdict" TO "reading" (D1, owner 2026-08-13: the harness reports,
    ## the owner rules). The CONTENT is unchanged and stays, because it is not a ruling — it is
    ## the confidence interval restated in words, which is the measurement. The heading was the
    ## problem: a column called "verdict" invites being quoted as the pass.
    print(f"{'model':<8}{'pairs':>6}{'geo mean':>11}{'95% interval':>22}   reading")
    for model in tiers:
        pairs = _paired_ratios(rows, model)
        if not pairs:
            continue
        geo, lo, hi = _ratio_interval([r for _, _, r in pairs])
        if len(pairs) < MIN_PAIRS_FOR_VERDICT:
            verdict = f"NO VERDICT — {len(pairs)} pair(s), need {MIN_PAIRS_FOR_VERDICT}"
            interval = "—"
        else:
            interval = f"{lo:.2f}x – {hi:.2f}x"
            if hi < 1.0:
                verdict = f"index uses {(1 - geo) * 100:.0f}% FEWER tokens"
            elif lo > 1.0:
                verdict = f"index uses {(geo - 1) * 100:.0f}% MORE tokens"
            else:
                verdict = "PARITY — interval spans 1.00, not resolved"
        print(f"{model:<8}{len(pairs):>6}{geo:>10.2f}x{interval:>22}   {verdict}")
    print(
        "  Per-question ratios are DESCRIPTIVE ONLY and never carry a verdict: at the measured\n"
        "  spread a single question's ratio is uninterpretable. The claim rests on the pooled\n"
        "  pairs, which is why the full matrix runs 11 questions x 3 runs per arm and model."
    )

    ## THE CLAIM. For each cheaper tier WITH the index, compare against every dearer tier
    ## WITHOUT it.
    ##
    ## QUALITY AND TOKENS ARE PRINTED AS TWO NUMBERS AND NEVER COLLAPSED INTO ONE.
    ## This used to divide the two tiers' `cost_usd` and print a single "0.42x cheaper".
    ## That bakes one day's price sheet into a permanent claim, and it hides the thing a
    ## reader needs: a haiku token and an opus token are different goods, so the honest
    ## statement is both counts side by side, letting a reader apply whatever they pay.
    ## THE "REACHES"/"below" TOKEN IS GONE (D1). It was `c_pct >= d_pct` printed as a word —
    ## the pass question answered by the harness. Both percentages are still printed, so no
    ## information is lost: applying `>=` is the owner's call, and a one-word answer to it
    ## invites being quoted as the result while the two numbers behind it go unread.
    print("\n=== TIER CROSSING — a cheaper model + index against a dearer one raw ===")
    print(f"{'cheap+index':<16}{'vs dear raw':<14}{'quality':>20}{'tokens each':>30}")
    any_row = False
    for i, cheap in enumerate(tiers):
        ck = (cheap, "mcp")
        if ck not in quality:
            continue
        c_earned, c_possible, _ = quality[ck]
        c_pct = 100 * c_earned / c_possible if c_possible else 0.0
        for dear in tiers[i + 1 :]:
            dk = (dear, "src")
            if dk not in quality:
                continue
            d_earned, d_possible, _ = quality[dk]
            d_pct = 100 * d_earned / d_possible if d_possible else 0.0
            print(
                f"{cheap + '+mcp':<16}{dear + ' raw':<14}"
                f"{f'{c_pct:.0f}% vs {d_pct:.0f}%':>20}"
                f"{f'{_median(toks[ck]):,.0f} vs {_median(toks[dk]):,.0f}':>30}"
            )
            any_row = True
    if not any_row:
        print("  (no tier pairs present — run more than one model to use this view)")

    print(
        "\nTokens are the unit of record. Within a model they are directly comparable, which is"
        "\nwhere the hypothesis lives. ACROSS tiers they are different goods — the two counts are"
        "\nprinted side by side rather than divided, so a reader applies their own prices instead"
        "\nof inheriting a rate this file hardcoded on some particular day."
        "\n\nCV is run-to-run spread on identical cells. Where it approaches the arm difference,"
        "\nthe difference is not resolved at this sample size — say so rather than quoting a ratio."
    )
