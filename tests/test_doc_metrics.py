# SPDX-License-Identifier: MIT
"""Acceptance figures have ONE home, and a copy outside it is a defect.

**SKILLS.md SHIPPED FOUR WRONG NUMBERS, AND ONE OF THEM WAS FABRICATED.** Its summary carried
figures from a partial two-target run that the full grid superseded, and it had transcribed the
A/B pre-registration's `+11.8%` *turns* as "11.8 dossier calls per question" — a percentage read
as a count, then reasoned from in prose. 1.1.1 was the release that first shipped SKILLS.md inside
the wheel, so the wrong figures went out wider than they had ever been.

**THE CAUSE WAS PLACEMENT, NOT CARELESSNESS.** A figure in `acceptance/runs/<date>/` is versioned
with the run that produced it, pre-registered, and published beside the `KNOWN-DEFECTS.md` that
says which way each defect moves it. The same figure pasted into a usage document has no owner, no
test, and no disclosure — and the next grid invalidates it silently. Correcting such a copy is the
wrong fix: it preserves the second source that drifted in the first place.

So the rule is one source and N=0 touch points, and this test is what makes the rule real. A
prose rule unenforced by a test is how the first four got in.

**WHAT IS NOT BANNED.** Qualitative claims — "answers less completely", "costs meaningfully less"
— are guidance a reader can act on and do not go stale when the grid reruns. Version numbers,
complexity limits and dates are not measurements of the index's performance. What is banned is the
shape of a RESULT: a point delta, a comparative percentage, a cell count, a dispersion statistic.

@brief No acceptance figure may appear in a document outside acceptance/.
@version 1
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

## THE SHAPE OF A RESULT, not the shape of any number. Each pattern is one way this repository has
## actually published an acceptance figure:
##   - "13.92 pt", "17.9 points"      — a completeness delta
##   - "35.2% fewer", "20% below"     — a comparative cost or quality claim
##   - "SEM", "4.2σ"                  — a dispersion statistic, only ever from a grid
##   - "144-cell"                     — the grid's size
##   - "245 of 353 —"                 — a counted share, as the pre-registration writes it
## A bare percentage is deliberately NOT matched: "97% of the time" as plain emphasis is not a
## measurement, and a rule that fired on it would be switched off.
_RESULT_SHAPES = (
    r"\d+(?:\.\d+)?\s*(?:pt|points)\b",
    r"\d+(?:\.\d+)?\s*%\s*(?:fewer|less|more|below|above|better|worse)",
    r"\bSEM\b",
    r"σ",
    r"\b\d+-cell\b",
    r"\b\d+ of \d+\s*—",
)
_RESULT = re.compile("|".join(_RESULT_SHAPES))

## `acceptance/` IS THE HOME, so it is not scanned — that is the whole point rather than an
## exemption. `tests/` holds this file's own examples, which would otherwise match themselves.
_HOME = ("acceptance", "tests")


##
# @brief Every markdown document outside acceptance/ that a reader could quote from.
# @return Repo-relative paths.
# @version 1
# @dg_internal
def _documents() -> list[Path]:
    """Repo root and `docs/` only. A document under `acceptance/` is the source of truth and a
    document under `tests/` is a fixture; everything else is a place a figure can be copied to and
    then outlive the run that produced it.

    @brief Documents that must carry no figures.
    @return The paths.
    @version 1
    """
    found = [*REPO_ROOT.glob("*.md"), *(REPO_ROOT / "docs").rglob("*.md")]
    return sorted(
        p for p in found if not any(part in _HOME for part in p.relative_to(REPO_ROOT).parts)
    )


##
# @brief No document outside acceptance/ may carry an acceptance figure.
# @return None.
# @version 1
def test_no_acceptance_figure_outside_acceptance() -> None:
    """THE FAILURE NAMES THE LINE AND THE MATCH, because "a doc has a number in it" sends the
    reader to read every doc. The fix is almost always to delete the figure and point at the run
    directory, not to correct it — a corrected copy is still a copy.

    @brief Documents carry no figures.
    @return None.
    @version 1
    """
    offences: list[str] = []
    for path in _documents():
        rel = path.relative_to(REPO_ROOT)
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            offences += [
                f"{rel}:{number}: {match.group(0)!r} in: {line.strip()[:100]}"
                for match in _RESULT.finditer(line)
            ]

    assert not offences, (
        "acceptance figures appear outside acceptance/, where nothing versions them with the run "
        "that produced them and nothing discloses what moves them:\n  "
        + "\n  ".join(offences)
        + "\n\nDelete the figure and point at acceptance/runs/<date>/RESULTS.md. Do not correct "
        "it in place — a corrected copy is still a second source, and the first one drifted."
    )


##
# @brief The scan must actually look at the documents it claims to cover.
# @return None.
# @version 1
def test_the_scan_covers_the_documents_a_reader_quotes_from() -> None:
    """A PASS MUST NOT BE ABLE TO MEAN "NOTHING WAS SCANNED". A glob that silently matched nothing
    — a moved `docs/`, a renamed README — would make the check above vacuous and green, which is
    this project's most-repeated defect shape. So the two documents most likely to carry a copied
    figure are asserted to be in the set by name.

    @brief The scan is not vacuous.
    @return None.
    @version 1
    """
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _documents()}

    assert len(scanned) >= 5, f"only {len(scanned)} document(s) scanned: {sorted(scanned)}"
    for required in ("README.md", "SKILLS.md"):
        assert required in scanned, f"{required} is not being scanned; got {sorted(scanned)}"


##
# @brief The detector must catch each result shape this repository has published.
# @param figure A figure in a shape that has actually shipped.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "figure",
    [
        "scored 13.92 pt below baseline",
        "scored **17.9 points** below",
        "while using 35.2% fewer output tokens",
        "quality is 20% below baseline",
        "cluster-robust SEM 3.31",
        "a 4.2σ result",
        "on the 144-cell grid",
        "245 of 353 — 69%",
    ],
)
def test_the_detector_catches_a_figure_that_actually_shipped(figure: str) -> None:
    """EVERY STRING HERE IS ONE THIS REPOSITORY REALLY PUBLISHED, in SKILLS.md or in a RESULTS.md
    headline someone could paste. A detector tested only against invented examples is a detector
    tuned to the examples.

    @brief Each shipped shape is detected.
    @param figure The figure.
    @return None.
    @version 1
    """
    assert _RESULT.search(figure), f"the detector would let {figure!r} through"


##
# @brief Guidance and ordinary numbers must not trip the detector.
# @param allowed Text that must remain legal.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "allowed",
    [
        "the index answers less completely than a shell-only agent",
        "cognitive complexity <= 15, returns <= 3",
        "clew 1.1.1 ships SKILLS.md in the wheel",
        "97% of the time this is what you want",
        "doxygen exits 2 and writes nothing",
        "up to eight subjects per call",
    ],
)
def test_guidance_and_ordinary_numbers_are_not_figures(allowed: str) -> None:
    """THE PERMISSIVE LEG IS THE ONE THAT KEEPS THE CHECK ALIVE. A rule that fired on a version
    number, a complexity limit or a plain emphatic percentage would be excluded within a day, and
    then the real figures would walk back in behind it. `97%` is here deliberately: a bare
    percentage is not a measurement of the index.

    @brief Legal text stays legal.
    @param allowed The text.
    @return None.
    @version 1
    """
    assert not _RESULT.search(allowed), f"the detector wrongly flags {allowed!r}"
