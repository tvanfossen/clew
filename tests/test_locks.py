# SPDX-License-Identifier: MIT
"""R1 lock layer L1: lock identity and acquisition sites (task #52).

clew could say two threads touch the same key but not whether the access is
GUARDED. These tests cover the facts half, across BOTH reference idioms — C++
RAII guards (a declaration, not a call) and C/POSIX lock/unlock pairs.

@brief Tests for clew.locks.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.harvest import try_import_tree_sitter
from clew.locks import (
    DEFAULT_LOCK_PATTERNS,
    SCOPE_UNKNOWN,
    _walk_lock_sites,
    detect_undeclared_lock_primitives,
    load_lock_patterns,
)
from clew.vocabulary import DeclarationError

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the lock-layer tests need tree_sitter + its C/C++ grammars",
)

_CPP = b"""\
namespace demo {
class Widget {
 public:
  void tick() {
    std::lock_guard<std::mutex> g(mutex_);
    work();
  }
  void peek() const {
    std::shared_lock<std::shared_mutex> s(rw_);
  }
 private:
  mutable std::mutex mutex_;
  mutable std::shared_mutex rw_;
};
}
void LinkOwner::tx_loop() {
  std::lock_guard<std::mutex> g(tx_mutex_);
  send();
}
"""

_C = b"""\
void balanced(void) {
  pthread_mutex_lock(&g_lock);
  work();
  pthread_mutex_unlock(&g_lock);
}
void unbalanced(void) {
  pthread_mutex_lock(&other_lock);
}
"""


## @brief Parse source and harvest its lock sites.
## @param src Source bytes.
## @param cpp Use the C++ grammar when true, else C.
## @return Harvested site records.
## @version 1
def _sites(src: bytes, cpp: bool = True) -> list[list]:
    """@brief Walk one source blob for lock acquisition sites."""
    import tree_sitter_c
    import tree_sitter_cpp
    from tree_sitter import Language, Parser

    mod = tree_sitter_cpp if cpp else tree_sitter_c
    parser = Parser(Language(mod.language()))
    patterns = {p.name: p for p in DEFAULT_LOCK_PATTERNS}
    return _walk_lock_sites(parser.parse(src), src, patterns)


def test_raii_guard_is_found_though_it_is_a_declaration_not_a_call() -> None:
    """A C++ guard is a DECLARATION, so it is invisible to the call-site
    harvester every other AST layer is built on — it needs its own node
    handling or the entire C++ idiom reads as zero locks."""
    by_operand = {s[1]: s for s in _sites(_CPP)}
    assert "mutex_" in by_operand
    assert by_operand["mutex_"][5] == "raii"
    assert by_operand["mutex_"][7] == "exclusive"
    # shared_lock is a READ lock — mode must not be flattened to exclusive.
    assert by_operand["rw_"][7] == "shared"


def test_identity_is_scope_qualified() -> None:
    """`mutex_` recurs across many classes on a C++ codebase. Name-only keying would report
    unrelated classes as sharing a mutex — the worst error available here, since
    a fabricated shared lock is indistinguishable from real synchronization."""
    scopes = {s[1]: s[2] for s in _sites(_CPP)}
    assert scopes["mutex_"] == "class:Widget"
    assert scopes["rw_"] == "class:Widget"


def test_out_of_line_member_definition_still_resolves_its_class() -> None:
    """`void LinkOwner::tx_loop() {...}` has NO enclosing class_specifier, so
    the class must come from the qualified function name. Reading only the
    enclosing class node left 25 of a C++ codebase's 33 acquisitions scope-unknown."""
    scopes = {s[1]: s[2] for s in _sites(_CPP)}
    assert scopes["tx_mutex_"] == "class:LinkOwner"


def test_c_pair_extent_is_the_matching_unlock_and_absence_is_not_invented() -> None:
    """An explicit lock/unlock pair has no lexical scope to read an extent from.
    A matched release gives the extent; NO match must yield None rather than a
    guess, since an invented extent makes a critical section look larger than
    it is.

    The extent is now computed by `critical_sections.resolve_section` (L2), so
    that one analysis produces both the extent and the membership and the two
    cannot disagree. The harder extent cases — an early-return release, a
    conditional release that falls through — live in
    tests/test_critical_sections.py; what this pins is the L1 contract those
    must keep satisfying."""
    by_operand = {s[1]: s for s in _sites(_C, cpp=False)}
    assert by_operand["g_lock"][4] is not None, "balanced pair should have an extent"
    assert by_operand["other_lock"][4] is None, "unbalanced lock must not invent one"


