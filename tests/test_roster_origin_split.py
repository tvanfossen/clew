# SPDX-License-Identifier: MIT
"""The one first-party/external reporting contract (gh#352): every roster splits, buckets sum.

WHAT THIS FILE EXISTS TO STOP. `lock_roster`'s payload used to end with "Quote
distinct_mutexes as the mutex count", and on the public
[tvanfossen/entropic](https://github.com/tvanfossen/entropic) index that number is 97 —
of which 52 belong to the vendored `extern/llama.cpp` submodule. The tool instructed a
caller to attribute the majority of another repository's locks to entropic, and the
acceptance rubric had begun COMPENSATING by widening a mark to accept 97 "when attributed
and split". A tool teaching its own grader to accept its defect is the failure here, not
the wrong number.

THE CONTRACT: `first_party` + `external` + `unresolved` == `total`, the split is over the
number the payload tells a caller to QUOTE, and no query filters on the tag. That last
clause is asserted as loudly as the arithmetic — an answer that silently omitted submodule
rows is the filtered-answer-that-reads-as-an-empty-answer failure, and it would also make
a `chain_trace` into that submodule inexplicable.

@brief Tests for the roster origin split and its arithmetic.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import query as q
from clew.query.models import OriginSplit
from clew.vocabulary import EXTERNAL_ROOT_COLUMN

_SCHEMA = f"""
    CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, {EXTERNAL_ROOT_COLUMN} TEXT);
    CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE locks (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, scope TEXT NOT NULL,
        kind TEXT NOT NULL, decl_path_rowid INTEGER, decl_line INTEGER,
        identity_confidence TEXT NOT NULL, source TEXT NOT NULL,
        UNIQUE(name, scope, kind)
    );
    CREATE TABLE lock_acquisitions (
        id INTEGER PRIMARY KEY, lock_id INTEGER, holder_rowid INTEGER,
        path_rowid INTEGER, form TEXT, role TEXT, mode TEXT,
        start_line INTEGER, end_line INTEGER, pattern_name TEXT,
        declared INTEGER, confidence TEXT
    );
"""

## Mirrors the real thing: `path` with no external column at all, which is every index built
## before gh#335 stamped one.
_SCHEMA_UNTAGGED = _SCHEMA.replace(f", {EXTERNAL_ROOT_COLUMN} TEXT", "")


## @brief Build a lock index from (id, name, scope, kind, decl_path_rowid) tuples.
## @param tmp_path Directory to write the database into.
## @param locks Lock rows to insert.
## @param files (rowid, name, external_root or None) file rows.
## @param tagged False to build a `path` table with no external column at all.
## @return Path to the database.
## @version 1
def _lock_db(
    tmp_path: Path,
    locks: list[tuple[int, str, str, str, int | None]],
    files: list[tuple[int, str, str | None]],
    tagged: bool = True,
) -> Path:
    """REAL TABLES, not a stubbed query. The split is computed in SQL plus a collapse, and a
    fake `lock_roster` would assert the arithmetic while proving nothing about the join that
    supplies its input — which is where the external column's absence has to degrade.

    @brief Seed a lock-layer fixture.
    @return Database path.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA if tagged else _SCHEMA_UNTAGGED)
    for rowid, name, owner in files:
        if tagged:
            conn.execute(
                f"INSERT INTO path (rowid, name, {EXTERNAL_ROOT_COLUMN}) VALUES (?, ?, ?)",
                (rowid, name, owner),
            )
        else:
            conn.execute("INSERT INTO path (rowid, name) VALUES (?, ?)", (rowid, name))
    conn.executemany(
        "INSERT INTO locks (id, name, scope, kind, decl_path_rowid, decl_line, "
        "identity_confidence, source) VALUES (?, ?, ?, ?, ?, 10, 'high', 'ast')",
        locks,
    )
    conn.commit()
    conn.close()
    return db


