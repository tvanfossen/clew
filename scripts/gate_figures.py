# SPDX-License-Identifier: MIT
"""The per-repo acceptance gate, as `acceptance/runs/1.4.0-pending/PRE-REGISTRATION.md` states it.

Per repo and arm, against that repo's baseline arm in the same grid:
  * TOTAL TOKENS — input + output + cache_read + cache_creation summed over the repo's cells, from
    each cell's `.meta.json`, as % vs baseline. Unweighted: cost is tokens, never dollars.
  * SEPARATION — per cluster (question), arm mean − baseline mean over replicates, averaged over
    the repo's clusters. A cell with no ruled score (`score` null) is excluded.
The gate (index_only): tokens % LOWER than the comparator's AND separation no more than 3.0 pt
below it. Baseline drift is printed beside, never folded in.

    .venv/bin/python scripts/gate_figures.py acceptance/runs/<run> acceptance/runs/1.3.0-final

WITH ONE ARGUMENT the run stands alone (the 2.0.0 pre-registration, amended 2026-11-17): each
repo's arms against that run's own baseline, per question too, and NO verdict — the release
decision is the owner's, so a standalone report states figures only.

    .venv/bin/python scripts/gate_figures.py acceptance/runs/2.0.0

`tests/test_gate_figures.py` pins that this reproduces 1.3.0-final's published figures.

@brief Per-repo token and separation figures, and the pre-registered gate.
@version 2
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

TARGETS = ("mattermost", "mbedtls", "self", "entropic")
ARMS = ("index_only", "index")
_TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")
## Pre-registered quality tolerance, points below the comparator.
TOLERANCE = 3.0


## @brief Summed total tokens per arm for one target.
## @param run The run directory.
## @param target The target.
## @return {arm: tokens}.
## @version 1
def _tokens(run: Path, target: str) -> dict[str, int]:
    """@brief Sum tokens per arm. @return Totals."""
    total: dict[str, int] = defaultdict(int)
    for path in (run / target / "answers").glob("*.meta.json"):
        meta = json.loads(path.read_text(encoding="utf-8"))
        total[meta["arm"]] += sum(int(meta.get(k) or 0) for k in _TOKEN_KEYS)
    return dict(total)


## @brief Ruled scores per (question, arm) for one target, in points.
## @param run The run directory.
## @param target The target.
## @return {question: {arm: [scores]}}.
## @version 1
def _scores(run: Path, target: str) -> dict[str, dict[str, list[float]]]:
    """@brief Collect scores; a null score is excluded. @return Scores."""
    out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for path in (run / target / "answers").glob("*.grade.json"):
        grade = json.loads(path.read_text(encoding="utf-8"))
        score = grade.get("score")
        if score is not None:
            question = path.name.split("_")[0]
            out[question][grade["arm"]].append(100 * score if score <= 1 else score)
    return out


## @brief Token % and separation per arm for one target, plus baseline mean.
## @param run The run directory.
## @param target The target.
## @return {arm: {tokens_pct, separation, clusters}, "baseline_mean": float, "baseline_tokens": int}.
## @version 1
def repo_figures(run: Path, target: str) -> dict:
    """@brief One repo's figures. @return Figures."""
    tokens, scores = _tokens(run, target), _scores(run, target)
    out: dict = {
        "baseline_mean": st.mean(x for q in scores.values() for x in q["baseline"]),
        "baseline_tokens": tokens["baseline"],
    }
    for arm in ARMS:
        seps = {
            q: st.mean(v[arm]) - st.mean(v["baseline"])
            for q, v in scores.items()
            if v.get(arm) and v.get("baseline")
        }
        out[arm] = {
            "tokens_pct": 100 * (tokens[arm] / tokens["baseline"] - 1),
            "separation": st.mean(seps.values()),
            "clusters": dict(sorted(seps.items())),
        }
    return out


## @brief The pre-registered gate for one repo's index_only arm.
## @param comparator The comparator's arm figures.
## @param candidate The candidate's arm figures.
## @return (cost ok, quality ok).
## @version 1
def gate(comparator: dict, candidate: dict) -> tuple[bool, bool]:
    """@brief Cost strictly lower; quality within the tolerance. @return Both verdicts."""
    cost = candidate["tokens_pct"] < comparator["tokens_pct"]
    quality = candidate["separation"] >= comparator["separation"] - TOLERANCE
    return cost, quality


## @brief Print one run's per-repo figures with no comparator and no verdict.
## @param run The run.
## @return Exit status 0.
## @version 1
def standalone(run: Path) -> int:
    """@brief Print figures only, per repo, arm and question. @return 0."""
    print(f"{'repo':10} {'arm':10} {'tokens':>8} {'sep':>8}  per question")
    for target in TARGETS:
        fig = repo_figures(run, target)
        for arm in ARMS:
            a = fig[arm]
            per_q = "  ".join(f"{q} {v:+.2f}" for q, v in a["clusters"].items())
            print(f"{target:10} {arm:10} {a['tokens_pct']:+7.1f}% {a['separation']:+8.2f}  {per_q}")
        print(
            f"{target:10} baseline mean {fig['baseline_mean']:.2f}, tokens {fig['baseline_tokens']}"
        )
    return 0


## @brief Print the per-repo table for a candidate run, against a comparator run when given.
## @param run The candidate run.
## @param comparator The comparator run, or None for a standalone run.
## @return Exit status: 0 when every repo passes (always 0 standalone), 1 otherwise.
## v2: the comparator is optional; a standalone run prints figures and no verdict.
## @version 2
def main(run: Path, comparator: Path | None = None) -> int:
    """@brief Print the gate, or figures only. @return 0 or 1."""
    if comparator is None:
        return standalone(run)
    passed = True
    print(
        f"{'repo':10} {'arm':10} {'tok cmp':>8} {'tok new':>8} {'sep cmp':>8} {'sep new':>8}  gate"
    )
    for target in TARGETS:
        old, new = repo_figures(comparator, target), repo_figures(run, target)
        for arm in ARMS:
            a, b = old[arm], new[arm]
            verdict = ""
            if arm == "index_only":
                cost, quality = gate(a, b)
                passed &= cost and quality
                verdict = ("PASS" if cost and quality else "MISS") + (
                    f" (cost {'ok' if cost else 'miss'}, quality {'ok' if quality else 'miss'})"
                )
            print(
                f"{target:10} {arm:10} {a['tokens_pct']:+7.1f}% {b['tokens_pct']:+7.1f}% "
                f"{a['separation']:+8.2f} {b['separation']:+8.2f}  {verdict}"
            )
        drift = new["baseline_mean"] - old["baseline_mean"]
        tok = 100 * (new["baseline_tokens"] / old["baseline_tokens"] - 1)
        print(f"{target:10} baseline drift {drift:+.2f} pt, tokens {tok:+.1f}%")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
