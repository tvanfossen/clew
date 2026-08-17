# SPDX-License-Identifier: MIT
"""gh#21 + gh#31 — an empty result claims only the confidence it has earned.

The thing these tests exist to protect is NOT that empty results are hedged. It
is that they are GRADED. The original wording —

    This is a definitive empty result from the database, NOT an error and NOT a
    malformed call — the database records none. Do not retry this query or fall
    back to guessing.

— is correct and valuable for a genuinely absent symbol, and a change that
softened every empty result would trade one wrong answer for fifteen vague ones.
So the control test here (`test_an_absent_symbol_keeps_the_definitive_note`) is
as load-bearing as the fixes, and so is the one asserting the other fourteen
tools' notes did not move.

The SECOND thing they protect, added after the cost pass: that the grade is delivered in
a couple of sentences rather than a page. The derivation paragraph the notes used to
repeat was 66% of a zero-row `search`, and the two rules pull against each other — so
`test_an_empty_reply_does_not_repeat_the_scope_DERIVATION` asserts the absence AND a byte
ceiling AND that the grade survived, since any one of the three alone is satisfiable by
breaking the other two.

@brief Tests for graded empty-result notes on search and list_files.
@version 2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.mcp_server.tools_query import QueryTools
from clew.query import index_scope, indexed_extensions, token_hit_counts

## The scope provenance a build stamps into `build_meta`. Present here so the empty
## notes have something real to report, and absent from `bare` below so the
## "not recorded" path is exercised too.
SCOPE_ROWS = [
    ("scope.source", "doxygen-guard"),
    ("scope.reason", "doxygen-guard hook scope declared in .pre-commit-config.yaml"),
]

FILES = [
    ("app/src/fsm.py", 1),
    ("app/src/pump.py", 1),
    ("docs/design.md", 1),
    ("[STL]", 1),
    ("app", 2),
]

## (name, brief). `roots` appears in a brief and `resolution` nowhere, which is exactly
## gh#31's measured shape: `_target_from_roots`'s brief is "First usable repo root among
## the client's advertised roots" — it has `roots`, and neither `target` nor `resolution`.
SYMBOLS = [
    ("_target_from_roots", "First usable repo root among the client's advertised roots"),
    ("ensure_target", "Derive the active target for this call"),
    ("run_pump", "Start the pump"),
]

FILE_DOCS = [
    ("app/src/fsm.py", "State machine for the pump controller. Guards against re-entry."),
]


## @brief A minimal index with scope provenance, files, symbols and file docs.
## @param tmp_path Pytest temporary directory.
## @return Path to the database.
## @version 1
@pytest.fixture
def db(tmp_path: Path) -> Path:
    """Hand-built rather than pipeline-built so the SHAPE under test is visible in the
    test: which extensions exist, which token appears in which brief, and whether the
    `file_docs` table is there at all."""
    path = tmp_path / "clew.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO build_meta (key, value) VALUES (?, ?)", SCOPE_ROWS)
    conn.execute("CREATE TABLE path (name TEXT, type INTEGER)")
    conn.executemany("INSERT INTO path (name, type) VALUES (?, ?)", FILES)
    conn.execute(
        "CREATE TABLE memberdef (name TEXT, kind TEXT, briefdescription TEXT, file_id INTEGER)"
    )
    conn.executemany(
        "INSERT INTO memberdef (name, kind, briefdescription, file_id) VALUES (?, 'function', ?, 1)",
        SYMBOLS,
    )
    conn.execute("CREATE TABLE file_docs (file_path TEXT NOT NULL, doc TEXT NOT NULL)")
    conn.executemany("INSERT INTO file_docs (file_path, doc) VALUES (?, ?)", FILE_DOCS)
    conn.commit()
    conn.close()
    return path


## @brief Tools bound to the fixture index.
## @param db The fixture index.
## @return Bound tool set.
## @version 1
@pytest.fixture
def tools(db: Path) -> QueryTools:
    """@brief Bind the tool set to the fixture database.
    @return QueryTools.
    @version 1
    """
    return QueryTools(lambda: db, lambda: db.parent)


## @brief The scope summary reports provenance and the covered shape.
## @param db The fixture index.
## @return None.
## @version 1
def test_index_scope_summarises_provenance_and_shape(db: Path) -> None:
    """This is the information gh#21 says an empty result must carry, and which only
    `status` could produce — a separate call the caller had no reason to make."""
    scope = index_scope(db)
    assert scope.source == "doxygen-guard"
    assert "pre-commit-config" in scope.reason
    ## The synthetic `[STL]` row and the directory row are not files.
    assert scope.file_count == 3
    assert scope.top_levels == ("app", "docs")
    assert scope.extensions == (".md", ".py")


## @brief A genuinely absent single token still gets the full definitive note.
## @param tools The bound tool set.
## @return None.
## @version 1
def test_an_absent_symbol_keeps_the_definitive_note(tools: QueryTools) -> None:
    """THE CONTROL ON THE WHOLE CHANGE. An agent that retries a well-formed query or
    falls back to guessing wastes a turn and may fabricate, so the strong wording has
    to survive where it is earned. If this test ever needs weakening, the fix has
    become a blanket hedge and has lost its point."""
    out = tools.search("zzznosuchtoken")
    assert out["count"] == 0
    note = out["note"]
    assert "definitive" in note
    assert "Do not retry this query or fall back to guessing" in note
    assert "NOT an error and NOT a malformed call" in note
    ## A single token cannot be an over-specified conjunction, so no diagnosis is paid.
    assert "token_hits" not in out


## @brief A multi-token miss is not definitive and names the token that emptied it.
## @param tools The bound tool set.
## @return None.
## @version 1
def test_a_conjunction_miss_names_the_dead_token(tools: QueryTools) -> None:
    """gh#31 verbatim. `roots` matches, `target` matches, `resolution` matches nothing,
    and the OLD reply told the caller not to retry — forbidding the one correct next
    move. Dropping a token that matches nothing is not guessing."""
    out = tools.search("roots target resolution")
    assert out["count"] == 0
    ## `target` matches two symbols by name, `roots` one by brief, `resolution` nothing.
    assert out["token_hits"] == {"roots": 1, "target": 2, "resolution": 0}
    note = out["note"]
    assert "NOT a definitive negative" in note
    assert "Do not retry" not in note, "the correct retry must not be forbidden"
    assert "'resolution'" in note, "the note must name the token that emptied it"
    assert "CONJUNCTION" in note


## @brief A multi-token miss where every token matches advises fewer tokens.
## @param tools The bound tool set.
## @return None.
## @version 1
def test_a_miss_with_every_token_matching_advises_fewer_tokens(tools: QueryTools) -> None:
    """A different diagnosis in KIND, not degree: nothing is deletable because every
    token is pulling its weight, and the problem is that no ONE unit carries them all.
    Naming a guilty token here would be a fabrication."""
    out = tools.search("roots pump")
    assert out["count"] == 0
    assert min(out["token_hits"].values()) > 0
    note = out["note"]
    assert "NOT a definitive negative" in note
    assert "FEWER TOKENS" in note


## @brief The per-token diagnosis is capped, not unbounded.
## @param tools The bound tool set.
## @return None.
## @version 1
def test_the_token_diagnosis_is_capped(tools: QueryTools) -> None:
    """The diagnosis costs one COUNT per token. It is paid only on a call that has
    already returned nothing, and the worst case is bounded by the TOOL rather than by
    the length of whatever sentence a caller pasted in."""
    out = tools.search("a b c d e f g h i j k l")
    assert out["count"] == 0
    assert len(out["token_hits"]) == 8


## THE TWO `list_files` GRADING TESTS LIVED HERE — `test_an_out_of_scope_extension_is_
## certain_with_a_reason` (gh#21's opening `*.c` case) and `test_a_pattern_miss_inside_
## the_scope_is_not_definitive` — and are DELETED with the tool and its grader. They are
## not ported to another tool, deliberately: what they asserted was the three-way grading
## of a FILE GLOB (extension indexed nowhere / indexed but the glob missed / nothing
## indexed at all), which no surviving tool takes. Re-pointing them at `search` would have
## kept two green tests measuring a distinction that no longer exists.
##
## `test_extension_certainty_reads_the_uncapped_list` below SURVIVES and is the reason
## this is safe to remove: `indexed_extensions` is R2, still exported, still asserted to
## differ from the display-truncated `IndexScope.extensions`. The rule that a certainty
## claim must not be derived from a truncated list outlives the tool that first needed it.


## @brief The extension certainty comes from the uncapped extension list.
## @param db The fixture index.
## @return None.
## @version 1
def test_extension_certainty_reads_the_uncapped_list(db: Path) -> None:
    """`IndexScope.extensions` is TRUNCATED for display. Deriving "no `.c` file is
    indexed" from a truncated list would manufacture exactly the false certainty this
    change removes, so the two accessors are separate and this pins that they are."""
    assert index_scope(db, cap=1).extensions == (".md",)
    assert indexed_extensions(db) == (".md", ".py")


## @brief Token counts span both corpora search reads.
## @param db The fixture index.
## @return None.
## @version 1
def test_token_counts_span_symbols_and_file_docs(db: Path) -> None:
    """A token matching only a file's documentation did NOT empty the query, and saying
    otherwise would send the caller to drop the one token that was working."""
    ## 'reentry' is in no symbol name or brief; only in fsm.py's file documentation.
    assert token_hit_counts(db, ["re-entry"]) == {"re-entry": 1}
    assert token_hit_counts(db, ["nowhere"]) == {"nowhere": 0}


## @brief An index with no file-doc corpus says so instead of asserting a negative.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_index_without_the_corpus_is_not_definitive(tmp_path: Path) -> None:
    """An index built before build 23 has no `file_docs` table. A detector that cannot
    look must not report a negative — the standing lesson, applied to the newest table.
    Note this is the ONLY case where a single-token miss is graded down."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE path (name TEXT, type INTEGER)")
    conn.execute("INSERT INTO path (name, type) VALUES ('a/b.py', 1)")
    conn.execute(
        "CREATE TABLE memberdef (name TEXT, kind TEXT, briefdescription TEXT, file_id INT)"
    )
    conn.commit()
    conn.close()
    out = QueryTools(lambda: path, lambda: tmp_path).search("deadlock")
    assert out["count"] == 0
    note = out["note"]
    assert "NO file-level documentation corpus" in note
    assert "NOT definitive" in note
    assert "Do not retry" not in note


