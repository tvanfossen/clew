# SPDX-License-Identifier: MIT
"""How the index actually gets USED, mined from a run's per-cell tool histograms.

A matrix answers "did the index arm score better". It does not answer "how did an
agent reach that answer", and the second question is worth as much: a score says a
capability was sufficient, a usage pattern says whether it was *usable*.

Three shapes this surfaces that a score cannot:

- **Grinding.** One tool called 40+ times in a single cell is rarely exploration. It
  usually means the reply did not carry what the caller needed, so it re-asked the
  same way. A cell that grinds and still scores well hides a real cost in tokens and
  turns; a cell that grinds and scores badly misattributes a *usability* defect to a
  *capability* gap.
- **Dead capability.** A tool that exists, is described, and is never called across an
  entire run is not obviously broken — nothing fails — but nobody found it. That is a
  discoverability finding, and it is invisible to every score.
- **Adoption.** A tool added since the last run either gets used or does not. Binary,
  visible in one cell, and the thing a spot check is actually for.

Reads the runner's own log, so it needs no new instrumentation and can be run against
a partial sweep while it is still going.

@brief Per-run tool-usage report: grinding, unused tools, adoption.
@version 1
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

## A cell header, e.g. `[12/66] Q3 mcp sonnet r1 ...`
_CELL = re.compile(r"^\[(\d+)/(\d+)\]\s+(Q\d+)\s+(\w+)\s+(\w+)\s+r(\d+)")

## A tool histogram entry, e.g. `mcp__clew__dossier×7`
_TOOL = re.compile(r"([A-Za-z_][\w.-]*)×(\d+)")

## Above this many calls to ONE tool in ONE cell, the shape stops looking like
## exploration. Not a threshold anything fails on — a number that decides what gets
## printed, so it errs low rather than hiding the pattern it exists to show.
GRIND_THRESHOLD = 15


## @brief Parse the runner log into per-cell tool histograms.
## @param log Path to the runner's stdout log.
## @return List of (cell_label, arm, model, {tool: count}).
## @version 1
def parse_cells(log: Path) -> list[tuple[str, str, str, dict[str, int]]]:
    """Pairs each cell header with the `tools:` line that follows it. A cell with no
    tool line (an abort, a refusal) yields an empty histogram rather than being
    dropped — a cell that called nothing is itself a finding.

    @brief Extract per-cell tool histograms from the log.
    @return One tuple per cell.
    @version 1
    """
    cells: list[tuple[str, str, str, dict[str, int]]] = []
    pending: tuple[str, str, str] | None = None
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        header = _CELL.match(line.strip())
        if header:
            if pending is not None:
                cells.append((*pending, {}))
            pending = (
                f"{header.group(3)}_{header.group(5)}_{header.group(4)}",
                header.group(4),
                header.group(5),
            )
            continue
        if pending is not None and line.strip().startswith("tools:"):
            hist = {m.group(1): int(m.group(2)) for m in _TOOL.finditer(line)}
            cells.append((*pending, hist))
            pending = None
    if pending is not None:
        cells.append((*pending, {}))
    return cells


## @brief Report grinding, unused tools and adoption for one run.
## @param cells Parsed per-cell histograms.
## @return Report text.
## @version 1
def report(cells: list[tuple[str, str, str, dict[str, int]]]) -> str:
    """@brief Render the usage report.
    @return Report text.
    @version 1
    """
    lines: list[str] = []
    mcp = [c for c in cells if c[1] == "mcp"]
    totals: collections.Counter = collections.Counter()
    for _, _, _, hist in mcp:
        totals.update(hist)

    lines.append(f"index-arm cells parsed: {len(mcp)} of {len(cells)}")
    lines.append("")
    lines.append("TOOL CALLS ACROSS THE RUN")
    for tool, n in totals.most_common():
        cells_using = sum(1 for _, _, _, h in mcp if tool in h)
        lines.append(f"  {n:>5}  in {cells_using:>2}/{len(mcp)} cells  {tool}")

    lines.append("")
    lines.append(f"GRINDING — one tool called >{GRIND_THRESHOLD}x in a single cell")
    ground = [
        (label, model, tool, n)
        for label, _, model, hist in mcp
        for tool, n in hist.items()
        if n > GRIND_THRESHOLD
    ]
    if ground:
        for label, model, tool, n in sorted(ground, key=lambda r: -r[3]):
            lines.append(f"  {n:>4}x  {tool}  [{label} {model}]")
    else:
        lines.append("  none")

    lines.append("")
    lines.append("CELLS THAT CALLED NO TOOL AT ALL")
    silent = [f"{label} {model}" for label, _, model, hist in mcp if not hist]
    lines.append("  " + (", ".join(silent) if silent else "none"))
    return "\n".join(lines)


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main(argv: list[str]) -> int:
    """@brief Print the usage report for a runner log.
    @return Exit code.
    @version 1
    """
    log = Path(argv[0]) if argv else Path(".claude/tmp/rlc-run.log")
    if not log.is_file():
        print(f"no such log: {log}")
        return 1
    print(report(parse_cells(log)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
