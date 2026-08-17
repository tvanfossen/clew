# SPDX-License-Identifier: MIT
"""R1 lock layer L2: critical-section membership (task #52).

L1 said a lock exists and where it is taken; L2 says WHAT RUNS while it is held.
These tests pin the part that is easy to get plausibly wrong — the extent — over
both reference idioms, because the obvious implementation (every call between
the acquire line and the release line) fabricates membership on real code.

The counter-example is not hypothetical. From a C/POSIX codebase::

    pthread_mutex_lock(&cmd_queue_mutex);   // 2574
    if (cmd_id_queued_locked(id)) {         // 2575  under the lock
        pthread_mutex_unlock(&...);         // 2577
        cmd_send_response(...);             // 2578  NOT under the lock
        return true;
    }
    pthread_mutex_unlock(&cmd_queue_mutex); // 2590

`cmd_send_response` is lexically inside 2574..2590 and runs with the lock
released. A span-based layer reports it as synchronized — a specific, false
claim, and worse than reporting nothing.

@brief Tests for clew.critical_sections.
@version 1
"""

from __future__ import annotations

import sqlite3

import pytest

from clew.critical_sections import (
    EXTENT_EXACT,
    EXTENT_INFERRED,
    EXTENT_UNRESOLVED,
    ensure_section_table,
    insert_section_calls,
    resolve_section,
)
from clew.harvest import enclosing, try_import_tree_sitter
from clew.locks import DEFAULT_LOCK_PATTERNS, _walk_lock_sites
from clew.vocabulary import (
    SECTION_MATCH_AMBIGUOUS,
    SECTION_MATCH_EXTERNAL,
    SECTION_MATCH_RECEIVER_UNVERIFIED,
    SECTION_MATCH_RESOLVED,
)

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the critical-section tests need tree_sitter + its C/C++ grammars",
)

## Index of the harvested site record's fields, so a test reads by meaning.
## `_walk_lock_sites` emits a positional list (it is cached as JSON), and an
## index literal in an assertion is unreadable the moment the shape changes.
OPERAND, END_LINE, CONFIDENCE, CALLS = 1, 4, 9, 10


## @brief Parse source and harvest its lock sites with L2 membership.
## @param src Source bytes.
## @param cpp Use the C++ grammar when true, else C.
## @return Harvested site records.
## @version 1
def _sites(src: bytes, cpp: bool = True) -> list[list]:
    """@brief Walk one source blob for lock sites + their critical sections."""
    import tree_sitter_c
    import tree_sitter_cpp
    from tree_sitter import Language, Parser

    mod = tree_sitter_cpp if cpp else tree_sitter_c
    parser = Parser(Language(mod.language()))
    patterns = {p.name: p for p in DEFAULT_LOCK_PATTERNS}
    return _walk_lock_sites(parser.parse(src), src, patterns)


## @brief Callee names recorded inside the section of a named operand.
## @param sites Harvested site records.
## @param operand Mutex operand name.
## @return The member callee names, in source order.
## @version 1
def _members(sites: list[list], operand: str) -> list[str]:
    """@brief Member callee names for one operand's section."""
    site = next(s for s in sites if s[OPERAND] == operand)
    return [call[0] for call in site[CALLS]]


# ── idiom 1: C++ RAII, where the hold is a language guarantee ────────────────

_RAII = b"""\
class Widget {
 public:
  void tick() {
    prepare();
    std::lock_guard<std::mutex> g(mutex_);
    read_state();
    write_state();
  }
 private:
  mutable std::mutex mutex_;
};
"""


def test_raii_membership_is_everything_after_the_guard_in_its_block() -> None:
    """A C++ guard holds until the end of its enclosing block, by language rule,
    so the section needs no release token at all. `prepare()` runs BEFORE the
    guard is constructed and must not be included — the acquisition's own end
    byte is the floor, not the start of the block."""
    assert _members(_sites(_RAII), "mutex_") == ["read_state", "write_state"]