## The whole-repo tier's real `scope.reason`, abridged only where it lists candidate config
## paths. Present verbatim enough to carry the two things a per-query reply must not repeat:
## the derivation narrative and the `Declare \`x-clew: index_scope:\`` advice.
WHOLE_REPO_REASON = (
    "no index_scope is declared for this repo — no doxygen-guard config was found "
    "(searched .doxygen-guard.yaml, .pre-commit-config.yaml (doxygen-guard hook --config "
    "arg), conf/doxygen-guard.yaml) — so the whole repository is the index scope, INCLUDING "
    "any nested git trees, less the paths git ignores and the dot/cache directories. A "
    "Doxyfile, if the repo ships one, still supplies ALIASES and PREDEFINED but no longer "
    "supplies the INPUT: that is a documentation target, not a reasoning boundary. Declare "
    "`x-clew: index_scope:` in .doxygen-guard.yaml, or an `index_scope:` in "
    ".clew.yaml, to let the two differ."
)


## @brief An index whose scope provenance carries the full whole-repo paragraph.
## @param tmp_path Pytest temporary directory.
## @return Path to the database.
## @version 1
@pytest.fixture
def wide_db(tmp_path: Path) -> Path:
    """Separate from `db` because `db`'s reason is one short clause, and a length rule
    asserted against a short string proves nothing. This is the string the mbedtls index
    actually holds."""
    path = tmp_path / "wide.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO build_meta (key, value) VALUES (?, ?)",
        [("scope.source", "whole-repo"), ("scope.reason", WHOLE_REPO_REASON)],
    )
    conn.execute("CREATE TABLE path (name TEXT, type INTEGER)")
    conn.executemany("INSERT INTO path (name, type) VALUES (?, ?)", FILES)
    conn.execute(
        "CREATE TABLE memberdef (name TEXT, kind TEXT, briefdescription TEXT, file_id INTEGER)"
    )
    conn.execute("CREATE TABLE file_docs (file_path TEXT NOT NULL, doc TEXT NOT NULL)")
    conn.commit()
    conn.close()
    return path


