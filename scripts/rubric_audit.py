# SPDX-License-Identifier: MIT
"""Cross-rubric audit — the properties the loader cannot enforce alone.

The loader validates ONE rubric's shape. These are properties of the SET: that no mark grades
the instrument instead of the target, that a question's weight is not concentrated in one mark,
and that the four targets are comparable in size. A grid whose targets differ by 2x in total
weight is not four measurements of one thing.

@brief Audit the shipped rubrics as a set.
@version 1
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from acceptance.grader.rubric import Mark, Question, Rubric, load  # noqa: E402

## Words that would mean a mark grades clew rather than the target repository. Deliberately
## narrow: `index` alone is a false positive on any repo that has an index of its own, so each
## entry is a tool-surface spelling that cannot occur by accident in a source-derived mark.
_INSTRUMENT = ("mcp__clew", "dossier(", "clew.db", "the index arm", "coverage.barren")

## The shipped targets, discovered one level deep so the private tree (which nests a repo
## directory under `internal/`) is structurally excluded without being named here.
TARGETS = sorted(
    p
    for p in (ROOT / "acceptance" / "targets").glob("*/questions.yaml")
    if p.parent.name != "internal"
)


## @brief Total weighted decisions a mark contributes.
## @param mark The mark.
## @return (decisions, points).
## @version 1
def _cost(mark: Mark) -> tuple[int, int]:
    """@brief Decisions and points for one mark.
    @return (decisions, points).
    @version 1
    """
    n = len(mark.members) + 1 if mark.type == "set" else 1
    return n, n * mark.weight


## @brief Findings for one question.
## @param q The question.
## @param where Target name for the message.
## @return List of complaint strings.
## @version 1
def _audit_question(q: Question, where: str) -> list[str]:
    """@brief Audit one question.
    @return Complaints.
    @version 1
    """
    out: list[str] = []
    points = sum(_cost(m)[1] for m in q.marks)
    for i, mark in enumerate(q.marks):
        text = f"{mark.text} {mark.evidence}".lower()
        for token in _INSTRUMENT:
            if token.lower() in text:
                out.append(f"{where} {q.id} mark[{i}]: grades the instrument ({token!r})")
        share = _cost(mark)[1] / points if points else 0
        ## A single mark carrying more than half a question's weight makes the question one
        ## coin flip wearing a rubric's clothes.
        if share > 0.5:
            out.append(f"{where} {q.id} mark[{i}]: carries {share:.0%} of the question's weight")
    ## THE SATURATION SHAPE, FAILED RATHER THAN NOTED. Unlike a missing set mark — which a
    ## question can legitimately not need — a question whose every citation lands in one file
    ## cannot discriminate between the arms whatever its marks say, so measuring it spends cells
    ## to learn nothing. Two of them already did.
    return out


## @brief Questions with no completeness measure — reported, never failed.
## @param rubric The rubric.
## @param where Target name.
## @return List of note strings.
## @version 1
def _no_set_mark(rubric: Rubric, where: str) -> list[str]:
    """INFORMATIONAL, NOT A COMPLAINT. A set mark measures completeness, and a question with
    nothing enumerable to complete legitimately has none. Failing on its absence would push a
    set mark onto questions that do not have one — forcing a tag to fit, which is worse than
    the gap it papers over.

    @brief Note questions carrying no set mark.
    @return Notes.
    @version 1
    """
    out = [
        f"{where} {q.id}: no set mark (fine if nothing is enumerable here)"
        for q in rubric.questions
        if not any(m.type == "set" for m in q.marks)
    ]
    ## REPORTED, NEVER FAILED — and the demotion is the point. Citation concentration was a
    ## HYPOTHESIS about why two cells saturated at n=1, not an established property, and failing
    ## a build on it would have enforced a guess as policy and rewritten four questions to
    ## satisfy it. n=1 over two questions cannot separate "the answer lived in one file" from
    ## "the question was simply not hard". The number is printed so the weekend grid can TEST it
    ## — if single-file questions saturate and multi-file ones do not, that is a measured result
    ## and the check can be armed then.
    for q in rubric.questions:
        files, busiest = _spread(q)
        if files:
            out.append(f"{where} {q.id}: cites {files} file(s), {busiest:.0%} in the busiest")
    return out


## @brief Distinct files a question's marks cite, and the share the busiest one carries.
## @param q The question.
## @return (distinct files, busiest file's share of cited refs).
## @version 1
def _spread(q: Question) -> tuple[int, float]:
    """THE DESIGN RULE, MADE MEASURABLE. A question discriminates only where the complete answer
    is assembled from places no single read reaches — if it lives in one file, reading that file
    is cheap for either arm and no retrieval substrate can matter.

    Two questions were measured saturated at n=1 for exactly this reason, both scoring 100% on
    both arms, and in both cases the whole answer lived in one file. Neither the loader nor a
    reviewer caught it; the grid did, at the cost of the cells.

    A PROXY, AND SAID SO. Citing four files does not prove an answer needs four reads, and a
    question can spread its citations while its ANSWER still lives in one place. What it catches
    is the shape that has actually failed: every mark pointing at the same file.

    @brief Measure a question's citation spread.
    @return (distinct files, busiest share).
    @version 1
    """
    files: dict[str, int] = {}
    for mark in q.marks:
        for ref in mark.refs:
            if ref:
                files[str(ref[0])] = files.get(str(ref[0]), 0) + 1
    if not files:
        return 0, 0.0
    return len(files), max(files.values()) / sum(files.values())


## @brief Every file a rubric's marks cite that is absent from the pinned checkout.
## @param rubric The rubric.
## @param checkout The target's working tree at the pin, or None to skip.
## @return List of complaint strings.
## @version 1
def _missing_refs(rubric: Rubric, checkout: Path | None, where: str) -> list[str]:
    """THE STRUCTURAL VERSION OF "are these line numbers real". A mark citing a path that does
    not exist at the pin is a mark verified against some other tree, and every line number in it
    is then a claim about a different file — which reads exactly like a correct mark until a
    grader disagrees with it and nobody can tell which side is wrong.

    Only EXISTENCE is checked here. A line number inside an existing file cannot be validated
    without re-reading the source, which is the author's job; a missing file can, and it is the
    failure that actually happens when a pin moves.

    Skipped rather than failed when no checkout is available: a machine without the target
    cloned must still be able to run the rest of the audit.

    @brief Refs point at files that exist at the pin.
    @return Complaints.
    @version 1
    """
    if checkout is None or not checkout.is_dir():
        return []
    out: list[str] = []
    for q in rubric.questions:
        for i, mark in enumerate(q.marks):
            for ref in mark.refs:
                if not ref:
                    continue
                rel = str(ref[0])
                if not (checkout / rel).exists():
                    out.append(f"{where} {q.id} mark[{i}]: cites {rel!r}, absent at the pin")
    return out


## @brief Files a rubric cites that the target's built index does not contain.
## @param rubric The rubric.
## @param db Path to a built clew.db, or None to skip.
## @param where Target name.
## @return List of note strings.
## @version 1
def _unreachable_refs(rubric: Rubric, db: Path | None, where: str) -> list[str]:
    """HOW TO READ THE index_only ARM'S MISSES, computed before the cells are spent.

    That arm has no shell by construction, so a mark citing a file the index never ingested —
    a Makefile, a CMakeLists, a generator script, a YAML config — cannot be reached however good
    retrieval is. Those marks are legitimate: the fact is real and a source arm can find it. But
    scored without this note they read as retrieval failures, and a reader would draw a
    conclusion about the tool from a question about file coverage.

    INFORMATIONAL, NEVER A FAILURE. Removing such a mark would bias the rubric toward what the
    index happens to ingest, which is the self-portrait this project keeps warning about.

    A LOWER BOUND, and said so: a mark citing an INDEXED file can still need source text the
    index does not carry. What this catches is the hard case — the file is not there at all.

    @brief Cited files absent from the index.
    @return Notes.
    @version 1
    """
    if db is None or not db.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        indexed = {r[0] for r in conn.execute("SELECT DISTINCT name FROM path").fetchall()}
    except sqlite3.Error:
        return []
    out: list[str] = []
    for q in rubric.questions:
        missing = sorted(
            {
                str(ref[0])
                for m in q.marks
                for ref in m.refs
                if ref and not any(i.endswith(str(ref[0])) for i in indexed)
            }
        )
        if missing:
            out.append(
                f"{where} {q.id}: cites {len(missing)} file(s) NOT in the index — {', '.join(missing)}"
            )
    return out


## @brief The built index for a target under the run directories, newest first.
## @param name Target directory name.
## @return The database path, or None.
## @version 1
def _index_db(name: str) -> Path | None:
    """@brief Find a provisioned index for a target.
    @return Path or None.
    @version 1
    """
    runs = ROOT / "acceptance" / "runs"
    if not runs.is_dir():
        return None
    for run in sorted(runs.iterdir(), reverse=True):
        found = sorted((run / name / "state" / "targets").glob("*/clew.db"))
        if found:
            return found[0]
    return None


## @brief Locate a target's checkout under the run directories, newest first.
## @param name Target directory name.
## @return The checkout path, or None.
## @version 1
def _checkout(name: str, commit: str) -> Path | None:
    """AT THE PIN, OR NOT AT ALL. This took the newest directory that merely EXISTED, and a
    FAILED provision leaves an empty `repo/` behind — so the audit selected a clone that had
    fetched nothing and reported all 46 of one target's refs as "absent at the pin".

    Confidently wrong, and wrong in the direction that wastes the most time: every mark named,
    every one of them fine. The audit's whole claim is that a cited file exists AT THE PINNED
    COMMIT, so it has to verify the checkout is at that commit rather than assume a directory
    named `repo` is one.

    @brief Find a checkout that is actually at the pin.
    @return Path, or None when no run holds one.
    @version 1
    """
    runs = ROOT / "acceptance" / "runs"
    if not runs.is_dir():
        return None
    for run in sorted(runs.iterdir(), reverse=True):
        candidate = run / name / "repo"
        if not (candidate / ".git").exists():
            continue
        try:
            head = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if head == commit:
            return candidate
    return None


## @brief Audit every shipped rubric.
## @return Process exit code.
## @version 2
def main() -> int:
    """@brief Entry point.
    @return Exit code.
    @version 1
    """
    complaints: list[str] = []
    notes: list[str] = []
    sizes: dict[str, int] = {}
    for path in TARGETS:
        rubric: Rubric = load(path)
        name = path.parent.name
        total = 0
        for q in rubric.questions:
            complaints += _audit_question(q, name)
            total += sum(_cost(m)[1] for m in q.marks)
        notes += _no_set_mark(rubric, name)
        notes += _unreachable_refs(rubric, _index_db(name), name)
        checkout = _checkout(name, rubric.commit)
        if checkout is None:
            notes.append(
                f"{name}: no checkout AT THE PIN {rubric.commit[:10]}, ref existence unchecked"
            )
        else:
            complaints += _missing_refs(rubric, checkout, name)
        sizes[name] = total
        decisions = sum(_cost(m)[0] for q in rubric.questions for m in q.marks)
        print(
            f"{name:<10} v{rubric.version:<8} {len(rubric.questions)}q  {decisions:3d} decisions  {total:3d} points"
        )

    spread = max(sizes.values()) / min(sizes.values())
    print(
        f"\nsize spread {spread:.1f}x  (largest {max(sizes, key=sizes.get)}, smallest {min(sizes, key=sizes.get)})"
    )
    for line in notes:
        print(f"  . {line}")
    for line in complaints:
        print(f"  ! {line}")
    return 1 if complaints else 0


if __name__ == "__main__":
    raise SystemExit(main())