def test_raii_extent_is_the_block_end_and_needs_no_inference() -> None:
    """Nothing had to be reasoned past, so the extent is reported 'high'. This
    is what makes the C++ idiom the easy half: `confidence` grades the EXTENT,
    and an RAII hold's extent is not an inference."""
    site = next(s for s in _sites(_RAII) if s[OPERAND] == "mutex_")
    assert site[END_LINE] == 8, "the hold runs to the closing brace of tick()"
    assert site[CONFIDENCE] == EXTENT_EXACT


# ── idiom 2: C/POSIX explicit pairs ──────────────────────────────────────────

_C_BALANCED = b"""\
void balanced(void) {
  before();
  pthread_mutex_lock(&g_lock);
  inside_one();
  inside_two();
  pthread_mutex_unlock(&g_lock);
  after();
}
"""


def test_explicit_pair_membership_stops_at_the_unlock() -> None:
    """The calls before the lock and after the unlock are NOT under it. Getting
    this wrong in either direction is a false synchronization claim."""
    assert _members(_sites(_C_BALANCED, cpp=False), "g_lock") == ["inside_one", "inside_two"]


def test_a_release_of_a_DIFFERENT_mutex_does_not_end_the_section() -> None:
    """The operand must match. Truncating at an unrelated mutex's unlock would
    silently shrink the section and drop real members."""
    src = b"""\
void f(void) {
  pthread_mutex_lock(&a_lock);
  pthread_mutex_unlock(&b_lock);
  still_under_a();
  pthread_mutex_unlock(&a_lock);
}
"""
    assert _members(_sites(src, cpp=False), "a_lock") == ["still_under_a"]


# ── the case a lexical span gets wrong: early return out of a section ────────

_C_EARLY_RETURN = b"""\
void guarded(int bad) {
  pthread_mutex_lock(&q_lock);
  if (checked(bad)) {
    logged_inside();
    pthread_mutex_unlock(&q_lock);
    respond_unlocked();
    return;
  }
  appended();
  pthread_mutex_unlock(&q_lock);
}
"""


def test_early_return_out_of_a_section_excludes_what_follows_its_unlock() -> None:
    """The measured counter-example, reduced. `respond_unlocked` is LEXICALLY
    between the acquire and the fall-through unlock but executes after the
    branch's own unlock, so a span-based rule reports it as synchronized.

    Membership is decided by block-chain shadowing instead: a release earlier in
    any block on the node's ancestor chain ends the hold on that path.
    `logged_inside` (before the branch unlock) and `appended` (after the branch,
    which returned) are both genuinely held; `respond_unlocked` is not.
    """
    members = _members(_sites(_C_EARLY_RETURN, cpp=False), "q_lock")
    assert "logged_inside" in members
    assert "appended" in members, "the branch returned, so the lock is still held after it"
    assert "respond_unlocked" not in members, "runs AFTER the branch's own unlock"


def test_early_return_extent_is_the_fall_through_unlock_not_the_branch_one() -> None:
    """The branch's unlock is a CONDITIONAL release: control leaves the block, so
    it does not end the hold for the code that follows. Taking it as the extent
    would report a four-line critical section where the real one is ten.

    Reported 'medium' rather than 'high' because the jump-termination inference
    is load-bearing here, and a consumer should be able to see that.
    """
    site = next(s for s in _sites(_C_EARLY_RETURN, cpp=False) if s[OPERAND] == "q_lock")
    assert site[END_LINE] == 10, "the fall-through unlock, not the one at line 5"
    assert site[CONFIDENCE] == EXTENT_INFERRED


def test_the_closing_release_is_deterministic_not_traversal_ordered() -> None:
    """With two candidate releases the answer must come from the code, not from
    which one a DFS stack happened to pop first — the defect this rule replaces.
    Parsing the same bytes repeatedly must give one stable extent."""
    extents = {
        next(s for s in _sites(_C_EARLY_RETURN, cpp=False) if s[OPERAND] == "q_lock")[END_LINE]
        for _ in range(5)
    }
    assert extents == {10}


