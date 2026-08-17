## @brief Convert a markdown acceptance rubric into the YAML grading key, once.
## @version 1
"""Translate `questions.md` into `questions.yaml`, deriving each mark's evidence ONCE.

WHY A SCRIPT AND NOT A READER FALLBACK. The YAML reader deliberately does not derive symbols or
refs from prose — that is the defect being migrated away from, and a reader that fell back to the
regexes would keep it alive under a new file format with nothing to show it had. So the derivation
runs exactly here, its output is written into the file as data, and from then on a mark's evidence
is whatever an author declared.

THE OUTPUT IS NOT THE END STATE. It is a faithful TRANSLATION, which is what
`bench_rubric.assert_rubrics_equivalent` checks before any correction lands. The corrections — the
false mark, the contradictory census, the prohibitions, the junk-token evidence — are made
afterwards, by hand, against a file that already parses to the same 173 marks. Doing both at once
without the gate makes a dropped mark indistinguishable from a corrected one, which has already
invalidated one grading run here.

Run:
    .venv/bin/python acceptance/bench/rubric_to_yaml.py acceptance/targets/mbedtls/questions.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))


## Front-matter keys carried into the YAML document. Every OTHER key in the markdown front matter
## is dropped deliberately: the counts (`marks`, `graded_marks`) become derived from the list's
## length, because a written count is a second source of truth and every one of them in this rubric
## has been wrong at some point — `marks: 98` survived a 108-mark atomisation, and two prose sites
## still assert 98/89 against a file the parser reads as 173.
## PROVENANCE KEYS ARE LOAD-BEARING AND WERE BEING DROPPED. `build_version` and
## `ground_truth_build_version` were absent from this tuple, so converting a rubric that declared
## `build_version: 32` produced a YAML declaring NOTHING — turning a stale-but-attributed key into
## an UNATTRIBUTED one. `preflight_rubric_provenance` refuses both, so the gate still failed closed
## and the loss was survivable; it was survivable by accident, and the two states mean different
## things ("measured at 32, now stale" vs "nobody recorded where these came from").
##
## The first target migrated hid this because it declares `ground_truth_source` instead, which the
## gate accepts outright — so the missing keys were never exercised until a second target converted.
CARRIED_KEYS = (
    "target",
    "commit",
    "target_ref",
    "version",
    "ground_truth_source",
    "ground_truth_build_version",
    "build_version",
)

## The machine-path key that must NOT be carried. `target_clone` publishes the builder's home
## directory, which this repo's standing rule forbids in anything committed — and `grade_matrix`
## already normalises machine paths out of the grade sidecars while the key itself carried one.
DROPPED_KEYS = ("target_clone",)


## @brief Render one string as a YAML block scalar, indented.
## @param text The text to render.
## @param indent Number of spaces to indent the body by.
## @return The block scalar lines, newline-terminated.
## @version 1
def block_scalar(text: str, indent: int) -> str:
    """A LITERAL BLOCK (`|-`), not a quoted scalar, and not folded. Mark texts carry backticks,
    colons, quotes, em dashes and `#` — every one of which needs escaping in a quoted scalar and
    none of which needs anything here. A folded block (`>`) would reflow the text and change what
    the equivalence gate compares.

    @brief Emit `|-` plus indented body lines.
    @return YAML block scalar text.
    @version 1
    """
    pad = " " * indent
    body = "\n".join(f"{pad}{line}".rstrip() for line in text.splitlines() or [""])
    return f"|-\n{body}\n"


## @brief Render one mark as a YAML list entry.
## @param mark The Mark to render.
## @return YAML lines for this mark.
## @version 1
def render_mark(mark) -> str:
    """EVERY DERIVED FIELD IS WRITTEN EXPLICITLY, including empty ones for symbols and refs when
    the mark genuinely names no evidence. An omitted key and a declared-empty one read the same to
    the parser but not to a person: `symbols: []` says "this mark is conceptual and that was
    checked", where silence says "nobody looked".

    @brief Render a mark entry.
    @return YAML text.
    @version 1
    """
    out = [f"  - text: {block_scalar(mark.text, 6)}"]
    if mark.arm_only:
        out.append(f"    arm_only: {mark.arm_only}\n")
    out.append(f"    symbols: {list(mark.symbols)}\n")
    refs = [[name, lo, hi] for name, lo, hi in mark.refs]
    out.append(f"    refs: {refs}\n")
    return "".join(out)


## @brief Convert one markdown rubric to YAML text.
## @param md Path to the markdown rubric.
## @return The YAML document text.
## @version 1
def convert(md: Path) -> str:
    """@brief Build the YAML document from a markdown rubric.
    @return YAML text.
    @version 1
    """
    import bench_rubric
    import run_matrix

    front = bench_rubric.front_matter(md)
    rubrics = bench_rubric.parse_rubric(md)
    prompts = {q["id"]: q for q in run_matrix.parse_questions(md)}

    lines = [
        "# SPDX-License-Identifier: MIT\n",
        "#\n",
        "# THE GRADING KEY, AS DATA. Generated from questions.md by scripts/rubric_to_yaml.py and\n",
        "# then corrected by hand; the markdown is kept for its prose and is no longer the key.\n",
        "#\n",
        "# A mark's `symbols` and `refs` are DECLARED here rather than guessed from its prose. The\n",
        "# markdown reader inferred them with regexes, so a mark's punctuation decided whether it\n",
        "# was machine-checkable. Both directions were measured on the first target migrated: a\n",
        "# whole-file citation extracted nothing and went to the LLM judge, which scored MISS with\n",
        "# quote NONE while the answer named the file; and a junk token — a bare vendor prefix the\n",
        "# regex lifted out of prose — awarded its mark unseen, because an objective HIT skips the\n",
        "# judge entirely.\n",
        "#\n",
        "# CONVERSION IS MECHANICAL AND CARRIES THE DEFECTS ACROSS. The inferred evidence is\n",
        "# preserved verbatim so the equivalence gate can compare like with like; correcting it is a\n",
        "# separate, reviewable pass. Do not read a declared symbol here as one an author chose.\n",
        "#\n",
        "# `refs` entries are [file], [file, line] or [file, lo, hi]. A bare [file] is a whole-file\n",
        "# citation, which the markdown reader could not express at all.\n",
        "#\n",
        "# NO COUNTS ARE WRITTEN. `marks` and `graded_marks` are the list's length and the fence\n",
        "# arithmetic; every written count in this rubric's history has been wrong at some point.\n",
    ]
    for key in CARRIED_KEYS:
        if front.get(key):
            value = front[key].strip()
            lines.append(f"{key}: {value}\n" if ":" not in value else f'{key}: "{value}"\n')
    lines.append("\nquestions:\n")
    for qid in sorted(rubrics, key=lambda q: int(q[1:])):
        rubric = rubrics[qid]
        lines.append(f"  - id: {qid}\n")
        lines.append(f"    title: {block_scalar(rubric.title, 8)}")
        prompt = (prompts.get(qid) or {}).get("text", "")
        lines.append(f"    prompt: {block_scalar(prompt, 8)}")
        lines.append("    marks:\n")
        for mark in rubric.marks:
            lines.append("".join("  " + ln + "\n" for ln in render_mark(mark).splitlines()))
    return "".join(lines)


## @brief CLI entry point.
## @return Process exit code.
## @version 1
def main() -> int:
    """@brief Convert a markdown rubric to YAML beside it.
    @return 0 on success.
    @version 1
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rubric", type=Path, help="Path to questions.md")
    ap.add_argument("--out", type=Path, default=None, help="Output path (default: questions.yaml)")
    args = ap.parse_args()

    out = args.out or args.rubric.with_suffix(".yaml")
    out.write_text(convert(args.rubric), encoding="utf-8")
    print(f"wrote {out}")

    import bench_rubric

    ## THE GATE RUNS HERE TOO, so a conversion that silently dropped a mark cannot be committed
    ## by someone who forgot to check. It compares text, count and fencing per mark.
    bench_rubric.assert_rubrics_equivalent(args.rubric, out)
    md, yml = bench_rubric.parse_rubric(args.rubric), bench_rubric.parse_rubric_yaml(out)
    print(
        f"equivalent: {len(md)} questions, "
        f"{sum(len(r.marks) for r in md.values())} marks == "
        f"{sum(len(r.marks) for r in yml.values())} marks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
