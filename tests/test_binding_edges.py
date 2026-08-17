# SPDX-License-Identifier: MIT
"""gh#1: a statically visible function-pointer BINDING must produce a call edge.

One rule, two instances, and a regression test for each in the language it occurs
in — because the two are broken by DIFFERENT mechanisms and a single test would
have let either half rot:

  * **C** — `int (*mutex_lock)(m *) = impl_lock;` at FILE SCOPE parses as a
    `declaration`/`init_declarator`. Layer 4's harvest only looked for an
    `assignment_expression`, so the row never existed; and the in-function form
    `mutex_lock = impl_lock;` DID get harvested but the fold then dropped it,
    because it only kept a row whose RHS named one of the enclosing function's
    PARAMETERS. Both halves are covered below.
  * **Python** — `sub.set_defaults(func=cmd_rubric)` hands a reference to
    argparse. No layer looking for a CALL to `cmd_rubric` finds one, so every
    argparse subcommand handler in this repo's own `acceptance/bench/` reported zero
    callers.

The GRADING test is the one a future refactor will silently break, so it is
explicit and it covers both languages: a binding is static but the call through it
is indirect, and both `mark_reachability` and the thread BFS traverse non-fuzzy
edges — grading one 'exact' would promote a weaker premise to fact.

Helpers are imported from the two sibling test modules that already own them
rather than respelled here; `tests/` is not a package but conftest puts rootdir on
`sys.path`, which is the same mechanism `conftest` itself uses for `richdb`.

@brief Tests for gh#1 binding-derived call edges (C + Python).
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_python_ast import _make_py_db, _parse
from test_r1_richness import _make_db

from clew.call_edges import _ast_harvest_calls, import_ast_call_edges
from clew.callback_edges import import_callback_registration_edges
from clew.harvest import try_import_tree_sitter
from clew.preprocessor import SOURCE_DECLARED, PreprocessorConfig

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the gh#1 binding tests need tree_sitter + its C/Python grammars",
)

## The Mbed-TLS shape: a file-scope function-pointer object initialised to a
## concrete implementation, then invoked indirectly from a second function.
_C_FILE_SCOPE = """\
int impl_lock(int *m) { return *m; }
int (*mutex_lock)(int *) = impl_lock;
void critical(void) { mutex_lock(0); }
"""

## The same binding written as an assignment inside a wiring function. Harvested
## before gh#1, then discarded by the fold for not naming a parameter.
_C_IN_FUNCTION = """\
int impl_lock(int *m) { return *m; }
int (*mutex_lock)(int *) = 0;
void wire(void) { mutex_lock = impl_lock; }
void critical(void) { mutex_lock(0); }
"""

## An ordinary scalar initialiser sharing a name with a function. The harvest
## accepts the row; nothing must turn it into an edge.
_C_SCALAR_CONTROL = """\
int impl_lock(int *m) { return *m; }
int not_a_pointer = impl_lock;
void critical(void) { return; }
"""

## A global carrying BOTH a parameter registration that dead-ends out of repo AND a
## direct binding to a name that is not an indexed function. The terminus must
## survive: a binding to a non-function is not a binding at all.
_C_TERMINUS_WITH_JUNK_BINDING = """\
static Cb_t my_cb = 0;
void register_cb(int x, Cb_t eventCb) {
    (void)x;
    my_cb = eventCb;
}
void invoke_cb(int e) {
    my_cb(e);
}
void app_layer(Cb_t appCb) {
    register_cb(0, appCb);
}
void reset_cb(void) {
    my_cb = some_extern_thing;
}
"""

_PY_ARGPARSE = """\
def cmd_rubric(args):
    return 0


def build_parser(sub):
    rubric = sub.add_parser("rubric")
    rubric.set_defaults(func=cmd_rubric)
    return rubric
"""


def _binding_edges(db: Path) -> list[tuple[str, str, str, str]]:
    """Every call edge as (caller name, callee name, source, confidence)."""
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT caller.name, callee.name, e.source, e.confidence "
        "FROM call_edges e "
        "JOIN memberdef caller ON caller.rowid = e.caller_rowid "
        "JOIN memberdef callee ON callee.rowid = e.callee_rowid",
    ).fetchall()
    conn.close()
    return rows


def _c_edges(tmp_path: Path, source: str, functions: list[tuple[int, str, int, int]]):
    """Parse one synthetic C file through Layer 4 and return its call edges."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(source)
    db = _make_db(tmp_path, functions, call_edges=[])
    import_callback_registration_edges(db, tmp_path)
    return _binding_edges(db)