# ── nesting: two locks held at once ──────────────────────────────────────────


def test_a_nested_acquisition_is_recorded_under_the_outer_hold_too() -> None:
    """An inner guard in a nested block does not end the outer hold, so a call
    inside the inner block is under BOTH locks. Reporting it under only the
    inner one would hide exactly the two-lock holding an ordering check needs."""
    src = b"""\
void Owner::run() {
  std::lock_guard<std::mutex> outer(outer_mutex_);
  outer_work();
  {
    std::lock_guard<std::mutex> inner(inner_mutex_);
    shared_work();
  }
}
"""
    sites = _sites(src)
    assert _members(sites, "inner_mutex_") == ["shared_work"]
    outer = _members(sites, "outer_mutex_")
    assert "outer_work" in outer
    assert "shared_work" in outer, "the inner block is still inside the outer hold"


# ── fail closed ──────────────────────────────────────────────────────────────


def test_an_unbalanced_lock_yields_no_extent_and_NO_membership() -> None:
    """The primary fail-closed case. With no release at all the hold escapes the
    function, so its extent is unknown — and an unknown extent must produce no
    membership rather than a partial list, because a partial list is
    indistinguishable from a complete one to whoever reads it."""
    src = b"""\
void leaks(void) {
  pthread_mutex_lock(&orphan_lock);
  might_be_under_it();
}
"""
    site = next(s for s in _sites(src, cpp=False) if s[OPERAND] == "orphan_lock")
    assert site[END_LINE] is None
    assert site[CALLS] == []
    assert site[CONFIDENCE] == EXTENT_UNRESOLVED


def test_a_conditional_release_that_does_not_jump_away_fails_closed() -> None:
    """`if (x) { unlock; }` with NO return releases the lock on one path only, so
    after the branch the lock state is genuinely unknown. There is no honest
    extent to report, and claiming either answer invents synchronization.

    This is the case that separates fail-closed from merely conservative: the
    detector CAN see a release here, and still refuses to use it."""
    src = b"""\
void maybe(int x) {
  pthread_mutex_lock(&m_lock);
  if (x) {
    pthread_mutex_unlock(&m_lock);
  }
  unknown_state();
}
"""
    site = next(s for s in _sites(src, cpp=False) if s[OPERAND] == "m_lock")
    assert site[END_LINE] is None
    assert site[CALLS] == []
    assert site[CONFIDENCE] == EXTENT_UNRESOLVED


## @brief A parsed node that has no enclosing block.
## @return A tree-sitter root node.
## @version 1
def _rootless_node():
    """@brief A node with no `compound_statement` ancestor, for degenerate input."""
    import tree_sitter_c
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_c.language()))
    return parser.parse(b"int x;").root_node


def test_an_unnamed_operand_yields_no_section() -> None:
    """Without an operand there is no lock identity to attribute membership to,
    and L1 already refuses to create a lock row for one. L2 must agree rather
    than recording calls under a section belonging to nothing."""
    section = resolve_section(_rootless_node(), b"int x;", None, "")
    assert section.end_line is None
    assert section.calls == []
    assert section.confidence == EXTENT_UNRESOLVED


def test_a_declared_call_primitive_with_no_known_release_fails_closed() -> None:
    """A repo declaring its own `call`-form primitive has no release counterpart
    registered, so the extent cannot be derived. It must NOT fall through to the
    RAII block-scope rule, which would report a whole function as one critical
    section on no evidence — the one fail-OPEN a unified walk could introduce."""
    from clew.locks import _section_for, load_lock_patterns

    declared = next(
        p
        for p in load_lock_patterns({"locks": [{"name": "bsp_take", "form": "call"}]})
        if p.name == "bsp_take"
    )
    section = _section_for(_rootless_node(), b"int x;", declared, "some_lock")
    assert section.end_line is None
    assert section.calls == []
    assert section.confidence == EXTENT_UNRESOLVED


# ── persistence: callee resolution never borrows a rowid ─────────────────────


