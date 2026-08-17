# SPDX-License-Identifier: MIT
"""gh#374 — the typedef/enumeration corpora, and an empty result that cannot overclaim.

THE DEFECT IS A CLASS, NOT A KIND. Four times now a `memberdef`/`compounddef` kind
has been present in the index and absent from `search`, and every time the reply was
not "outranked" or "no rows" but a maximally confident *"This IS a definitive empty
result from the database ... Do not retry this query or fall back to guessing"* —
a sentence engineered to stop the caller making the one call that would refute it.
Classes (gh#315), variables (gh#372), macros (gh#373), and now typedefs and
enumerations, which on the mbedtls index were 282 of 7,717 distinct `memberdef`
names: `mbedtls_ssl_mode_t`, `mbedtls_x509_buf`, `psa_key_derivation_step_t` and 279
more, all unfindable and all denied with certainty.

So the tests come in two halves and the SECOND half is the load-bearing one:

  1. The two new corpora are searched — the instance.
  2. An empty result is graded against the kinds THIS DATABASE HOLDS minus the kinds
     `search` reads, so a corpus nobody has added yet downgrades the verdict on the
     day it first appears. That is the class.

`test_a_genuinely_absent_token_still_gets_the_definitive_note` is the control on
half 2 and is as load-bearing as either fix: a change that hedged every empty result
would trade one confidently-wrong answer for a tool that never commits to anything,
and the strong wording is what stops an agent burning a turn re-searching.

@brief Tests for the type corpora and for verdict grading against unread corpora.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.mcp_server.emptiness import search_emptiness
from clew.query import SEARCHED_MEMBERDEF_KINDS, search, unsearched_corpora

## doxygen's own spellings for the two kinds gh#374 adds, written literally rather than
## imported from the production tuple: a test that reads the constant under test cannot
## catch that constant being changed to a kind doxygen never emits.
TYPEDEF_KIND = "typedef"
ENUM_KIND = "enumeration"

## (name, kind, brief). `ctx_state_t` and `mbed_mode_t` exist ONLY as a type — nothing
## else in the fixture carries either name — so a hit on them can only have come from
## the new corpora. `poll_state` is the collision case: a function AND a typedef of the
## same name, which is how a C header habitually names a callback type after the
## function it fronts, and which is the shape a "look up a type only when no function
## resolves" implementation would silently get wrong.
SYMBOLS = [
    ("run_pump", "function", "Start the pump"),
    ("poll_state", "function", "Poll the state machine once"),
    ("poll_state", TYPEDEF_KIND, "Callback type for a state poll"),
    ("ctx_state_t", TYPEDEF_KIND, "Opaque handle to a state context"),
    ("mbed_mode_t", ENUM_KIND, "How the transport frames a record"),
]

## Compound rows. `group` is a kind `search` does not read at all — doxygen writes one
## per `@defgroup` and mbedtls's index holds 39 — and it stands in for ANY unread
## corpus, the grading being by subtraction rather than by this name.
##
## `legacy_shim.c` is the subtler half: a FILE, indexed, with no `file_docs` row. Files
## look covered (`corpus.file_doc_rows` is a search corpus) and an UNDOCUMENTED file is
## not, so this row is what stops `file` being excluded from the unread set on an
## assumption instead of on the searcher's actual reach.
COMPOUNDS = [
    ("asn1_module", "group", "ASN.1 encoding and decoding"),
    ("legacy_shim.c", "file", ""),
]


## @brief A minimal index carrying functions, types, one unread compound kind and file docs.
## @param tmp_path Pytest temporary directory.
## @return Path to the database.
## @version 1
@pytest.fixture
def db(tmp_path: Path) -> Path:
    """Hand-built so the SHAPE under test is visible in the test itself: which name
    exists under which kind, and which kinds the database holds at all — the second
    being what the emptiness grading subtracts from.

    `file_docs` is populated because an index WITHOUT it takes a different branch
    (`_NO_FILE_DOCS`), and a fixture missing it would let the definitive-note control
    pass for the wrong reason.

    @brief Build the two-corpus fixture index.
    @return Database path.
    @version 1
    """
    path = tmp_path / "clew.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.execute("INSERT INTO path (rowid, name, type) VALUES (1, 'src/pump.c', 1)")
    conn.execute(
        "CREATE TABLE memberdef (name TEXT, kind TEXT, briefdescription TEXT, "
        "initializer TEXT, file_id INTEGER)"
    )
    conn.executemany(
        "INSERT INTO memberdef (name, kind, briefdescription, initializer, file_id) "
        "VALUES (?, ?, ?, NULL, 1)",
        SYMBOLS,
    )
    conn.execute(
        "CREATE TABLE compounddef (name TEXT, kind TEXT, briefdescription TEXT, file_id INTEGER)"
    )
    conn.executemany(
        "INSERT INTO compounddef (name, kind, briefdescription, file_id) VALUES (?, ?, ?, 1)",
        COMPOUNDS,
    )
    conn.execute("CREATE TABLE file_docs (file_path TEXT NOT NULL, doc TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO file_docs (file_path, doc) VALUES ('src/pump.c', 'Pump control loop.')"
    )
    conn.commit()
    conn.close()
    return path


## @brief A typedef that shares its name with nothing else is findable.
## @param db The fixture index.
## @return None.
## @version 1
def test_a_typedef_is_findable(db: Path) -> None:
    """The measured case: on mbedtls, 239 typedef names existed under no other kind, so
    `search` returned zero for names like `mbedtls_x509_buf` and said so definitively."""
    hits = search(db, "ctx_state_t")
    assert [(h.name, h.kind) for h in hits] == [("ctx_state_t", TYPEDEF_KIND)]


## @brief An enumeration is findable, and reports its own kind rather than a function's.
## @param db The fixture index.
## @return None.
## @version 1
def test_an_enumeration_is_findable_and_says_it_is_one(db: Path) -> None:
    """`kind` is what a caller must read before treating a hit as callable: an
    enumeration has no body, no callers and no callees, and every call, thread and
    requirement layer filters `kind='function'`. A hit that came back labelled
    `function` would be worse than the empty result it replaced."""
    hits = search(db, "mbed_mode_t")
    assert [(h.name, h.kind) for h in hits] == [("mbed_mode_t", ENUM_KIND)]


## @brief A name that is BOTH a function and a typedef returns both, function first.
## @param db The fixture index.
## @return None.
## @version 1
def test_a_name_that_is_both_a_function_and_a_type_returns_both(db: Path) -> None:
    """THE COLLISION CASE, and the one an obvious implementation gets wrong. Falling
    back to the type corpus only when no function resolves would pass every other test
    here and go dark on the shape C headers use most — a callback typedef named after
    the function it fronts. Both rows must come back, and the FUNCTION must lead:
    types sit in the lowest tie-break tier for exactly this."""
    hits = search(db, "poll_state")
    assert [(h.name, h.kind) for h in hits] == [
        ("poll_state", "function"),
        ("poll_state", TYPEDEF_KIND),
    ]


## @brief The searched set names both new kinds, so what is read and what is SAID agree.
## @return None.
## @version 1
def test_the_searched_set_is_the_one_the_reply_quotes() -> None:
    """The corpora used to be added one wrapper at a time with nothing tying the
    searcher to the sentence describing it, and the sentence was wrong for months
    across three additions. This asserts the single source of truth carries the new
    kinds; `test_an_unread_corpus_downgrades_the_verdict` asserts the reply is built
    from it."""
    kinds = [kind for kind, _tier in SEARCHED_MEMBERDEF_KINDS]
    assert TYPEDEF_KIND in kinds
    assert ENUM_KIND in kinds
    assert kinds[0] == "function"


## @brief A genuinely absent single token still gets the full definitive note.
## @param db The fixture index.
## @return None.
## @version 1
def test_a_genuinely_absent_token_still_gets_the_definitive_note(db: Path) -> None:
    """THE CONTROL ON THE GRADING. Nothing in this database matches, in a read corpus
    or an unread one, so the strong wording is earned and must survive. If this test
    ever needs weakening, the change has become a blanket hedge — which is the other
    way to be useless about an empty result."""
    assert search(db, "zzznosuchtoken") == []
    note, extra = search_emptiness(db, "zzznosuchtoken")
    assert "definitive" in note
    assert "Do not retry this query or fall back to guessing" in note
    assert "unsearched_corpus_hits" not in extra


## @brief A match in a corpus `search` does not read strips the definitive claim.
## @param db The fixture index.
## @return None.
## @version 1
def test_an_unread_corpus_downgrades_the_verdict(db: Path) -> None:
    """THE CLASS FIX. `asn1_module` is a doxygen `group`, which `search` does not read
    and is not being taught to read here — the point is that the reply KNOWS it did not
    look. The old note asserted absence with maximum confidence in exactly this
    situation, and did so four times over four different kinds.

    The count is published as well as worded, so the claim is checkable by the caller
    rather than merely asserted at them."""
    assert search(db, "asn1_module") == []
    note, extra = search_emptiness(db, "asn1_module")
    assert "NOT DEFINITIVE" in note
    assert "Do not retry this query or fall back to guessing" not in note
    assert "1 group" in note
    assert extra["unsearched_corpus_hits"] == {"group": 1}


## @brief The unread set is derived by subtraction, so a NEW unread kind is caught unaided.
## @param db The fixture index.
## @return None.
## @version 1
def test_the_unread_set_is_derived_from_the_database(db: Path) -> None:
    """The difference between a fix and a guard. A hardcoded list of unread kinds would
    be exactly as stale as the hardcoded list of READ kinds turned out to be; this
    inserts a kind no line of production code mentions and requires it to be reported.
    A future doxygen kind, or a layer a later pipeline stage adds, is covered on the day
    it first appears with no edit to the grader."""
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO memberdef (name, kind, briefdescription, initializer, file_id) "
        "VALUES ('quantum_widget', 'concept', 'A kind that did not exist yesterday', NULL, 1)"
    )
    conn.commit()
    conn.close()
    assert search(db, "quantum_widget") == []
    assert unsearched_corpora(db, ["quantum_widget"]) == {"concept": 1}
    ## THE OTHER DIRECTION, and it needs asserting HERE because no reply can show it:
    ## a searched kind that matched means `search` returned hits, so the grader is
    ## never called and a subtraction that had stopped subtracting would look exactly
    ## like one that works. `poll_state` is a function AND a typedef, both read.
    assert unsearched_corpora(db, ["poll_state"]) == {}
    note, _extra = search_emptiness(db, "quantum_widget")
    assert "NOT DEFINITIVE" in note
    assert "1 concept" in note


## @brief An UNDOCUMENTED indexed file is reported, not assumed covered.
## @param db The fixture index.
## @return None.
## @version 1
def test_an_undocumented_file_is_not_assumed_searchable(db: Path) -> None:
    """The near-miss in this change. `file` looks like a covered kind because file-level
    documentation IS a search corpus — but that corpus is `file_docs`, one row per
    DOCUMENTED file, so `legacy_shim.c` (indexed, no docstring) is reachable by no
    route `search` has. Excluding `file` from the unread set would have asserted
    coverage the searcher does not have, which is this defect one table over.

    The documented control is `src/pump.c`: it has a `file_docs` row, so it is FOUND
    and never reaches the grader at all."""
    assert search(db, "legacy_shim") == []
    note, extra = search_emptiness(db, "legacy_shim")
    assert extra["unsearched_corpus_hits"] == {"file": 1}
    assert "NOT DEFINITIVE" in note
    assert [h.name for h in search(db, "pump.c")] == ["src/pump.c"]


## @brief A multi-token miss keeps its per-token diagnosis and gains the unread finding.
## @param db The fixture index.
## @return None.
## @version 1
def test_a_conjunction_miss_still_names_its_dead_token(db: Path) -> None:
    """gh#31's diagnosis is not displaced by gh#374's. The two answer different
    questions — WHICH token emptied the conjunction, and whether the emptiness is a
    claim about the repository — and a reply that dropped the first to make room for
    the second would re-open the defect it was written for."""
    assert search(db, "pump zzznosuchtoken") == []
    note, extra = search_emptiness(db, "pump zzznosuchtoken")
    assert extra["token_hits"] == {"pump": 2, "zzznosuchtoken": 0}
    assert "'zzznosuchtoken'" in note
    assert "RETRY WITHOUT THEM" in note


## @brief A token matching only a TYPE is never named as the token that emptied a query.
## @param db The fixture index.
## @return None.
## @version 1
def test_a_type_only_token_is_not_blamed_for_the_conjunction(db: Path) -> None:
    """gh#31's defect, reachable through gh#374's corpora. The per-token diagnosis
    counts matches so it can tell the caller WHICH token to drop, and it counted only
    the kinds it had listed for itself. Add a corpus to the searcher and not to the
    counter and the counter names the working token as the guilty one — advice that is
    not merely unhelpful but backwards.

    `mbed_mode_t` matches the enumeration and nothing else; `run_pump` matches the
    function and nothing else. Neither is to blame: both match alone, no unit carries
    both, and the correct advice is fewer tokens. A counter blind to the type corpora
    reports `mbed_mode_t=0` and tells the caller to delete it."""
    assert search(db, "mbed_mode_t run_pump") == []
    _note, extra = search_emptiness(db, "mbed_mode_t run_pump")
    assert extra["token_hits"] == {"mbed_mode_t": 1, "run_pump": 1}
    assert "RETRY WITH FEWER TOKENS" in _note