## @brief A per-query empty reply carries the covered shape, never the derivation paragraph.
## @param wide_db The index holding the full whole-repo reason.
## @return None.
## @version 1
def test_an_empty_reply_does_not_repeat_the_scope_DERIVATION(wide_db: Path) -> None:
    """MEASURED on the mbedtls acceptance cell: a zero-row `search` cost 2,556 bytes, two
    thirds of it this paragraph emitted TWICE — once as prose in the note, once as
    `scope.reason` in the payload — and it appeared three times across the one cell. Its
    closing sentence tells the reader to declare an `index_scope:`, which is operator
    configuration a mid-session agent cannot act on.

    Asserted as an ABSENCE plus a byte ceiling, because either alone is weak: an absence
    check passes if the paragraph is merely reworded, and a ceiling passes if the grading is
    gutted instead. The grade itself is pinned by the tests above.

    `status.scope.reason` is where it lives now, and `tests/test_freshness.py` pins that
    verbatim — so this cannot be satisfied by deleting the paragraph from the pipeline."""
    out = QueryTools(lambda: wide_db, lambda: wide_db.parent).search("zzznosuchtoken")
    assert out["count"] == 0
    ## The grade survives — this is not a blanket hedge.
    assert "definitive" in out["note"]
    ## The covered SHAPE still rides in the payload: that is what tells a caller whether a
    ## miss could be a scope miss at all.
    assert out["scope"]["source"] == "whole-repo"
    assert out["scope"]["extensions"] == [".md", ".py"]
    body = str(out)
    assert "reason" not in out["scope"], "the derivation belongs to status, not to a query"
    assert "index_scope:" not in body, "declaration advice is operator guidance, not an answer"
    assert "no doxygen-guard config was found" not in body
    assert len(body) < 900, f"an empty search reply grew back to {len(body)} bytes"