def test_ownership_tags_are_not_mistaken_for_mutexes() -> None:
    """std::adopt_lock is a TAG, not a mutex. The filter is deliberately narrow:
    an earlier cut dropped anything containing '_lock', which silently discarded
    every real mutex named g_lock / data_lock — the common C naming."""
    src = b"void f(){ std::lock_guard<std::mutex> g(m_, std::adopt_lock); }\n"
    operands = {s[1] for s in _sites(src)}
    assert "m_" in operands
    assert not any("adopt_lock" in o for o in operands)


def test_a_declared_call_wrapper_can_name_its_release_and_so_gets_an_extent() -> None:
    """A repo's OWN lock wrapper could be declared but never closed.

    `_RELEASERS` is a module-level dict of built-in primitives, so a declared
    `call`-form wrapper had no route to name its unlock counterpart. The extent
    resolver refuses to fall back to the block extent — correctly, since treating
    an unknown release as block-scoped would report a whole function as one
    critical section on no evidence — so EVERY acquisition on a declared wrapper
    reported a NULL extent and contributed no membership.

    That was not a hypothesis. Measured on a real C library whose locking goes
    through an `mbedtls_mutex_lock`-style wrapper: **5 acquisition sites detected,
    0 with a resolved extent**, purely for want of somewhere to write the
    counterpart down. With `releases:` declared, the same build resolved 5 of 5
    and produced 25 critical-section calls.

    Both halves are asserted here, because a `releases:` that parsed but did not
    reach the resolver would look identical to the old behaviour.

    @brief A declared `releases:` closes a declared wrapper's extent.
    @version 1
    """
    src = b"""\
void guarded(void) {
  bsp_lock_take(&dev_lock);
  do_work();
  bsp_lock_give(&dev_lock);
}
"""
    declared = load_lock_patterns(
        {
            "locks": [
                {
                    "name": "bsp_lock_take",
                    "form": "call",
                    "role": "acquire",
                    "releases": "bsp_lock_give",
                }
            ]
        }
    )
    assert any(p.name == "bsp_lock_take" and p.releases == "bsp_lock_give" for p in declared), (
        "the declared release counterpart must survive parsing"
    )

    import tree_sitter_c
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_c.language()))
    sites = _walk_lock_sites(parser.parse(src), src, {p.name: p for p in declared})
    takes = [s for s in sites if s[0] == "bsp_lock_take"]
    assert takes, "the declared wrapper must be detected at all"
    assert takes[0][4] is not None, (
        "a declared wrapper naming its release must get a resolved extent; "
        "None here means `releases:` never reached the extent resolver"
    )


def test_declared_wrapper_merges_over_the_builtin_primitives() -> None:
    """The built-ins are language/OS primitives. A project's OWN guard type is
    DECLARED, never guessed — and declaring one must not drop the defaults."""
    patterns = load_lock_patterns({"locks": [{"name": "ScopedLock", "form": "raii"}]})
    names = {p.name for p in patterns}
    assert "ScopedLock" in names
    assert {p.name for p in DEFAULT_LOCK_PATTERNS} <= names


def test_invalid_declared_kind_fails_closed_rather_than_normalizing() -> None:
    """A typo'd `kind` REFUSES the build instead of normalizing to 'unknown'.

    `kind` is part of lock IDENTITY — `UNIQUE(name, scope, kind)`, and the
    lookup at insert time re-selects on all three. Normalizing means two
    DIFFERENT typos ('mutexx' and 'muted') both become 'unknown' and therefore
    collapse into ONE lock row, so acquisitions of two unrelated primitives are
    reported as taking the same lock. That is a fabricated shared lock, which is
    exactly what this module's scope-qualified identity rule exists to prevent —
    and unlike a missing row it is indistinguishable from real synchronization.
    """
    with pytest.raises(DeclarationError) as exc:
        load_lock_patterns({"locks": [{"name": "W", "kind": "bogus"}]})
    message = str(exc.value)
    assert "'W'" in message
    assert "'bogus'" in message
    assert "mutex, recursive_mutex, shared_mutex, semaphore, spinlock, unknown" in message


def test_invalid_declared_role_fails_closed() -> None:
    """`role` was the ONE declared lock enum with no guard at all: it rode raw
    into the INSERT and tripped `CHECK(role IN (...))` as a bare IntegrityError
    mid-build, naming neither the pattern nor the file. It now refuses at load
    time like its three siblings."""
    with pytest.raises(DeclarationError) as exc:
        load_lock_patterns({"locks": [{"name": "W", "role": "lock"}]})
    assert "'lock'" in str(exc.value)
    assert "acquire, try_acquire, scoped" in str(exc.value)