## @brief An in-memory DB carrying the L2 table and a minimal memberdef.
## @return Open connection.
## @version 1
def _section_db() -> sqlite3.Connection:
    """@brief Build a throwaway DB with critical_section_calls."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE memberdef (name TEXT, kind TEXT);
        CREATE TABLE lock_acquisitions (id INTEGER PRIMARY KEY);
        INSERT INTO lock_acquisitions (id) VALUES (1);
        """
    )
    ensure_section_table(conn)
    return conn


def test_an_ambiguous_callee_is_ONE_row_with_no_rowid_not_one_per_candidate() -> None:
    """A call site is a PHYSICAL LOCATION — it can only ever be one call. Fanning
    an ambiguous name out the way `call_edges` does would answer "what runs under
    this lock" with N functions where exactly one runs, and nothing in the result
    would mark the N-1 as invented.

    So the row stays single, `callee_rowid` stays NULL — never another symbol's
    rowid — and `resolution` records why.
    """
    conn = _section_db()
    inserted = insert_section_calls(conn, 1, [["react", 10]], {"react": [7, 8, 9]})
    assert inserted == 1
    rows = conn.execute("SELECT callee_rowid, resolution FROM critical_section_calls").fetchall()
    assert rows == [(None, SECTION_MATCH_AMBIGUOUS)]


def test_a_callee_with_no_memberdef_is_external_not_fuzzy() -> None:
    """The majority case: a critical section is full of stdlib, vendor and macro
    calls that have no memberdef at all. Filing those under `call_match`'s
    nearest member ('fuzzy') would claim an in-repo callee was ambiguous when
    there was never a candidate to be ambiguous between."""
    conn = _section_db()
    insert_section_calls(conn, 1, [["memcpy", 4]], {})
    assert conn.execute("SELECT resolution FROM critical_section_calls").fetchone() == (
        SECTION_MATCH_EXTERNAL,
    )


def test_a_uniquely_named_BARE_callee_resolves_to_its_rowid() -> None:
    """The case the cross-function nesting query depends on: only a RESOLVED
    row can be joined back to a function that takes another lock.

    The third payload element is the BARE flag, added because this test's own premise —
    `tap_record` is a free function, called as `tap_record(...)` — was never expressed and so
    the resolver applied it to `x.tap_record()` too. See the sibling test below for what that
    cost. The intent here is unchanged: a bare call whose name is unique IS that function.
    """
    conn = _section_db()
    insert_section_calls(conn, 1, [["tap_record", 251, True]], {"tap_record": [42]})
    assert conn.execute(
        "SELECT callee_rowid, resolution FROM critical_section_calls"
    ).fetchone() == (
        42,
        SECTION_MATCH_RESOLVED,
    )


def test_a_uniquely_named_MEMBER_callee_does_NOT_resolve() -> None:
    """A UNIQUE NAME IS NOT EVIDENCE ABOUT A RECEIVER — `fd384e5` applied that to
    `ast_member` call edges and this resolver did not follow, so the defect survived here.

    `x.store(...)` has had its receiver unwrapped away, so "exactly one indexed `store`" is a
    fact about the INDEX, not about the call — and the stdlib method it really named has no
    memberdef to compete with it.

    Measured on the public entropic index before the fix: 13 of 17 cross-function two-lock
    holdings were fabrications. `router_dirty_.store(true, std::memory_order_release)` is
    `std::atomic::store`, unindexed, so it matched the single indexed `store`
    (`PromptCache::store`) and `lock_nestings` reported IdentityManager's mutex nesting inside
    PromptCache's. Worse than the fan-out it mirrors, because `lock_nestings` is described to
    models as the raw material for a deadlock argument.

    DEMOTED, NOT DROPPED, and that distinction was measured rather than argued. Nulling the
    rowid took `lock_nestings` from 17 rows to ZERO on entropic, because the one GENUINE
    nesting is a member call too — `it->second.has_access(...)` on an `MCPKeySet`. The false
    `store` and the true `has_access` are syntactically identical; only the receiver's TYPE
    separates them. Trading 13 false positives for a layer that returns nothing is a worse
    answer, so the rowid stays and `resolution` carries the weakness.
    """
    conn = _section_db()
    insert_section_calls(conn, 1, [["store", 181, False]], {"store": [42]})
    assert conn.execute(
        "SELECT callee_rowid, resolution FROM critical_section_calls"
    ).fetchone() == (42, SECTION_MATCH_RECEIVER_UNVERIFIED), (
        "a member call keeps its rowid but must NOT claim the receiver was verified"
    )


