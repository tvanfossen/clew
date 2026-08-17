#!/usr/bin/env python
# SPDX-License-Identifier: MIT
##
# @brief Re-analysis of a graded grid restricted to the marks the OTHER arm missed.
# @details A headline "the two arms score the same" can mean two very different things, and
#          the aggregate cannot tell them apart. Either the arms answer the SAME marks — in
#          which case the index adds nothing — or they answer DIFFERENT marks and the totals
#          happen to land together, in which case each arm has a distinct competence and the
#          aggregate is hiding it.
#
#          The discriminator is conditional hit-rate. For every mark index and question that
#          both arms answered, this partitions the marks by what the OTHER arm did and reports
#          each arm's hit-rate on the subset the other one missed. If an arm's hit-rate on the
#          other's misses equals its unconditional hit-rate, the two arms are independent and
#          neither has a competence the other lacks. If it is materially lower, the arms are
#          failing on the SAME marks and the tie is a shared ceiling, not an equivalence.
#
#          It also states the headroom explicitly: an arm cannot win a mark the other arm
#          already banked, so an arm facing 55 available marks and one facing 100 are not
#          running the same experiment even at identical completeness.
#
#          Reads only committed `*.grade.json` sidecars. No cells are run and no judge is
#          called, so this costs nothing and cannot perturb what it measures.
# @version 1
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

##
# @brief Arm label used for the index (MCP) arm in cell filenames.
INDEX_ARM = "mcp"

##
# @brief Arm label used for the source-reading arm in cell filenames.
SOURCE_ARM = "src"


##
# @brief Read one sidecar's per-mark verdicts.
# @details A mark is HIT when the objective scorer awarded it or the judge did; the sidecar
#          records both and either is sufficient, which mirrors `bench_score._decide`. Marks
#          the harness could not score (`n/a` from both) are returned as None so a caller can
#          exclude them rather than count them as misses — counting an unscored mark as a miss
#          is the failure `unmarked_pct` exists to make visible.
# @param path sidecar path
# @return dict mapping mark index -> True (hit) / False (miss) / None (unscored)
# @version 1
def mark_verdicts(path: Path) -> dict:
    """@brief Read one sidecar's per-mark verdicts, keyed by mark index. @version 1"""
    blob = json.loads(path.read_text())
    out = {}
    for mark in blob.get("marks", []):
        objective = (mark.get("objective") or {}).get("verdict", "n/a")
        judged = (mark.get("judge") or {}).get("verdict", "n/a")
        if "HIT" in (objective, judged):
            out[mark["index"]] = True
        elif "MISS" in (objective, judged):
            out[mark["index"]] = False
        else:
            out[mark["index"]] = None
    return out


##
# @brief Index every sidecar in a directory by (question, model, arm).
# @param directory directory holding `*.grade.json`
# @return dict mapping (q, model, arm) -> per-mark verdict dict
# @version 1
def load_cells(directory: Path) -> dict:
    """@brief Index every sidecar in a directory by (question, model, arm). @version 1"""
    cells = {}
    for path in sorted(directory.glob("*.grade.json")):
        parts = path.name[: -len(".grade.json")].split("_")
        if len(parts) < 3:
            continue
        cells[(parts[0], parts[1], parts[2])] = mark_verdicts(path)
    return cells


##
# @brief Accumulate conditional and unconditional tallies for one paired cell.
# @param index per-mark verdicts for the index arm
# @param source per-mark verdicts for the source arm
# @param acc mutable tally dict to add into
# @version 1
def tally_pair(index: dict, source: dict, acc: dict) -> None:
    """@brief Accumulate conditional and unconditional tallies for one paired cell. @version 1"""
    for key in sorted(set(index) & set(source)):
        i, s = index[key], source[key]
        if i is None or s is None:
            acc["unscored"] += 1
            continue
        acc["marks"] += 1
        acc["index_hit"] += int(i)
        acc["source_hit"] += int(s)
        if not s:
            acc["source_missed"] += 1
            acc["index_hit_on_source_miss"] += int(i)
        if not i:
            acc["index_missed"] += 1
            acc["source_hit_on_index_miss"] += int(s)
        if i and s:
            acc["both_hit"] += 1
        if not i and not s:
            acc["both_miss"] += 1


