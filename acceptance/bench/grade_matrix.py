## @brief Benchmark GRADER: completeness vs the frozen rubric + blind pairwise quality.
## @version 1
"""Score benchmark answers on the architect's two judgement axes.

Axis 1 (time/cost) belongs to `run_matrix.py`; this module owns:

- **Completeness** — every mark of the frozen rubric scored HIT or MISS per
  answer (a mark is a mark; there is no partial credit and no half point),
  objectively first (symbols + `file:line`, see
  `bench_score.py`) and by a tool-less LLM judge for anything the objective
  pass could not settle. Every verdict carries evidence, because these grades
  are **advisory to a human** who must be able to overturn them.
- **Quality** — blind pairwise comparison of two arms' answers to the same
  question. The judge never learns which arm wrote which answer, arm-to-A/B
  assignment is randomised, and every pair is judged **both ways** so a verdict
  that flips under order swap is reported as unreliable rather than counted.

Non-negotiables enforced here:

- No judging prompt ever contains an arm, model or run identifier.
- An unparseable judge reply is `judge_error`, never a 0.
- Bonus items the rubric fences as raw-arm-only are scored but reported
  separately and never counted against the db arm.

Usage:
  .venv/bin/python acceptance/bench/grade_matrix.py complete --answers runs/pilot
  .venv/bin/python acceptance/bench/grade_matrix.py pairwise --answers runs/pilot --q Q1
  .venv/bin/python acceptance/bench/grade_matrix.py report   --answers runs/pilot
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bench_judge as judge
import bench_publish
import target_check
from bench_rubric import (
    Mark,
    load_rubric,
    preflight_rubric_provenance,
    reachable_fence,
)
from bench_score import answer_citations, score_mark
from grade_prompts import (
    FALSITY_VERDICTS,
    MARK_VERDICTS,
    anonymise,
    falsity_prompt,
    mark_prompt,
    pairwise_prompt,
)

HERE = Path(__file__).resolve().parent
## `--rubric` IS REQUIRED AND HAS NO DEFAULT, deliberately.
##
## It used to default to this repo's own self-index matrix. A default is exactly
## how the retracted grid happened: a value that was right when it was written,
## never revisited, and silently wrong once the work moved to a different target.
## Grading one target's answers against another target's rubric would not crash —
## it would produce a full set of plausible MISS verdicts and a
## publishable-looking number.
##
## There is no safe default here, because the correct rubric is a property of the
## RUN, not of the tool. Making the argument mandatory costs one flag and removes
## a whole class of silent mis-grade.
## WHAT A VERDICT IS WORTH, as a module constant so it can be asserted. It was a local
## literal inside `summarise`, duplicated as a second literal for the counts, and contradicted
## by a THIRD hardcoded 0.5 in the score expression — three copies of one rule, none of them
## read by a test.
##
## Every weight is 0.0 or 1.0: a mark is a mark (owner, 2026-08-13). `JUDGE_ERROR` is scorable
## but is NOT in `MARK_VERDICTS`, because the judge cannot self-report a transport failure —
## the harness assigns it. It weighs 0.0 and `unmarked_pct` is reported beside every score for
## exactly that reason: weighing 0.0 makes it arithmetically identical to a genuine MISS, and
## on one grid that silently converted 102 unruled marks into failures against both arms.
VERDICT_WEIGHT: dict[str, float] = {"HIT": 1.0, "MISS": 0.0, "JUDGE_ERROR": 0.0}

## HOW STRONG A FALSITY MAJORITY MUST BE TO VETO. D3 makes one judge call able to zero a whole
## question, and that judge has already produced 102 unruled marks on one grid — so a bare
## majority is not enough. 3 of 3 (or 5 of 5) is required: unanimity across independent samples,
## and the agreement ratio is recorded either way so a divided vote is visible rather than
## laundered into a clean flag.
##
## Deliberately conservative in one direction only. A missed falsehood costs one wrong cell,
## which the owner reading the answer can still catch; a WRONGLY vetoed cell reads as a
## catastrophic tool failure and is exactly the kind of number that gets quoted.
VETO_AGREEMENT = 1.0

## Independent falsity samples per cell. Odd, so a non-unanimous vote still has a majority to
## report. 0 disables the pass entirely — it costs this many extra judge calls per cell, and
## session capacity is the constraint that actually binds a sweep.
##
## RE-ARMED (3), and the SELECTION is what made arming defensible rather than any change to the
## veto. It was disarmed because `grade_answer` handed it every MARK TEXT as an established fact,
## on the argument that under D2 each mark is one source-verified atomic fact and a second catalog
## could drift from the key. The argument was good; its premise was false. An audit of all 173
## marks found Q3 #18 asserting "a DEFAULT build of this repository creates no threads at all",
## refuted by `programs/test/benchmark.c:430` — that `_beginthread` is gated on `_WIN32`, a
## PLATFORM condition, with `MBEDTLS_HAVE_TIME` active and `MBEDTLS_TIMING_ALT` commented out. Q1
## #27 said FIVE named global mutexes where the committed `evidence.md` census says six. Around
## fourteen further marks were GRADING INSTRUCTIONS rather than facts about the target at all.
##
## Fed a false fact the veto INVERTS: an answer that correctly reports the Windows spawn is ruled
## CONTRADICTED, stamped `index_false` and zeroed, so the MORE accurate arm is punished on a
## whole-question basis. That is worse than not checking.
##
## What changed: batch 2 deleted the grading instructions, batches 1-4 corrected the false marks,
## and marks now carry `veto_safe` — so `veto_facts` feeds the veto a DECLARED SUBSET whose premise
## actually holds, keeping the no-second-catalog virtue and dropping only what is not a fact.
##
## ARMING WITHOUT THE FILTER WOULD BE WORSE THAN LEAVING IT OFF, which is why the two land together:
## batch 4 enumerated acceptable answer SETS in mark prose ("a file not in this tree does not earn
## the mark"), and handed to the veto as facts those would rule an answer naming a different correct
## file CONTRADICTED.
##
## `falsity_check` still returns None at 0 samples OR on an empty fact list, which `summarise`
## records as `falsity_checked: null` and the report prints as "unchecked" — the honest third state,
## never a pass.
VETO_SAMPLES = 3

ANSWER_NAME = re.compile(r"^(Q\d+)_([A-Za-z0-9.-]+)_(src|mcp)_r(\d+)$")
CRITERIA = ("CORRECTNESS", "CAUSAL_COMPLETENESS", "CITATION_INTEGRITY", "CLARITY")

## Consecutive cells carrying ANY judge error before grading gives up.
##
## THREE, and the trigger is ANY error rather than a fully-errored cell. The first version
## required EVERY mark of a cell to fail, and that was MEASURABLY too weak: a real run went 41
## cells clean, degraded on cell 42 and never recovered, but the all-errored condition did not
## hold until cell 119. It burned 78 contaminated cells — 449 of 1,026 marks, 43.8% — before
## stopping. The guard fired, and far too late to be worth having.
##
## The measured shape justifies the looser trigger: capacity exhaustion is MONOTONIC. Once the
## judge starts refusing it does not recover, so a cell with any error is a reliable early
## signal and three in a row is not a transient. On that run this would have fired at cell 44.
##
## Why stopping matters at all: JUDGE_ERROR weighs 0.0, arithmetically identical to "the judge
## ruled MISS", so a transport failure reads as a substantive result to anything that does not
## check `unmarked_pct`. An earlier pass scored 102 of 324 marks exactly that way.
MAX_CONSECUTIVE_DEGRADED_CELLS = 3


## @brief Identify an answer file from its filename convention.
## @param path Answer markdown path.
## @return Cell dict, or None when the name does not match.
## @version 1
def parse_cell(path: Path) -> dict | None:
    """@brief Decode `Q1_haiku_src_r1.md` into its cell coordinates.
    @return Cell record or None.
    @version 1
    """
    found = ANSWER_NAME.match(path.stem)
    if not found:
        return None
    return {"q": found.group(1), "model": found.group(2), "arm": found.group(3),
            "run": int(found.group(4)), "path": path}  # fmt: skip


## @brief List the answer files in a run directory.
## @param answers Run directory.
## @return Cell records, ordered by filename.
## @version 1
def list_cells(answers: Path) -> list[dict]:
    """VOID CELLS ARE EXCLUDED AND NAMED, never silently dropped. A cell whose index answered
    about a different repository has meaningless marks, so averaging them corrupts every
    figure the run publishes — but excluding one without saying so is the failure this project
    already shipped twice, most recently when 102 unruled marks were counted as substantive.
    Every exclusion is printed with its coordinates.

    A run directory with NO `target_ok` column was written before the check existed. It is
    reported as UNCHECKED rather than clean: absence of the column is absence of the
    measurement, and the two must not share a spelling.

    @brief Enumerate gradable answers, excluding and naming void cells.
    @return Cell list.
    @version 2
    """
    cells = [c for c in (parse_cell(p) for p in sorted(answers.glob("*.md"))) if c]
    if not target_check.records_target_column(answers):
        print(
            f"NOTE: {answers}/metrics.csv carries no `target_ok` column — this run predates "
            "the wrong-repository check. Its cells are UNCHECKED for target correctness, "
            "which is not the same as checked and clean."
        )
        return cells
    voids = target_check.void_cells(answers)
    if voids:
        print(f"EXCLUDED {len(voids)} VOID cell(s) — index answered about another repository:")
        for stem, coords in sorted(voids.items()):
            print(f"  {stem}  ({coords})")
    return [c for c in cells if c["path"].stem not in voids]


## @brief Ask the judge to settle one mark against one answer.
## @param mark Rubric mark.
## @param body Anonymised answer text.
## @param model Judge model alias.
## @return Verdict dict (verdict / quote / why / judge_error / raw).
## @version 1
def judge_mark(mark: Mark, body: str, model: str) -> dict:
    """@brief Run the LLM-judge pass for one mark.
    @return Judge verdict record.
    @version 1
    """
    reply = judge.ask(mark_prompt(mark.text, body), model=model)
    if reply.error:
        return {"verdict": None, "judge_error": reply.error}
    ## The SAME constant the prompt renders its verdict block from, never a second copy —
    ## a token the judge is offered but the extractor rejects becomes a JUDGE_ERROR, which
    ## weighs what a genuine MISS weighs, so the disagreement would read as a bad ANSWER.
    got = judge.extract_verdict(reply.text, "VERDICT", MARK_VERDICTS)
    if got.token is None:
        return {"verdict": None, "judge_error": "no VERDICT token", "raw": reply.text}
    ## The raw reply is always kept: a verdict whose WHY contradicts it is how the
    ## copied-placeholder failure mode (v1 prompts literally showed `VERDICT: HIT`)
    ## was caught, and a human re-checking a grade needs to see the same thing.
    record: dict = {"verdict": got.token, "quote": judge.field(reply.text, "QUOTE"),
                    "why": judge.field(reply.text, "WHY"), "raw": reply.text}  # fmt: skip
    ## Recorded, never silent: a reply that named several verdicts was resolved by
    ## taking the LAST (the judge self-correcting), and a reader must be able to
    ## tell such a grade from one the judge stated once. `summarise` counts these
    ## so the per-cell rate is visible next to the score.
    if got.disambiguated:
        record["verdict_disambiguated"] = True
        record["verdict_sequence"] = list(got.tokens)
    return record


## @brief Combine the objective and judge verdicts for one mark.
## @param objective Objective verdict token.
## @param judged Judge verdict record or None.
## @return Final verdict token, or "JUDGE_ERROR".
## @version 1
def _final_verdict(objective: str, judged: dict | None) -> str:
    """The better of the two wins: the objective pass is deliberately strict
    (an answer that says the right thing in different words fails it), so the
    judge can only ever *raise* a verdict, never lower a proven citation.

    @brief Reconcile objective and judge verdicts.
    @return Final verdict token.
    @version 2
    """
    ## Two ranks, not three: with PARTIAL gone the reconciliation is "did either pass find
    ## it", which is what "the judge can only raise" always meant.
    rank = {"MISS": 0, "n/a": 0, "HIT": 1}
    if judged is None:
        return objective if objective != "n/a" else "MISS"
    if judged.get("verdict") is None:
        return "JUDGE_ERROR" if objective in ("n/a", "MISS") else objective
    ## `judged` FIRST, and n/a normalised away. `max` returns its first argument on
    ## a tie, and "n/a" ties with "MISS" at rank 0 — so with `objective` first, an
    ## objective "n/a" beat a judge's "MISS" and `n/a` became the FINAL verdict.
    ## That is not a scoring error (both weigh 0) but it is a reporting one:
    ## `summarise` counts only HIT/PARTIAL/MISS/JUDGE_ERROR, so those marks
    ## disappeared from the counts while still filling `marks_total` — Q4's mcp cell
    ## reported 2 hit + 0 partial + 2 miss + 0 errors out of 9.
    ##
    ## `n/a` means "the objective pass had nothing to match on", which is the exact
    ## case the judge exists to settle. Once the judge has ruled, its verdict is the
    ## verdict.
    best = max(judged["verdict"], objective, key=lambda v: rank.get(v, 0))
    return "MISS" if best == "n/a" else best


## @brief Score one mark end to end (objective, then judge if unsettled).
## @param mark Rubric mark.
## @param answer Raw answer text.
## @param body Anonymised answer text.
## @param cites Answer citation index.
## @param opts Parsed CLI options.
## @return Per-mark result dict.
## @version 1
def grade_mark(mark: Mark, answer: str, body: str, cites: dict, opts) -> dict:
    """@brief Produce one mark's verdict with full evidence.
    @return Mark result record.
    @version 1
    """
    objective = score_mark(mark, answer, cites, drift=opts.drift)
    judged = None
    if objective.verdict != "HIT" and not opts.no_judge:
        judged = judge_mark(mark, body, opts.judge_model)
    return {
        "index": mark.index, "text": mark.text,
        "arm_only": mark.arm_only, "conceptual": mark.conceptual,
        "objective": {"verdict": objective.verdict, "symbols_hit": objective.symbols_hit,
                      "symbols_weak": objective.symbols_weak, "symbols_missed": objective.symbols_missed,
                      "refs_hit": objective.refs_hit, "refs_file_only": objective.refs_file_only,
                      "refs_missed": objective.refs_missed, "evidence": objective.evidence},
        "judge": judged,
        "verdict": _final_verdict(objective.verdict, judged),
    }  # fmt: skip


## @brief Select the mark texts the falsity veto may treat as established facts.
## @param marks The question's marks.
## @return Texts of the veto-safe marks, in rubric order.
## @version 1
def veto_facts(marks) -> list[str]:
    """THE SUBSET THE VETO IS ALLOWED TO TREAT AS TRUE. A mark earns `veto_safe` by being a claim
    about the TARGET that was re-verified against source — not a grading rule, not an enumeration of
    acceptable answers, not a judgement about an answer's completeness. Everything else is graded
    normally and simply never becomes a fact an answer can contradict.

    RETURNS A LIST SO AN EMPTY ONE PROPAGATES. `falsity_check` refuses on an empty fact list, which
    is the fail-closed path when a rubric declares nothing veto-safe: unchecked, not clean.

    @brief Select the mark texts the falsity veto may treat as established facts.
    @param marks The question's marks.
    @return Texts of the veto-safe marks, in rubric order.
    @version 1
    """
    return [mark.text for mark in marks if mark.veto_safe]


## @brief Vote on whether an answer contradicts the rubric's veto-safe facts.
## @param truths Established facts, already filtered to the veto-safe subset.
## @param body Anonymised answer text.
## @param model Judge model.
## @param samples Independent samples to vote over; 0 disables.
## @return Falsity record, or None when not checked.
## @version 2
def falsity_check(truths: list[str], body: str, model: str, samples: int) -> dict | None:
    """D3'S VETO, and the whole design is about not trusting it too much.

    VOTED, NOT ASKED ONCE. `bench_judge.vote` has existed since the harness was written, is
    documented in `methodology.md` as an active reliability safeguard, and was called from
    NOWHERE — every mark's verdict came from a single sample. A veto that can zero a question
    is the one place that is indefensible, so this is its first real caller.

    UNANIMITY REQUIRED (`VETO_AGREEMENT`). A 2-of-3 majority would let one flaky sample carry a
    catastrophic-looking result. The agreement ratio and the full tally are recorded whether or
    not the veto fires, so "the judge was divided" is a readable state instead of an invisible
    one.

    ERRORS DO NOT VETO. `vote` counts an unparseable or failed sample as an error rather than a
    vote, and a run whose samples all errored returns `verdict=None` — which must read as "not
    checked", never as "clean" and never as "false". That distinction is the same one the
    `unmarked_pct` work exists for: a transport failure scored as a substantive result is how
    102 marks became failures against both arms.

    @brief Vote on whether the answer contradicts the established facts.
    @return Falsity record with the veto decision and its evidence, or None.
    @version 1
    """
    if samples <= 0 or not truths:
        return None
    tally = judge.vote(
        falsity_prompt(truths, body), "VERDICT", FALSITY_VERDICTS, n=samples, model=model
    )
    contradicted = tally.verdict == "CONTRADICTED"
    return {
        "checked": tally.verdict is not None,
        "verdict": tally.verdict,
        "agreement": round(tally.agreement, 2),
        "tally": [list(pair) for pair in tally.tally],
        "samples": tally.samples,
        "errors": tally.errors,
        ## HOW MANY FACTS THE PASS ACTUALLY WEIGHED, because "clean" over one fact and "clean" over
        ## nineteen are different claims and both used to print the same word. This is the same
        ## failure the three-state `falsity_checked` exists to prevent, one level in: arming a
        ## rubric that declares a single veto-safe mark moves every cell from `unchecked` to
        ## `clean` while almost nothing was checked, so the fix for the emptier state manufactures
        ## a reassuring one. A denominator beside the verdict is what keeps the move honest.
        "facts": len(truths),
        ## The veto itself, kept separate from the judge's raw verdict so a reader can see a
        ## CONTRADICTED that did NOT reach unanimity and therefore did not fire.
        "vetoed": bool(contradicted and tally.agreement >= VETO_AGREEMENT),
    }


## @brief Refuse, by name, any verdict the score cannot weigh.
## @param results Per-mark result dicts, already fence-filtered.
## @param weight The countable verdict set mapped to its weight.
## @return None.
## @version 1
def _refuse_unscorable(results: list[dict], weight: dict[str, float]) -> None:
    """UP FRONT, because the alternative is a bare `KeyError` from inside the scoring loop.
    `weight[...]` is subscripted twice per mark — once on the final verdict and once on the
    judge's — and neither used `.get`, so a verdict outside the set surfaced as
    `KeyError: 'PARTIAL'` with no statement of what was wrong or which mark carried it. The
    anti-vacuity check further down says all of that, and never ran, because the loop raised
    first.

    BOTH verdicts are checked. `score_strict` weighs the JUDGE's token where the judge ruled,
    so a stored sidecar carrying a retired verdict fails on the strict column even when its
    final verdict is fine — and that is precisely the case that arrives when a verdict is
    removed from the set while graded runs already exist on disk.

    @brief Raise naming any unscorable verdict rather than failing on a subscript.
    @return None.
    @version 1
    """
    seen = {r["verdict"] for r in results}
    seen |= {v for r in results if (v := (r.get("judge") or {}).get("verdict")) is not None}
    unexpected = sorted(seen - set(weight))
    if unexpected:
        offenders = [r["index"] for r in results if r["verdict"] in unexpected and "index" in r]
        raise AssertionError(
            f"summarise cannot score these marks: uncounted verdict values {unexpected} "
            f"(marks {offenders or 'unnumbered'}). Scorable verdicts are "
            f"{sorted(weight)}. A retired verdict in a stored sidecar must be re-graded, "
            "not re-weighted — weighing it zero would report it as a genuine MISS."
        )


## @brief Aggregate per-mark verdicts into a summary block.
## @param results Per-mark result dicts.
## @param arm The arm being scored, so fenced marks can be excluded.
## @param falsity Falsity-pass record, or None when the pass did not run.
## @return Summary counts, the score, and the veto state.
## @version 4
def summarise(results: list[dict], arm: str = "", falsity: dict | None = None) -> dict:
    """A MARK IS A MARK — hit or miss, never a half point (owner, 2026-08-13).
    `questions-TEMPLATE.md` had said exactly that all along while the code disagreed,
    weighting PARTIAL 0.5 in the weight map and again through a SEPARATE hardcoded 0.5 in the
    score expression. Nothing tested either number, so the two could have drifted apart
    unnoticed as easily as they could both be wrong.

    Under atomic marks the middle verdict is not a finer measurement, it is a refusal to
    decide that then gets averaged into a headline. So PARTIAL is not re-weighted to 0 — it is
    removed from the countable set, which makes the anti-vacuity check below reject it rather
    than score it silently.

    FENCED MARKS ARE EXCLUDED FROM THE ARM THAT CANNOT REACH THEM, rather than scored zero.
    `arm_only` names the arm that CAN reach a mark, so a mark tagged `db` is dropped from the
    raw arm's denominator and vice versa.

    This is the half that was missing. The parser recorded `arm_only` into every sidecar and
    nothing ever read it; the rubric said the correction "must be applied by hand" and nobody
    did, so a published result counted four unreachable marks against the raw arm and
    understated it by 4 points. Scoring zero and excluding are very different: zero says
    "tried and failed", exclusion says "was never on the exam".

    `arm=""` scores everything, which keeps the bonus path and any caller that does not know
    its arm behaving exactly as before.

    @brief Summarise a set of mark verdicts, honouring arm fences.
    @return Summary dict.
    @version 3
    """
    ## ONE SOURCE for the countable set, and `counts` is derived from it, so the two cannot
    ## disagree about what a verdict is — they were separate literals, which is how a set
    ## change had to be made in two places and remembered in a third.
    weight = VERDICT_WEIGHT
    counts = dict.fromkeys(weight, 0)
    strict = 0.0
    disambiguated = 0
    ## Drop marks this arm was never able to reach. `arm_only` names the arm that CAN.
    ##
    ## TWO VOCABULARIES, and comparing them directly is wrong in a way that looks right: the
    ## rubric writes `raw`/`db` while the harness writes `src`/`mcp`. A naive `!=` fenced the
    ## db arm out of its OWN marks, because "db" != "mcp". Caught by a control that asserted
    ## the exclusion points the right way rather than merely that it happens.
    ##
    ## THE MAPPING NOW LIVES IN `bench_rubric.reachable_fence`, because a second consumer
    ## arrived: `run_matrix.plan_cells` must not schedule a cell whose every mark is fenced
    ## against its arm, and it needs the identical translation. Copying it there would have put
    ## the inversion this comment warns about into the one place nobody would re-read.
    reachable = reachable_fence(arm)
    fenced_out = [r for r in results if arm and r.get("arm_only") and r["arm_only"] != reachable]
    results = [r for r in results if r not in fenced_out]
    _refuse_unscorable(results, weight)
    for item in results:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
        judged = (item.get("judge") or {}).get("verdict")
        strict += weight[judged] if judged else weight[item["verdict"]]
        if (item.get("judge") or {}).get("verdict_disambiguated"):
            disambiguated += 1
    ## Anti-vacuity: the four reported counts must account for every mark. They did
    ## not — an `n/a` final verdict fell through `counts` while still filling
    ## `marks_total`, so a cell read as "2 hit + 0 partial + 2 miss + 0 errors of 9"
    ## and nobody noticed for a whole grid. A summary whose parts do not sum to its
    ## whole is not a summary.
    ## PARTIAL's absence here is what makes its removal enforced rather than advisory: a
    ## sidecar or a judge reply still carrying one now RAISES by name instead of being
    ## re-weighted to zero and reported as a MISS.
    reported = tuple(VERDICT_WEIGHT)
    counted = sum(counts[k] for k in reported)
    if counted != len(results):
        ## `counts` grows a key for any verdict seen (it uses .get), so the missing
        ## values must be found against the REPORTED keys, not against `counts`.
        unexpected = sorted({r["verdict"] for r in results} - set(reported))
        raise AssertionError(
            f"summarise lost {len(results) - counted} of {len(results)} marks; "
            f"uncounted verdict values: {unexpected}"
        )
    ## A MARK THE JUDGE NEVER RULED ON WAS NOT MEASURED. `JUDGE_ERROR` weighs 0.0, which made
    ## it arithmetically identical to "the judge ruled MISS" — so a transport failure was
    ## scored as a substantive result. On one corrected grid that was 102 of 324
    ## marks (31%), every one of them the same cause: the grading run exhausted session
    ## capacity and every subsequent judge call returned "You've hit your session limit".
    ##
    ## `unmarked_pct` makes the exam's coverage visible beside its score, because a 51% built
    ## from 69% of the marks is a different claim from a 51% built from all of them. The score
    ## and denominator still INCLUDE these — removing them silently would inflate every score
    ## the moment the judge got flaky, which is a worse failure than the one being fixed.
    ## Report it; let a human decide whether the run is usable.
    judged_marks = len(results) - counts["JUDGE_ERROR"]
    return {
        "marks_hit": counts["HIT"],
        "marks_miss": counts["MISS"], "judge_errors": counts["JUDGE_ERROR"],
        ## Share of this cell's marks the judge never ruled on. 0.0 is a fully graded cell.
        "unmarked_pct": round(100.0 * counts["JUDGE_ERROR"] / max(1, len(results)), 1),
        "marks_judged": judged_marks,
        ## Marks whose verdict came from a self-correcting reply. Reported beside
        ## the score because a cell built mostly from disambiguated verdicts is
        ## weaker evidence than the same score stated once.
        "verdicts_disambiguated": disambiguated,
        ## Marks this arm was fenced out of, reported so an excluded mark is VISIBLE rather
        ## than a silently smaller denominator. A reader must be able to see that 6/6 and
        ## 6/10 are different claims about the same answer.
        "marks_fenced_out": len(fenced_out),
        ## D3'S VETO, AS ITS OWN FIELDS AND NEVER FOLDED INTO `marks_miss`. A false statement
        ## traceable to an index reply zeroes the question — the agent is instructed to trust
        ## the index absolutely, so the falsehood is the TOOL's, and a 99% token reduction with
        ## a false answer is a failure, not a win.
        ##
        ## `score` KEEPS ITS MEASURED VALUE and `quality_vetoed` carries the veto separately.
        ## Collapsing the score to 0 here would destroy the per-cell evidence a human needs to
        ## confirm the veto by hand — and the veto is judge-driven, by the same judge that
        ## produced 102 unruled marks on one grid. Consumers that compute a headline honour
        ## `quality_vetoed`; the per-cell view shows both, so "scored 24/30 AND vetoed" is a
        ## readable state rather than an unexplained zero.
        ##
        ## AND `None` WHEN THE PASS NEVER RAN, because the per-cell view was already honest while
        ## the aggregate was not. `_veto_cell` has printed four distinguishable words since the
        ## DIVIDED fix, but this field recorded 0 whether the pass found nothing or was never
        ## armed — so anything SUMMING it prints a reassuring zero over cells nobody checked.
        ## Measured on the pre-release grid: 50 of 74 public cells were never falsity-checked
        ## (entropic declares no veto-safe mark at all, so its 28 are unchecked by construction),
        ## and an aggregate over them was published as `index_false: 0` in the same session that
        ## found it. A TYPE fixes what a caveat cannot: `sum()` over a None raises instead of
        ## reading zero, and the warning that has to survive is the one nobody has to read.
        "index_false": None if falsity is None else (1 if falsity.get("vetoed") else 0),
        "quality_vetoed": bool((falsity or {}).get("vetoed")),
        ## Three states, not two: not run, ran and found nothing, ran and could not tell.
        ## "unchecked" must never read as "clean" — this repo's standing rule.
        "falsity_checked": None if falsity is None else bool(falsity.get("checked")),
        ## THE FOURTH STATE, carried so the report can print it. A judge that ruled
        ## CONTRADICTED without reaching `VETO_AGREEMENT` leaves `vetoed` False and `checked`
        ## True, which the per-cell view rendered as "clean" — identical to the judge finding
        ## nothing wrong. "an answer that contradicts a stated fact, on a divided vote" is the
        ## single most useful thing this pass can say, and it was the one thing it could not.
        "falsity_verdict": (falsity or {}).get("verdict"),
        "marks_total": len(results),
        ## One mark, one point. This expression once carried its OWN hardcoded 0.5 rather
        ## than reading `weight`, so partial credit was defined twice and tested nowhere.
        "score": float(counts["HIT"]),
        ## `score` takes the better of the two passes (the objective pass is strict
        ## about wording); `score_strict` defers to the judge wherever it ran, so a
        ## human sees the spread between "cited the right things" and "said the
        ## right thing" instead of one number hiding the disagreement.
        "score_strict": round(strict, 2),
    }  # fmt: skip


## @brief Grade one answer file for completeness and write its JSON sidecar.
## @param cell Cell record.
## @param rubric QuestionRubric for the cell's question.
## @param opts Parsed CLI options.
## @return The sidecar dict.
## @version 2
def grade_answer(cell: dict, rubric, opts) -> dict:
    """@brief Score one answer against the frozen key.
    @return Sidecar record (also written to disk).
    @version 2
    """
    answer = cell["path"].read_text(encoding="utf-8")
    body = anonymise(answer)
    cites = answer_citations(answer)
    with ThreadPoolExecutor(max_workers=opts.jobs) as pool:
        marks = list(pool.map(lambda m: grade_mark(m, answer, body, cites, opts), rubric.marks))
    ## THE VETO-SAFE SUBSET, not every mark. See `VETO_SAMPLES` for why the whole key was the wrong
    ## input and what had to be corrected before arming; `falsity_check` reports an empty subset as
    ## "unchecked" rather than as clean.
    falsity = falsity_check(veto_facts(rubric.marks), body, opts.judge_model, opts.veto_samples)
    sidecar = {
        "q": cell["q"], "arm": cell["arm"], "model": cell["model"], "run": cell["run"],
        "answer": cell["path"].name, "rubric": str(opts.rubric),
        "declared_mark_count": rubric.declared_mark_count,
        "summary": summarise(marks, cell["arm"], falsity),
        "falsity": falsity,
        "marks": marks,
    }  # fmt: skip
    ## Normalised like every other artifact: a grade sidecar quotes the answer verbatim, so
    ## a machine path in an answer becomes a machine path in the grade.
    bench_publish.write_json(cell["path"].with_suffix(".grade.json"), sidecar)
    return sidecar


## @brief `complete` subcommand: score every answer against the frozen rubric.
## @param opts Parsed CLI options.
## @return Exit code.
## @version 3
def cmd_complete(opts) -> int:
    """RESUMABLE and FAIL-FAST, both for the same reason: 396 cells is roughly 3,500 judge
    calls and will cross a session limit partway.

    A cell whose sidecar is complete is skipped. A sidecar containing judge errors is NOT
    complete — it is a measurement interrupted by capacity, and re-grading it is the
    difference between a gap and a silent zero.

    @brief Run completeness grading over a run directory.
    @return Exit code.
    @version 3
    """
    ## BEFORE ANY MARK IS SCORED. A grading key whose figures were measured at an older
    ## pipeline marks the index arm wrong for being right, and the drift is one-directional:
    ## the source arm reads an unmoved tree. Refused here as well as in `run_matrix` because
    ## grading a previously-collected sweep is a separate invocation — one function, two call
    ## sites, so the refusal cannot say two different things.
    preflight_rubric_provenance(Path(opts.rubric))
    rubrics = load_rubric(Path(opts.rubric))
    answers = Path(opts.answers).expanduser().resolve()
    cells = [c for c in list_cells(answers) if not opts.q or c["q"] in opts.q.split(",")]
    if not cells:
        print(f"no answers under {answers}")
        return 2
    graded = skipped = 0
    consecutive_error_cells = 0
    for cell in cells:
        rubric = rubrics.get(cell["q"])
        if rubric is None:
            print(f"  ! no rubric for {cell['q']}, skipping {cell['path'].name}")
            continue
        ## RESUMABLE, exactly like the cell runner. Grading a 396-cell matrix is roughly 3,500
        ## judge calls and WILL cross a session limit; without this, every restart re-graded
        ## from scratch and an unattended loop would treadmill forever on work already paid
        ## for. A sidecar whose marks are all ruled is finished work.
        out = cell["path"].with_suffix(".grade.json")
        if out.exists() and not opts.force:
            try:
                prior = json.loads(out.read_text())
                if prior.get("summary", {}).get("judge_errors", 1) == 0:
                    skipped += 1
                    continue
                ## A sidecar containing judge errors is NOT finished — it is a measurement
                ## interrupted by capacity. Re-grade it rather than inheriting the gap, which
                ## is how 102 of 324 marks were once counted as failures against both arms.
                print(f"  re-grading {cell['path'].name} (prior run left judge errors)")
            except ValueError:
                print(f"  re-grading {cell['path'].name} (unreadable sidecar)")
        print(
            f"grading {cell['path'].name} ({len(rubric.marks)} marks) ...",
            flush=True,
        )
        sidecar = grade_answer(cell, rubric, opts)
        graded += 1
        s = sidecar["summary"]
        print(f"    hit={s['marks_hit']} miss={s['marks_miss']} "
              f"judge_errors={s['judge_errors']} unmarked={s['unmarked_pct']}% "
              f"score={s['score']}/{s['marks_total']}")  # fmt: skip
        ## FAIL FAST ON A DEAD JUDGE. Every mark of a cell erroring means the judge is not
        ## answering — capacity, almost always. Continuing writes JUDGE_ERROR across every
        ## remaining cell, which is indistinguishable from "the judge ruled MISS" in any
        ## summary that does not read `unmarked_pct`. Stop and let the operator resume.
        degraded = s["judge_errors"] > 0
        consecutive_error_cells = consecutive_error_cells + 1 if degraded else 0
        if consecutive_error_cells >= MAX_CONSECUTIVE_DEGRADED_CELLS:
            print(
                f"\nABORT: {consecutive_error_cells} consecutive cells carrying judge errors. "
                f"The judge is failing — usually session capacity, and once it starts it does "
                f"not recover. Wait for the reset named in the error above, then re-run the "
                f"same command: complete cells are skipped and every cell holding a judge "
                f"error is re-graded, so nothing measured here is kept."
            )
            return 1
    print(f"\ndone; {graded} cell(s) graded, {skipped} already complete")
    return 0


## @brief Run one blind pairwise comparison in a single presentation order.
## @param question Frozen question text (context only).
## @param first Anonymised answer shown as A.
## @param second Anonymised answer shown as B.
## @param model Judge model alias.
## @return Verdict record per criterion plus OVERALL.
## @version 1
def judge_pair(question: str, first: str, second: str, model: str) -> dict:
    """@brief Judge one A/B presentation.
    @return Per-criterion verdicts or a judge_error.
    @version 1
    """
    reply = judge.ask(pairwise_prompt(question, first, second), model=model)
    if reply.error:
        return {"judge_error": reply.error}
    out: dict = {}
    for label in (*CRITERIA, "OVERALL"):
        token = judge.verdict_token(reply.text, label, ("A", "B", "TIE"))
        if token is None:
            return {"judge_error": f"no single {label} token", "raw": reply.text}
        out[label] = token
    out["why"] = judge.field(reply.text, "WHY")
    return out


## @brief Map an A/B verdict back to the arm that produced it.
## @param token "A", "B" or "TIE".
## @param mapping Position -> arm mapping for that presentation.
## @return Arm name or "tie".
## @version 1
def _to_arm(token: str, mapping: dict[str, str]) -> str:
    """@brief Deanonymise a positional verdict.
    @return Arm name or "tie".
    @version 1
    """
    return "tie" if token == "TIE" else mapping[token]


## @brief `pairwise` subcommand: blind, order-swapped quality comparison.
## @param opts Parsed CLI options.
## @return Exit code.
## @version 2
def cmd_pairwise(opts) -> int:
    """Both orders are judged; when they disagree on the winning arm the pair
    is flagged `position_bias` and must not be counted as a result.

    @brief Compare two arms' answers blind, both ways.
    @return Exit code.
    @version 2
    """
    answers = Path(opts.answers).expanduser().resolve()
    cells = [c for c in list_cells(answers) if c["q"] == opts.q]
    by_arm = {c["arm"]: c for c in cells if not opts.model or c["model"] == opts.model}
    if len(by_arm) < 2:
        print(f"need two arms for {opts.q}; found {sorted(by_arm)}")
        return 2
    question = _question_text(Path(opts.rubric), opts.q)
    left, right = by_arm["src"], by_arm["mcp"]
    texts = {left["arm"]: anonymise(left["path"].read_text(encoding="utf-8")),
             right["arm"]: anonymise(right["path"].read_text(encoding="utf-8"))}  # fmt: skip

    rng = random.Random(opts.seed)
    arms = [left["arm"], right["arm"]]
    rng.shuffle(arms)
    forward = {"A": arms[0], "B": arms[1]}
    reverse = {"A": arms[1], "B": arms[0]}
    run_a = judge_pair(question, texts[forward["A"]], texts[forward["B"]], opts.judge_model)
    run_b = judge_pair(question, texts[reverse["A"]], texts[reverse["B"]], opts.judge_model)
    record = _pair_record(opts, left, right, forward, reverse, run_a, run_b)
    out = answers / f"{opts.q}_{left['model']}_pairwise.json"
    bench_publish.write_json(out, record)
    print(json.dumps({k: v for k, v in record.items() if k != "runs"}, indent=2))
    return 0


## @brief Assemble the pairwise sidecar, including the position-bias check.
## @param opts Parsed CLI options.
## @param left First cell.
## @param right Second cell.
## @param forward Position mapping for run 1.
## @param reverse Position mapping for run 2.
## @param run_a Run 1 verdicts.
## @param run_b Run 2 verdicts.
## @return Pairwise record.
## @version 1
def _pair_record(opts, left, right, forward, reverse, run_a, run_b) -> dict:
    """@brief Build the pairwise result with its reliability flags.
    @return Pairwise record.
    @version 1
    """
    errored = "judge_error" in run_a or "judge_error" in run_b
    winners = (
        None
        if errored
        else (_to_arm(run_a["OVERALL"], forward), _to_arm(run_b["OVERALL"], reverse))
    )
    return {
        "q": opts.q, "model": left["model"], "seed": opts.seed,
        "answers": {left["arm"]: left["path"].name, right["arm"]: right["path"].name},
        "position_mapping": {"run1": forward, "run2": reverse},
        "overall_by_arm": list(winners) if winners else None,
        "position_bias": (winners is not None and winners[0] != winners[1]),
        "stable_winner": winners[0] if winners and winners[0] == winners[1] else None,
        "criteria_by_arm": None if errored else {
            c: [_to_arm(run_a[c], forward), _to_arm(run_b[c], reverse)] for c in CRITERIA
        },
        "judge_error": errored,
        "runs": {"run1": run_a, "run2": run_b},
    }  # fmt: skip


## @brief Pull one frozen question's text out of the matrix file.
## @param path Matrix markdown path.
## @param qid Question id.
## @return Question text (empty when not found).
## @version 1
def _question_text(path: Path, qid: str) -> str:
    """@brief Read the frozen question blockquote for context.
    @return Question text.
    @version 1
    """
    sys.path.insert(0, str(HERE))
    from run_matrix import (
        parse_questions,
    )

    for question in parse_questions(path):
        if question["id"] == qid:
            return question["text"]
    return ""


## @brief `report` subcommand: merge completeness, quality and runner metrics.
## @param opts Parsed CLI options.
## @return Exit code.
## @version 2
def cmd_report(opts) -> int:
    """@brief Emit the three-axis markdown results doc.
    @return Exit code.
    @version 2
    """
    from grade_report import build_report

    answers = Path(opts.answers).expanduser().resolve()
    text = build_report(answers)
    bench_publish.write(answers / "grading-report.md", text)
    print(text)
    return 0


## @brief Count a question's arm-fenced marks.
## @param rubric One parsed question's rubric.
## @return A phrase naming the count.
## @version 2
## @dg_internal
def fencing_summary(rubric) -> str:
    """A fence drops a mark from the denominator of the arm that cannot reach it, so it
    decides whether a two-arm comparison is fair. Under the current rule a fence is a
    RUBRIC DEFECT rather than a feature, so the expected count is ZERO and a non-zero one
    is a finding about the key.

    @brief Report the fenced-mark count.
    @return A phrase naming the count.
    @version 2
    """
    marks = sum(1 for m in rubric.marks if m.arm_only)
    return f"{marks} fenced mark{'' if marks == 1 else 's'}"


## @brief `rubric` subcommand: dump the parsed frozen key for inspection.
## @param opts Parsed CLI options.
## @return Exit code.
## @version 2
def cmd_rubric(opts) -> int:
    """@brief Print the parsed rubric so a human can verify the parse.
    @return Exit code.
    @version 1
    """
    rubrics = load_rubric(Path(opts.rubric))
    bad = 0
    for qid, rubric in rubrics.items():
        ok = len(rubric.marks) == rubric.declared_mark_count
        bad += not ok
        print(f"{qid} — {rubric.title}: {len(rubric.marks)}/{rubric.declared_mark_count} marks "
              f"[{'OK' if ok else 'MISMATCH'}], {fencing_summary(rubric)}")  # fmt: skip
        if opts.verbose:
            for mark in rubric.marks:
                print(f"    {mark.index:>2}. conceptual={mark.conceptual} "
                      f"syms={mark.symbols} refs={mark.refs}")  # fmt: skip
    ## A FLOOR, because zero questions used to certify clean. `parse_rubric` returns an empty
    ## mapping for a file whose headings do not match `_Q_HEADING` — a shape change in the rubric
    ## format, or one mistyped heading, and this printed nothing and exited 0. The documented
    ## verification step then attested to a rubric the harness cannot read at all.
    if not rubrics:
        print(f"NO QUESTIONS PARSED from {opts.rubric} — headings must be `# Q<n> — title`")
        return 1
    return 1 if bad else 0


## @brief `show` subcommand: print one sidecar's per-mark verdicts and evidence.
## @param opts Parsed CLI options.
## @return Exit code.
## @version 1
def cmd_show(opts) -> int:
    """The human-review path: every verdict, the evidence behind it, and which
    pass produced it, without opening the JSON by hand.

    @brief Print a grade sidecar in reviewable form.
    @return Exit code.
    @version 1
    """
    sidecar = json.loads(Path(opts.sidecar).read_text(encoding="utf-8"))
    print(
        f"{sidecar['answer']}  score={sidecar['summary']['score']}/{sidecar['summary']['marks_total']}"
    )
    for mark in sidecar["marks"]:
        if opts.only and mark["verdict"] != opts.only.upper():
            continue
        judged = mark["judge"] or {}
        print(f"\n[mark #{mark['index']}] {mark['verdict']}  "
              f"(objective={mark['objective']['verdict']}, judge={judged.get('verdict')})")  # fmt: skip
        print(f"  mark: {mark['text'][:220]}")
        for line in mark["objective"]["evidence"][: opts.evidence]:
            print(f"  obj:  {line[:220]}")
        if judged.get("quote"):
            print(f"  judge quote: {judged['quote'][:220]}")
        if judged.get("why"):
            print(f"  judge why:   {judged['why'][:220]}")
        if judged.get("judge_error"):
            print(f"  JUDGE_ERROR: {judged['judge_error']}")
    return 0


## @brief Build the argument parser.
## @param argv Raw CLI arguments.
## @return Parsed namespace.
## @version 1
def parse_args(argv: list[str]):
    """@brief Parse grader CLI arguments.
    @return Options namespace.
    @version 1
    """
    parser = argparse.ArgumentParser(
        description="docs-db benchmark grader (completeness + blind quality)"
    )
    parser.add_argument(
        "--rubric",
        required=True,
        help="frozen matrix markdown for THIS run's target (no default — see module header)",
    )
    parser.add_argument("--judge-model", default=judge.DEFAULT_MODEL)
    subs = parser.add_subparsers(dest="cmd", required=True)

    complete = subs.add_parser("complete", help="score answers against the frozen rubric")
    complete.add_argument("--answers", required=True)
    complete.add_argument("--q", default="", help="comma-separated question filter")
    complete.add_argument("--drift", type=int, default=4, help="tolerated line drift")
    complete.add_argument("--jobs", type=int, default=4, help="concurrent judge calls")
    complete.add_argument("--no-judge", action="store_true", help="objective pass only")
    ## OPT-IN COUNT, NOT A BOOLEAN. It costs this many extra judge calls PER CELL, and session
    ## capacity — not money — is what actually binds a sweep here; a 6-agent fan-out has been
    ## cut to 1 by a session limit on this project. Naming the number in the flag makes the
    ## cost of arming the veto visible at the call site instead of hidden in a default.
    complete.add_argument(
        "--veto-samples",
        type=int,
        default=VETO_SAMPLES,
        help=f"independent falsity samples per cell (0 disables; default {VETO_SAMPLES}). "
        f"A veto needs unanimity across all of them.",
    )
    complete.add_argument(
        "--force", action="store_true", help="re-grade cells whose sidecar is already complete"
    )
    complete.set_defaults(func=cmd_complete)

    pair = subs.add_parser("pairwise", help="blind order-swapped quality comparison")
    pair.add_argument("--answers", required=True)
    pair.add_argument("--q", required=True)
    pair.add_argument("--model", default="", help="restrict to one candidate model")
    pair.add_argument("--seed", type=int, default=0, help="seeds the A/B arm assignment")
    pair.set_defaults(func=cmd_pairwise)

    report = subs.add_parser("report", help="merge grades + runner metrics into markdown")
    report.add_argument("--answers", required=True)
    report.set_defaults(func=cmd_report)

    rubric = subs.add_parser("rubric", help="dump the parsed frozen rubric")
    rubric.add_argument("--verbose", action="store_true")
    rubric.set_defaults(func=cmd_rubric)

    show = subs.add_parser("show", help="print one grade sidecar with its evidence")
    show.add_argument("sidecar")
    show.add_argument("--only", default="", help="filter to HIT / MISS / JUDGE_ERROR")
    show.add_argument("--evidence", type=int, default=3, help="objective evidence lines per mark")
    show.set_defaults(func=cmd_show)
    return parser.parse_args(argv)


if __name__ == "__main__":
    _opts = parse_args(sys.argv[1:])
    raise SystemExit(_opts.func(_opts))