## The three cases in one fixture, so no assertion can pass by the collapse being a no-op:
## the repo's own mutex, a vendored one, and one whose declaring file never resolved.
_MIXED_LOCKS: list[tuple[int, str, str, str, int | None]] = [
    (1, "state_mutex_", "class:Engine", "mutex", 1),
    (2, "ggml_mutex", "class:Backend", "mutex", 2),
    (3, "orphan_mutex_", "class:Unknown", "mutex", None),
]
_MIXED_FILES: list[tuple[int, str, str | None]] = [
    (1, "src/engine.cpp", None),
    (2, "extern/llama.cpp/ggml/src/backend.cpp", "extern/llama.cpp"),
]


## @brief The split decomposes the distinct-mutex count into three buckets that sum.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_lock_split_decomposes_the_count_callers_are_told_to_quote(tmp_path: Path) -> None:
    """@brief first_party + external + unresolved == total == distinct_mutexes.
    @version 1
    """
    inv = q.lock_roster(_lock_db(tmp_path, _MIXED_LOCKS, _MIXED_FILES))

    assert inv.distinct_mutexes == 3
    assert inv.origin.total == inv.distinct_mutexes, (
        "the split must decompose the number `row_meaning` tells a caller to quote — a split "
        "over `rows` would sum to a total nobody quotes"
    )
    assert (inv.origin.first_party, inv.origin.external, inv.origin.unresolved) == (1, 1, 1)
    assert inv.origin.external_roots == ("extern/llama.cpp",)


## @brief The buckets account for every member, on any input.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_buckets_always_sum_to_the_total(tmp_path: Path) -> None:
    """THE INVARIANT, asserted rather than assumed — and it is the whole reason a caller can
    trust the split. A classification that silently dropped members would report plausible
    thirds that omit rows, which is worse than no split because it reads as a measurement.

    @brief The three buckets sum to the total.
    @version 1
    """
    inv = q.lock_roster(_lock_db(tmp_path, _MIXED_LOCKS, _MIXED_FILES))
    o = inv.origin

    assert o.first_party + o.external + o.unresolved == o.total


## @brief A mutex taken with two guard kinds counts ONCE in the split.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_split_counts_mutexes_and_not_rows(tmp_path: Path) -> None:
    """THE CONTROL THAT SEPARATES THE TWO PLAUSIBLE IMPLEMENTATIONS. `locks` is keyed
    UNIQUE(name, scope, kind), so one `std::shared_mutex` taken with a `lock_guard` and a
    `shared_lock` occupies TWO rows for ONE mutex. Splitting rows would report `external: 2`
    here — arithmetically consistent, and an answer to a question nobody asked.

    @brief One physical mutex contributes one member to the split.
    @version 1
    """
    inv = q.lock_roster(
        _lock_db(
            tmp_path,
            [
                (1, "ggml_mutex", "class:Backend", "shared_mutex", 2),
                (2, "ggml_mutex", "class:Backend", "mutex", 2),
            ],
            _MIXED_FILES,
        )
    )

    assert inv.rows == 2, "two identities"
    assert inv.distinct_mutexes == 1, "one physical mutex"
    assert inv.origin.total == 1 and inv.origin.external == 1, (
        "the split is over mutexes; counting rows would say external: 2 for one mutex"
    )


## @brief Nothing is filtered out of the roster by the tag.
## @param tmp_path pytest temp dir.
## @version 1
def test_no_lock_is_filtered_out_of_the_roster(tmp_path: Path) -> None:
    """THE CLAUSE THAT IS EASIEST TO GET WRONG WHILE LOOKING RIGHT. The obvious way to make
    the first-party figure correct is to drop the external rows, and then every number reads
    well while `lock_roster` has quietly stopped being an inventory. gh#333 admits nested
    trees precisely so a `chain_trace` can continue into them; a roster that hid their locks
    would make those traces unexplainable.

    @brief Every lock is returned; the split is reported beside them.
    @version 1
    """
    inv = q.lock_roster(_lock_db(tmp_path, _MIXED_LOCKS, _MIXED_FILES))

    assert inv.rows == 3, "all three rows survive"
    assert {e.name for e in inv.locks} == {"state_mutex_", "ggml_mutex", "orphan_mutex_"}
    external = [e for e in inv.locks if e.external_root]
    assert [e.name for e in external] == ["ggml_mutex"], "and each row says whose it is"
    assert [e.name for e in inv.locks if not e.path_resolved] == ["orphan_mutex_"], (
        "`path_resolved` is separate from `file == ''` because an empty file string is also "
        "what a missing declaration line looks like"
    )