# ─── instance 1: C ──────────────────────────────────────────────────────────


def test_c_file_scope_pointer_binding_produces_a_call_edge(tmp_path: Path) -> None:
    """The Mbed-TLS instance. `int (*mutex_lock)(int *) = impl_lock;` is a
    `declaration`, so before gh#1 the binding was never harvested at all and
    `critical`'s indirect call resolved to nothing."""
    edges = _c_edges(
        tmp_path,
        _C_FILE_SCOPE,
        [(1, "impl_lock", 1, 1), (2, "critical", 3, 3)],
    )
    assert ("critical", "impl_lock", "fnptr", "resolved") in edges


def test_c_in_function_direct_binding_produces_a_call_edge(tmp_path: Path) -> None:
    """The half that WAS harvested and then dropped by the fold: an assignment
    whose RHS names a function rather than one of `wire`'s own parameters."""
    edges = _c_edges(
        tmp_path,
        _C_IN_FUNCTION,
        [(1, "impl_lock", 1, 1), (2, "wire", 3, 3), (3, "critical", 4, 4)],
    )
    assert ("critical", "impl_lock", "fnptr", "resolved") in edges


def test_c_scalar_initialiser_does_not_fabricate_an_edge(tmp_path: Path) -> None:
    """The fail-closed control for harvesting EVERY `init_declarator` rather than
    only function-pointer ones. `int not_a_pointer = impl_lock;` is harvested, but
    nothing calls `not_a_pointer(...)`, so no edge may be written. This is what
    makes the deliberately type-blind harvest safe."""
    edges = _c_edges(
        tmp_path,
        _C_SCALAR_CONTROL,
        [(1, "impl_lock", 1, 1), (2, "critical", 3, 3)],
    )
    assert edges == []


