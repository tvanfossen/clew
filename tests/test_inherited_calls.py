# SPDX-License-Identifier: MIT
"""A call through `self` / `this` to an INHERITED method resolves to the base that defines it.

Found on TypeScript mixins. The qualified match looked only at the calling class, so `this.m()`
where `m` lives on a base failed closed. It bites where clew resolves calls itself — JS/TS, which
doxygen does not read. An end-to-end Python case was written and PASSED WITHOUT THE FIX, because
doxygen's own cross-references already resolve `self.helper()`; a test that cannot fail was
removed rather than kept, and the TypeScript case in tests/test_ts_mixins.py carries the
end-to-end proof. The fix walks DECLARED bases, nearest first, and refuses a tie.

@brief Tests for inherited-method resolution through declared bases.
@version 1
"""

from __future__ import annotations

from clew.call_edges import _inherited


## @brief The nearest base wins, and a same-distance tie refuses.
## @return None.
## @version 1
def test_nearest_base_wins_and_a_tie_refuses() -> None:
    """@brief Breadth-first over declared bases.
    @return None.
    @version 1
    """
    definition_of = {1: "m.Base.run", 2: "m.Grand.run", 3: "m.Left.go", 4: "m.Right.go"}
    bases_of = {"Child": {"Base"}, "Base": {"Grand"}, "Diamond": {"Left", "Right"}}
    assert _inherited("Child.run", [1, 2], definition_of, bases_of) == [1]
    assert _inherited("Diamond.go", [3, 4], definition_of, bases_of) == [], "a tie must refuse"
    assert _inherited("Unknown.run", [1, 2], definition_of, bases_of) == []
