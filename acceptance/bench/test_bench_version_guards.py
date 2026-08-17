# SPDX-License-Identifier: MIT
## @brief Pin the two version guards that would have caught the 2026-08-05 NO-GO.
## @version 1
"""On 2026-08-05 a ~198-cell acceptance run was refused by a human, not by the harness.

Both committed grading keys held ground truth measured at build 16/17, both served indexes
were still AT 17, and `CLEW_BUILD_VERSION` was 27. `preflight_target` checked that a
database existed, that it held `path` rows, and that a sample of those paths resolved under the
target — every term passed, because a STALE index is a perfectly valid index of the right
repository. It just answers from an older pipeline.

The drift is not symmetric, which is what makes it fatal rather than untidy: the source arm
reads an unmoved source tree and cannot be penalised by index drift, so only the arm under test
can be marked wrong for being right. This project has already voided a 396-cell grid that way.

`grep -rn preflight tests/` was empty before this file existed — the guard that gates every
published number had no test at all.

Also pinned here: a coverage check that printed "COMPLETE — every graded cell fully ruled" over
an empty directory, and the append-only metrics schema, whose field list gained `build_ms`.
"""

from __future__ import annotations

import json
import sqlite3
import types
from pathlib import Path

import bench_arms
import bench_rubric
import grading_coverage
import pytest
import run_matrix

from clew.signature import (
    CLEW_BUILD_VERSION,
    write_build_signature,
)