def test_an_absent_bare_flag_reads_as_MEMBER_ish() -> None:
    """Fail closed on the old payload shape. A 2-element call predates the flag, and guessing
    `bare=True` for it would restore exactly the defect above on any un-migrated path. The
    build-version bump wipes cached payloads, so this is a belt-and-braces default rather than
    a live code path — which is the point: the conservative reading costs a resolution that
    can be recovered, the optimistic one invents a lock nesting that cannot be detected."""
    conn = _section_db()
    insert_section_calls(conn, 1, [["tap_record", 251]], {"tap_record": [42]})
    assert conn.execute("SELECT resolution FROM critical_section_calls").fetchone() == (
        SECTION_MATCH_RECEIVER_UNVERIFIED,
    )


def test_the_same_call_site_is_not_recorded_twice() -> None:
    """A site is identified by (acquisition, line, name). Re-running the import
    must not duplicate it — a duplicated member would inflate "what runs under
    this lock" with a call that happens once."""
    conn = _section_db()
    insert_section_calls(conn, 1, [["work", 5]], {"work": [3]})
    insert_section_calls(conn, 1, [["work", 5]], {"work": [3]})
    assert conn.execute("SELECT COUNT(*) FROM critical_section_calls").fetchone()[0] == 1


def test_the_table_is_created_even_for_a_repo_with_no_locks() -> None:
    """Same always-created contract L1 gives, so R2 and R4 never branch on table
    existence — the requirements-table precedent both follow."""
    conn = sqlite3.connect(":memory:")
    ensure_section_table(conn)
    assert conn.execute("SELECT COUNT(*) FROM critical_section_calls").fetchone()[0] == 0


# ── R2 accessors ─────────────────────────────────────────────────────────────

## Two locks BOTH named `mutex_`, in different classes — the collision that makes
## a bare lock name useless as an identity. `writer` holds Owner::mutex_ and
## calls `enqueue`, which holds Queue::mutex_: a cross-function two-lock holding,
## which is the shape L1 alone could not see.
_FIXTURE_SQL = """
CREATE TABLE memberdef (name TEXT, kind TEXT, definition TEXT, file_id INT, bodyfile_id INT);
CREATE TABLE path (name TEXT);
INSERT INTO path (rowid, name) VALUES (1, 'src/owner.cpp');
INSERT INTO memberdef (rowid, name, kind, definition, file_id, bodyfile_id)
  VALUES (1, 'writer', 'function', 'void Owner::writer()', 1, 1),
         (2, 'enqueue', 'function', 'void Queue::enqueue()', 1, 1),
         (3, 'audit', 'function', 'void audit()', 1, 1);
INSERT INTO locks (rowid, name, scope, kind, identity_confidence, source)
  VALUES (1, 'mutex_', 'class:Owner', 'mutex', 'high', 'ast_use'),
         (2, 'mutex_', 'class:Queue', 'mutex', 'high', 'ast_use');
INSERT INTO lock_acquisitions
  (id, lock_id, holder_rowid, path_rowid, form, role, mode,
   start_line, end_line, pattern_name, declared, confidence)
  VALUES (1, 1, 1, 1, 'raii', 'scoped', 'exclusive', 10, 20, 'lock_guard', 0, 'high'),
         (2, 2, 2, 1, 'raii', 'scoped', 'exclusive', 40, 45, 'lock_guard', 0, 'high');
INSERT INTO critical_section_calls
  (acquisition_id, callee_rowid, callee_name, call_line, resolution)
  VALUES (1, 2, 'enqueue', 12, 'resolved'),
         (1, NULL, 'memcpy', 15, 'external'),
         (2, 3, 'audit', 42, 'resolved');
"""