## @brief The payload names the first-party count and stops steering callers to the total.
## @param tmp_path pytest temp dir.
## @version 1
def test_row_meaning_leads_with_the_first_party_count(tmp_path: Path) -> None:
    """THE DEFECT WAS IN THE SENTENCE, not only in the number. `row_meaning` is what a model
    quotes, so leaving "Quote distinct_mutexes as the mutex count" in place would preserve the
    wrong attribution even with a correct `origin` field sitting next to it.

    @brief The payload tells a caller to quote `origin.first_party`.
    @version 1
    """
    inv = q.lock_roster(_lock_db(tmp_path, _MIXED_LOCKS, _MIXED_FILES))

    assert "origin.first_party" in inv.row_meaning
    assert "extern/llama.cpp" in inv.row_meaning, "the external root is named, not just counted"
    assert "1 are THIS repository's" in inv.row_meaning


## @brief An index with no external column reads as entirely first party.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_lock_payload_does_not_call_an_identity_count_a_mutex_count(tmp_path: Path) -> None:
    """THE SAME DEFECT AS THIS FILE'S HEADER, ONE AXIS OVER, AND IT SURVIVED ITS OWN FIX.
    "Quote distinct_mutexes as the mutex count" became "Quote origin.first_party as the
    repository's mutex count", which corrected WHOSE count to quote and left in place the
    instruction to quote an IDENTITY count as an OBJECT count. Those are different numbers.

    A row is `(name, scope, kind)` where `name` is the acquisition site's operand text with
    `&`/`*` stripped — a use-site SPELLING, not an object. Two consequences, in opposite
    directions, and the payload named neither:

      * one object reached by two spellings (`&ssl->mutex` here, `&ctx->mutex` there) is TWO
        rows, over-counting;
      * one spelling reached from unrelated struct types (`&ctx->mutex` on an rsa context and
        on an entropy context) is ONE row, under-counting — a false shared-lock claim by this
        module's own standard.

    Measured on Mbed-TLS/mbedtls at mbedtls-3.6.7: the payload says 1 and the source holds 16
    mutex objects (6 globals, 8 struct members, 2 in the test suites). The sentence is
    instruction-grade and a graded agent quoted its thread-layer twin verbatim, which under the
    owner's rule 8 makes the falsehood the TOOL's — the agent is told to trust the index
    absolutely.

    ROUTING, NOT A DISCLAIMER. "I cannot enumerate the objects" leaves the reader to hunt or to
    quote the number anyway. Naming the operand shapes — which spellings are member expressions,
    and therefore objects this layer does not model — collapses the follow-up to one grep. The
    repo already does this for graded emptiness and for kind refusals; the rosters never got it.

    @brief The lock payload must not present its row count as an object count.
    @return None.
    @version 1
    """
    ## Two DIFFERENT objects reached by one spelling, plus a bare global. Three rows, and the
    ## true object count is not derivable from them — which is the point.
    locks: list[tuple[int, str, str, str, int | None]] = [
        (1, "ctx->mutex", "unknown", "mutex", 1),
        (2, "heap.mutex", "unknown", "mutex", 2),
        (3, "debug_mutex", "unknown", "mutex", 2),
    ]
    files: list[tuple[int, str, str | None]] = [
        (1, "library/rsa.c", None),
        (2, "library/memory_buffer_alloc.c", None),
    ]
    roster = q.lock_roster(_lock_db(tmp_path, locks, files))

    ## ASSERTED AS A POSITIVE REQUIREMENT, NOT AS AN ABSENT PHRASE. The first version of this
    ## test forbade the exact string "as the repository's mutex count", and a mutation that
    ## rephrased the SAME falsehood as "own mutex count" sailed past it. A substring ban cannot
    ## distinguish "quote X as the mutex count" from "never as its mutex count" either, since
    ## the correct text has to contain the phrase in order to refuse it. So require the
    ## REFUSAL and the replacement instruction to be present.
    assert "never as its mutex count" in roster.row_meaning, (
        "the payload must explicitly refuse to have its row count read as a mutex count"
    )
    assert "IDENTITIES" in roster.row_meaning, (
        "and must name what origin.first_party IS a count of instead"
    )
    ## What it must say a row's identity IS:
    assert "spelling" in roster.row_meaning.lower(), (
        "it must say what a row's identity IS — the operand text at a use site"
    )
    assert "ctx->mutex" in roster.row_meaning or "member" in roster.row_meaning.lower(), (
        "and must ROUTE: name the member-expression spellings, whose objects it cannot enumerate"
    )
    ## The attribution split is NOT weakened — that is this file's original contract.
    assert "first_party" in roster.row_meaning
    assert roster.origin.first_party + roster.origin.external + roster.origin.unresolved == (
        roster.origin.total
    )


