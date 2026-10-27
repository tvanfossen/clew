# SPDX-License-Identifier: MIT
"""A thread that exists in the source and in no index row.

**MEASURED ON A GRADED CELL.** Asked which threads a C++ service creates and how they shut down,
an agent with only the index reported FIVE sites. The source has NINE. It scored 37% and its own
caveat guessed the cause correctly: *"the index misses the per-client serve threads ... they do
not appear as rows."*

The four it could not see:

    src/inference/interface_factory.cpp:246   poller   = std::thread([cancel, &flag, &done]{...})
    src/core/response_generator.cpp:413       observer = std::thread([&ci, flag, &done]{...})
    src/inference/inference_c_api.cpp:385     poller_  = std::thread([this, cancel_flag]{...})
    src/facade/external_bridge.cpp:1222       std::thread([...]{...}).detach()

**MEMBER ASSIGNMENT WAS NEVER THE PROBLEM** — `monitor_thread_ = std::thread(&HealthMonitor::
monitor_loop, this)` is detected and always was. The sole discriminator is a NAMED entry versus a
LAMBDA: `_entry_names` resolves a lambda only when its body is a single call
(`[this]{ poll_loop(); }`), and all four of these have multi-statement bodies, so it returns None
and `_resolve_spawn_site` dropped the spawn entirely.

**FAILING CLOSED ON THE ENTRY NAME MUST NOT DROP THE SPAWN.** The thread is there; only its entry
is unnameable. The schema has allowed a NULL entry from the start — `insert_threads`' own
docstring says *"NULL entry = thread present, no closure"* — so the row had somewhere to go the
whole time. Reporting no row says "no thread", which is the flattering reading of a parser limit
and the exact failure `absence is not emptiness` names.

**THE NAME MUST DISTINGUISH THEM, OR THE FIX RECORDS ONE ROW INSTEAD OF FOUR.** `threads` is
UNIQUE(name, entry_memberdef_rowid, kind); with a NULL entry and a constant placeholder, four
unnamed lambdas in one tree collapse to a single row — a fix that looks like it worked and
undercounts by three. The assignment target carries the name instead.

@brief A lambda-bodied thread spawn is recorded, not dropped.
@version 1
"""

from __future__ import annotations

from typing import Any

from clew.harvest import _cached_parser
from clew.threads import _walk_spawn_sites, load_thread_patterns, patterns_by_name

## The four shapes the entropic grid proved invisible, plus a NAMED entry as the control: a fix
## that broke the working case while adding the new one must fail here rather than read as a win.
_LAMBDA_FORMS = b"""
#include <thread>
struct Runner {
    void monitor_loop();
    void start() {
        monitor_thread_ = std::thread(&Runner::monitor_loop, this);
    }
    void poll() {
        poller_ = std::thread([this]() {
            while (running_) { step(); tick(); }
        });
    }
    std::thread monitor_thread_;
    std::thread poller_;
    bool running_;
    void step();
    void tick();
};

void run_local() {
    std::thread poller;
    poller = std::thread([]() {
        while (true) { work(); more_work(); }
    });
    std::thread observer = std::thread([]() {
        for (;;) { watch(); also_watch(); }
    });
}

void fire_and_forget() {
    std::thread([]() {
        setup();
        teardown();
    }).detach();
}
"""


##
# @brief Parse C++ with the harvester's own parser.
# @param src Raw source bytes.
# @return (tree, src) pair.
# @version 1
# @dg_internal
def _parse(src: bytes) -> tuple[Any, bytes]:
    """REUSES `_cached_parser` so the test parses with the same grammar the harvest does — a
    test with its own parser can pass against a tree the pipeline never sees.

    @brief Parse with the harvester's parser.
    @return Tree and source.
    @version 1
    """
    parser = _cached_parser("substrate:cpp", {})
    assert parser is not None, "the C++ grammar must be available"
    return parser.parse(src), src


##
# @brief Every lambda-bodied spawn must be harvested, not dropped.
# @return None.
# @version 1
def test_a_lambda_bodied_spawn_is_harvested() -> None:
    """FIVE SITES IN THIS FIXTURE: one named entry and four lambdas, three assigned and one
    detached temporary. Before the fix only the named one survived.

    @brief All five spawn sites are seen.
    @return None.
    @version 1
    """
    patterns = patterns_by_name(load_thread_patterns(None))
    tree, src = _parse(_LAMBDA_FORMS)

    sites = _walk_spawn_sites(tree, src, patterns)

    assert len(sites) == 5, (
        f"expected 5 spawn sites (1 named + 4 lambda-bodied), got {len(sites)}: "
        f"{[s[0] for s in sites]}"
    )


##
# @brief The named-entry control must still resolve to its entry function.
# @return None.
# @version 1
def test_the_named_entry_control_still_resolves() -> None:
    """THE TWO-SIDED ASSERTION. Recording unnameable entries must not cost the nameable ones, and
    a test that only counted rows would not notice if it had.

    @brief A named entry keeps its entry name.
    @return None.
    @version 1
    """
    patterns = patterns_by_name(load_thread_patterns(None))
    tree, src = _parse(_LAMBDA_FORMS)

    sites = _walk_spawn_sites(tree, src, patterns)
    entries = [s[1] for s in sites]

    assert "monitor_loop" in entries, f"the named entry stopped resolving: {entries}"


##
# @brief Unnamed spawns must carry distinct names, or they collapse to one row.
# @return None.
# @version 1
def test_unnamed_spawns_get_distinct_names() -> None:
    """**THE FIX THAT LOOKS LIKE IT WORKED AND UNDERCOUNTS BY THREE.** `threads` is
    UNIQUE(name, entry_memberdef_rowid, kind). With a NULL entry, four lambdas sharing one
    placeholder name collapse into a single row, so the harvester would report 2 threads where
    the source has 5 — and every count downstream would be wrong while the bug report said fixed.

    The assignment target is what distinguishes them: `poller_`, `poller`, `observer`. The
    detached temporary has no target and must still differ from the others.

    @brief Unnamed spawns do not collide.
    @return None.
    @version 1
    """
    patterns = patterns_by_name(load_thread_patterns(None))
    tree, src = _parse(_LAMBDA_FORMS)

    names = [s[0] for s in _walk_spawn_sites(tree, src, patterns)]

    assert len(set(names)) == len(names), f"spawn names collide and would collapse rows: {names}"
