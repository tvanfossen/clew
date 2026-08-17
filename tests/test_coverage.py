# SPDX-License-Identifier: MIT
"""Index-coverage detection (gh#6) — the defect case, and the benign case.

The benign-case tests matter at least as much as the alarming one. This project
has shipped a guard that fired on correct input, and CLAUDE.md records the
lesson: "a guard that fires on some of the real cases is worse than no guard",
because it converts "unchecked" into "checked and fine". Both real benign
targets are represented here as fixtures shaped like their measured values.

@brief Tests for index-coverage measurement, warning and persistence.
@version 1
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from clew.coverage import (
    MIN_SUBSTANTIVE_FILES,
    IndexCoverage,
    measure_index_coverage,
    report_index_coverage,
)

## Comfortably over MIN_SUBSTANTIVE_LINES so a fixture's line count is never the
## variable under test — the tests here are about YIELD, not about the line floor,
## which has its own test below.
BIG = 400


## @brief Build a synthetic index plus the source tree its paths refer to.
## @param tmp_path Directory to build the repo and database under.
## @param files Sequence of (repo-relative path, line count, symbols yielded).
## @param prose Repo-relative paths that yielded prose instead of symbols.
## @return (database path, repo root).
## @version 1
def _coverage_db(
    tmp_path: Path,
    files: list[tuple[str, int, int]],
    prose: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    """Writes REAL files with the requested line counts, because the measurement
    counts lines off disk — a fixture that only seeded the `path` table would
    measure zero substantive files and pass every assertion vacuously.

    Symbols are seeded via `bodyfile_id` for half and `file_id` for the rest, so
    the unioned attribution is exercised rather than assumed.

    @brief Seed a coverage fixture: source tree plus indexed database.
    @return Database path and repo root.
    @version 1
    """
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);"
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,"
        " file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER);"
        "CREATE VIRTUAL TABLE supplementary_docs USING fts5(file_path, heading, content);"
    )
    for index, (name, lines, symbols) in enumerate(files, start=1):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(f"line {n}" for n in range(lines)), encoding="utf-8")
        conn.execute("INSERT INTO path (rowid, type, name) VALUES (?, 1, ?)", (index, name))
        for slot in range(symbols):
            decl_side = slot % 2 == 0
            conn.execute(
                "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend)"
                " VALUES ('function', ?, ?, ?, 1, 9)",
                (
                    f"fn_{index}_{slot}",
                    index if decl_side else None,
                    index if not decl_side else None,
                ),
            )
    for name in prose:
        conn.execute(
            "INSERT INTO supplementary_docs (file_path, heading, content) VALUES (?, 'H', 'body')",
            (name,),
        )
    conn.commit()
    conn.close()
    return db_path, root


## @brief A file set where every file is substantial and fully indexed.
## @param count Number of files to describe.
## @param symbols Symbols each file yields.
## @return List of (path, lines, symbols) tuples.
## @version 1
def _healthy(count: int, symbols: int = 6) -> list[tuple[str, int, int]]:
    """@brief Describe `count` substantial, symbol-yielding implementation files.

    @return Fixture rows for _coverage_db.
    @version 1
    """
    return [(f"src/mod_{n}.c", BIG, symbols) for n in range(count)]


def test_a_mostly_barren_index_warns_and_names_the_largest_offenders(
    tmp_path: Path, caplog
) -> None:
    """THE CASE gh#6 EXISTS FOR, shaped like the measured mbedtls build.

    184 of 221 implementation files yielded at most one symbol, 162 of them over
    100 lines, including a 9,969-line file with zero — while the build announced
    2,555 functions and 28,151 call edges and said nothing. A 198-cell acceptance
    run was then executed against that index and voided, at roughly 318M tokens
    to discover after the fact.

    Asserts the ratio is the headline and that the offenders are NAMED with their
    line counts. Naming them is what makes the warning actionable rather than
    merely alarming: a 9,969-line file with zero symbols is a preprocessor problem
    someone can go and look at.

    @brief A high barren ratio warns and names the biggest barren files.
    @version 1
    """
    files = _healthy(6) + [(f"library/guarded_{n}.c", 500 + n, 0) for n in range(24)]
    files.append(("library/ssl_tls.c", 9969, 0))
    db_path, root = _coverage_db(tmp_path, files)

    with caplog.at_level(logging.WARNING):
        coverage = report_index_coverage(db_path, root)

    assert coverage.substantive_files == 31
    assert coverage.barren_files == 25
    assert coverage.alarming
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a mostly-barren index must warn"
    message = "\n".join(warnings)
    assert "80.6%" in message, message
    assert "library/ssl_tls.c" in message, message
    assert "9969 lines" in message, message


def test_the_benign_entropic_case_does_NOT_warn(tmp_path: Path, caplog) -> None:
    """THE FALSE-ALARM GUARD, and it is the reason the threshold is a ratio.

    entropic measures 7 barren of 177 substantive files (4.0%). Its barren files
    are Windows and Darwin platform sources inside a vendored fuzzer — genuinely
    inapplicable code, not a missing preprocessor definition. A check that fired
    here would be worse than no check at all: it converts "unchecked" into
    "checked and fine", which is how the identifier leak, the disarmed coverage
    gate and a voided 36-cell grid all happened.

    @brief A small legitimate barren residue must stay silent.
    @version 1
    """
    files = _healthy(170) + [
        (f"vendor/Fuzzer/FuzzerUtil{platform}.cpp", 200, 0)
        for platform in ("Windows", "Darwin", "Posix", "IOWindows", "Merge", "Main", "Extra")
    ]
    db_path, root = _coverage_db(tmp_path, files)

    with caplog.at_level(logging.WARNING):
        coverage = report_index_coverage(db_path, root)

    assert coverage.substantive_files == 177
    assert coverage.barren_files == 7
    assert round(coverage.barren_ratio, 3) == 0.04
    assert not coverage.alarming
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], (
        "entropic's inapplicable platform files are not a defect and must not warn"
    )


def test_a_header_that_only_DECLARES_is_not_barren(tmp_path: Path) -> None:
    """WHY THE METRIC IS SYMBOLS AND NOT BODIES, which is the whole reason it can
    be language-agnostic instead of an extension list.

    A real header declares: its declarations ARE memberdef rows, so it yields
    symbols while yielding no bodies. Counting bodies instead would report 85% of
    mbedtls's headers and 54% of entropic's as barren — measured, both benign.
    A guarded-out translation unit is distinguishable precisely because it yields
    NEITHER declarations nor bodies.

    @brief Declaration-only headers yield symbols and are not barren.
    @version 1
    """
    files = [(f"include/api_{n}.h", BIG, 5) for n in range(MIN_SUBSTANTIVE_FILES + 5)]
    db_path, root = _coverage_db(tmp_path, files)

    coverage = measure_index_coverage(db_path, root)

    assert coverage.barren_files == 0
    assert not coverage.alarming


def test_a_cpp_body_attributed_only_by_bodyfile_id_is_not_barren(tmp_path: Path) -> None:
    """THE DECL/DEF DUALITY, and a defect this test was written to catch.

    doxygen records a C++ method declared in a header and defined in a `.cpp` with
    `file_id` = the HEADER and `bodyfile_id` = the `.cpp`. Counting `file_id` alone
    therefore reports a fully-indexed translation unit as barren — measured on
    entropic, `src/mcp/server_manager.cpp` shows 1 row by `file_id` and 33 bodies
    by `bodyfile_id`. The first version of this probe reported 18 of 97 entropic
    `.cpp` files barren for exactly this reason; unioning the two attributions took
    it to 4.

    @brief A translation unit known only via bodyfile_id is not barren.
    @version 1
    """
    db_path, root = _coverage_db(tmp_path, [("src/unit.cpp", BIG, 0)])
    conn = sqlite3.connect(str(db_path))
    for slot in range(33):
        conn.execute(
            "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend)"
            " VALUES ('function', ?, NULL, 1, 1, 9)",
            (f"method_{slot}",),
        )
    conn.commit()
    conn.close()

    coverage = measure_index_coverage(db_path, root)

    assert coverage.barren_files == 0, "bodyfile_id-only attribution must count as a yield"


def test_a_prose_file_is_not_counted_as_barren(tmp_path: Path) -> None:
    """A markdown file is not barren; it is not code.

    Measured on mbedtls: 27 substantive `.md` files yield zero memberdef rows, and
    counting them inflated the headline ratio for a reason that has nothing to do
    with the preprocessor. They contributed PROSE, which is a yield.

    @brief Files that yielded prose are excluded from the barren count.
    @version 1
    """
    docs = [(f"docs/guide_{n}.md", BIG, 0) for n in range(MIN_SUBSTANTIVE_FILES + 5)]
    db_path, root = _coverage_db(tmp_path, docs, prose=tuple(name for name, _, _ in docs))

    coverage = measure_index_coverage(db_path, root)

    assert coverage.indexed_files == 0, "prose-yielding files are not code and are excluded"
    assert coverage.barren_files == 0
    assert not coverage.alarming


def test_markdown_that_yielded_no_prose_is_still_not_barren(tmp_path: Path) -> None:
    """`supplementary_docs` membership is a PROXY for "this file is prose", and it
    holds only while every indexed markdown file is also ingested. Ingestion has its
    own file set, so a wide INPUT indexes markdown that never reaches it — measured on
    this repo's own whole-repo index, where 894 `.md` files took `barren_ratio` from
    0.015 to 0.795 and tripped `alarming` on a build whose code coverage had not moved.

    The rule this module states is about the FILE, not about the ingestion: a markdown
    file is not barren, it is not code.

    @brief Markdown absent from supplementary_docs is excluded from the barren count.
    @version 1
    """
    docs = [(f"evidence/cell_{n}.md", BIG, 0) for n in range(MIN_SUBSTANTIVE_FILES + 5)]
    db_path, root = _coverage_db(tmp_path, docs, prose=())

    coverage = measure_index_coverage(db_path, root)

    assert coverage.indexed_files == 0, "markdown is not code, ingested or not"
    assert coverage.barren_files == 0
    assert not coverage.alarming


def test_a_small_barren_file_is_below_the_line_floor(tmp_path: Path) -> None:
    """A stub header or a re-export `__init__.py` yielding nothing proves nothing.

    This repo's own single offender is `clew/query/__init__.py` — 137 lines
    of re-exports, 1 symbol — and the line floor is what keeps entropic's residue
    at 4 files rather than 32.

    @brief Files under the line floor are not judged.
    @version 1
    """
    files = _healthy(MIN_SUBSTANTIVE_FILES) + [(f"src/stub_{n}.h", 10, 0) for n in range(40)]
    db_path, root = _coverage_db(tmp_path, files)

    coverage = measure_index_coverage(db_path, root)

    assert coverage.substantive_files == MIN_SUBSTANTIVE_FILES
    assert coverage.barren_files == 0
    assert not coverage.alarming


def test_a_tiny_index_never_alarms_however_barren(tmp_path: Path) -> None:
    """A ratio needs a denominator worth dividing by: two files, one barren, is
    50% and means nothing. Every real target measures 116 substantive files or
    more, so the floor cannot mask a real case.

    @brief Below the sample floor the ratio is not a measurement.
    @version 1
    """
    db_path, root = _coverage_db(tmp_path, [("src/a.c", BIG, 0), ("src/b.c", BIG, 6)])

    coverage = measure_index_coverage(db_path, root)

    assert coverage.barren_ratio == 0.5
    assert not coverage.alarming, "a two-file index is not evidence of anything"


def test_an_unreadable_database_fails_soft(tmp_path: Path) -> None:
    """Coverage describes a build that has ALREADY SUCCEEDED, so a measurement that
    raises must not destroy the index it describes. An all-zero measurement is also
    what `alarming` correctly reads as "not enough sample", so failing soft cannot
    manufacture an alarm either.

    @brief An unreadable index measures to all-zero and does not alarm.
    @version 1
    """
    missing = tmp_path / "nope.db"

    coverage = measure_index_coverage(missing, tmp_path)

    assert coverage == IndexCoverage(0, 0, 0, ())
    assert not coverage.alarming


def test_coverage_is_persisted_into_build_meta_and_reaches_status(tmp_path: Path) -> None:
    """gh#6 part 2. A coverage number that lives only in a build warning has exactly
    the defect CLAUDE.md records for scope provenance: the pipeline computed it into
    the build LOG, which is gone by the time anyone queries the database.

    `status` was the surface that reported the voided index as present, current and
    healthy. Staleness answers "does this describe the code as it is now"; coverage
    answers "does it describe the code at all".

    Asserts a measured ZERO survives too — `write_build_signature` drops falsy
    values, so coverage passes strings deliberately, and a build with no barren
    files must still record `barren_files=0` rather than omitting it.

    @brief Coverage round-trips through build_meta into db_status.
    @version 1
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db_path, root = _coverage_db(tmp_path, _healthy(MIN_SUBSTANTIVE_FILES + 4))
    coverage = measure_index_coverage(db_path, root)
    write_build_signature(db_path, coverage=coverage.as_meta())

    status = db_status(Target(repo_path=str(root), slug="t", db_path=str(db_path)))
    reported = status["coverage"]

    assert reported["substantive_files"] == str(MIN_SUBSTANTIVE_FILES + 4)
    assert reported["barren_files"] == "0", "a measured zero must be recorded, not omitted"
    assert reported["barren_ratio"] == "0.000"