## @brief A database carrying the full L1+L2 lock layer with a scope collision.
## @return Open connection usable directly as a `DbSource`.
## @version 1
def _query_db() -> sqlite3.Connection:
    """@brief Build the R2 fixture database."""
    conn = sqlite3.connect(":memory:")
    from clew.locks import _ensure_lock_tables

    _ensure_lock_tables(conn)
    conn.executescript(_FIXTURE_SQL)
    return conn


def test_locks_held_when_answers_the_question_L1_could_not() -> None:
    """`enqueue` is called from inside `writer`'s hold of Owner::mutex_, so
    calling it means contending for a lock its own signature never mentions.
    The whole section comes back, not just the matching call, because "what else
    runs under the lock I am about to contend for" is the next question."""
    from clew.query import locks_held_when

    held = locks_held_when(_query_db(), "enqueue")
    assert [(s.lock, s.lock_scope, s.holder) for s in held] == [("mutex_", "class:Owner", "writer")]
    assert [c.callee for c in held[0].calls] == ["enqueue", "memcpy"]


def test_locks_held_when_matches_on_rowid_so_a_name_collision_cannot_leak() -> None:
    """Matching on the callee NAME would report every same-named function's
    holds as this one's. `audit` is called under Queue::mutex_ and nothing else;
    a name-based join through the ambiguous `mutex_` rows must not reach it."""
    from clew.query import locks_held_when

    held = locks_held_when(_query_db(), "audit")
    assert [(s.lock, s.lock_scope) for s in held] == [("mutex_", "class:Queue")]


def test_runs_under_lock_without_a_scope_unions_the_same_named_locks() -> None:
    """`mutex_` is a real member name in many classes. Omitting the scope is
    ALLOWED — a file-scope C mutex genuinely is unique by name — but it unions,
    and every returned section carries its own `lock_scope` so the caller can
    always tell which lock it got. That is the honest trade: no silent merge."""
    from clew.query import runs_under_lock

    conn = _query_db()
    both = runs_under_lock(conn, "mutex_")
    assert sorted(s.lock_scope for s in both) == ["class:Owner", "class:Queue"]
    only_queue = runs_under_lock(conn, "mutex_", "class:Queue")
    assert [s.lock_scope for s in only_queue] == ["class:Queue"]
    assert [c.callee for c in only_queue[0].calls] == ["audit"]


def test_sections_in_reports_what_a_function_does_under_its_own_lock() -> None:
    """The inverse of locks_held_when: the holds a function itself opens, with
    the extent and every member call."""
    from clew.query import sections_in

    sections = sections_in(_query_db(), "writer")
    assert len(sections) == 1
    assert (sections[0].start_line, sections[0].end_line) == (10, 20)
    assert sections[0].confidence == EXTENT_EXACT


def test_lock_nestings_reports_the_cross_function_two_lock_holding() -> None:
    """The measurement L1 recorded as impossible. Within a function both
    real codebases showed ZERO simultaneous holdings; the real ones span a
    call. Reported as an ORDERED pair, because the order — not the fact of
    nesting — is what a deadlock check compares between sites.

    Both locks are named `mutex_`, so this also pins that identity is by SCOPE:
    a name-keyed layer would see one lock nested inside itself and report
    nothing, or worse, a self-deadlock.
    """
    from clew.query import lock_nestings

    nestings = lock_nestings(_query_db())
    assert len(nestings) == 1
    assert (nestings[0].outer_scope, nestings[0].inner_scope) == ("class:Owner", "class:Queue")
    assert (nestings[0].via, nestings[0].holder, nestings[0].line) == ("enqueue", "writer", 12)


