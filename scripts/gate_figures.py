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

`tests/test_gate_figures.py` pins that this reproduces 1.3.0-final's published figures.

@brief Per-repo token and separation figures, and the pre-registered gate.
@version 1
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


## @brief Print the per-repo table for a candidate run against a comparator run.
## @param run The candidate run.
## @param comparator The comparator run.
## @return Exit status: 0 when every repo passes, 1 otherwise.
## @version 1
def main(run: Path, comparator: Path) -> int:
    """@brief Print the gate. @return 0 or 1."""
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
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
