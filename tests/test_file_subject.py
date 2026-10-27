# SPDX-License-Identifier: MIT
"""A FILE PATH IS A SUBJECT (C1 of the 1.1.0 acceptance review).

MEASURED, on the frozen 1.1.0 transcripts: of 237 subjects `dossier` was asked for and
missed, **48 — 20.3% — were file paths**. The model passed
`src/inference/llama_cpp_tokenizer.cpp` as a `subject` and was told the index holds nothing
of that name, while the index held a `path` row for it, nine `memberdef` rows under it and,
for a documented file, its whole module docstring in `file_docs`.

The hand-traced half is worse than the count. Five graded clusters carrying **31 weight** lost
marks that are file-level claims — what a file is for, what it contains, whether it is
generated — and the refusal the surface actually served was

    "a file has no dossier — its documentation is `search(corpus='prose')`"

which is a token CONJUNCTION over every corpus, not "tell me about this file", and which
ranks a file hit against member and markdown hits. The recovery hint added in 16d6c25
redirected a file-path miss to `search(corpus="files")`, which returns
`FileEntry(path, symbol_count, external_root)` — **no documentation field at all**. That
redirect was written in this repository, by this project, pointing at a dead end.

`_KIND_NO_SUBJECT` already records the shape of this mistake one entry up, about
`enumeration`: "The refusal was accurate when written and became false when the subject was
built." This is the same correction for `file`.

WHY A DEDICATED TEST FILE. The file subject is the first subject kind whose NAME IS NOT AN
IDENTIFIER, so it is the first one for which "is this string a subject" cannot be answered by
the memberdef probes, and the first that must refuse a synthetic path. Those properties have
no home in the per-kind tests.
"""

from __future__ import annotations


import clew.query as q


## @brief A documented file resolves as a `file` subject carrying its documentation.
## @version 1
def test_a_documented_file_path_is_a_subject_and_carries_its_documentation(rich_db, repo_root):
    """RED BEFORE THE FIX: `resolve_subject` has no `file` probe, so this returns None and
    the served refusal names `search(corpus='prose')`.

    `event_bus.c` is the fixture's richest documented file — 9 symbols and a `file_docs` row.
    The assertion is on the DOCUMENTATION being present, because that is the field the 31
    weight was lost on; a path echo and a count were already reachable through `list_files`.
    """
    built = q.dossier(rich_db, "src/event_bus/event_bus.c", repo_root=repo_root)
    assert built is not None, "a file path the index holds rows for must resolve as a subject"
    assert built.kind == "file"
    assert built.file is not None
    assert built.file.path == "src/event_bus/event_bus.c"
    assert built.file.documentation, (
        "file_docs holds a row for this path; the subject must serve it"
    )
    assert built.file.symbol_count == 9


## @brief A file with symbols but no file-level comment resolves, and says so by absence.
## @version 1
def test_an_undocumented_file_resolves_and_reports_no_documentation(rich_db, repo_root):
    """ABSENCE IS NOT EMPTINESS, applied to the one field this subject exists to carry.
    `event_bus.h` has 10 symbols and no `file_docs` row — the file was read and carries no
    file-level comment. That is a measurement, and it must not be confused with the file
    being unknown (which returns None) or with the corpus being absent (which
    `has_file_docs` reports).
    """
    built = q.dossier(rich_db, "src/event_bus/event_bus.h", repo_root=repo_root)
    assert built is not None
    assert built.kind == "file"
    assert built.file.documentation == ""
    assert built.file.symbol_count == 10


## @brief A file the index knows of but harvested nothing from says which of the two it is.
## @version 1
def test_a_known_file_with_no_harvested_content_is_distinguishable_from_an_unknown_one(
    rich_db, repo_root
):
    """THE DISTINCTION THIS WHOLE SUBJECT IS FOR. `pthread.h` is a `path` row doxygen
    recorded from an `#include` and never resolved to content: 0 symbols, no documentation.
    An unknown path resolves to nothing at all.

    Both would read as "nothing here" if the subject reported only counts, and they are
    different facts — the first is "I know this file exists and could not read it", which is
    `DirectoryEntry.unresolved_files` at one-file granularity, and the second is "not in this
    index". `harvested` carries it.
    """
    known = q.dossier(rich_db, "pthread.h", repo_root=repo_root)
    assert known is not None, "a path row is knowledge of the file, and must resolve"
    assert known.file.symbol_count == 0
    assert known.file.harvested is False

    assert q.dossier(rich_db, "src/nothing/invented.c", repo_root=repo_root) is None


## @brief The synthetic `[STL]` path is never a subject.
## @version 1
def test_the_synthetic_stl_path_is_not_a_file_subject(rich_db, repo_root):
    """`list_files` excludes it by `SYNTHETIC_PATH` and so must this. It is doxygen's
    placeholder owner for standard-library symbols, not a file in the repository, and
    serving it as one would put a path nobody can open into a reply whose whole purpose is
    naming files that can be read.
    """
    assert q.dossier(rich_db, "[STL]", repo_root=repo_root) is None


## @brief `kind='file'` is accepted rather than refused.
## @version 1
def test_kind_file_from_a_search_row_round_trips(rich_db, repo_root):
    """`search`'s own description promises "READ `kind` ON EVERY ROW: it is what you pass
    back", and the `files` corpus labels its rows `file`. That promise was false for this one
    kind: `_KIND_NO_SUBJECT` raised, naming a route that could not answer the question.
    """
    built = q.dossier(rich_db, "src/main.c", kind="file", repo_root=repo_root)
    assert built is not None
    assert built.kind == "file"