def test_lock_roster_carries_the_nestings_so_the_follow_up_call_is_unnecessary() -> None:
    """THE ROUND-3 FOLD. `lock_nestings` was a separate MCP tool over the SAME two tables
    and is deleted; the inventory carries the answer. Pins the fold at the level that
    matters — the pair set the deleted tool returned must be recoverable from the roster,
    or the collapse traded a round trip for an answer.

    The exemplar fields come through too, because a pair a caller cannot go and READ is
    not evidence. `sites` is what makes the collapse honest rather than lossy-and-quiet.
    """
    from clew.query import lock_nestings, lock_roster

    conn = _query_db()
    inventory = lock_roster(conn)
    sites = lock_nestings(conn)

    assert {(n.outer_scope, n.inner_scope) for n in inventory.nestings} == {
        (n.outer_scope, n.inner_scope) for n in sites
    }, "every pair the deleted tool reported must survive in the roster"
    assert sum(p.sites for p in inventory.nestings) == len(sites), (
        "the site count must account for every row, or the collapse dropped evidence "
        "without saying so"
    )
    pair = inventory.nestings[0]
    assert (pair.via, pair.holder, pair.line) == ("enqueue", "writer", 12)
    assert (pair.sites, pair.resolved_sites) == (1, 1)


def test_the_roster_collapses_nesting_sites_onto_pairs_and_prefers_a_resolved_exemplar() -> None:
    """TWO CLAIMS, AND THE SECOND IS THE ONE A NAIVE `dict` INSERTION GETS WRONG.

    `nestings_on` orders by scope and name, never by evidence, so keeping the first row
    seen hands the caller an unverified-receiver site to go and read while a confirmed one
    sits behind it in the same group. Measured on the public entropic index 19 of 26 sites
    are unverified, so first-seen picks a weak exemplar most of the time.

    A SECOND SITE FOR THE SAME PAIR IS ADDED HERE DELIBERATELY, ordered so the weak one
    comes first. Without the second site the group has one member, first-seen and
    best-resolved agree, and the test passes with the preference deleted.
    """
    from clew.query import lock_roster

    conn = _query_db()
    ## A second call from the SAME outer section into the SAME inner lock holder, whose
    ## receiver was never verified, inserted at a LOWER line so it sorts first.
    conn.execute(
        "INSERT INTO critical_section_calls "
        "(acquisition_id, callee_rowid, callee_name, call_line, resolution) "
        ## callee_rowid 2 is `enqueue`, which is acquisition 2's HOLDER — that is what makes
        ## a nesting. Rowid 3 (`audit`) holds nothing, so a call to it creates no pair and
        ## the probe would silently test one site instead of two.
        "VALUES (1, 2, 'enqueue', 11, 'receiver_unverified')"
    )
    nestings = lock_roster(conn).nestings

    assert len(nestings) == 1, "two sites of one pair are ONE nesting, not two"
    pair = nestings[0]
    assert (pair.sites, pair.resolved_sites) == (2, 1)
    assert (pair.via, pair.line) == ("enqueue", 12), (
        "the exemplar must be the RESOLVED site, not the first one the SQL ordering "
        "happened to yield"
    )


def test_an_empty_nesting_layer_says_so_definitively_rather_than_saying_nothing() -> None:
    """THE SENTENCE IS THE WHOLE POINT OF THE FOLD ON A TARGET LIKE MBEDTLS, whose lock
    primitive is a function pointer and whose nesting layer is therefore empty. Three of
    three observed acceptance runs called `lock_nestings` and got zero rows, because a
    roster that says nothing about nesting gives a caller no way to know the follow-up is
    pointless. Silence and "definitively none" cost the same bytes and differ by a call.

    `nestings` must be PRESENT and empty, not absent: `wire.one` keeps envelope keys, and
    an absent key reads as "not measured", which is the state that made the call look
    worth paying for in the first place.
    """
    from clew.query import lock_roster

    conn = _query_db()
    conn.execute("DELETE FROM critical_section_calls")
    inventory = lock_roster(conn)

    assert inventory.nestings == ()
    assert "0 two-lock holdings" in inventory.nesting_meaning
    assert "definitive" in inventory.nesting_meaning
    assert "not a proof of deadlock-freedom" in inventory.nesting_meaning.lower()
    ## And the locks are untouched — an empty nesting layer is not an empty lock layer.
    assert inventory.rows == 2