def test_direct_binding_to_a_non_function_still_records_the_terminus(tmp_path: Path) -> None:
    """The guard that a mutation control proved NOTHING else pins: the whole suite
    passed with the `_is_known_function` filter deleted from the emission, because
    an unresolvable name produces no edge either way. What it silently destroys is
    the TERMINUS.

    `my_cb` is registered from `register_cb`'s parameter and that chain forwards out
    of repo, so it must be recorded as an `unresolved_callback` boundary. It is ALSO
    assigned `some_extern_thing`, which no indexed function bears. Unfiltered, that
    junk name makes `bound` non-empty, the `if not bound` branch is skipped, and the
    boundary row vanishes — a layer losing data while every test stays green."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(_C_TERMINUS_WITH_JUNK_BINDING)
    db = _make_db(
        tmp_path,
        [
            (1, "register_cb", 2, 5),
            (2, "invoke_cb", 6, 8),
            (3, "app_layer", 9, 11),
            (4, "reset_cb", 12, 14),
        ],
        call_edges=[],
    )
    import_callback_registration_edges(db, tmp_path)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT memberdef_rowid, global_name, kind FROM external_boundaries",
    ).fetchall()
    conn.close()
    assert rows == [(2, "my_cb", "unresolved_callback")]


# ─── instance 2: Python ─────────────────────────────────────────────────────


def test_python_keyword_argument_binding_is_harvested(tmp_path: Path) -> None:
    """`rubric.set_defaults(func=cmd_rubric)` must yield a harvested site for
    `cmd_rubric` tagged 'binding'. Before gh#1 the walk recorded only the
    `set_defaults` / `add_parser` callees and the bound reference vanished."""
    (tmp_path / "bench.py").write_text(_PY_ARGPARSE)
    tree, data = _parse(tmp_path, "bench.py")
    sites = {(s[0], s[2]) for s in _ast_harvest_calls(tree, data)}
    assert ("cmd_rubric", "binding") in sites


def test_python_keyword_argument_binding_lands_in_db(tmp_path: Path) -> None:
    """End-to-end, because the harvest alone proves nothing a consumer can read:
    `build_parser` must become a CALLER of `cmd_rubric` in `call_edges`."""
    (tmp_path / "bench.py").write_text(_PY_ARGPARSE)
    db = _make_py_db(tmp_path, root=tmp_path, rel="bench.py")
    import_ast_call_edges(db, tmp_path)
    edges = _binding_edges(db)
    assert ("build_parser", "cmd_rubric", "binding", "resolved") in edges


# ─── grading ────────────────────────────────────────────────────────────────


def test_python_binding_edge_is_resolved_and_never_exact(tmp_path: Path) -> None:
    """The test a future refactor will silently break. 'exact' is reserved for an
    edge doxygen itself observed; a binding is a static reference to an INDIRECT
    call, and both `mark_reachability` and the thread BFS traverse non-fuzzy
    edges, so calling it 'exact' would propagate a weaker premise as fact."""
    (tmp_path / "bench.py").write_text(_PY_ARGPARSE)
    db = _make_py_db(tmp_path, root=tmp_path, rel="bench.py")
    import_ast_call_edges(db, tmp_path)
    graded = [(callee, conf) for _c, callee, src, conf in _binding_edges(db) if src == "binding"]
    assert graded, "expected at least one binding edge to grade"
    assert all(conf == "resolved" for _callee, conf in graded)
    assert all(conf != "exact" for _callee, conf in graded)


def test_c_binding_edge_is_resolved_and_never_exact(tmp_path: Path) -> None:
    """Same grading rule on the C half, which reaches `call_edges` by a different
    route (Layer 4's bind-then-visit-call-sites) and so could regress alone."""
    edges = _c_edges(
        tmp_path,
        _C_FILE_SCOPE,
        [(1, "impl_lock", 1, 1), (2, "critical", 3, 3)],
    )
    graded = [conf for _caller, _callee, src, conf in edges if src == "fnptr"]
    assert graded, "expected at least one fnptr edge to grade"
    assert all(conf == "resolved" for conf in graded)
    assert all(conf != "exact" for conf in graded)


def test_binding_is_a_declared_call_source() -> None:
    """`vocabulary.py` is the single source for every enumerated value and for the
    DDL CHECK clauses built from them, so a producer writing 'binding' without it
    being declared there would fail the CHECK at insert time."""
    from clew.vocabulary import CALL_SOURCE, CALL_SOURCE_BINDING

    assert CALL_SOURCE_BINDING in CALL_SOURCE.values
    ## Ranked below `ast` (an OBSERVED call describes the pair better) and above
    ## `ast_member` (a binding names a bare identifier, never an unwrapped tail).
    assert CALL_SOURCE.rank["ast"] > CALL_SOURCE.rank[CALL_SOURCE_BINDING]
    assert CALL_SOURCE.rank[CALL_SOURCE_BINDING] > CALL_SOURCE.rank["ast_member"]


# ─── gh#35: a binding in mutually exclusive #if branches ────────────────────
#
# Mbed-TLS `library/threading.c`, reduced to its load-bearing shape. ONE pointer
# is bound twice, in two branches that cannot both exist in any build, and one of
# the two targets is a failure stub.
_C_TWO_BRANCHES = """\
int impl_pthread(int *m) { return *m; }
int impl_fail(int *m) { return -1; }
#if defined(THREADING_PTHREAD)
int (*mutex_lock)(int *) = impl_pthread;
#endif
#if defined(THREADING_ALT)
int (*mutex_lock)(int *) = impl_fail;
#endif
void critical(void) { mutex_lock(0); }
"""

_TWO_BRANCH_FUNCS = [
    (1, "impl_pthread", 1, 1),
    (2, "impl_fail", 2, 2),
    (3, "critical", 9, 9),
]

## The `#else` arm of a single guard — the other way to write two alternatives,
## and the one whose polarity a chain walk has to compose rather than overwrite.
_C_IF_ELSE = """\
int impl_pthread(int *m) { return *m; }
int impl_fail(int *m) { return -1; }
#if defined(THREADING_PTHREAD)
int (*mutex_lock)(int *) = impl_pthread;
#else
int (*mutex_lock)(int *) = impl_fail;
#endif
void critical(void) { mutex_lock(0); }
"""

_IF_ELSE_FUNCS = [
    (1, "impl_pthread", 1, 1),
    (2, "impl_fail", 2, 2),
    (3, "critical", 8, 8),
]


def _c_edges_with_config(tmp_path: Path, source: str, functions, macros):
    """Layer 4 over one synthetic C file with a DECLARED preprocessor config."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "foo.c").write_text(source)
    db = _make_db(tmp_path, functions, call_edges=[])
    config = (
        PreprocessorConfig(macros=tuple(f'"{m}"' for m in macros), source=SOURCE_DECLARED)
        if macros is not None
        else None
    )
    import_callback_registration_edges(db, tmp_path, None, config)
    return _binding_edges(db)


def test_a_branch_resolved_binding_emits_only_the_live_branchs_edge(tmp_path: Path) -> None:
    """gh#35's whole point. With `THREADING_PTHREAD` declared, `critical` reaches
    `impl_pthread` and MUST NOT reach `impl_fail` — the dead branch's binding does
    not exist in this build, and before gh#35 both were emitted at 'resolved', so
    the graph asserted a call to a failure stub as fact."""
    edges = _c_edges_with_config(
        tmp_path, _C_TWO_BRANCHES, _TWO_BRANCH_FUNCS, ["THREADING_PTHREAD"]
    )
    assert ("critical", "impl_pthread", "fnptr", "resolved") in edges
    assert not [e for e in edges if e[1] == "impl_fail"], "the dead branch must emit nothing"


def test_the_other_configuration_selects_the_other_branch(tmp_path: Path) -> None:
    """The control that shows the selection is READING the configuration rather
    than preferring the first binding it folded. Same source, other macro, opposite
    answer — and this is the direction that catches a rule accidentally hardcoded
    to whichever branch appears first in the file."""
    edges = _c_edges_with_config(tmp_path, _C_TWO_BRANCHES, _TWO_BRANCH_FUNCS, ["THREADING_ALT"])
    assert ("critical", "impl_fail", "fnptr", "resolved") in edges
    assert not [e for e in edges if e[1] == "impl_pthread"], "the dead branch must emit nothing"


def test_an_undeclared_branch_is_not_resolved(tmp_path: Path) -> None:
    """gh#35 requirement 2. With NO configuration declared, the pipeline cannot know
    which branch is live, so both edges may still be emitted — but neither may claim
    'resolved'. Both `mark_reachability` and the thread BFS traverse non-fuzzy edges,
    so a 'resolved' here propagates one of two mutually exclusive premises as fact.

    Both alternatives ARE still present: dropping them would trade an over-complete
    graph for an empty one, and the caller side of the dispatch was empty before
    gh#1 fixed exactly that."""
    edges = _c_edges_with_config(tmp_path, _C_TWO_BRANCHES, _TWO_BRANCH_FUNCS, None)
    through = {(callee, conf) for _caller, callee, src, conf in edges if src == "fnptr"}
    assert ("impl_pthread", "fuzzy") in through
    assert ("impl_fail", "fuzzy") in through
    assert not [c for c, conf in through if conf == "resolved"], (
        "an undecidable branch must never grade 'resolved'"
    )


def test_an_unconditional_binding_is_unaffected_by_branch_selection(tmp_path: Path) -> None:
    """THE REGRESSION CONTROL, and the one that matters most: gh#35 must change
    nothing for a binding that has no `#if` around it. A branch-free binding grades
    'resolved' with no configuration declared, exactly as it did before — otherwise
    the fix silently weakens every fnptr edge in every repository that declares no
    preprocessor configuration, which is most of them."""
    edges = _c_edges_with_config(
        tmp_path, _C_FILE_SCOPE, [(1, "impl_lock", 1, 1), (2, "critical", 3, 3)], None
    )
    assert ("critical", "impl_lock", "fnptr", "resolved") in edges


def test_an_else_arm_binding_is_selected_by_the_negated_guard(tmp_path: Path) -> None:
    """The `#else` spelling of the same alternation. A node in the else arm is a
    DESCENDANT of the `preproc_else`, which is a child of the `#if` it negates, so the
    chain walk has to flip the polarity of the guard it then reaches. Without that, an
    else-arm binding reads as sharing the `#if`'s own condition and BOTH branches
    select together — which looks exactly like the bug being fixed."""
    edges = _c_edges_with_config(tmp_path, _C_IF_ELSE, _IF_ELSE_FUNCS, ["THREADING_PTHREAD"])
    assert ("critical", "impl_pthread", "fnptr", "resolved") in edges
    assert not [e for e in edges if e[1] == "impl_fail"]

    other = _c_edges_with_config(tmp_path / "b", _C_IF_ELSE, _IF_ELSE_FUNCS, ["SOMETHING_ELSE"])
    assert ("critical", "impl_fail", "fnptr", "resolved") in other
    assert not [e for e in other if e[1] == "impl_pthread"]


def test_a_guard_the_evaluator_cannot_read_weakens_rather_than_drops(tmp_path: Path) -> None:
    """The fail-closed direction, stated as an edge outcome rather than as a unit
    verdict. `#if _POSIX_VERSION >= 200809L` is real `#if` grammar and outside a
    `defined`-only evaluator, and the binding under it must be WEAKENED, never
    dropped — dropping would delete the live edge of a binding we simply could not
    read, which is strictly worse than the over-complete graph gh#35 fixes."""
    source = """\
int impl_lock(int *m) { return *m; }
#if _POSIX_VERSION >= 200809L
int (*mutex_lock)(int *) = impl_lock;
#endif
void critical(void) { mutex_lock(0); }
"""
    edges = _c_edges_with_config(
        tmp_path, source, [(1, "impl_lock", 1, 1), (2, "critical", 5, 5)], ["THREADING_PTHREAD"]
    )
    assert ("critical", "impl_lock", "fnptr", "fuzzy") in edges
    assert ("critical", "impl_lock", "fnptr", "resolved") not in edges


def test_ifdef_and_ifndef_are_normalised_to_opposite_polarities(tmp_path: Path) -> None:
    """`#ifdef X` and `#ifndef X` are the SAME tree-sitter node type
    (`preproc_ifdef`) and differ only in the directive token, so the polarity has to
    be read off that token. Getting it backwards selects the wrong implementation
    while still emitting exactly one confident edge — the most dangerous possible
    outcome, because it looks like the fix working."""
    source = """\
int impl_a(int *m) { return *m; }
int impl_b(int *m) { return -1; }
#ifdef PICK_A
int (*mutex_lock)(int *) = impl_a;
#endif
#ifndef PICK_A
int (*mutex_lock)(int *) = impl_b;
#endif
void critical(void) { mutex_lock(0); }
"""
    funcs = [(1, "impl_a", 1, 1), (2, "impl_b", 2, 2), (3, "critical", 9, 9)]
    on = _c_edges_with_config(tmp_path / "on", source, funcs, ["PICK_A"])
    assert ("critical", "impl_a", "fnptr", "resolved") in on
    assert not [e for e in on if e[1] == "impl_b"], "#ifndef PICK_A is dead when PICK_A is set"

    off = _c_edges_with_config(tmp_path / "off", source, funcs, ["OTHER"])
    assert ("critical", "impl_b", "fnptr", "resolved") in off
    assert not [e for e in off if e[1] == "impl_a"], "#ifdef PICK_A is dead when PICK_A is unset"


# ─── gh#35 follow-up: selection must SELECT, never erase ─────────────────────
#
# The case a declared configuration reaches on a REAL target and no synthetic
# fixture reached before: the config names neither alternative, so every one of a
# global's bindings grades dead and the layer empties for that global.
#
# Measured on Mbed-TLS v3.6.7 with the 142 macros harvested from its own
# `include/mbedtls/mbedtls_config.h` — the configuration gh#17 exists to read.
# That header ships `MBEDTLS_THREADING_C` COMMENTED OUT, so neither
# `MBEDTLS_THREADING_PTHREAD` nor `MBEDTLS_THREADING_ALT` is declared and all 8
# bindings of the four `mbedtls_mutex_*` pointers were dropped:
#
#   no PREDEFINED           157 fnptr rows,   0 external boundaries
#   142-macro PREDEFINED      0 fnptr rows,   3 external boundaries
#
# 38 of those rows were the callers of `threading_mutex_lock_pthread`, which the
# gh#11 AST recovery still indexes as a function in the same build. So one build
# said "this code exists, reason about it" and "nothing can reach it" about the
# same `#if`.


def test_a_config_that_selects_no_branch_weakens_rather_than_erases(tmp_path: Path) -> None:
    """Branch selection is a SELECTION AMONG ALTERNATIVES, not an eraser. When a
    declared configuration eliminates EVERY binding of one global, nothing was
    selected — the configuration did not say which implementation is live, it said
    this variant binds none of them, while the index still carries every one of the
    bound functions. Emitting nothing there states a certainty the configuration
    never supplied, and it is the same fallback-to-False that
    `evaluate_condition` refuses one level down.

    So the global falls back to the undecided grading: every eliminated binding is
    restored at 'fuzzy', never 'resolved'. 'fuzzy' is skipped by both
    `mark_reachability` and the thread BFS, so nothing downstream reads a branch
    this build cannot compile as fact."""
    edges = _c_edges_with_config(
        tmp_path, _C_TWO_BRANCHES, _TWO_BRANCH_FUNCS, ["SOMETHING_UNRELATED"]
    )
    through = {(callee, conf) for _caller, callee, src, conf in edges if src == "fnptr"}
    assert ("impl_pthread", "fuzzy") in through, "an eliminated alternative must survive as fuzzy"
    assert ("impl_fail", "fuzzy") in through, "an eliminated alternative must survive as fuzzy"
    assert not [c for c, conf in through if conf == "resolved"], (
        "a configuration that selected nothing must not grade anything 'resolved'"
    )


def test_the_fallback_never_resurrects_a_losing_alternative(tmp_path: Path) -> None:
    """The negative half, and the one that would let the fix ship broken. The
    fallback must fire ONLY when selection left the global with nothing. A version
    keyed on "any binding was dropped" rather than on "every binding was dropped"
    passes the test above and silently undoes gh#35's whole result — `impl_fail`
    would come back at 'fuzzy' in the configuration that positively selects
    `impl_pthread`, which is the failure stub gh#35 exists to keep out of the
    graph.

    Written as its own test rather than trusted to the gh#35 tests above because
    those assert on `impl_fail` at 'resolved'; a resurrected FUZZY row would pass
    every one of them."""
    edges = _c_edges_with_config(
        tmp_path, _C_TWO_BRANCHES, _TWO_BRANCH_FUNCS, ["THREADING_PTHREAD"]
    )
    assert ("critical", "impl_pthread", "fnptr", "resolved") in edges
    assert not [e for e in edges if e[1] == "impl_fail"], (
        "a live alternative exists, so the dead one must still emit nothing — at any confidence"
    )


## The same all-dead alternation, plus the registration seam Mbed-TLS actually
## ships: `set_alt` forwards its parameter into the same global, and no in-repo
## caller supplies a concrete function. That registration IS a true out-of-repo
## terminus — an application provides the implementation — and it is what puts the
## global on the `if not bound` path on the real target.
_C_ALL_DEAD_WITH_REGISTRATION = """\
int impl_pthread(int *m) { return *m; }
int impl_fail(int *m) { return -1; }
#if defined(THREADING_PTHREAD)
int (*mutex_lock)(int *) = impl_pthread;
#endif
#if defined(THREADING_ALT)
int (*mutex_lock)(int *) = impl_fail;
#endif
void set_alt(int (*lock)(int *)) { mutex_lock = lock; }
void wire(int (*user_lock)(int *)) { set_alt(user_lock); }
void critical(void) { mutex_lock(0); }
"""

_ALL_DEAD_FUNCS = [
    (1, "impl_pthread", 1, 1),
    (2, "impl_fail", 2, 2),
    (3, "set_alt", 9, 9),
    (4, "wire", 10, 10),
    (5, "critical", 11, 11),
]


def test_the_fallback_does_not_cost_the_out_of_repo_terminus(tmp_path: Path) -> None:
    """The regression the fix could most easily cause, and the reason the fallback
    is applied AFTER the terminus is recorded rather than instead of it.

    On the real target the same three globals are BOTH bound behind a dead `#if`
    AND settable from outside through a forwarding registration. Both facts are
    true at once and a reader wants both: the terminus says an application supplies
    the implementation, the fuzzy edges say which implementations ship in this
    repository. A fallback that made `bound` non-empty BEFORE the `if not bound`
    test would silently delete the terminus — the layer would look repaired while
    quietly losing the 3 boundary rows the erasing build did produce."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "foo.c").write_text(_C_ALL_DEAD_WITH_REGISTRATION)
    db = _make_db(tmp_path, _ALL_DEAD_FUNCS, call_edges=[])
    config = PreprocessorConfig(macros=('"SOMETHING_UNRELATED"',), source=SOURCE_DECLARED)
    import_callback_registration_edges(db, tmp_path, None, config)

    conn = sqlite3.connect(str(db))
    boundaries = conn.execute("SELECT global_name FROM external_boundaries").fetchall()
    conn.close()
    assert ("mutex_lock",) in boundaries, (
        "the forwarded-parameter registration still dead-ends out of repo"
    )

    through = {
        (callee, conf) for _caller, callee, src_, conf in _binding_edges(db) if src_ == "fnptr"
    }
    assert ("impl_pthread", "fuzzy") in through
    assert ("impl_fail", "fuzzy") in through