## @brief Asking for a non-file kind on a file path is still a filter, not an override.
## @version 1
def test_a_file_path_asked_for_as_a_function_resolves_to_nothing(rich_db, repo_root):
    """The rule every other kind obeys — "AN EXPLICIT KIND IS A FILTER, NOT AN OVERRIDE" —
    and worth pinning here because a file path is the one subject whose spelling makes the
    caller's intent unambiguous, which is exactly when a surface is tempted to be helpful
    and hand back the thing it was told to rule out.
    """
    assert q.dossier(rich_db, "src/main.c", kind="function", repo_root=repo_root) is None


## @brief A file's members are listed so the subject answers "what is in here".
## @version 1
def test_a_file_subject_lists_the_symbols_it_defines(rich_db, repo_root):
    """A count alone does not answer the graded question, which is what the file CONTAINS.
    The members come from the same `memberdef`/`file_id` join `list_files` counts, so the
    list and the count cannot disagree.
    """
    built = q.dossier(rich_db, "src/event_bus/event_bus.c", repo_root=repo_root)
    names = {m.name for m in built.file.members}
    assert len(names) == built.file.symbol_count
    assert "event_bus_publish" in names, f"expected the publisher among {sorted(names)}"


# ─── the thin-schema contract, which this feature's first draft broke ─────────


## @brief The file probe degrades on an index whose `path` table has no `type` column.
## @version 1
def test_the_file_probe_degrades_on_a_minimal_path_table(tmp_path):
    """RED WHEN WRITTEN, AGAINST CODE ALREADY IN THE TREE. The first draft of
    `is_indexed_file` named `path.type` unconditionally. This repository's minimal fixtures
    create `path (rowid, name)` and nothing else, so the probe raised `no such column: type`
    — and because `resolve_subject` runs EVERY probe against EVERY bare name, it took 14
    unrelated tests down with it: every enum subject, both kconfig subjects, three recovery
    hints.

    That is the `has_columns` graceful-degradation contract, and the blast radius is the
    argument for pinning it here rather than trusting the next probe author to remember: a new
    probe is the one kind of change that can make an unrelated subject kind raise.

    @brief A thin `path` table answers thinly rather than raising.
    @return None.
    @version 1
    """
    import sqlite3

    from clew.query.corpus import file_subject, is_indexed_file

    db = tmp_path / "thin.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO path (name) VALUES ('src/thin.c')")
    conn.commit()

    assert is_indexed_file(conn, "src/thin.c") is True
    assert is_indexed_file(conn, "src/absent.c") is False
    built = file_subject(conn, "src/thin.c")
    assert built is not None
    ## No `memberdef` table at all: zero members is what this index knows, and it must not
    ## raise on the way to saying so.
    assert built.members == ()
    assert built.symbol_count == 0
    conn.close()


## @brief An index with no `path` table at all resolves no file and does not raise.
## @version 1
def test_no_path_table_is_not_a_file(tmp_path):
    """The outermost degradation step, and the one `table_exists` is for.

    @brief A `path`-less index answers no rather than raising.
    @return None.
    @version 1
    """
    import sqlite3

    from clew.query.corpus import is_indexed_file

    conn = sqlite3.connect(tmp_path / "empty.db")
    assert is_indexed_file(conn, "src/thin.c") is False
    conn.close()


# ─── the documentation is the payload, so it is the thing that needs a bound ──


## @brief A long file-level comment is capped, and says that it was.
## @version 1
def test_long_file_documentation_is_capped_with_an_explicit_notice(tmp_path):
    """THE ONE FIELD ON THIS SUBJECT THAT IS UNBOUNDED BY ANYTHING THE INDEX CONTROLS.
    `members` is a list and is trimmed by `_DOSSIER_LISTS` like every other list on the
    surface; `documentation` is a scalar string and is therefore invisible to
    `_shrink_to_budget`. Measured in this repository: `clew/tiers.py` carries 2,794
    characters of module docstring, `clew/cli.py` more, and a generated header's `@file`
    block has no ceiling at all. An unbounded scalar inside a budgeted payload is how the
    65,536-byte cap gets exceeded by a reply that every list-trimmer reports as compliant.

    CAPPED WITH THE SAME CONSTANT AND THE SAME NOTICE as a function's `@details` prose, from
    one implementation rather than a second copy of the convention. A truncation notice that
    is nearly the same in two places is the one that drifts into saying two different things.

    @brief File documentation is bounded and discloses the cut.
    @return None.
    @version 1
    """
    import sqlite3

    from clew.query._common import DETAIL_CAP
    from clew.query.corpus import file_subject

    doc = "x" * (DETAIL_CAP + 500)
    db = tmp_path / "long.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.execute("INSERT INTO path (name, type) VALUES ('src/verbose.c', 1)")
    conn.execute("CREATE TABLE file_docs (file_path TEXT NOT NULL, doc TEXT NOT NULL)")
    conn.execute("INSERT INTO file_docs VALUES ('src/verbose.c', ?)", (doc,))
    conn.commit()

    built = file_subject(conn, "src/verbose.c")
    assert len(built.documentation) < len(doc), "an unbounded scalar defeats the payload budget"
    assert "truncated" in built.documentation, (
        f"a silent cut reads as a complete document: {built.documentation[-120:]!r}"
    )
    assert str(len(doc)) in built.documentation, (
        "the notice must state the true length, so a reader knows how much it is not seeing"
    )
    conn.close()