def test_the_roster_reports_the_pair_count_and_not_the_site_count() -> None:
    """THE SAME ROW-COUNT-IS-NOT-IDENTITY-COUNT TRAP `distinct_mutexes` EXISTS TO FIX, one
    layer over. Measured on the public entropic index, `lock_nestings` returns 26 rows over
    12 distinct pairs, so a caller told "26 nestings" reports more than twice the honest
    figure. `nesting_meaning` has to name which number to quote, the way `row_meaning` does
    for the mutexes — a payload that ships both numbers and ranks neither is how the
    conflation happened for locks."""
    from clew.query import lock_roster

    conn = _query_db()
    conn.execute(
        "INSERT INTO critical_section_calls "
        "(acquisition_id, callee_rowid, callee_name, call_line, resolution) "
        ## callee_rowid 2 is `enqueue`, which is acquisition 2's HOLDER — that is what makes
        ## a nesting. Rowid 3 (`audit`) holds nothing, so a call to it creates no pair and
        ## the probe would silently test one site instead of two.
        "VALUES (1, 2, 'enqueue', 11, 'receiver_unverified')"
    )
    meaning = lock_roster(conn).nesting_meaning

    assert "1 distinct two-lock holding(s) over 2 call site(s)" in meaning
    assert "Quote 1" in meaning, "the sentence must name the figure to quote, not just both"


def test_every_accessor_degrades_to_empty_on_a_database_without_the_layer() -> None:
    """#41's contract: a consumer may be pointed at an artifact built before L2
    existed and must get an empty answer, not an OperationalError. Both tables
    are checked, because a database built between L1 and L2 has one and not the
    other and a single-table guard would still raise on the join."""
    from clew.query import (
        lock_nestings,
        locks_held_when,
        runs_under_lock,
        sections_in,
    )

    bare = sqlite3.connect(":memory:")
    bare.executescript("CREATE TABLE memberdef (name TEXT, kind TEXT, definition TEXT);")
    assert locks_held_when(bare, "anything") == []
    assert sections_in(bare, "anything") == []
    assert runs_under_lock(bare, "anything") == []
    assert lock_nestings(bare) == []


def test_an_unresolved_extent_carries_no_calls_through_to_R2() -> None:
    """The fail-closed rule has to survive the query layer too: a section whose
    extent is NULL must arrive with an empty `calls`, so a consumer cannot read
    a partial membership as a complete one."""
    from clew.query import sections_in

    conn = _query_db()
    conn.execute(
        "INSERT INTO lock_acquisitions "
        "(id, lock_id, holder_rowid, path_rowid, form, role, mode, start_line, end_line, "
        " pattern_name, declared, confidence) "
        "VALUES (3, 1, 3, 1, 'call', 'acquire', 'exclusive', 60, NULL, "
        "'pthread_mutex_lock', 0, 'low')"
    )
    section = next(s for s in sections_in(conn, "audit") if s.start_line == 60)
    assert section.end_line is None
    assert section.calls == ()
    assert section.confidence == EXTENT_UNRESOLVED


def test_enclosing_walks_parents_so_a_block_is_not_its_own_ancestor() -> None:
    """The shadowing chain relies on it: `enclosing(block, BLOCK_TYPES)` must
    give the block OUTSIDE, or the walk from a node to the acquisition's block
    would never terminate and a release would shadow itself."""
    import tree_sitter_c
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_c.language()))
    tree = parser.parse(b"void f(void){ { g(); } }")
    calls = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "call_expression":
            calls.append(node)
    inner = enclosing(calls[0], ("compound_statement",))
    outer = enclosing(inner, ("compound_statement",))
    assert outer is not None and outer.id != inner.id