def test_an_index_predating_the_tag_reads_as_all_first_party(tmp_path: Path) -> None:
    """DEGRADATION, NOT AN `OperationalError`. Selecting a column a stale index lacks raises
    rather than degrades — the failure `has_columns` exists to prevent, measured live on a
    build-version-2 target where five tier-1 tools died on `no such column`.

    AND THE FALLBACK IS THE CORRECT ANSWER, not merely a safe one: an index below build
    version 32 EXCLUDED nested trees outright rather than tagging them, so every row in it
    really is first party.

    @brief A pre-tag index answers all-first-party instead of raising.
    @version 1
    """
    inv = q.lock_roster(
        _lock_db(tmp_path, _MIXED_LOCKS, [(1, "src/engine.cpp", None)], tagged=False)
    )

    assert inv.distinct_mutexes == 3
    assert inv.origin.external == 0
    assert inv.origin.external_roots == ()
    assert inv.origin.first_party + inv.origin.unresolved == 3


## @brief An absent lock layer yields a consistent empty split, not a missing field.
## @param tmp_path pytest temp dir.
## @version 1
def test_an_absent_lock_layer_still_carries_a_split(tmp_path: Path) -> None:
    """An index predating the layer must not answer "no split available" — a caller reading
    `origin.first_party` should get 0 with the buckets still summing, so the contract holds on
    every path rather than on the populated one only.

    @brief The empty inventory carries a zeroed, consistent split.
    @version 1
    """
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("CREATE TABLE path (name TEXT);")
    conn.commit()
    conn.close()

    inv = q.lock_roster(db)

    assert inv.origin.total == 0
    assert inv.origin.first_party + inv.origin.external + inv.origin.unresolved == 0


# ─── threads: attribution by SPAWN SITE, not by entry symbol (gh#346) ─────────

_THREAD_SCHEMA = f"""
    CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, {EXTERNAL_ROOT_COLUMN} TEXT);
    CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE threads (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, entry_memberdef_rowid INTEGER,
        kind TEXT NOT NULL, source TEXT NOT NULL, confidence TEXT NOT NULL,
        spawn_path_rowid INTEGER, spawn_line INTEGER
    );
"""

## The pre-gh#346 shape: the layer exists and records no spawn site anywhere.
_THREAD_SCHEMA_NO_SITE = _THREAD_SCHEMA.replace(
    ",\n        spawn_path_rowid INTEGER, spawn_line INTEGER", ""
)


