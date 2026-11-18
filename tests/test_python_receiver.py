# SPDX-License-Identifier: MIT
"""A Python method's receiver is its first parameter, whatever it is named (R5-CORE D1; 2.0.0).

FOUND BY THE 2.0.0 CORE AUDIT (agent C, vetted: pyast.py:81): `SELF_NAMES = ("self", "cls")` is
PEP 8 convention, not grammar. `def m(this)`, a metaclass's `mcs` or a `klass` receiver made
`this.helper()` a receiver-borne call the member-type map could not resolve, where `self.helper()`
names its class exactly. The tree states the receiver: a method's first parameter. A
`@staticmethod` has none.

@brief Tests receiver derivation for Python method calls.
@version 1
"""

from __future__ import annotations

import pytest

from clew.tsnode import Parser


def _scopes(source: str) -> dict[str, tuple[str, str]]:
    """@brief Each call's (qualifier, receiver), keyed by callee tail. @return Map."""
    from clew.pyast import harvest_calls

    tree = Parser("python").parse(source.encode())
    calls = harvest_calls(tree, source.encode(), "plain", "member", "binding")
    return {c[0]: (c[3], c[4]) for c in calls}


@pytest.mark.parametrize("receiver", ["self", "this", "mcs", "klass"])
def test_the_first_parameter_is_the_receiver(receiver: str) -> None:
    """@brief `<first param>.helper()` is qualified by the enclosing class."""
    src = f"class Foo:\n    def run({receiver}):\n        {receiver}.helper()\n"
    assert _scopes(src)["helper"] == ("Foo.helper", "")


def test_a_staticmethod_has_no_receiver() -> None:
    """@brief A staticmethod's first parameter is an ordinary argument."""
    src = "class Foo:\n    @staticmethod\n    def run(item):\n        item.helper()\n"
    assert _scopes(src)["helper"] == ("", "item")
