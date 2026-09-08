# SPDX-License-Identifier: MIT
"""gh#21 — Python call sites carried no receiver, so nothing about them resolved.

`pyast.harvest_calls` emitted `[name, line, source]`. The C path emits seven
elements, and `_fold_call_payload` reads the later indices defensively — so every
Python call silently supplied `qualified=""`, `receiver=""`. `_narrow_by_receiver`
requires a receiver, so it had **never fired on a Python repository**: every member
call reached the refusal path and produced no edge, however unambiguous it was.

MEASURED before this change — refusals carrying receiver evidence:

    clew (Python)   3367 refusals   100% blind
    entropic (C++)  8811 refusals    55% blind, 45% with a receiver

`self.foo()` is the commonest shape in the corpus and the one where the receiver's
class is not an inference at all — it IS the enclosing class. That case is emitted as
a QUALIFIER rather than a receiver, because a qualifier is the stronger evidence: it
names the class outright, so `_narrow_by_qualifier` can resolve it instead of merely
narrowing.

NO ARITY. The C path carries `argc` to separate overloads; Python has none, so
emitting it would cost a count per call site to break no tie. The payload stays five
elements and `_fold_call_payload` defaults arity to unknown.

@brief Tests for Python receiver and qualifier harvesting.
@version 1
"""

from __future__ import annotations

import pytest

from clew.call_edges import SOURCE_AST, SOURCE_AST_MEMBER, SOURCE_BINDING
from clew.harvest import _ast_parse_one_file, try_import_tree_sitter
from clew.pyast import harvest_calls

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the Python receiver tests need tree_sitter + the Python grammar",
)

_SOURCE = '''\
"""Module."""


class Engine:
    """An engine."""

    def run(self):
        """Calls a sibling method and a member's method."""
        self.prepare()
        self.cache.clear()
        other.dispatch()
        free_function()


class Other:
    """Another class with the same method name."""

    def prepare(self):
        """Same bare name, different class."""
        return None
'''


##
# @brief Parse the fixture the way the pipeline does.
# @param tmp_path Pytest temp dir.
# @return (tree, source bytes).
# @version 1
def _sites(tmp_path):
    """@brief Harvest the fixture's call sites."""
    Language, Parser = try_import_tree_sitter()
    path = tmp_path / "m.py"
    path.write_text(_SOURCE, encoding="utf-8")
    tree, src = _ast_parse_one_file("m.py", path, {}, Parser, Language)
    return {
        s[0]: s for s in harvest_calls(tree, src, SOURCE_AST, SOURCE_AST_MEMBER, SOURCE_BINDING)
    }


def test_a_self_call_carries_its_enclosing_class_as_a_qualifier(tmp_path) -> None:
    """`self.prepare()` names its class exactly — the enclosing one — so this is emitted as a
    QUALIFIER, not a receiver. That matters because the two take different paths:
    `_narrow_by_qualifier` RESOLVES a call whose class is written at the site, while
    `_narrow_by_receiver` only narrows and then still needs the class pinned.

    The fixture has a second `prepare` on another class precisely so a bare-tail match would
    be ambiguous and the qualifier has to be what separates them.
    """
    sites = _sites(tmp_path)
    assert "prepare" in sites, sorted(sites)
    assert sites["prepare"][3] == "Engine.prepare", (
        f"a self-call must name its enclosing class: {sites['prepare']}"
    )
    assert sites["prepare"][4] == "", "a self-call is a qualifier, not a receiver"


def test_a_member_call_carries_the_receivers_tail(tmp_path) -> None:
    """`self.cache.clear()` is the shape `_narrow_by_receiver` exists for: the receiver is
    `self.cache`, whose TAIL — `cache` — is the member variable whose declared type the index
    may hold. Taking the whole text or the root (`self`) would both resolve to the wrong
    thing, which is the same rule the C `_receiver_tail` records."""
    sites = _sites(tmp_path)
    assert "clear" in sites
    assert sites["clear"][4] == "cache", f"receiver tail should be `cache`: {sites['clear']}"
    assert sites["clear"][3] == "", "a member call names no class, so it carries no qualifier"


def test_a_plain_object_call_carries_that_object_as_the_receiver(tmp_path) -> None:
    """`other.dispatch()` — receiver is a bare name. It usually denotes a local or a
    parameter that doxygen does not index, which then fails to resolve later; that is the
    correct outcome and needs no special case here, exactly as on the C path."""
    sites = _sites(tmp_path)
    assert sites["dispatch"][4] == "other"


def test_a_free_call_carries_neither(tmp_path) -> None:
    """THE CONTROL. A bare `identifier` callee has no receiver and no qualifier, and marking
    one would send a free function down the member-resolution path where a unique name is
    NOT evidence — the distinction `_ast_record_call_edge` grades everything against."""
    sites = _sites(tmp_path)
    assert sites["free_function"][2] == SOURCE_AST
    assert sites["free_function"][3] == ""
    assert sites["free_function"][4] == ""


def test_the_payload_keeps_the_shape_the_folder_reads(tmp_path) -> None:
    """`_fold_call_payload` reads by INDEX and tolerates a short payload, so the element
    ORDER has to match the C path's — name, line, source, qualifier, receiver — or a Python
    site would supply its receiver where the folder expects a qualifier.

    Asserted as `>= 5` rather than `== 5` for the reason the C sibling gives: the payload is
    cached, so a shorter one from an older build must stay readable and pinning an exact
    arity would make this test the thing that breaks when it legitimately grows.
    """
    sites = _sites(tmp_path)
    assert all(len(s) >= 5 for s in sites.values())
    assert all(isinstance(s[3], str) and isinstance(s[4], str) for s in sites.values())