def test_status_publishes_the_barren_ratio_and_offenders(tmp_path: Path) -> None:
    """The consumer-facing half: a thin index must be visible to an agent that never
    saw the build log, WITH the offenders, so `status` alone is enough to refuse an
    expensive run against a hollow index.

    @brief status carries the ratio and the largest offenders.
    @version 1
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    files = _healthy(6) + [(f"library/guarded_{n}.c", 500, 0) for n in range(25)]
    db_path, root = _coverage_db(tmp_path, files)
    coverage = measure_index_coverage(db_path, root)
    write_build_signature(db_path, coverage=coverage.as_meta())

    status = db_status(Target(repo_path=str(root), slug="t", db_path=str(db_path)))
    reported = status["coverage"]

    assert reported["barren_ratio"] == "0.806"
    assert "library/guarded_" in reported["largest_barren"]


def test_status_on_a_PRE_COVERAGE_index_says_nothing_rather_than_guessing(tmp_path: Path) -> None:
    """An index built before build 18 cannot supply these fields, and an absent key
    honestly reads as "not recorded". Fabricating a healthy-looking default would be
    the same class of defect as the whole issue: a number that looks like a
    measurement and is not.

    @brief A pre-coverage index reports an empty coverage mapping.
    @version 1
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    write_build_signature(db)

    status = db_status(Target(repo_path=str(tmp_path), slug="t", db_path=str(db)))

    assert status["coverage"] == {}


def test_total_absence_reports_once_not_twice(tmp_path: Path, caplog) -> None:
    """The two terms COMPOSE rather than compete. A build that extracted literally
    nothing satisfies both the total-absence check and the barren-ratio check, and
    must produce ONE precise message — the one that names PREDEFINED — instead of
    two overlapping ones that train the reader to skim.

    @brief A zero-body index warns once, via the more actionable term.
    @version 1
    """
    files = [(f"src/mod_{n}.c", BIG, 0) for n in range(MIN_SUBSTANTIVE_FILES + 5)]
    db_path, root = _coverage_db(tmp_path, files)

    with caplog.at_level(logging.WARNING):
        report_index_coverage(db_path, root)

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1, warnings
    assert "NOT ONE yielded a function body" in warnings[0]