## @brief Build a threads index from (id, name, entry_rowid, spawn_path_rowid, line) tuples.
## @param tmp_path Directory to write the database into.
## @param threads Thread rows.
## @param files (rowid, name, external_root or None) file rows.
## @param with_site False to build the pre-35 schema with no spawn-site columns.
## @return Path to the database.
## @version 1
def _thread_db(
    tmp_path: Path,
    threads: list[tuple[int, str, int | None, int | None, int | None]],
    files: list[tuple[int, str, str | None]],
    with_site: bool = True,
) -> Path:
    """@brief Seed a thread-layer fixture.
    @return Database path.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_THREAD_SCHEMA if with_site else _THREAD_SCHEMA_NO_SITE)
    conn.executemany(
        f"INSERT INTO path (rowid, name, {EXTERNAL_ROOT_COLUMN}) VALUES (?, ?, ?)", files
    )
    conn.execute("INSERT INTO memberdef (rowid, name) VALUES (1, 'poll_loop')")
    if with_site:
        conn.executemany(
            "INSERT INTO threads (id, name, entry_memberdef_rowid, kind, source, confidence, "
            "spawn_path_rowid, spawn_line) VALUES (?, ?, ?, 'pthread', 'ast_spawn', 'medium', "
            "?, ?)",
            threads,
        )
    else:
        conn.executemany(
            "INSERT INTO threads (id, name, entry_memberdef_rowid, kind, source, confidence) "
            "VALUES (?, ?, ?, 'pthread', 'ast_spawn', 'medium')",
            [(t[0], t[1], t[2]) for t in threads],
        )
    conn.commit()
    conn.close()
    return db


_THREAD_FILES: list[tuple[int, str, str | None]] = [
    (1, "src/runtime.cpp", None),
    (2, "extern/llama.cpp/src/llama.cpp", "extern/llama.cpp"),
]


## @brief A thread spawned in a submodule is EXTERNAL even with a NULL entry.
## @param tmp_path pytest temp dir.
## @version 1
def test_a_null_entry_thread_is_attributed_by_its_spawn_site(tmp_path: Path) -> None:
    """THE DEFECT gh#346 CLOSES, in one row. A thread's entry symbol is legitimately NULL —
    `_insert_threads` refuses to resolve a member-function pointer naming a class this index does
    not cover, and refuses a bare name that is not unique, because NULL beats borrowing a
    same-named method on another class. Anchored to that entry, such a row has NO FILE, so it
    could not be tagged, so a submodule's thread counted as FIRST PARTY.

    That inflates the exact figure gh#335's invariance control rests on: admitting a submodule
    must raise the TOTAL and leave every first-party number IDENTICAL. Measured on entropic, 2 of
    12 thread rows resolved to no file at all.

    The spawn site always has a file, because it is where the spawn construct was MATCHED — so
    the row below is external on the evidence of WHERE IT WAS CREATED, with its entry still null.

    @brief A NULL-entry thread spawned externally is tagged external.
    @version 1
    """
    inv = q.thread_roster(
        _thread_db(tmp_path, [(1, "unresolved_worker", None, 2, 88)], _THREAD_FILES)
    )

    assert inv.rows == 1
    thread = inv.threads[0]
    assert thread.entry is None, "the fixture's whole point is an unresolved entry"
    assert thread.spawn_file == "extern/llama.cpp/src/llama.cpp"
    assert thread.spawn_line == 88
    assert thread.external_root == "extern/llama.cpp"
    assert (inv.origin.first_party, inv.origin.external, inv.origin.unresolved) == (0, 1, 0), (
        "anchored to its NULL entry this row had no file and defaulted into first_party — "
        "which is the inflation gh#335's invariance control cannot detect"
    )


## @brief The thread split buckets every row and sums.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_thread_split_buckets_every_row(tmp_path: Path) -> None:
    """One thread per bucket, including a spawn site whose path rowid resolves to NOTHING — that
    lands in UNRESOLVED rather than first party, because "we do not know whose this is" is not
    "it is ours". Folding it into first_party is how a count comes to look healthier than its
    evidence.

    @brief first_party + external + unresolved == total.
    @version 1
    """
    inv = q.thread_roster(
        _thread_db(
            tmp_path,
            [
                (1, "poll_loop", 1, 1, 12),
                (2, "llama_worker", None, 2, 40),
                ## A spawn path rowid with no `path` row — an index whose file table lost it.
                (3, "ghost", None, 99, 7),
            ],
            _THREAD_FILES,
        )
    )
    o = inv.origin

    assert (o.total, o.first_party, o.external, o.unresolved) == (3, 1, 1, 1)
    assert o.first_party + o.external + o.unresolved == o.total
    assert o.external_roots == ("extern/llama.cpp",)


## @brief The payload sentence names the first-party count, not just the total.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_thread_payload_leads_with_the_first_party_count(tmp_path: Path) -> None:
    """`row_meaning` is what a model quotes, so a correct `origin` beside a sentence naming only
    the total would preserve the wrong attribution — the lesson `lock_roster.row_meaning` already
    carries. It must also state the ANCHOR, because "attributed by spawn site" is what explains a
    row that has an owner and no entry.

    @brief The sentence names origin.first_party and the spawn-site anchor.
    @version 1
    """
    inv = q.thread_roster(
        _thread_db(
            tmp_path, [(1, "poll_loop", 1, 1, 12), (2, "llama_worker", None, 2, 40)], _THREAD_FILES
        )
    )

    assert "origin.first_party" in inv.row_meaning
    assert "SPAWN SITE" in inv.row_meaning
    assert "extern/llama.cpp" in inv.row_meaning
    assert "1 are spawned by THIS" in inv.row_meaning


## @brief The payload must not present a matched-pattern count as the repository's thread count.
## @param tmp_path pytest temp dir.
## @version 1
def test_the_thread_payload_does_not_call_a_matched_count_the_thread_count(tmp_path: Path) -> None:
    """`_roster_meaning` said "Quote origin.first_party as the repository's thread count". On
    Mbed-TLS/mbedtls that is 1 against a true 2: `pthread_create` in the sample TLS server is
    matched, and `_beginthread(TimerProc, 0, NULL)` at `programs/test/benchmark.c:430` is not —
    because no Windows spawn primitive exists in `DEFAULT_SPAWN_PATTERNS` at all, so the
    harvester had no way to see it.

    A graded answer quoted the sentence back: "consistent with the index's count of exactly one
    first-party thread." Confident incompleteness, produced by the PAYLOAD rather than by the
    agent — and under the owner's rule 8 the agent is instructed to trust the index absolutely,
    which makes the falsehood the tool's.

    THE COUNT IS OF SPAWN SITES THIS BUILD'S PATTERNS MATCHED. That is a fact about the pattern
    set, not about the repository, and the pattern set is DECLARABLE — so the sentence can route
    to the fix rather than overstate the fact. Routing beats hedging: "may be incomplete" leaves
    a reader nowhere, `thread_patterns` names the one-line declaration that widens it.

    @brief The thread payload bounds its count by the pattern set and routes to widening it.
    @version 1
    """
    inv = q.thread_roster(
        _thread_db(
            tmp_path, [(1, "poll_loop", 1, 1, 12), (2, "llama_worker", None, 2, 40)], _THREAD_FILES
        )
    )

    assert "as the repository's thread count" not in inv.row_meaning, (
        "the payload overstates a matched-pattern count as the repository's thread count"
    )
    assert "pattern" in inv.row_meaning.lower(), (
        "it must say the count is bounded by the spawn patterns this build knew"
    )
    assert "thread_patterns" in inv.row_meaning, (
        "and must ROUTE to the declaration that widens them, not merely hedge"
    )
    ## The attribution split is NOT weakened — that is this file's original contract.
    assert "origin.first_party" in inv.row_meaning
    assert "SPAWN SITE" in inv.row_meaning


## @brief A pre-35 index says it cannot attribute, instead of reporting zeros as a measurement.
## @param tmp_path pytest temp dir.
## @version 1
def test_an_index_with_no_spawn_sites_refuses_to_pose_as_a_measurement(tmp_path: Path) -> None:
    """THE DISTINCTION THAT MATTERS MORE THAN THE NUMBER. An index built before gh#346 records no
    spawn site, so every thread lands in `unresolved` — and a caller reading `first_party: 0`
    would take that as "this repo spawns no threads of its own", which is a claim about the CODE
    made from a fact about the BUILD. That is the same failure as the absent-table case one level
    up, and the only thing that separates them is the sentence.

    It must also NOT raise: selecting a column a stale index lacks is an `OperationalError`, the
    degradation `has_columns` exists to prevent.

    @brief A spawn-site-less index states its own unattributability.
    @version 1
    """
    inv = q.thread_roster(
        _thread_db(
            tmp_path,
            [(1, "poll_loop", 1, None, None), (2, "worker", None, None, None)],
            _THREAD_FILES,
            with_site=False,
        )
    )

    assert inv.rows == 2, "the threads are still listed — nothing is filtered"
    assert inv.origin.unresolved == 2 and inv.origin.first_party == 0
    assert "predates build version 35" in inv.row_meaning
    assert "not a measurement of this repo" in inv.row_meaning


## @brief An absent thread layer is distinguished from a repo that spawns nothing.
## @param tmp_path pytest temp dir.
## @version 1
def test_an_absent_thread_layer_says_so(tmp_path: Path) -> None:
    """An absent table is a fact about the BUILD and never evidence about the code — and a caller
    that cannot tell the two apart reports a threadless codebase and a pre-layer index
    identically.

    @brief The absent layer is named as absent.
    @version 1
    """
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("CREATE TABLE path (name TEXT);")
    conn.commit()
    conn.close()

    inv = q.thread_roster(db)

    assert inv.threads == ()
    assert "predates the thread layer" in inv.row_meaning
    assert "NOT evidence" in inv.row_meaning


## @brief `OriginSplit.of` classifies the three origin shapes.
## @version 1
def test_origin_split_of_classifies_the_three_shapes() -> None:
    """`''` is a resolved first-party file, a non-empty string is the owning external root, and
    `None` is a member with no resolved file. `None` stays its OWN bucket rather than folding
    into `first_party`, because "we do not know whose this is" is a different claim from "it is
    ours" — folding them is how a coverage figure comes to look healthier than its evidence.

    @brief The classifier maps each origin shape to its bucket.
    @version 1
    """
    split = OriginSplit.of(["", "vendor/a", "vendor/a", "vendor/b", None])

    assert split.total == 5
    assert (split.first_party, split.external, split.unresolved) == (1, 3, 1)
    assert split.external_roots == ("vendor/a", "vendor/b"), "deduplicated and sorted"


## @brief A lossy classification is refused rather than reported.
## @version 1
def test_origin_split_refuses_a_total_its_buckets_do_not_explain() -> None:
    """THE GUARD ON THE GUARD. `OriginSplit` is constructible directly, so a caller can build a
    split whose buckets do not sum — and a payload that reports one is worse than one that
    reports nothing, because it reads as a measurement. `of` is the only supported constructor
    and it refuses.

    Asserted by driving `of` through a subclass whose arithmetic is wrong, which is the only
    way to reach the check: the classifier itself cannot produce a lossy split, and that is
    exactly why the check needs a test — nothing else would ever execute the branch.

    @brief The sum check fires on a lossy classification.
    @version 1
    """

    class _Lossy(OriginSplit):
        """@brief An OriginSplit that drops the external bucket.
        @version 1
        """

        ## @brief Construct a deliberately lossy split.
        ## @param kwargs Field values from `of`.
        ## @return The lossy instance.
        ## @version 1
        def __init__(self, **kwargs: object) -> None:
            """@brief Zero the external count so the buckets cannot sum.
            @version 1
            """
            super().__init__(**{**kwargs, "external": 0})  # type: ignore[arg-type]

    with pytest.raises(AssertionError, match="lost rows"):
        _Lossy.of(["", "vendor/a"])
