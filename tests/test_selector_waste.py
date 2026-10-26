# SPDX-License-Identifier: MIT
"""The measurement that reported a perfect score because it was broken.

`scripts/selector_waste.py` counts how often `dossier` returned nothing, from frozen session
transcripts, with no judge. **ITS FIRST RUN REPORTED 0.0% AND THAT WAS THE SCRIPT, NOT THE TOOL.**
Two defects, each enough on its own:

1. it passed the reply through `json.dumps` before matching, which escapes the quotes, so a reply
   carrying `"found": false` became `\\"found\\": false` and the substring check could never fire;
2. it truncated the reply to 4,000 characters, so the field could fall off the end of a long one.

A detector that matches nothing reports zero waste — the best possible result on the very axis
under test, handed out for free. That is this repository's recurring failure shape, and it
appeared inside the instrument built to measure it.

So these tests pin the PROPERTIES that broke, not the wording of the matcher: every spelling the
payload can arrive in is detected, no length is clipped, and an unreadable cell is never counted
as a clean one.

@brief The waste counter must not report zero because it looked wrong.
@version 1
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent


##
# @brief Load the counter script as a module without making `scripts/` a package.
# @return The loaded module.
# @version 1
# @dg_internal
def _load() -> ModuleType:
    """@brief Load `scripts/selector_waste.py`.
    @return The module.
    @version 1
    """
    path = REPO_ROOT / "scripts" / "selector_waste.py"
    spec = importlib.util.spec_from_file_location("selector_waste", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


waste = _load()


##
# @brief A single reply's miss must be attributed to its one subject.
# @return None.
# @version 1
def test_a_single_miss_is_attributed_to_its_subject() -> None:
    """A single reply has no `results` array: top-level `found is False` IS the miss, and a hit
    carries no `found` key at all — measured on the real surface, not assumed.

    @brief Single misses attribute.
    @return None.
    @version 1
    """
    assert waste.missed_subjects('{"found": false}', ["execute"]) == ["execute"]
    assert waste.missed_subjects('{"name": "execute", "file": "x.cpp"}', ["execute"]) == []


##
# @brief A batch reply must be attributed PER ENTRY, never per call.
# @return None.
# @version 1
def test_a_batch_reply_is_attributed_per_entry() -> None:
    """**THIS IS THE DEFECT THAT OVERSTATED EVERY NUMBER THIS SCRIPT PRODUCED.** A batch reply's
    top-level `found` is a COUNT OF HITS, not a boolean: the real surface returns `found: 1` for
    `dossier(["execute", "absent"])`. A substring search for `"found":false` therefore fired on any
    batch containing one bad name, the whole call was counted as a miss, and then EVERY subject in
    it was classified as missed — including the ones that hit.

    That is how 121 subjects came to be labelled "a bare name the index does not hold" while
    `memberdef` held them as functions. Corrected, that row is 31.

    The `found: 1` in this fixture is deliberate: a boolean reading of it would be `True`, so a
    test that only checked the top level would pass while the per-entry attribution stayed broken.

    @brief Batch misses attribute per entry.
    @return None.
    @version 1
    """
    reply = json.dumps(
        {
            "kind": "dossiers",
            "found": 1,
            "results": [
                {"name": "execute", "file": "manager.cpp"},
                {"name": "absent", "found": False},
            ],
        }
    )

    assert waste.missed_subjects(reply, ["execute", "absent"]) == ["absent"], (
        "a batch reply was not attributed per entry — the subject that HIT was counted as missed"
    )


##
# @brief A batch where everything hit must report no misses.
# @return None.
# @version 1
def test_a_fully_answered_batch_reports_nothing_missed() -> None:
    """The permissive leg. An attributor wired to return every name would pass the test above and
    report 100% waste.

    @brief A full batch is clean.
    @return None.
    @version 1
    """
    reply = json.dumps(
        {"found": 2, "results": [{"name": "a", "file": "x"}, {"name": "b", "file": "y"}]}
    )

    assert waste.missed_subjects(reply, ["a", "b"]) == []


##
# @brief An unreadable reply must be unknown, not clean.
# @return None.
# @version 1
def test_an_unparseable_reply_is_not_counted_as_a_hit() -> None:
    """ABSENCE IS NOT EMPTINESS, on the axis where it flatters. A reply this script cannot parse
    has to be surfaced, because returning `[]` would credit it as a full hit — the best possible
    result, handed out for a reply nobody could read.

    The escaped spelling is here because `json.dumps` produced exactly it and the first version of
    this script could not see it, reporting a clean 0.0%.

    @brief Unparseable is disclosed.
    @return None.
    @version 1
    """
    assert waste.missed_subjects('{\\"found\\": false}', ["x"]) == ["<unparseable>"]
    assert waste.missed_subjects("not json at all", ["x"]) == []


##
# @brief The result flattener must handle every content shape without reshaping it.
# @return None.
# @version 1
def test_result_text_flattens_without_reshaping() -> None:
    """A `tool_result`'s content is a string in some transcripts and a list of parts in others.
    Both must come back as the text itself — never re-serialised, which is what introduced the
    escaping in the first place.

    @brief Content shapes flatten to text.
    @return None.
    @version 1
    """
    assert waste.result_text('{"found": false}') == '{"found": false}'
    assert "found" in waste.result_text([{"type": "text", "text": '{"found": false}'}])
    assert waste.result_text(None) == ""
    ## The round trip that matters: a list-shaped reply must still be attributable.
    flattened = waste.result_text([{"type": "text", "text": '{"found": false}'}])
    assert waste.missed_subjects(flattened, ["execute"]) == ["execute"]


##
# @brief Calls must be counted by tool_use id, not by block.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_calls_are_counted_by_id_not_by_repeated_block(tmp_path: Path) -> None:
    """A SESSION TRANSCRIPT REPEATS ROWS. `acceptance/execute.py` records a 1.1.0 cell whose JSONL
    held 30 `tool_use` blocks against SIXTEEN distinct ids, so counting blocks reported nearly
    double — uniformly across arms, so every ratio looked right while every absolute was wrong.

    This transcript writes the same call three times and asserts the count is one.

    @brief Repeated blocks count once.
    @return None.
    @version 1
    """
    use = {
        "type": "tool_use",
        "id": "call-1",
        "name": "mcp__clew__dossier",
        "input": {"subject": "f"},
    }
    result = {"type": "tool_result", "tool_use_id": "call-1", "content": '{"found": false}'}
    path = tmp_path / "t.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"message": {"content": [block]}})
            for block in (use, use, result, use, result)
        ),
        encoding="utf-8",
    )

    totals, causes = waste.count_cell(path)

    assert totals["dossier_calls"] == 1, f"repeated blocks were counted separately: {totals}"
    assert totals["subjects_missed"] == 1, f"the miss was not attributed: {totals}"
    assert totals["calls_fully_missed"] == 1, f"a single-subject miss is a FULL miss: {totals}"
    assert sum(causes.values()) == 1, f"one missed subject expected, got {causes}"


##
# @brief Miss causes must be keyed per subject, and a batched call counts several.
# @return None.
# @version 1
def test_miss_causes_are_counted_per_subject_not_per_call() -> None:
    """TWO DENOMINATORS, AND CONFLATING THEM MISSTATES THE RESULT. A batched
    `dossier(subject=[a, b, c])` that misses is ONE wasted round trip but THREE unanswered names.
    The published breakdown quotes subjects; the miss rate quotes calls.

    @brief Causes are per subject.
    @return None.
    @version 1
    """
    causes = waste.classify_miss(["tokenize", "src/x.cpp", "C::f"], False)

    assert len(causes) == 3, f"a three-subject call produced {len(causes)} cause(s)"
    assert causes == [
        "a bare name the index does not hold",
        "a FILE PATH as subject",
        "a QUALIFIED name as subject",
    ], causes


##
# @brief A call that passed `qualified` is attributed to the selector whatever the subject looked like.
# @return None.
# @version 1
def test_a_qualified_call_is_attributed_to_the_selector() -> None:
    """If a selector was passed, the selector is why the call failed — the subject's shape is
    beside the point. Checking subject shape first would have scattered those 14 calls across the
    other three causes and hidden the defect that was actually fixed.

    @brief Qualified dominates the classification.
    @return None.
    @version 1
    """
    assert waste.classify_miss("C::f", True) == ["passed `qualified` that could not match"]
    assert waste.classify_miss("src/x.cpp", True) == ["passed `qualified` that could not match"]


##
# @brief A cell whose transcript cannot be found must be unreadable, never zero waste.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_a_missing_transcript_is_unreadable_not_clean(tmp_path: Path) -> None:
    """**ABSENCE IS NOT EMPTINESS, ON THE AXIS WHERE IT FLATTERS MOST.** Zero waste is the best
    possible result here. A cell whose transcript is gone has to be reported as unmeasured, or a
    missing file buys a perfect score — and `acceptance/execute.count_tools` returns `-1` for
    exactly this reason rather than `0`.

    @brief A missing transcript is disclosed.
    @return None.
    @version 1
    """
    answers = tmp_path / "target" / "answers"
    answers.mkdir(parents=True)
    (answers / "Q1_m_index_only_r1.raw.json").write_text(
        json.dumps({"session_id": "no-such-session-000"}), encoding="utf-8"
    )

    assert waste.transcript_for(answers / "Q1_m_index_only_r1.raw.json") is None

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = waste.main([str(tmp_path)])
    out = buffer.getvalue()

    assert rc == 0
    assert "unreadable transcripts: 1" in out, f"a missing transcript was not disclosed:\n{out}"
    assert "index_only" not in out.split("unreadable")[0] or "0.0%" not in out, (
        f"a cell with no transcript was reported as a measured 0% miss rate:\n{out}"
    )


##
# @brief An envelope with no session id must be unreadable rather than silently skipped.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_an_envelope_without_a_session_id_is_unreadable(tmp_path: Path) -> None:
    """`.meta.json` does not carry the session id and `.raw.json` does; an envelope missing it is
    a cell that cannot be measured, which is a different fact from a cell that was measured and
    found clean.

    @brief A missing session id is disclosed.
    @return None.
    @version 1
    """
    raw = tmp_path / "x.raw.json"
    raw.write_text(json.dumps({"subtype": "success"}), encoding="utf-8")

    assert waste.transcript_for(raw) is None
