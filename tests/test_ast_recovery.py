# SPDX-License-Identifier: MIT
"""C++ AST recovery: header grammar disambiguation (#50) + callee unwrapping (#48).

Both defects starved the same layer. `.h` was routed unconditionally to the C
grammar, which does not merely fail on a C++ header but FABRICATES structure;
and a call's callee had to be a bare `identifier`, which discarded every C++
member, qualified and template call — 66.7% of a C++ codebase's call sites.

@brief Tests for the C++ AST recovery fixes.
@version 1
"""

from __future__ import annotations

import pytest

from clew.call_edges import (
    SOURCE_AST,
    SOURCE_AST_MEMBER,
    _ast_harvest_calls,
)
from clew.harvest import _ast_parse_one_file, try_import_tree_sitter

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the AST recovery tests need tree_sitter + its C/C++ grammars",
)

_CPP_HEADER = """\
#pragma once
namespace demo {
class Widget {
 public:
  void tick();
 private:
  mutable std::mutex mutex_;
};
template <typename T>
T clamp(T v, T lo, T hi) { return v < lo ? lo : v > hi ? hi : v; }
}  // namespace demo
"""

_C_HEADER = """\
#ifndef DEMO_H
#define DEMO_H
struct point { int x; int y; };
int demo_add(int a, int b);
#endif
"""

_CALL_SITES = """\
#include "w.hpp"
namespace demo {
void Widget::tick() {
  free_fn();                 // identifier          -> ast
  obj.method();              // field_expression    -> ast_member
  ptr->other();              // field_expression    -> ast_member
  demo::Helper::run();       // qualified_identifier-> ast_member
  make<int>();               // template_function   -> ast_member
  (*fnptr)();                // no static name      -> dropped
}
}  // namespace demo
"""


## @brief Parse a source string through the real harvest path.
## @param tmp_path Pytest temp dir.
## @param name File name (its extension drives grammar selection).
## @param text Source text.
## @return (tree, src_bytes) from _ast_parse_one_file.
## @version 1
def _parse(tmp_path, name: str, text: str):
    """@brief Write a source file and parse it exactly as the pipeline does."""
    Language, Parser = try_import_tree_sitter()
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return _ast_parse_one_file(name, path, {}, Parser, Language)


