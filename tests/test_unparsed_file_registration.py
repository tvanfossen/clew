# SPDX-License-Identifier: MIT
"""A FILE THE INDEX CANNOT PARSE IS STILL A FILE IT CAN NAME (C5, plan step 7).

mbedtls Q4 is the lowest-scoring cluster on the 1.1.0 grid at −40.00 pt, and the plan's own
analysis of it is that it is NOT a Perl question:

    "library/error.c IS GENERATED — the file carries no banner saying so, so an answer that
     reads it top to bottom will describe a hand-written lookup table and be wrong."

Seven of its eight marks are `type: conclusion` about build provenance. The eighth is a `set`
mark that wants `scripts/generate_errors.pl` as **a name in a list**. No Perl parser is needed
to put a name in a list.

`synth.claims()` gates `register_paths`, so a file type nothing claims gets NO `path` row and
clew cannot report that the file exists at all. Counted on the frozen mbedtls checkout — 948
files — the 6 `.pl` files and 8 `Makefile`s are invisible to every surface the index has.

THE TREATMENT ALREADY EXISTS AND IS ALREADY DOCUMENTED, in `synth.py`'s own words about YAML:

    "REGISTERED AND NEVER HARVESTED: present in the file set, findable by name, named by the
     not-indexed report, and contributing nothing to the namespace."

C5 extends that to source types with no grammar. This is `absence is not emptiness` applied to
the file set: *"I know this file exists and I cannot read it"* beats silence.

**`found = 0`, NOT `found = 1`, AND THAT IS THE WHOLE DESIGN.** doxygen's own `path.found`
already means "resolved to content", C1's `_was_harvested` already reads it, and
`FileSubject.harvested` already surfaces it. So the honest statement needs no new column and no
new model field — it needs the right value in a column that has meant this since doxygen wrote
it. A registered file with `found = 1` would claim it was read.

WHY THE CLAIMED SET IS SMALL AND MEASURED. The census above also found 140 `.data`, 94
`.function` and 61 `.vcxproj` files. Those are deliberately NOT claimed: `.data`/`.function` are
mbedtls's own test-fixture formats rather than a language, and registering 234 rows would move
`coverage.indexed_files` and every `DirectoryEntry.indexed_files` for a repo-specific file
format. Claiming a type because it exists somewhere is how an inventory becomes noise.

@brief A no-grammar source file is registered by name and reports that it was not read.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.synth import UNPARSED_EXTS, UNPARSED_NAMES, claims, register_paths


## @brief The types C5 claims, and the types it deliberately does not.
## @version 1
@pytest.mark.parametrize(
    ("rel", "wanted", "why"),
    [
        pytest.param("scripts/generate_errors.pl", True, "the mbedtls Q4 set mark", id="perl"),
        pytest.param("scripts/mbedtls_dev/helper.pm", True, "a Perl module", id="perl-module"),
        pytest.param("Makefile", True, "8 of them in the mbedtls checkout", id="makefile"),
        pytest.param("library/Makefile", True, "matched as a path component", id="nested-makefile"),
        pytest.param("build/rules.mk", True, "an included make fragment", id="mk"),
        pytest.param(
            "tests/suites/test_suite_aes.data",
            False,
            "an mbedtls test-fixture format, not a language — 140 of them",
            id="not-data",
        ),
        pytest.param(
            "visualc/VS2017/mbedtls.vcxproj",
            False,
            "an MSVC project file — 61 of them, and XML rather than source",
            id="not-vcxproj",
        ),
        pytest.param(
            "scripts/oldmakefile.txt", False, "a suffix test would claim this", id="not-lookalike"
        ),
    ],
)
def test_the_claimed_set_is_exactly_what_was_measured(rel: str, wanted: bool, why: str) -> None:
    """ASSERTED IN BOTH DIRECTIONS. A claimed set tested only for what it includes grows by
    accretion; the three negative cases are the ones that keep `coverage.indexed_files`
    meaningful.

    `oldmakefile.txt` is the lookalike `SCRIPT_NAMES`' own comment warns about — a suffix test
    (`endswith("makefile")`) claims it, a path-component match does not.
    """
    assert claims(rel) is wanted, f"{rel}: {why}"


## @brief A no-grammar file is registered, and says it was not read.
## @version 1
def test_an_unparsed_file_is_registered_as_known_but_unread(tmp_path: Path) -> None:
    """RED BEFORE THE FIX: `claims()` returns False for `.pl`, so `register_paths` inserts no
    row and the file is not in the file set at all.

    The assertion is on `found = 0` rather than merely on the row existing, because a row with
    `found = 1` claims the file resolved to content — which would make a Perl script
    indistinguishable from a C file clew actually parsed, on the one surface whose job is saying
    what is in here.
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, local INTEGER, "
        "found INTEGER, name TEXT)"
    )
    conn.commit()
    conn.close()

    inserted = register_paths(db, ["scripts/generate_errors.pl", "src/app.ts"])
    assert inserted == 2, "both the unparsed file and the claimed TS file must be registered"

    conn = sqlite3.connect(str(db))
    rows = dict(conn.execute("SELECT name, found FROM path"))
    conn.close()

    assert rows["scripts/generate_errors.pl"] == 0, (
        "a file no grammar reads must report that it was NOT resolved to content; found=1 would "
        "claim it was parsed"
    )
    assert rows["src/app.ts"] == 1, (
        "C5 must not change what a file the parse front end DOES read reports"
    )


