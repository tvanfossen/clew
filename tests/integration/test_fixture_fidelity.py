# SPDX-License-Identifier: MIT
"""The reason this tier exists: prove the synthetic fixture still matches reality.

71 tests were converted from building `sample/` with real doxygen to reading a
hand-built `rich_db`. That trade is only sound while the fixture's schema is the
schema the extractors actually emit. **Without this file the conversion is a net
LOSS of safety**, because a fixture can rot away from the pipeline silently and
every converted test keeps passing — they assert over the fixture, so the fixture
is what defines "correct" for them. Nothing else in the suite compares it to a
real build.

Two properties, and they fail for different reasons:

  * **The table set.** A table the fixture lacks is a table no converted test can
    exercise. `search_prose` over an absent `supplementary_docs`, `lookup_class`
    over an absent `reimplements` — the query returns empty, the test asserts
    empty, and it looks like a passing test of a working feature.
  * **The `CHECK(col IN (...))` map.** This is the vocabulary the shipped schema
    enforces. If the fixture's CHECKs are looser, a converted test can insert a
    value a real database would REJECT and then assert the query layer handles
    it — a test of behaviour that can never occur. If they are tighter, the
    fixture cannot represent data a real build produces.

Compared against `self_index_db` rather than the cloned target, deliberately: the
table set and the CHECK map are properties of the PIPELINE, not of what it is
pointed at (verified — a Python-only synthesized-Doxyfile build of an external
repo and a build of this checkout emit the identical 33 tables and the identical
27-entry CHECK map). Using our own index makes the single most important test in
the tier network-free, so it can be a required CI job with no tolerated failures.

`parse_checks` is reused from `tests/schema_snapshot.py`, which already backs
the committed golden snapshot in `tests/test_vocabulary.py`. A second CHECK
parser would be a second thing to be wrong.

@brief Assert the synthetic rich_db fixture matches a real build's schema.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from schema_snapshot import parse_checks

pytestmark = pytest.mark.integration

## Tables SQLite creates on its own behalf, which no fixture author controls:
## `sqlite_sequence` appears the moment an AUTOINCREMENT table takes a row, and
## `sqlite_stat*` appear after ANALYZE. Excluded by prefix rather than by name so
## a future internal table does not turn into a spurious failure.
_INTERNAL_PREFIX = "sqlite_"


## @brief Every non-internal table name in a database.
## @param db Database to inspect.
## @return Set of table names, SQLite-internal tables excluded.
## @version 1
def _tables(db: Path) -> set[str]:
    """FTS5 shadow tables (`supplementary_docs_data`, `_idx`, `_docsize`,
    `_content`, `_config`) are deliberately NOT excluded: they come free with the
    one `CREATE VIRTUAL TABLE` the pipeline issues, so their absence means the
    fixture never created the virtual table — exactly the kind of gap this test
    is for.

    @brief Read a database's table set.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return {
            name
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not name.startswith(_INTERNAL_PREFIX)
        }
    finally:
        conn.close()


## @brief Describe a two-way set difference in a message someone can act on.
## @param real Values the real build has.
## @param fixture Values the fixture has.
## @param noun What the values are, for the message text.
## @return A multi-line report, or "" when the sets are equal.
## @version 1
def _set_diff(real: set[str], fixture: set[str], noun: str) -> str:
    """Names BOTH directions separately, because they call for opposite fixes:
    missing means "add it to the fixture", extra means "the fixture invents
    something the pipeline does not ship, so the tests built on it are fiction".

    @brief Render an actionable set-difference report.
    @version 1
    """
    missing = sorted(real - fixture)
    extra = sorted(fixture - real)
    lines = []
    if missing:
        lines.append(f"rich_db is MISSING {len(missing)} {noun} a real build emits: {missing}")
    if extra:
        lines.append(f"rich_db INVENTS {len(extra)} {noun} no real build emits: {extra}")
    return "\n".join(lines)


## @brief rich_db must carry exactly the tables a real build emits.
## @param rich_db The synthetic session fixture from tests/conftest.py.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_rich_db_table_set_matches_a_real_build(rich_db: Path, self_index_db: Path) -> None:
    """Exact equality, both directions. A missing table silently turns every
    converted test that queries it into a test of an empty result; an invented
    one turns a converted test into a test of a schema that does not ship.

    @brief Fixture table set equals real build table set.
    @version 1
    """
    report = _set_diff(_tables(self_index_db), _tables(rich_db), "table(s)")
    assert report == "", report


## @brief rich_db must enforce exactly the vocabulary a real build enforces.
## @param rich_db The synthetic session fixture from tests/conftest.py.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_rich_db_check_constraints_match_a_real_build(rich_db: Path, self_index_db: Path) -> None:
    """The load-bearing half. A looser fixture CHECK lets a converted test insert
    a value the shipped schema REJECTS and then assert the query layer copes with
    it — a green test for a state that cannot exist. A tighter one makes the
    fixture unable to represent real data.

    Both the constrained-column SET and the allowed VALUES per column are
    compared, because widening one vocabulary in the fixture is exactly as
    invisible as omitting a whole CHECK.

    @brief Fixture CHECK map equals real build CHECK map.
    @version 1
    """
    real = parse_checks(self_index_db)
    fixture = parse_checks(rich_db)

    problems = [_set_diff(set(real), set(fixture), "CHECK-constrained column(s)")]
    problems += [
        f"{column}: real build allows {real[column]}, rich_db allows {fixture[column]}"
        for column in sorted(set(real) & set(fixture))
        if real[column] != fixture[column]
    ]
    report = "\n".join(line for line in problems if line)
    assert report == "", report
