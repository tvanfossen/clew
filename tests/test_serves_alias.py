# SPDX-License-Identifier: MIT
"""`serves:` is read as `satisfies:` everywhere (#72 item 13, 2.1).

#72 (an adopter, 2026-11-23): its sub-catalogues link upward with `serves: [REQ-…]`, while clew read
only `satisfies`, so every sub-repository would have had to rename the key. One reader takes both,
for the index, the wiki and the gate alike.

@brief Tests the serves alias.
@version 1
"""

from __future__ import annotations

from clew.requirements import link_ids


def test_serves_and_satisfies_are_one_link_list() -> None:
    """@brief Both keys read, in order, without duplicates; every spelling a catalogue uses."""
    assert link_ids({"serves": ["REQ-A-001"]}) == ["REQ-A-001"]
    assert link_ids(
        {"satisfies": "REQ-A-001, REQ-A-002", "serves": ["REQ-A-002", "REQ-B-001"]}
    ) == [
        "REQ-A-001",
        "REQ-A-002",
        "REQ-B-001",
    ]
    assert link_ids({"name": "x"}) == []


def test_the_gate_checks_a_serves_link() -> None:
    """@brief A `serves` id no catalogue holds is a broken edge, as for `satisfies`."""
    from clew.guard.checks import check_satisfies

    rows = {"REQ-L-001": {"serves": "REQ-P-999"}, "REQ-L-002": {"serves": "REQ-P-001"}}
    found = check_satisfies(rows, {"REQ-P-001", "REQ-L-001", "REQ-L-002"}, "requirements.yaml")
    assert len(found) == 1 and "REQ-P-999" in found[0].message


def test_the_wiki_tree_follows_a_serves_link(tmp_path) -> None:  # noqa: ANN001
    """@brief The composite tree hangs a `serves` requirement under its parent."""
    import importlib

    composite_tests = importlib.import_module("tests.test_wiki_composite")
    from clew.wiki.composite import compose

    product, pins = composite_tests._fixture(tmp_path)
    pins["lib"] = composite_tests._repo(
        tmp_path / "lib",
        "requirements:\n  REQ-LIB-001:\n    name: Bounded retry\n    serves: [product:REQ-PRD-001]\n",
    )
    tree = compose(
        product, "product", composite_tests._specs(product, pins), probe=composite_tests._no_index
    )
    assert "lib:REQ-LIB-001" in tree.nodes["product:REQ-PRD-001"].satisfied_by