##
# @brief Build an empty tally.
# @return dict with every counter at zero
# @version 1
def new_tally() -> dict:
    """@brief Build an empty tally. @version 1"""
    keys = (
        "marks unscored index_hit source_hit source_missed index_hit_on_source_miss "
        "index_missed source_hit_on_index_miss both_hit both_miss"
    )
    return dict.fromkeys(keys.split(), 0)


##
# @brief Tally every paired cell in a directory, grouped by model.
# @param directory directory holding `*.grade.json`
# @return dict mapping model -> tally
# @version 1
def tally_directory(directory: Path) -> dict:
    """@brief Tally every paired cell in a directory, grouped by model. @version 1"""
    cells = load_cells(directory)
    out = defaultdict(new_tally)
    for (question, model, arm), verdicts in cells.items():
        if arm != INDEX_ARM:
            continue
        source = cells.get((question, model, SOURCE_ARM))
        if source is None:
            continue
        tally_pair(verdicts, source, out[model])
    return dict(out)


##
# @brief Format one tally as a line of the conditional-rate table.
# @param label row label
# @param t tally
# @return formatted line
# @version 2
def format_row(label: str, t: dict) -> str:
    """@brief Format one tally as a line of the conditional-rate table. @version 2"""

    def pct(num: int, den: int) -> str:
        return f"{100 * num / den:5.1f}%" if den else "    --"

    return (
        f"{label:22} {t['marks']:5d} "
        f"{pct(t['index_hit'], t['marks'])} {pct(t['source_hit'], t['marks'])}   "
        f"{t['source_missed']:5d} {pct(t['index_hit_on_source_miss'], t['source_missed'])}   "
        f"{t['index_missed']:5d} {pct(t['source_hit_on_index_miss'], t['index_missed'])}   "
        f"{t['both_miss']:5d} {pct(t['marks'] - t['both_miss'], t['marks'])}"
    )


##
# @brief Print the conditional-rate table for every directory given.
# @param directories answer directories to analyse
# @return process exit code
# @version 1
def report(directories: list) -> int:
    """@brief Print the conditional-rate table for every directory given. @version 1"""
    print(
        f"{'target/model':22} {'marks':>5} {'idx':>6} {'src':>6}   "
        f"{'srcMISS':>5} {'idx|sM':>6}   {'idxMISS':>5} {'src|iM':>6}   {'both0':>5} {'union':>6}"
    )
    overall = new_tally()
    for directory in directories:
        path = Path(directory)
        for model, t in sorted(tally_directory(path).items()):
            print(format_row(f"{path.name}/{model}", t))
            for key in overall:
                overall[key] += t[key]
    print(format_row("ALL", overall))
    print(
        "\nidx|sM = the index arm's hit-rate on marks the SOURCE arm missed.\n"
        "If it matches the unconditional idx rate, the arms fail independently.\n"
        "If it is materially lower, both arms are failing the SAME marks — a shared\n"
        "ceiling, which a tie in the aggregate cannot distinguish from equivalence.\n"
        "union  = marks at least ONE arm banked. It is the ceiling an agent holding both\n"
        "toolsets could reach, and the gap between it and the better single arm is what the\n"
        "head-to-head framing throws away."
    )
    return 0


##
# @brief CLI entry point.
# @return process exit code
# @version 1
def main() -> int:
    """@brief CLI entry point. @version 1"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--answers", action="append", required=True, help="graded answer directory (repeatable)"
    )
    args = parser.parse_args()
    return report(args.answers)


if __name__ == "__main__":
    sys.exit(main())