def test_invalid_declared_form_and_mode_fail_closed_instead_of_coercing() -> None:
    """`form` and `mode` used to coerce anything that was not the exact
    non-default spelling INTO the default: `form: "cal"` silently became an RAII
    guard and `mode: "shard"` an exclusive hold. Both are specific, real
    synchronization claims invented from a typo, so both now refuse."""
    with pytest.raises(DeclarationError):
        load_lock_patterns({"locks": [{"name": "W", "form": "cal"}]})
    with pytest.raises(DeclarationError):
        load_lock_patterns({"locks": [{"name": "W", "mode": "shard"}]})


def test_repo_with_no_locks_yields_nothing() -> None:
    """A correct negative, not an error."""
    assert _sites(b"int main(void){ return 0; }\n", cpp=False) == []


def test_unscoped_lock_is_kept_but_marked_rather_than_merged() -> None:
    """A free function's mutex has no class. It is still recorded — dropping it
    would under-report — but its scope is UNKNOWN so a consumer can weigh it
    instead of trusting a bare name that may recur elsewhere."""
    scopes = {s[1]: s[2] for s in _sites(_C, cpp=False)}
    assert scopes["g_lock"] == SCOPE_UNKNOWN


def test_a_pointer_return_type_does_not_split_a_lock_from_itself() -> None:
    """A member function returning a POINTER puts its sigil inside the declarator, so
    `Slot* SecondaryModelLoader::acquire()` yielded the scope `class:* SecondaryModelLoader`
    while the same class's void methods yielded `class:SecondaryModelLoader`.

    Scope is part of lock IDENTITY, so that split ONE mutex into TWO rows. Measured on the
    public entropic index at build version 14: 4 of 56 lock rows were starred, and every one
    was a duplicate of a `class:X` twin with the same name and the same kind — a 7% inflated
    lock count. The failure is pointed: the layer's central claim is that scope-qualified
    identity stops unrelated `mutex_` members from merging, and here the same mechanism was
    splitting a lock from itself.

    Reference returns (`&`) have the identical shape and are pinned too, because fixing only
    the case that showed up in one codebase is how the next one gets missed.
    """
    from clew.locks import _out_of_line_scope

    class _Span:
        """A node whose whole identity is its source span — enough for `_text`."""

        def __init__(self, text: bytes, node_type: str, parent: object = None) -> None:
            self.type = node_type
            self.parent = parent
            self.start_byte = 0
            self.end_byte = len(text)
            self.fields: dict[str, object] = {}

        def child_by_field_name(self, field: str) -> object:
            return self.fields.get(field)

    for declarator, expected in (
        (b"* SecondaryModelLoader::acquire", "class:SecondaryModelLoader"),
        (b"& ModelOrchestrator::ref", "class:ModelOrchestrator"),
        (b"PromptCache::store", "class:PromptCache"),
        (b"*PromptCache::get", "class:PromptCache"),
    ):
        fn = _Span(declarator, "function_definition")
        fn.fields["declarator"] = _Span(declarator, "function_declarator", fn)
        # `enclosing` walks the PARENT chain, so the seed must sit INSIDE the definition —
        # a node is never its own ancestor.
        inner = _Span(declarator, "call_expression", fn)
        assert _out_of_line_scope(inner, declarator) == expected, (
            f"{declarator!r} must attribute to the OWNER, never to the return-type sigil"
        )


# The three fixtures below are one experiment in three parts: the bare tail is
# LOAD-BEARING (a `using namespace std;` codebase writes it), a foreign
# namespace's guard is real, and a type that merely CONTAINS a guard token is
# not a guard at all. Any matcher has to keep the first two and reject the third.
_BARE = b"""\
using namespace std;
void bare_form() {
  lock_guard<mutex> g(bare_mutex_);
  unique_lock<mutex> u(other_mutex_);
}
"""

_FOREIGN_NS = b"""\
void foreign_ns() {
  boost::unique_lock<boost::mutex> g(boost_mutex_);
}
"""

_LOOKALIKE = b"""\
void audit(int depth_, int slot_) {
  std::vector<unique_lock_stats> tally(depth_);
  lock_guard_registry reg(slot_);
  std::map<int, shared_lock_metrics> seen(slot_);
}
"""


def test_the_bare_tail_is_load_bearing_and_must_keep_matching() -> None:
    """`using namespace std;` presents `lock_guard<mutex>` with no qualifier, and
    that is a REAL acquisition. Measured on the public
    [entropic](https://github.com/tvanfossen/entropic) tree: 6 `lock_guard<mutex>`
    and 6 `unique_lock<mutex>` declaration sites are written bare.

    So the fix for the lookalike case below may NOT be "require `std::`". This test
    is the fence that stops it: pinning the bare form means a later qualification
    breaks here rather than silently dropping twelve real acquisitions.
    """
    operands = {s[1] for s in _sites(_BARE)}
    assert operands == {"bare_mutex_", "other_mutex_"}