## @brief The other list-returning tools keep the strong note unchanged.
## @param tools The bound tool set.
## @return None.
## @version 1
def test_other_corpora_keep_the_undiluted_definitive_note(tools: QueryTools) -> None:
    """The fix is scoped to the corpus whose emptiness can have a cause OTHER than
    absence. A grading applied everywhere would trade one wrong answer for fifteen vague
    ones — which is the failure mode this whole change is a reaction to, inverted.

    THE SCOPE MOVED FROM TOOLS TO CORPORA (gh#372) without moving the line. `search`'s
    SYMBOL corpus is the graded one, because its match is a conjunction a single token can
    empty; both are now the same tool, so what carries the diagnosis is the corpus argument.

    THE PROSE HALF OF THIS TEST IS RETRACTED (gh#404), and the retraction is the point rather
    than a concession. It used to assert prose keeps the undiluted note, on the stated premise
    that "an FTS miss on markdown is a miss". That premise was measured FALSE twice over:
    prose also reads member documentation now, and even before that a token absent from prose
    can sit in three `memberdef` rows of the same index —
    `search(corpus='prose', 'MBEDTLS_ALLOW_PRIVATE_ACCESS')` said "definitive… do not retry"
    about exactly that, and a graded cell obeyed it and ran three greps.

    So prose IS graded now, and this fixture carries no `supplementary_docs` at all — which is
    the ABSENT-CORPUS case, where the honest answer names the absence. That is the same rule
    `_NO_FILE_DOCS` established one corpus over: an index that cannot look must not report a
    negative.

    WHAT THIS TEST STILL GUARDS, undiluted, is the thing it was written for: a surface whose
    emptiness can ONLY mean absence keeps the strong wording. A function with no callers has no
    callers, and weakening that would trade one wrong answer for fifteen vague ones.
    """
    absent = tools.search("no_such_token_anywhere_xyz", corpus="prose")
    assert absent["count"] == 0
    assert "carries NO ingested markdown corpus" in absent["note"], (
        "a corpus that was never built must say so — 'we looked and it is not there' and "
        "'there was nothing to look in' are different facts"
    )
    assert "NOT definitive" in absent["note"]

    ## THE ANTI-DILUTION HALF, on a corpus whose emptiness genuinely cannot mean anything else.
    ## An inventory corpus enumerates a layer; nothing about a token can empty it, so there is
    ## no second cause to grade for and the strong wording is correct.
    inventory = tools.search("no_such_token_anywhere_xyz", corpus="threads")
    note = str(inventory.get("note", ""))
    assert "NOT definitive" not in note, (
        f"an inventory corpus's emptiness IS absence — grading it would be exactly the dilution "
        f"this test exists to prevent: {note!r}"
    )


