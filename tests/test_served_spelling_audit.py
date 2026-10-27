# SPDX-License-Identifier: MIT
"""THE SCRIPT THAT PRODUCED A NUMBER IN A COMMIT MESSAGE, SO IT IS PINNED.

`scripts/served_spelling_audit.py` answers the question that decides whether a `dossier` miss is
clew's fault: was the string the caller passed one clew had printed in an earlier reply? A bare
name the index does not hold is a reader guessing. A spelling clew put on the wire under a `name`
field and then refused as a `subject` is a contract broken with itself.

**IT SHIPPED INFLATED ON ITS FIRST RUN AND THAT IS WHY THESE TESTS EXIST.** The first version
walked every `tool_result` BLOCK instead of pairing blocks by `tool_use` id, so a transcript that
repeats a row counted the same miss several times — 157 missed `index_only` subjects where
`selector_waste.py` counts 92 for the same cells. That is the exact inflation
`selector_waste.py`'s own header documents, reproduced by a second script written with the first
one's lesson available. Both numerator and denominator inflated, so the ratio survived and the
absolute figure did not — the failure mode that reads as harmless.

So the de-duplication is the first thing asserted, and it is asserted on a transcript built to
repeat, because a pairing bug is invisible on a transcript that does not.

@brief The attribution audit de-duplicates, attributes per key, and never scores a gap as clean.
@version 1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from served_spelling_audit import audit_cell, harvest_served, shape  # noqa: E402


##
# @brief Write a session transcript from (role, blocks) pairs.
# @param path Where to write it.
# @param rows The message content lists, in order.
# @return The path written.
# @version 1
def _transcript(path: Path, rows: list[list[dict]]) -> Path:
    """@brief Build a JSONL session transcript.
    @return The path.
    @version 1
    """
    path.write_text(
        "\n".join(json.dumps({"message": {"content": row}}) for row in rows) + "\n", "utf-8"
    )
    return path


##
# @brief A call block and the reply that answers it.
#
# NAMED `_use_block` AND NOT `_call`, which is what it was first. The thread harvester scans this
# whole repository, `tests/test_doxygen_timeout.py` really does spawn a thread on a nested helper
# called `_call`, and a second module-level `_call` made that entry name ambiguous — so the entry
# correctly failed closed to NULL and `test_self_index_thread_layer_resolves_its_entries` fired.
# This helper's name is arbitrary and the collision was gratuitous, so it is this side that moves.
# @version 1
def _use_block(cid: str, subject: object) -> dict:
    return {
        "type": "tool_use",
        "id": cid,
        "name": "mcp__clew__dossier",
        "input": {"subject": subject},
    }


def _reply(cid: str, payload: dict) -> dict:
    return {"type": "tool_result", "tool_use_id": cid, "content": json.dumps(payload)}


## @brief A repeated block pair is counted once.
## @version 1
def test_a_repeated_block_is_counted_once(tmp_path: Path) -> None:
    """THE DEFECT THIS SCRIPT SHIPPED, PINNED. The same call and reply appear three times, which
    is what the 1.1.0 transcripts actually do — one cell held 30 `tool_use` blocks against 16
    distinct ids. Counting blocks reports three misses where there is one.

    @brief Duplicate rows do not inflate the count.
    @return None.
    @version 1
    """
    miss = {"subject": "HealthMonitor::start", "found": False}
    rows = [[_use_block("c1", "HealthMonitor::start")], [_reply("c1", miss)]] * 3
    totals, _by_key, by_shape = audit_cell(_transcript(tmp_path / "s.jsonl", rows))

    assert totals["missed"] == 1, (
        f"a repeated block pair must count once; got {totals['missed']} — this is the inflation "
        f"that put 157 in a draft where the real figure is 92"
    )
    assert by_shape["qualified"] == 1


## @brief A miss is attributed to the key that served its spelling.
## @version 1
def test_a_miss_is_attributed_to_the_key_that_served_it(tmp_path: Path) -> None:
    """THE WHOLE POINT OF THE SCRIPT, and the shape of the C7 finding exactly: a thread row
    serves `name` and `entry`, the reader hands back `name`, and `name` is the one that misses.
    The attribution has to name the FIELD, because "a miss happened" is not fixable and "the
    `threads` corpus serves a `name` that is not a subject" is.
    """
    threads = {"threads": [{"name": "HealthMonitor::monitor_loop", "entry": "monitor_loop"}]}
    rows = [
        [_use_block("c1", "anything")],
        [_reply("c1", threads)],
        [_use_block("c2", "HealthMonitor::monitor_loop")],
        [_reply("c2", {"subject": "HealthMonitor::monitor_loop", "found": False})],
    ]
    totals, by_key, _by_shape = audit_cell(_transcript(tmp_path / "s.jsonl", rows))

    assert totals["missed"] == 1
    assert totals["served_by_clew"] == 1
    assert by_key["name"] == 1, f"expected attribution to `name`, got {dict(by_key)}"


## @brief A bare name clew never served is NOT attributed.
## @version 1
def test_a_spelling_clew_never_served_is_not_attributed(tmp_path: Path) -> None:
    """THE NEGATIVE HALF, and the one that keeps the headline honest. If every miss attributed,
    the 89.9% would be an artefact of the detector rather than a finding. A reader's own guess
    must come back unattributed, so the figure can move.
    """
    rows = [
        [_use_block("c1", "invented_symbol_nobody_served")],
        [_reply("c1", {"subject": "invented_symbol_nobody_served", "found": False})],
    ]
    totals, by_key, by_shape = audit_cell(_transcript(tmp_path / "s.jsonl", rows))

    assert totals["missed"] == 1
    assert totals["served_by_clew"] == 0, f"attributed a spelling nothing served: {dict(by_key)}"
    assert by_shape["bare"] == 1


## @brief A batch reply attributes per entry, not per call.
## @version 1
def test_a_batch_attributes_each_entry_separately(tmp_path: Path) -> None:
    """A BATCH REPLY'S TOP-LEVEL `found` IS A COUNT OF HITS, NOT A BOOLEAN — the defect
    `selector_waste.missed_subjects` was written to fix, and this script inherits that function
    rather than re-deciding it. One hit and one miss in one call must yield exactly one miss.
    """
    payload = {
        "found": 1,
        "results": [
            {"name": "monitor_loop", "subject_kind": "function"},
            {"name": "Watchdog::monitor_loop", "found": False},
        ],
    }
    rows = [
        [_use_block("c1", ["monitor_loop", "Watchdog::monitor_loop"])],
        [_reply("c1", payload)],
    ]
    totals, _by_key, by_shape = audit_cell(_transcript(tmp_path / "s.jsonl", rows))

    assert totals["missed"] == 1, f"a partial batch miss must count one, got {totals['missed']}"
    assert by_shape["qualified"] == 1


## @brief A path is a path before it is a qualification.
## @version 1
@pytest.mark.parametrize(
    ("subject", "expect"),
    [
        pytest.param("src/app.ts", "file path", id="path-with-dot"),
        pytest.param("generate_errors.pl", "file path", id="bare-filename"),
        pytest.param("Owner::method", "qualified", id="cxx"),
        pytest.param("pkg.module.fn", "qualified", id="python"),
        pytest.param("monitor_loop", "bare", id="bare"),
    ],
)
def test_shape_tests_a_path_before_a_qualification(subject: str, expect: str) -> None:
    """ORDER MATTERS AND IS ASSERTED. `src/app.ts` contains a `.`, so a qualification test running
    first reads it as owner `src/app` and member `ts` — which would move 48 file-path misses into
    the qualified bucket and send C7 after a mode C1 already fixed.
    """
    assert shape(subject) == expect


## @brief Served spellings are harvested from nested replies at any depth.
## @version 1
def test_served_spellings_are_found_at_every_depth() -> None:
    """The keys that matter sit at different depths per surface — `threads[]`, `results[]`,
    `callers[]` — so a harvester that only read the top level would under-attribute, which
    understates the finding rather than overstating it and is therefore the harder error to
    notice.
    """
    out: dict[str, set[str]] = {}
    harvest_served(
        {
            "results": [
                {"name": "outer", "callers": [{"name": "nested", "qualified": "Own::nested"}]}
            ],
            "threads": [{"entry": "deep", "spawn_function": "Spawner::go"}],
        },
        out,
    )
    assert out["name"] == {"outer", "nested"}
    assert out["qualified"] == {"Own::nested"}
    assert out["entry"] == {"deep"}
    assert out["spawn_function"] == {"Spawner::go"}