def test_a_guard_from_another_namespace_is_still_a_guard() -> None:
    """`boost::unique_lock` takes exclusive ownership of a mutex exactly as
    `std::unique_lock` does. The pattern names the CONVENTION, not the namespace,
    so a matcher keyed on the qualified `std::` spelling would report a
    boost-flavoured codebase as having no locks at all."""
    assert [s[1] for s in _sites(_FOREIGN_NS)] == ["boost_mutex_"]


def test_a_type_that_merely_contains_a_guard_token_is_not_an_acquisition() -> None:
    """THE FABRICATION THIS GUARDS. Matching was `pattern.name in type_text` — a
    raw substring test over the WHOLE type text, template arguments included. So
    `std::vector<unique_lock_stats>` matched `unique_lock`, and a container
    holding diagnostic counters was recorded as taking a lock on its own size
    argument.

    That is worse than a missed row in the direction that matters. A fabricated
    acquisition invents a lock IDENTITY (`_lock_id` keys on the operand name), and
    an invented lock is indistinguishable from real synchronization — the exact
    error the scope-qualified identity rule at the top of `locks.py` exists to
    prevent, arriving through the door next to it.

    It also cannot be corrected downstream: these are tier-3 FACTS, which
    accumulate and survive every stated tier, so no operator declaration can
    displace a row fabricated here.

    All three fixture lines carry a real operand in a real argument list, so the
    substring matcher produces a fully-formed, high-confidence, entirely
    fictitious row for each.
    """
    assert _sites(_LOOKALIKE) == []


def test_an_undeclared_acquire_release_pair_is_suggested(tmp_path: Path) -> None:
    """gh#385. The lock layer held ONE identity on mbedtls — `mutex->mutex`, scope unknown,
    confidence low — for a repository with five named global mutexes and 38 lock sites, and a
    graded agent copied that into its answer as "one first-party mutex identity resolved with
    1 acquisition". Every acquisition goes through the function POINTER `mbedtls_mutex_lock`,
    so the detector only ever saw `pthread_mutex_lock(&mutex->mutex)` inside the one wrapper.

    DECLARING IT IS THE FIX AND IT WORKS — measured: 1 identity / 1 acquisition becomes 10 / 46,
    with real names. Same answer the `STORE_SET_*` accessors got. So the DEFECT is that nothing
    told the owner to declare it: `detect_undeclared_accessor_families` exists for precisely
    this reason one layer over, and the lock layer had no counterpart.

    PAIRED, NOT NAME-SNIFFED. A name containing "lock" proves nothing — `spinlock_t`,
    `unlock_reason`, `lock_free_queue` all do. What identifies a primitive is that BOTH halves
    of an acquire/release pair are indexed, a property of the code rather than of a naming
    fashion. Measured on real targets: 1 pair on mbedtls with nothing declared, 0 once
    declared, 0 on this repo's own index — it names the one thing to act on and goes quiet.

    @brief An indexed acquire/release pair no pattern covers is suggested, once.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE memberdef (name TEXT, kind TEXT)")
    conn.executemany(
        "INSERT INTO memberdef(name, kind) VALUES(?, ?)",
        [
            ## The mbedtls shape: a function-POINTER pair, so neither half is ever a callee.
            ("proj_mutex_lock", "variable"),
            ("proj_mutex_unlock", "variable"),
            ## A FreeRTOS-style pair, to prove the suffix table is not just `_lock`.
            ("bsp_sem_take", "function"),
            ("bsp_sem_give", "function"),
            ## THE NEGATIVES, each a name a sniffer would fire on:
            ("spinlock_t", "typedef"),
            ("unlock_reason", "variable"),
            ("lock_free_queue", "function"),
            ## An acquire with NO partner is not a pair.
            ("orphan_lock", "function"),
        ],
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        found = dict(detect_undeclared_lock_primitives(conn, list(DEFAULT_LOCK_PATTERNS)))
    finally:
        conn.close()

    assert found == {
        "proj_mutex_lock": "proj_mutex_unlock",
        "bsp_sem_take": "bsp_sem_give",
    }, found

    ## AND A DECLARED PRIMITIVE GOES QUIET, or the hint nags forever about a solved problem.
    declared = load_lock_patterns({"locks": [{"name": "proj_mutex_lock", "form": "call"}]})
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        after = dict(detect_undeclared_lock_primitives(conn, declared))
    finally:
        conn.close()
    assert "proj_mutex_lock" not in after
    assert "bsp_sem_take" in after, "declaring one primitive must not silence the others"