## @brief A schema-stale index must not call an empty result definitive.
## @param db The fixture index.
## @return None.
## @version 1
def test_a_schema_stale_index_withdraws_the_definitive_claim(db: Path) -> None:
    """THE REPLY CONTRADICTED ITSELF, and the half a caller acts on was the wrong half.

    A schema-stale index is one built by an older pipeline than the server expects, and its
    staleness message says so plainly: it "may be missing whole layers rather than merely being
    out of date". A query against it that finds nothing then attached the standard empty note —
    "a definitive empty result from the database ... Do not retry this query or fall back to
    guessing" — beside that very warning. One payload, two incompatible claims.

    THE CONSUMER-VISIBLE SHAPE is the one this project has hit repeatedly from the other side:
    "the lock layer is empty on my repo" is indistinguishable from "my repo has no locks", and an
    unrebuilt index is the likeliest cause for someone who has just upgraded. Their bug report
    then quotes a zero instead of quoting the reason.

    NOT AN ABSENT-CORPUS DOWNGRADE. gh#393 proposed a second one of those inside `_verdict`, and
    it was built and REVERTED because it hedged nearly every reply — most indexes lacking a layer
    lack it because a fixture never made one. This is different in kind and narrower: it fires
    only when the SAME REPLY already carries a schema staleness axis, which is a measured fact
    about this database rather than an inference from a missing layer, and it fires at the one
    place staleness is stamped rather than inside the per-query verdict.

    BOTH DIRECTIONS ASSERTED. A current index must keep the strong wording — spending it is what
    gh#31 fought for, and a guard that fires on the ordinary case gets switched off.

    @brief The definitive claim is withdrawn on a schema-stale index, and kept on a current one.
    @return None.
    @version 1
    """
    schema_stale = [
        {
            "axis": "schema",
            "message": (
                "This index was built by pipeline version 44 and this server expects 50, so the "
                "index predates the server and may be missing whole layers."
            ),
        }
    ]
    stale = QueryTools(lambda: db, lambda: db.parent, lambda: schema_stale)
    current = QueryTools(lambda: db, lambda: db.parent, list)

    absent = "zzznosuchtoken"
    stale_out = stale.search(absent)
    current_out = current.search(absent)

    assert current_out["note"], "the control must produce a note at all, or it proves nothing"
    assert "definitive" in current_out["note"].lower(), (
        "a CURRENT index must keep the strong wording — a hedge on every reply is a hedge "
        "nobody reads"
    )
    assert "staleness" not in current_out

    assert stale_out.get("staleness"), "the stale reply must carry the axis this fix keys on"
    ## THE CLAIM, not the word: the replacement text says "NOT DEFINITIVE", which contains it.
    ## A test that greps for the substring would fail on the correct fix, which is how a good
    ## fix gets reverted to satisfy a bad assertion.
    assert "is a definitive" not in stale_out["note"].lower(), (
        "a reply whose own staleness block says whole layers may be missing must not also call "
        "its empty result definitive"
    )
    assert "not definitive" in stale_out["note"].lower(), "and must say so positively"
    assert "do not retry" not in stale_out["note"].lower(), (
        "and must not tell the caller that retrying is wrong, when refreshing is the fix"
    )
    assert "refresh" in stale_out["note"].lower(), "it must name the action that resolves it"


## @brief DATA staleness alone must not withdraw the definitive claim.
## @param db The fixture index.
## @return None.
## @version 1
def test_data_staleness_alone_keeps_the_definitive_claim(db: Path) -> None:
    """THE CONTROL ON THE SCHEMA DOWNGRADE, and the one that decides whether it is worth having.

    `data` staleness — some indexed files changed since the build — is the NORMAL state of any
    repository under active development. Nearly every reply in every session of this project has
    carried it. Hedging on it would hedge almost everything, which is precisely the failure that
    made gh#393's absent-corpus downgrade get built and reverted: a warning attached to the
    ordinary case is a warning the reader learns to skip, and then the one that mattered is
    skipped too.

    The two axes say different things and only one undermines the claim. `data` means the index
    describes slightly older code — which does not make "this database holds no such row" false.
    `schema` means the index predates the server and may be missing WHOLE LAYERS — which makes it
    exactly that.

    @brief Data staleness keeps the strong wording; only schema staleness withdraws it.
    @return None.
    @version 1
    """
    data_stale = [{"axis": "data", "message": "3 indexed source file(s) have changed"}]
    out = QueryTools(lambda: db, lambda: db.parent, lambda: data_stale).search("zzznosuchtoken")

    assert out.get("staleness"), "the reply must still carry the data axis"
    assert "is a definitive" in out["note"].lower(), (
        "data staleness is the ordinary state of a live repository; hedging on it would hedge "
        "nearly every reply and spend the strong wording on the common case"
    )
    assert "not definitive" not in out["note"].lower()
