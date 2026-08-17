# SPDX-License-Identifier: MIT
"""The look-alike constructor that must never be mistaken for a thread spawn.

This exists because the real bug was real: clew's own
`clew/query/symbols.py` constructs a dataclass named `Thread`, and
`the downstream explorer app` vendors a second copy. A spawn pattern keyed on the bare tail
`Thread` fabricates a thread row at both sites — a number that reads as a
finding and is an artifact.

`Decoy` is deliberately shaped like `threading.Thread`: constructed with a
`target=` keyword whose value is a real function. Only the IMPORT distinguishes
it, which is why the detector resolves callees through the importing file's own
bindings.
"""

from __future__ import annotations

from collections.abc import Callable


## @brief A thread-shaped object that is not a thread.
## @version 1
class Decoy:
    """@brief Look-alike constructor taking a `target=` callable.

    @version 1
    """

    ## @brief Store the target without ever running it.
    ## @param target The callable handed in, kept unused.
    ## @version 1
    def __init__(self, target: Callable[[], None]) -> None:
        self.target = target
