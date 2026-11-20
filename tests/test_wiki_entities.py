# SPDX-License-Identifier: MIT
"""Entity quick views: a modal per function on a flow, with the view strip (round 5, P5.6).

OWNER (round 5): every entity gets a page plus a QUICK-VIEW MODAL, with the view strip
Map · Block · Flow · Replay · Source · Tests · Reqs. A quick view, not a copy of the page: each view
carries small inline facts and links to the full view, lists capped with "N more on its page" —
the 14.6 MB evidence-diagram lesson says nothing per-entity is drawn in full on every page that
mentions it. Without script every view is shown, stacked; `clew-views.js` makes them tabs.

@brief Tests the entity quick view.
@version 1
"""

from __future__ import annotations

from clew.wiki.entities import VIEWS, EntityFacts, quick_view


def _facts(**overrides) -> EntityFacts:
    """@brief A function's facts, overridable. @return Facts."""
    base = {
        "name": "save",
        "file": "pkg/store.py",
        "brief": "Save the data.",
        "block": "Storage",
        "flows": (("flow-main", "main (pkg/cli.py)"),),
        "replays": (("flow-test_save", "test `test_save`"),),
        "tests": tuple((f"test_{i}", f"test-t-{i}.html") for i in range(8)),
        "reqs": ("REQ-S-001",),
        "page": "sym-pkg-store-py.html",
        "anchor": "s-save",
    }
    base.update(overrides)
    return EntityFacts(**base)


def test_the_view_strip_has_every_view_in_order() -> None:
    """@brief Map · Block · Flow · Replay · Source · Tests · Reqs, a tab and a panel each."""
    html = quick_view(_facts())
    assert VIEWS == ("map", "block", "flow", "replay", "source", "tests", "reqs")
    tabs = [html.split(f'data-view="{v}"', 1)[0].count("data-view=") for v in VIEWS]
    assert tabs == sorted(tabs) and all(f'data-view-panel="{v}"' in html for v in VIEWS)


def test_each_view_carries_its_facts_and_links_the_full_view() -> None:
    """@brief The map focuses the node; source opens the activity; flows, reqs and tests link."""
    html = quick_view(_facts())
    assert 'href="map.html#n=save%40pkg%2Fstore.py"' in html
    assert ">Storage<" in html
    assert 'href="flow-main.html"' in html and 'href="flow-test_save.html"' in html
    assert 'href="sym-pkg-store-py.html#s-save"' in html and "#act-s-save" in html
    assert 'href="req-REQ-S-001.html"' in html


def test_a_long_list_is_capped_with_a_pointer_to_the_page() -> None:
    """@brief Eight tests: five shown, "3 more on its page" linking the function's page."""
    html = quick_view(_facts())
    tests = html.split('data-view-panel="tests"', 1)[1].split("</section>", 1)[0]
    assert tests.count('href="test-t-') == 5
    assert "3 more on its page" in tests and 'href="sym-pkg-store-py.html#s-save"' in tests


def test_an_empty_view_says_so() -> None:
    """ABSENCE IS STATED: no requirement and no recorded run are sentences, not blank tabs.

    @brief Empty views.
    """
    html = quick_view(_facts(reqs=(), replays=()))
    reqs = html.split('data-view-panel="reqs"', 1)[1].split("</section>", 1)[0]
    replay = html.split('data-view-panel="replay"', 1)[1].split("</section>", 1)[0]
    assert "No requirement names this function" in reqs
    assert "No recorded run" in replay


def test_a_brief_is_plain_text_not_doxygen_xml(tmp_path) -> None:
    """FOUND BY LOOKING: the quick view printed `<para>…</para>`. Briefs are read through
    `strip_xml`, as the step modal's are.

    @brief Briefs without markup.
    """
    import sqlite3

    from clew.wiki.entities import _briefs

    db = tmp_path / "b.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_id INT,"
        " bodyfile_id INT, briefdescription TEXT);"
        "INSERT INTO path VALUES (1, 'pkg/a.py');"
        "INSERT INTO memberdef VALUES (1, 'f', 'function', 1, 1, '<para>Hold a lock. </para>');"
    )
    assert _briefs(conn) == {("f", "pkg/a.py"): "Hold a lock."}