## @brief The registered file is reachable by name through the file subject.
## @version 1
def test_the_registered_file_answers_as_a_file_subject(tmp_path: Path) -> None:
    """THE END THE MARK IS GRADED ON. Registration is the mechanism; being nameable is the
    outcome. C1 made a path a `dossier` subject, so the two changes together turn
    `scripts/generate_errors.pl` from a definitive negative into a reply that names the file and
    states plainly that nothing was harvested from it.
    """
    from clew.query.corpus import file_subject, list_files

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, local INTEGER, "
        "found INTEGER, name TEXT)"
    )
    conn.commit()
    conn.close()
    register_paths(db, ["scripts/generate_errors.pl"])

    conn = sqlite3.connect(str(db))
    try:
        built = file_subject(conn, "scripts/generate_errors.pl")
        assert built is not None, "the mark wants this name findable; a miss is the old answer"
        assert built.symbol_count == 0
        assert built.harvested is False, (
            "`I know of this file and could not read it` is the claim; `harvested=True` would "
            "say it was read and declares nothing, which is a different and wrong fact"
        )
    finally:
        conn.close()

    assert "scripts/generate_errors.pl" in {f.path for f in list_files(db, "*.pl")}, (
        "the file must also be enumerable, since `search(corpus='files')` is the route a reader "
        "takes when they do not already know the path"
    )


## @brief Nothing harvests the newly claimed types.
## @version 1
def test_no_harvester_claims_the_unparsed_types() -> None:
    """REGISTERED AND NEVER HARVESTED is half a promise until the harvest side is asserted.
    `script_claims` is what routes a file to the shell/CMake symbol harvester, and a type that
    reached it would put Perl subroutine names into the namespace that answers questions about C
    functions — with no grammar to parse them correctly.

    Asserted against the harvest router too, not only against `script_claims`, because they are
    two separate statements this package makes about the same file.
    """
    from clew.harvest import _CPP_EXTS, _PY_EXTS, _TS_EXTS
    from clew.synth import SCRIPT_EXTS, SCRIPT_NAMES, SYNTH_EXTS, script_claims

    for ext in UNPARSED_EXTS:
        assert not script_claims(f"x{ext}"), f"{ext} must not reach the script symbol harvester"
        for name, table in (
            ("harvest._CPP_EXTS", _CPP_EXTS),
            ("harvest._PY_EXTS", _PY_EXTS),
            ("harvest._TS_EXTS", _TS_EXTS),
            ("synth.SYNTH_EXTS", SYNTH_EXTS),
            ("synth.SCRIPT_EXTS", SCRIPT_EXTS),
        ):
            assert ext not in table, f"{ext} is claimed for harvest by {name}"

    for filename in UNPARSED_NAMES:
        assert not script_claims(filename), f"{filename} must not reach the script harvester"
        assert filename not in SCRIPT_NAMES, f"{filename} is claimed for harvest by SCRIPT_NAMES"


