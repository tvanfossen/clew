# SPDX-License-Identifier: MIT
"""The TypeScript/JSX acceptance target, asserted on its REAL tree.

WHY THIS FILE EXISTS. TypeScript shipped flagged harvested on synthetic fixtures alone, and every
fixture declared its components the easy way. The first build of this tree found what none of
them could: `NavigationHeader`, rendered from eight files, had no callers at all, because it is
declared `const NavigationHeader = forwardRef(...)`. A rubric graded on a tree the index cannot
answer about measures the index's blind spot and reports it as the arm's.

SO EVERY ASSERTION HERE IS ABOUT A FACT THE RUBRIC GRADES, read from the rubric itself: the pin,
and the set of files that render `NavigationHeader`. If the rubric changes, these change with it.

Opt-in with the rest of the integration tier (`--integration`); it fetches one pinned commit.

@brief Real-tree assertions for the mattermost-mobile target.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from clew.query.corpus import generation_rule
from clew.query.symbols import callers

## Resolved here rather than imported: the integration directory is not a package, so its conftest
## is a pytest plugin, not a module. The value matches `conftest.MATTERMOST_RUBRIC`.
MATTERMOST_RUBRIC = (
    Path(__file__).resolve().parents[2] / "acceptance/targets/mattermost/questions.yaml"
)


## @brief The members of one set mark in the mattermost rubric.
## @param question The question id.
## @return Member values.
## @version 1
def _set_members(question: str) -> set[str]:
    """@brief Read a set mark's members from the rubric.
    @return Members.
    @version 1
    """
    rubric = yaml.safe_load(MATTERMOST_RUBRIC.read_text(encoding="utf-8"))
    (q,) = [q for q in rubric["questions"] if q["id"] == question]
    (mark,) = [m for m in q["marks"] if m["type"] == "set"]
    return {m["value"] for m in mark["members"]}


## @brief Every file the rubric says renders NavigationHeader holds a `jsx` caller of it.
## @param mattermost_db The real index.
## @return None.
## @version 1
def test_the_files_that_render_navigationheader_are_its_jsx_callers(mattermost_db: Path) -> None:
    """EXACT, NOT A SUPERSET. A missing file is the defect this was found by; an extra file would
    mean a `<Header` or some other element was resolved to the wrong component.

    @brief Q3's set is what the index holds.
    @version 1
    """
    got = {
        row[0]
        for row in sqlite3.connect(mattermost_db).execute(
            "SELECT DISTINCT p.name FROM call_edges e "
            "JOIN memberdef callee ON callee.rowid = e.callee_rowid "
            "JOIN memberdef caller ON caller.rowid = e.caller_rowid "
            "JOIN path p ON p.rowid = caller.file_id "
            "WHERE callee.name = 'NavigationHeader' AND e.source = 'jsx'"
        )
    }
    assert got == _set_members("Q3"), (
        f"missing: {sorted(_set_members('Q3') - got)}; unexpected: {sorted(got - _set_members('Q3'))}"
    )


## @brief No `jsx` edge points at an HTML intrinsic.
## @param mattermost_db The real index.
## @return None.
## @version 1
def test_no_jsx_edge_points_at_a_lowercase_name(mattermost_db: Path) -> None:
    """`<View>` is a component and `<div>` is an element. A `jsx` edge to a lowercase name would
    mean the capitalisation filter failed on real input and the table filled with edges to
    symbols that happen to share an element's name.

    @brief The intrinsic filter holds on the real tree.
    @version 1
    """
    count = (
        sqlite3.connect(mattermost_db)
        .execute(
            "SELECT count(*) FROM call_edges e JOIN memberdef m ON m.rowid = e.callee_rowid "
            "WHERE e.source = 'jsx' AND substr(m.name, 1, 1) BETWEEN 'a' AND 'z'"
        )
        .fetchone()[0]
    )
    assert count == 0, f"{count} jsx edge(s) point at a lowercase name"


## @brief The one generated file is recorded, by its exact path, and no namesake is.
## @param mattermost_db The real index.
## @return None.
## @version 1
def test_only_the_emoji_table_is_self_declared_generated(mattermost_db: Path) -> None:
    """MEASURED: one file in this tree declares itself generated, `app/utils/emoji/index.ts`. Its
    basename is the most common in the repository, so a basename join would mark hundreds of
    hand-written files generated; this asserts the exact-path rule holds at that scale.

    @brief The exact-path rule holds on the real tree.
    @version 1
    """
    conn = sqlite3.connect(mattermost_db)
    paths = {
        r[0]
        for r in conn.execute(
            "SELECT output_literal FROM generated_files WHERE kind LIKE 'self-declared:%'"
        )
    }
    assert paths == {"app/utils/emoji/index.ts"}, paths
    assert generation_rule(conn, "app/components/navigation_header/index.tsx") is None


## @brief The websocket dispatcher is recorded as the caller of Q2's handler.
## @param mattermost_db The real index.
## @return None.
## @version 1
def test_the_websocket_dispatcher_calls_the_reaction_handler(mattermost_db: Path) -> None:
    """The first hop of Q2's flow, across files: `handleWebSocketEvent` (actions/websocket/event.ts)
    calls `handleReactionAddedToPostEvent` (actions/websocket/reactions.ts).

    @brief Q2's first hop is an edge.
    @version 1
    """
    names = {edge.name for edge in callers(mattermost_db, "handleReactionAddedToPostEvent")}
    assert "handleWebSocketEvent" in names, names