## @brief Count ERROR/MISSING nodes in a tree.
## @param root Root node.
## @return Number of parse errors.
## @version 1
def _errors(root) -> int:
    """@brief Total ERROR/MISSING nodes."""
    n, stack = 0, [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            n += 1
        stack.extend(node.children)
    return n


def test_cpp_header_named_dot_h_reparses_as_cpp(tmp_path) -> None:
    """#50: `.h` went to the C grammar unconditionally. On a C++ header that
    yields 7 ERROR/MISSING nodes AND reports TWO function definitions where one
    exists — fabricated structure, which is worse than missing structure. Any
    C++ project following the Google style guide names its headers `.h`."""
    parsed = _parse(tmp_path, "widget.h", _CPP_HEADER)
    assert parsed is not None
    tree, _ = parsed
    assert _errors(tree.root_node) == 0, "a C++ header must not be parsed as C"


def test_plain_c_header_is_unaffected(tmp_path) -> None:
    """A genuine C header parses cleanly as C, so it never reaches the retry —
    the fix costs nothing for C repos (IoT drops 0.2% of call sites, not 66%)."""
    parsed = _parse(tmp_path, "demo.h", _C_HEADER)
    assert parsed is not None
    tree, _ = parsed
    assert _errors(tree.root_node) == 0


def test_member_qualified_and_template_callees_are_recovered(tmp_path) -> None:
    """#48: requiring a bare `identifier` callee discarded every C++ member,
    qualified and template call. Each is now unwrapped to the unqualified tail
    that `memberdef.name` actually stores."""
    parsed = _parse(tmp_path, "w.cpp", _CALL_SITES)
    assert parsed is not None
    tree, src = parsed
    sites = _ast_harvest_calls(tree, src)
    found = {site[0]: site[2] for site in sites}

    assert found.get("free_fn") == SOURCE_AST
    for name in ("method", "other", "run", "make"):
        assert found.get(name) == SOURCE_AST_MEMBER, f"{name} should be recovered"


def test_callee_without_a_static_name_is_still_refused(tmp_path) -> None:
    """A call through a function POINTER has no static callee name and belongs
    to the fnptr layer. Unwrapping must not invent one — fail closed."""
    parsed = _parse(tmp_path, "w.cpp", _CALL_SITES)
    assert parsed is not None
    tree, src = parsed
    names = {site[0] for site in _ast_harvest_calls(tree, src)}
    assert "fnptr" not in names


def test_harvested_sites_carry_provenance(tmp_path) -> None:
    """Provenance rides on each site so an unwrapped member call is separable
    from a confirmed free-function call downstream — the two have very
    different reliability and must not be merged into one `ast` bucket."""
    parsed = _parse(tmp_path, "w.cpp", _CALL_SITES)
    assert parsed is not None
    tree, src = parsed
    sites = _ast_harvest_calls(tree, src)
    assert sites, "expected call sites"
    ## Arity is 4 since #75 (the trailing element is the qualified callee text), and the
    ## assertion is >= 3 rather than == 4 for the same reason `_fold_call_payload` reads
    ## `site[2] if len(site) > 2`: the payload is CACHED, so a shorter one from an older
    ## build must stay readable. Pinning an exact arity would make this test the thing that
    ## breaks when the payload legitimately grows.
    assert all(len(s) >= 3 for s in sites)
    assert {s[2] for s in sites} <= {SOURCE_AST, SOURCE_AST_MEMBER}


def test_a_qualified_call_site_resolves_instead_of_fanning_out() -> None:
    """#75's resolve half. `Ns::Class::method()` writes the class AT the call site, and
    `_callee_name_node` peeled it off to match `memberdef.name` — discarding the one piece
    of evidence that could say WHICH `method`. Measured on the public entropic index: 2,301
    of 10,723 member-ish call sites (21%) are qualified.

    Narrowing uses `query._common._qualified_match`, the SAME boundary-checked comparison
    `rowids_for_name` relies on, rather than a second matcher that could drift."""
    from clew.call_edges import _ast_record_call_edge

    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    _ast_record_call_edge(
        1,
        "poll",
        {"poll": [10, 11, 12]},
        resolved,
        fuzzy,
        "ast_member",
        qualified="net::Socket::poll",
        definition_of={
            10: "int net::Socket::poll(int)",
            11: "int ui::Widget::poll()",
            12: "void sched::Loop::poll()",
        },
    )
    assert resolved == [(1, 10, "ast_member")], "the qualified match must resolve to ONE"
    assert fuzzy == [], "and must not also fan out"


def test_a_qualified_name_matching_nothing_emits_NOTHING() -> None:
    """THE GUARD, and the reason it matters. When the call site names a class explicitly and
    no indexed function bears it, the callee is OUTSIDE the index — a stdlib or vendored
    type. Emitting nothing is what an unknown free function already does.

    Falling back to the unqualified fan-out here would reintroduce exactly the fabrication
    `fd384e5` removed, but WORSE: with the call site's own evidence contradicting it.
    Measured on entropic: 690 edges are removed by this path."""
    from clew.call_edges import _ast_record_call_edge

    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    _ast_record_call_edge(
        1,
        "size",
        {"size": [20, 21]},
        resolved,
        fuzzy,
        "ast_member",
        qualified="std::vector::size",
        definition_of={20: "int app::Buf::size()", 21: "int app::Ring::size()"},
    )
    assert resolved == [] and fuzzy == [], (
        "a qualified name matching nothing indexed must emit NOTHING, never fall back"
    )


def test_a_qualifier_matching_several_records_NOTHING() -> None:
    """Narrowing is not a promise of uniqueness. A qualified name that still matches more than
    one indexed signature (decl/def duality, or a genuine overload set on one class) is
    UNRESOLVED, and an unresolved call records nothing (gh#347).

    THIS TEST'S INTENT IS UNCHANGED AND ITS ASSERTION IS INVERTED. It always guarded against
    picking one candidate arbitrarily; it used to satisfy that by emitting ALL of them, which
    the owner retired: one true observation must not become N assertions, because a NAME is a
    mutable human convention and proves no linkage. Emitting nothing guards the same thing
    strictly rather than loudly.

    The narrowing itself still matters and is still asserted — by the sibling test where a
    qualifier narrows to exactly ONE and earns `resolved`. Here the point is that narrowing to
    TWO is not partial credit."""
    from clew.call_edges import _ast_record_call_edge

    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    _ast_record_call_edge(
        1,
        "send",
        {"send": [30, 31, 32]},
        resolved,
        fuzzy,
        "ast_member",
        qualified="net::Socket::send",
        definition_of={
            30: "int net::Socket::send(const char *)",
            31: "int net::Socket::send(int)",
            32: "int ui::Form::send()",
        },
    )
    assert resolved == [], "two candidates is not one; nothing is resolved"
    assert fuzzy == [], (
        "narrowed to the class and STILL ambiguous, so the call is unresolved and records "
        "nothing — emitting one row per candidate asserted two calls where one occurred"
    )


def test_a_RELATIVE_qualifier_still_resolves() -> None:
    """C++ lets a call site qualify relative to its enclosing namespace: inside
    `namespace entropic`, `mcp::sanitize_utf8()` names `entropic::mcp::sanitize_utf8`. On the
    public entropic index this is not a corner case — 92 of 662 matchable qualified sites take
    the relative form, including `detail::parse_range_header` (19) and `mcp::sanitize_utf8` (12).

    It works only because `_common._IDENT_CHARS` omits ':', so the character before the match
    is a boundary. That is an IMPLICIT dependency: adding ':' to that set to tighten some other
    comparison would silently delete these edges via the fail-closed path, which is the worst
    shape of regression — fewer edges, no error. An audit probe that spelled the boundary rule
    out by hand got exactly this wrong and reported 92 false deletions that did not exist.
    """
    from clew.call_edges import _ast_record_call_edge

    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    _ast_record_call_edge(
        1,
        "sanitize_utf8",
        {"sanitize_utf8": [40, 41]},
        resolved,
        fuzzy,
        "ast_member",
        qualified="mcp::sanitize_utf8",
        definition_of={
            40: "std::string entropic::mcp::sanitize_utf8(const std::string &)",
            41: "std::string other::text::sanitize_utf8(const char *)",
        },
    )
    assert resolved == [(1, 40, "ast_member")], (
        "a relative qualifier must resolve through the enclosing namespace"
    )
    assert fuzzy == []


def test_a_relative_qualifier_does_not_match_a_LONGER_identifier() -> None:
    """The boundary rule's real job. `Owner::run` must not match `CoOwner::run` — the ':'
    tolerance that enables relative lookup must not extend to a partial identifier, or the
    resolution would be worse than the fan-out it replaces: confidently wrong instead of
    honestly ambiguous."""
    from clew.call_edges import _ast_record_call_edge

    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    _ast_record_call_edge(
        1,
        "run",
        {"run": [50]},
        resolved,
        fuzzy,
        "ast_member",
        qualified="Owner::run",
        definition_of={50: "void net::CoOwner::run()"},
    )
    assert resolved == [] and fuzzy == [], "CoOwner::run must NOT satisfy Owner::run"