# ─── the default corpus must find it too ─────────────────────────────────────


## @brief A file registered by name is findable in the DEFAULT corpus.
## @version 1
def test_a_registered_file_is_findable_in_the_default_corpus(tmp_path: Path) -> None:
    """REGISTRATION IS NOT REACH, AND THE 1.1.0 TRANSCRIPTS SHOW THE DIFFERENCE. mbedtls Q4's
    `set` mark wants `scripts/generate_errors.pl` as a name in a list. The agent asked for it
    three ways, in this order:

        search("generate_errors")                   <- the DEFAULT corpus, tried FIRST
        search("generate_errors", corpus="files")
        search("generate_errors", corpus="prose")

    Replayed against an index rebuilt with C5 in place, the middle one answers and the other two
    return nothing. So the file is registered, and the corpus a reader reaches for first still
    says there is no such thing.

    THE CAUSE IS NARROW. `symbols._file_candidates` builds its file rows from
    `corpus.file_doc_rows`, which reads `file_docs` — so only a DOCUMENTED file can appear in the
    default corpus. A file the index knows by name and harvested nothing from has no such row by
    construction, which is exactly the class of file C5 exists to make nameable.

    The path is already the searchable unit here: `_search_rank(path, doc, ...)` scores a file's
    PATH where a symbol's name is scored. Only the row's source was too narrow.

    @brief The default corpus matches a registered path with no documentation.
    @return None.
    @version 1
    """
    import sqlite3

    from clew.query.symbols import search

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, local INTEGER, "
        "found INTEGER, name TEXT)"
    )
    conn.commit()
    conn.close()
    register_paths(db, ["scripts/generate_errors.pl", "src/app.ts"])

    names = [h.name for h in search(db, "generate_errors", limit=25)]
    assert "scripts/generate_errors.pl" in names, (
        f"the default corpus cannot find a file the index holds a path row for: {names}"
    )


## @brief Widening the corpus does not displace documented files.
## @version 2
def test_a_documented_file_is_not_displaced_by_a_name_only_match(tmp_path: Path) -> None:
    """THE BOUND ON WIDENING THE CORPUS: the new rows must not push out the ones that already
    carried evidence. Both files must be returned.

    THIS TEST FIRST ASSERTED THE OPPOSITE RANKING AND WAS WRONG. It required a documentation
    match to outrank a bare path match, which contradicts a rule this module states and enforces
    deliberately: `_file_candidates`' own docstring says the path is scored where a symbol's name
    is scored "so a conceptual token in prose stays weaker evidence than the same token in an
    identifier — the property `_search_rank` exists to enforce." A token in a PATH is therefore
    stronger evidence than the same token in prose, by design and by one shared weight table.

    The preference I had written in was invented here rather than taken from that table, so the
    assertion is now on what the widening must not break — presence — and the ordering is left to
    the function that owns it.
    """
    import sqlite3

    from clew.query.symbols import search

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, local INTEGER, "
        "found INTEGER, name TEXT)"
    )
    conn.execute("CREATE TABLE file_docs (file_path TEXT NOT NULL, doc TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO file_docs VALUES ('src/errors.c', "
        "'Generates the error table. See generate_errors for the generator.')"
    )
    conn.commit()
    conn.close()
    register_paths(db, ["scripts/generate_errors.pl"])

    names = [h.name for h in search(db, "generate_errors", limit=25)]
    assert "scripts/generate_errors.pl" in names, names
    assert "src/errors.c" in names, (
        f"widening the corpus must not displace a file whose DOCUMENTATION matches: {names}"
    )