## @brief Write a minimal index database, optionally stamped with a build version.
## @param path Database path to create.
## @param version Build version to stamp, or None to leave it unstamped.
## @return The path written.
## @version 1
def _index(path: Path, version: int | None) -> Path:
    """A `path` table with one row is enough for `preflight_target`'s other terms; the version
    term is what these tests exercise.

    @brief Build a stub index.
    @return The database path.
    @version 1
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE path (name TEXT, type INT)")
        conn.execute("INSERT INTO path(name, type) VALUES('src/a.cpp', 1)")
        conn.commit()
    finally:
        conn.close()
    if version is not None:
        write_build_signature(path, version=version)
    return path


## @brief A stale index is refused, and the refusal names both versions.
## @return None.
## @version 1
def test_a_stale_index_is_refused_and_names_both_versions(tmp_path: Path) -> None:
    """BOTH NUMBERS IN THE MESSAGE, asserted rather than assumed. "stale index" alone sends the
    reader to guess which side moved; the whole cost of the NO-GO was that nobody knew the two
    numbers disagreed until they were printed side by side.

    @brief The index-version guard fires on skew and reports both figures.
    @version 1
    """
    stale = CLEW_BUILD_VERSION - 1
    db = _index(tmp_path / "stale.db", stale)
    with pytest.raises(SystemExit) as caught:
        run_matrix._preflight_index_version(db)
    message = str(caught.value)
    assert str(stale) in message, "the refusal must name the version the index actually holds"
    assert str(CLEW_BUILD_VERSION) in message, "and the version the pipeline is at"
    assert "STALE INDEX" in message


## @brief An index with no stamped version is refused too.
## @return None.
## @version 1
def test_an_unstamped_index_is_refused(tmp_path: Path) -> None:
    """ "I cannot tell which pipeline built this" is not a pass. `read_build_signature` returns
    None for a database with no `build_meta` row, and treating None as "probably fine" restores
    exactly the unchecked state the guard exists to remove.

    @brief An index carrying no build_version is a refusal, not a shrug.
    @version 1
    """
    db = _index(tmp_path / "unstamped.db", None)
    with pytest.raises(SystemExit) as caught:
        run_matrix._preflight_index_version(db)
    assert "no build_version stamped" in str(caught.value)


## @brief A current index passes the version term silently.
## @return None.
## @version 1
def test_a_current_index_passes(tmp_path: Path) -> None:
    """The control. A guard that refuses everything is indistinguishable from a broken import,
    and this repo has shipped a gate whose first version took a layer to zero rows.

    @brief No skew, no refusal.
    @version 1
    """
    run_matrix._preflight_index_version(_index(tmp_path / "current.db", CLEW_BUILD_VERSION))


## @brief `preflight_target` itself refuses a stale index, before the path terms.
## @return None.
## @version 1
def test_preflight_target_refuses_a_stale_index(tmp_path: Path, monkeypatch) -> None:
    """WIRING, not logic. The helper above can be perfect and unreached — which is precisely
    the state `preflight_target` was in on 2026-08-05, with three passing terms and no version
    term at all. The target here has a resolvable indexed path, so the ONLY thing that can
    refuse it is the new term.

    @brief The stale-index guard is reached from the real preflight entry point.
    @version 1
    """
    target = tmp_path / "target"
    (target / "src").mkdir(parents=True)
    (target / "src" / "a.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    db = _index(tmp_path / "clew.db", CLEW_BUILD_VERSION - 1)

    from clew.mcp_server import state

    monkeypatch.setattr(
        state, "target_for", lambda _repo: types.SimpleNamespace(db_path=str(db)), raising=True
    )
    with pytest.raises(SystemExit) as caught:
        run_matrix.preflight_target(target)
    assert "STALE INDEX" in str(caught.value)


## @brief Front matter is read from the fence at the top of the file only.
## @return None.
## @version 1
def test_front_matter_ignores_a_horizontal_rule_deeper_in_the_document(tmp_path: Path) -> None:
    """`---` is also a markdown horizontal rule and the rubrics contain several. A parser that
    scans for any fence opens a phantom block mid-document and hands a guard values read out of
    prose — a check reading the wrong input reports something rather than nothing, which is how
    every quietly-wrong gate in this repo began.

    @brief Only a leading fence starts front matter.
    @version 1
    """
    doc = tmp_path / "no-front-matter.md"
    doc.write_text(
        "# Q1 — a question\n\nsome prose\n\n---\n\nground_truth_build_version: 9\n",
        encoding="utf-8",
    )
    assert bench_rubric.front_matter(doc) == {}, "a mid-document rule is not front matter"


## @brief A rubric measured against another build is refused, naming both versions.
## @return None.
## @version 2
def test_a_stale_rubric_is_refused_and_names_both_versions(tmp_path: Path) -> None:
    """This is the exact shape of the NO-GO: a key whose figures were measured at build 16
    against a pipeline at 27. The guard does NOT claim the key is correct — it checks the one
    half a machine can check.

    THE GUARD IT PINS WAS RENAMED AND WIDENED, and these tests broke rather than quietly
    passing, which is the mechanism working. `preflight_rubric_build_version` demanded a build
    version from EVERY rubric; mbedtls 1.0.0 then re-derived every figure from the target's own
    source, which cannot drift when our pipeline moves, and the old guard would have refused
    the one rubric that fixed the problem. `preflight_rubric_provenance` asks for provenance
    and accepts either form — see the source-derived case below, which is the half that makes
    the widening honest rather than a loosening.

    BOTH SPELLINGS ARE READ. `entropic/questions.md` says `build_version:` where the deleted
    guard's tests said `ground_truth_build_version:`; a guard knowing one would report a
    declared provenance as absent, which sends the reader to add a field already there.

    @brief The rubric-provenance guard fires on build skew and reports both figures.
    @version 2
    """
    for spelling in bench_rubric.BUILD_PROVENANCE_KEYS:
        rubric = tmp_path / f"{spelling}.md"
        rubric.write_text(f"<!-- x -->\n---\nrubric: t\n{spelling}: 16\n---\n", encoding="utf-8")
        with pytest.raises(SystemExit) as caught:
            bench_rubric.preflight_rubric_provenance(rubric, current=27)
        message = str(caught.value)
        assert "16" in message and "27" in message
        assert "STALE GRADING KEY" in message
        ## The control, in the same test so the two cannot drift apart: agreement is silent.
        assert bench_rubric.preflight_rubric_provenance(rubric, current=16) == 16


## @brief A rubric whose ground truth is read from the target's source passes at any build.
## @return None.
## @version 1
def test_a_source_derived_rubric_is_accepted_at_any_build_version(tmp_path: Path) -> None:
    """THE NEGATIVE HALF, and the reason the predecessor guard was deleted rather than kept.
    mbedtls 1.0.0 declares `ground_truth_source: MBEDTLS SOURCE at the commit above, read with
    git grep` and NO build version, deliberately: no figure in it came from a build of ours, so
    there is nothing for our pipeline to drift away from. A guard that still demanded a build
    version would refuse the only rubric currently fit to run.

    Written as its own test because a suite with only the refusal cases passes against a guard
    that refuses EVERYTHING — the shape this repo has recorded as "a check with a test for its
    failure path and none for its success path", which shipped a completely broken install
    path while staying green.

    @brief Source-derived provenance is accepted regardless of the pipeline version.
    @version 1
    """
    rubric = tmp_path / "questions.md"
    rubric.write_text(
        "<!-- x -->\n---\nrubric: t\nground_truth_source: read with git grep at the pin\n---\n",
        encoding="utf-8",
    )
    assert (
        bench_rubric.preflight_rubric_provenance(rubric, current=999)
        == bench_rubric.PROVENANCE_SOURCE
    ), "a key derived from the target's own source cannot be stale against OUR build version"


## @brief A rubric that declares no ground-truth provenance at all is refused.
## @return None.
## @version 2
def test_a_rubric_without_the_field_fails_closed(tmp_path: Path) -> None:
    """FAILS CLOSED, because "absent" is the state both rubrics were in while nothing read the
    field. Treating a missing declaration as acceptable would restore that silence for the next
    unattributed key, and an unattributed key is unfalsifiable rather than fine.

    Measured against the committed rubrics with `.claude/tmp/rubric_provenance_probe.py`, which
    is how this guard was believed rather than assumed: mbedtls 1.0.0 ACCEPTED as source-
    derived, entropic REFUSED at build 32 against 42, self REFUSED as unattributed. Both
    refusals match a judgement recorded independently elsewhere — entropic's rubric is deferred
    to #367 and the self rubric is documented as an unrun, stale draft — so the guard agrees
    with two conclusions it did not produce.

    @brief A missing declaration is an error, not a default.
    @version 2
    """
    rubric = tmp_path / "questions.md"
    rubric.write_text("<!-- x -->\n---\nrubric: t\nversion: 1.0.0\n---\n", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        bench_rubric.preflight_rubric_provenance(rubric, current=27)
    message = str(caught.value)
    assert "UNATTRIBUTED GRADING KEY" in message
    assert bench_rubric.SOURCE_PROVENANCE_KEY in message, "a refusal must name the fix"


## @brief `cmd_run` reaches the provenance guard before it spends anything.
## @return None.
## @version 1
def test_cmd_run_refuses_an_unattributed_rubric_before_any_cell(
    tmp_path: Path, monkeypatch
) -> None:
    """WIRING, not logic, and the same lesson one guard over: on 2026-08-05 the version check
    was absent from `preflight_target` while three other terms passed, so a perfect helper
    nobody calls is the documented failure rather than a hypothetical one. This drives the real
    entry point with the target term stubbed out, so the ONLY thing that can refuse is the
    provenance term.

    IN FRONT OF THE SPEND is the property being pinned, not merely "somewhere in cmd_run": a
    sweep that discovers its grading key is unattributed after the first cell has already paid
    a preflight, a config generation and a directory tree.

    THE OPTS NAMESPACE IS DELIBERATELY MINIMAL — it carries only the four fields the code
    reaches before the guard. Measured with the guard's call deleted: this test then fails with
    `AttributeError: 'types.SimpleNamespace' object has no attribute 'questions_filter'`, i.e.
    execution ran past the gate into cell planning. So the control is red either way, and the
    attribute that goes missing NAMES how far it got — a fuller namespace would let an unwired
    run proceed further and cost real work to find out.

    @brief The rubric guard is reached from the real run entry point.
    @version 1
    """
    monkeypatch.setattr(run_matrix, "preflight_target", lambda _target: None, raising=True)
    rubric = tmp_path / "questions.md"
    rubric.write_text("<!-- x -->\n---\nrubric: t\n---\n\n# Q1 — a question\n", encoding="utf-8")
    opts = types.SimpleNamespace(
        out=str(tmp_path / "out"),
        target=str(tmp_path),
        questions=str(rubric),
        no_restore=True,
    )
    with pytest.raises(SystemExit) as caught:
        run_matrix.cmd_run(opts)
    assert "UNATTRIBUTED GRADING KEY" in str(caught.value)
    assert not (tmp_path / "out").exists(), (
        "the refusal must land before the output tree is created — that ordering is the "
        "difference between a refusal and a half-started sweep"
    )


## @brief The one rubric the matrix run needs passes the provenance guard as committed.
## @return None.
## @version 1
def test_the_committed_mbedtls_rubric_passes_the_provenance_guard() -> None:
    """AGAINST THE COMMITTED FILE, not a fixture. Every other test here builds its own rubric,
    so all of them would pass while the real key the sweep will use is refused — and a guard
    wired in front of a ~198-cell spend has to be known to admit the case it is meant to admit
    BEFORE the operator finds out.

    Deliberately asserts only on mbedtls. entropic and self are expected to be refused today
    (#367), so pinning them would pin work in progress as correct.

    @brief The mbedtls rubric is accepted as source-derived.
    @version 1
    """
    rubric = bench_rubric.REPO_ROOT / "acceptance" / "targets" / "mbedtls" / "questions.yaml"
    assert rubric.is_file(), "the mbedtls rubric is the one this grid runs on"
    assert bench_rubric.preflight_rubric_provenance(rubric) == bench_rubric.PROVENANCE_SOURCE, (
        "the frozen 1.0.0 rubric declares source provenance — refusing it blocks the whole run"
    )


## @brief Coverage over a directory holding no sidecars is an ERROR.
## @return None.
## @version 1
def test_coverage_of_an_empty_directory_is_an_error(tmp_path: Path, capsys) -> None:
    """It printed "COMPLETE — every graded cell fully ruled" and exited 0, because zero cells
    means zero degraded cells. This is the documented "verify coverage before believing any
    score" step, and a green light on no data is worse than no check: `JUDGE_ERROR` weighs
    exactly what a genuine MISS weighs, so the number it guards is the only thing standing
    between a partial grading pass and a published score.

    @brief An empty answers directory fails the gate.
    @version 1
    """
    empty = tmp_path / "answers"
    empty.mkdir()
    code = grading_coverage.main([str(empty)])
    out = capsys.readouterr().out
    assert code == 1, "nothing graded is not the same as everything ruled"
    assert "ERROR" in out
    assert "COMPLETE" not in out


## @brief A missing directory is an error that names itself.
## @return None.
## @version 1
def test_coverage_of_a_missing_directory_is_an_error(tmp_path: Path, capsys) -> None:
    """@brief An absent answers directory fails the gate.
    @version 1
    """
    code = grading_coverage.main([str(tmp_path / "nope")])
    assert code == 1
    assert "no such directory" in capsys.readouterr().out


## @brief A sidecar carrying zero marks is unmeasurable, not complete.
## @return None.
## @version 1
def test_coverage_of_zero_mark_sidecars_is_an_error(tmp_path: Path, capsys) -> None:
    """`unmarked_pct` is `errors / marks`, which reads a reassuring 0.0% on an empty
    denominator. Same vacuous pass as the empty directory, one level down.

    @brief Zero marks is zero information.
    @version 1
    """
    (tmp_path / "Q1_haiku_mcp_r1.grade.json").write_text(
        json.dumps({"summary": {"marks_total": 0, "judge_errors": 0}, "marks": []}), "utf-8"
    )
    assert grading_coverage.main([str(tmp_path)]) == 1
    assert "zero marks" in capsys.readouterr().out


## @brief A fully ruled sidecar passes, and one carrying a judge error does not.
## @return None.
## @version 1
def test_coverage_separates_a_ruled_pass_from_a_degraded_cell(tmp_path: Path, capsys) -> None:
    """The control pair. Without the passing half, an "always fails" guard looks like a working
    one — and this repo has shipped a gate whose first version was wrong in exactly that way.

    @brief Real coverage data is graded on its judge errors alone.
    @version 1
    """
    cell = tmp_path / "Q1_haiku_mcp_r1.grade.json"
    cell.write_text(json.dumps({"summary": {"marks_total": 4, "judge_errors": 0}}), "utf-8")
    assert grading_coverage.main([str(tmp_path)]) == 0
    assert "COMPLETE" in capsys.readouterr().out

    cell.write_text(json.dumps({"summary": {"marks_total": 4, "judge_errors": 1}}), "utf-8")
    assert grading_coverage.main([str(tmp_path)]) == 1
    assert "need re-grading" in capsys.readouterr().out


## @brief The metrics schema carries build_ms, and a mismatched header is refused.
## @return None.
## @version 1
def test_appending_to_a_differently_shaped_metrics_file_is_refused(tmp_path: Path) -> None:
    """`metrics.csv` IS APPEND-ONLY, which is why adding a column is not free. `csv.DictReader`
    reads the file's own header, so rows written under a wider field list keep their positions
    and quietly acquire different meanings — the old rows stay right and the new ones are
    wrong, with nothing downstream able to tell. A run directory that predates a schema change
    needs a fresh --out; resumption keys on the answer FILES, so nothing measured is lost.

    @brief A header disagreeing with CSV_FIELDS stops the sweep instead of misaligning it.
    @version 1
    """
    assert "build_ms" in run_matrix.CSV_FIELDS, "documented in methodology.md before it existed"
    row = dict.fromkeys(run_matrix.CSV_FIELDS, "")
    run_matrix.append_row(tmp_path, row)
    header = (tmp_path / "metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run_matrix.CSV_FIELDS

    older = [f for f in run_matrix.CSV_FIELDS if f != "build_ms"]
    (tmp_path / "metrics.csv").write_text(",".join(older) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        run_matrix.append_row(tmp_path, row)
    message = str(caught.value)
    assert "build_ms" in message, "the refusal must name the field that moved"
    assert "APPEND-ONLY" in message


## @brief build_ms is measured from the transcript, and is None when nothing was built.
## @return None.
## @version 1
def test_build_ms_measures_a_paired_build_and_is_none_otherwise(tmp_path: Path) -> None:
    """NONE, NOT ZERO, for a cell that built nothing — every source-arm cell and every index-arm
    cell that found a warm index. A measured zero and "not applicable" sharing a spelling is
    the same conflation as `JUDGE_ERROR` weighing what a MISS weighs: the mean of the column
    would silently include cells that never built.

    An UNPAIRED call (a transcript truncated mid-build) is unmeasured too, not a guess.

    @brief Pair build_or_refresh with its result and difference the timestamps.
    @version 1
    """

    def event(stamp: str, block: dict) -> str:
        return json.dumps({"timestamp": stamp, "message": {"content": [block]}})

    use = {"type": "tool_use", "id": "t1", "name": "mcp__clew__build_or_refresh"}
    result = {"type": "tool_result", "tool_use_id": "t1"}
    paired = tmp_path / "paired.jsonl"
    paired.write_text(
        event("2026-08-05T10:00:00.000Z", use)
        + "\n"
        + event("2026-08-05T10:00:03.250Z", result)
        + "\n",
        encoding="utf-8",
    )
    assert bench_arms.build_ms(paired) == 3250

    unpaired = tmp_path / "unpaired.jsonl"
    unpaired.write_text(event("2026-08-05T10:00:00.000Z", use) + "\n", encoding="utf-8")
    assert bench_arms.build_ms(unpaired) is None, "a truncated build is unmeasured, not 0"

    none = tmp_path / "none.jsonl"
    none.write_text(
        event("2026-08-05T10:00:00.000Z", {"type": "tool_use", "id": "q", "name": "Grep"}) + "\n",
        encoding="utf-8",
    )
    assert bench_arms.build_ms(none) is None, "a cell that built nothing has no build time"


## @brief bringup_ms counts the correction surface too, and build_ms deliberately does not.
## @return None.
## @version 1
def test_bringup_ms_counts_declaring_as_well_as_building(tmp_path: Path) -> None:
    """ "BRINGUP IS A COST THAT MUST BE QUANTIFIED DIRECTLY" (owner, gh#360). Step 0 of using
    this tool on any repository is deciding what it should index, and answering that costs
    `propose_declaration` runs — each re-running pipeline importers against a copy of the
    index. Counting only `build_or_refresh` would charge that discovery to whichever question
    exposed the gap, which is the folding the owner ruled out, and would make the
    mid-session-extension feature look free.

    THE TWO ASSERTIONS ARE A PAIR AND BOTH ARE LOAD-BEARING. `bringup_ms` must INCLUDE the
    proposer; `build_ms` must EXCLUDE it, or the refresh-cost figure an agent quotes to a user
    silently acquires time no refresh spends. A single assertion would let one widened set
    satisfy both columns.

    @brief bringup_ms is a superset of build_ms by exactly the proposer's time.
    @version 1
    """

    def event(stamp: str, block: dict) -> str:
        return json.dumps({"timestamp": stamp, "message": {"content": [block]}})

    path = tmp_path / "bringup.jsonl"
    path.write_text(
        "\n".join(
            [
                event(
                    "2026-08-11T10:00:00.000Z",
                    {"type": "tool_use", "id": "b", "name": "mcp__clew__build_or_refresh"},
                ),
                event("2026-08-11T10:00:02.000Z", {"type": "tool_result", "tool_use_id": "b"}),
                event(
                    "2026-08-11T10:00:05.000Z",
                    {
                        "type": "tool_use",
                        "id": "p",
                        "name": "mcp__clew__propose_declaration",
                    },
                ),
                event("2026-08-11T10:00:09.500Z", {"type": "tool_result", "tool_use_id": "p"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert bench_arms.build_ms(path) == 2000, "the build alone is what a refresh costs"
    assert bench_arms.bringup_ms(path) == 6500, (
        "bringup is the build PLUS working out what to state"
    )
    assert "bringup_ms" in run_matrix.CSV_FIELDS, "a cell has to be able to record it"
