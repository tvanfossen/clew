# SPDX-License-Identifier: MIT
"""Dump the generated CHECK clauses for every registered column.

Exists to be run as a SUBPROCESS under a chosen PYTHONHASHSEED, which is the
only way to prove the emitted schema text does not vary between interpreter
runs. That property is not free: `threads._VALID_KINDS` used to be a `set`, and
a set's iteration order is not part of any contract — generating from one would
have made the shipped DDL differ build to build for no reason a reader could see.

Also useful by hand: `.venv/bin/python tests/vocab_dump.py` prints exactly what
the CREATE TABLE statements splice in.

@brief Print every registered column's generated CHECK clause, in order.
@version 2
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clew.vocabulary import (
    BOOL_COLUMNS,
    COLUMNS,
    bool_check,
    check,
)


## @brief Print one line per registered column: "table.column<TAB>clause".
## @return Process exit status (always 0).
## @version 1
def main() -> int:
    """Sorted by (table, column) so two runs are diffable regardless of dict
    construction order; the clause itself carries the vocabulary's own ORDER,
    which is the thing under test.

    @brief Emit the generated CHECK clause for every registered column.
    @version 1
    """
    for table, column in sorted(COLUMNS):
        print(f"{table}.{column}\t{check(table, column)}")
    for table, column in sorted(BOOL_COLUMNS):
        print(f"{table}.{column}\t{bool_check(column)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
