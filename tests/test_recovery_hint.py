# SPDX-License-Identifier: MIT
"""A definitive negative that told the reader to check the wrong thing.

On the 1.1.0 grid, **26.7% of `dossier` calls in the index-bearing arms returned nothing** — 92 of
345. The reply advised checking `target` and whether the index was stale. Both true; neither was
the problem. Of the 237 unanswered subjects, **80.6% were recoverable from what the index already
held**: the qualified form of a bare name (92 of 121), the bare tail of a qualified one (51 of 54),
and — starkest — the file itself for every single one of the 48 subjects that were a FILE PATH.

A model passed `src/inference/llama_cpp_tokenizer.cpp` as a `subject`, the index had scanned that
exact file, and the reply said "not indexed in this repository".

**WHAT THESE TESTS GUARD IS THE DISCIPLINE, NOT THE WORDING.** Three properties:

- a hint names only what was FOUND. 29 of the 121 bare names have no neighbour at all, and a
  fabricated suggestion for those would make every real hint untrustworthy — a reader cannot tell
  a guess from a lookup.
- a hint NEVER turns a miss into a hit. The envelope stays `found: false`; `absence is not
  emptiness` applies to the hint's own output.
- the hint is derived by the SAME rule the `qualified` selector accepts, so it can never advertise
  a form the selector would reject. Deriving advice from one rule and acceptance from another is
  precisely how the served text came to advertise `signature`.

@brief A miss must say what to try instead, and only what it found.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.query._common import matching_identity, qualified_name_of
from clew.query.recovery import bare_tail, looks_like_path, recovery_hint

QUALIFIED = "ServerManager::execute"


##
# @brief An index holding `execute` only as a class member, plus some files.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def index(tmp_path: Path) -> Path:
    """Models the cell traced by hand: `dossier('execute')` called four times against an index
    whose only `execute` is `ServerManager::execute`. `run` is planted as a bare name with no
    qualification so the "nothing to suggest" leg has a real subject, and two paths are planted so
    the file redirection has something to find.

    @brief Seed a memberdef/path DB with one qualified-only name.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, name) VALUES (?, ?)",
        [(1, "src/inference/llama_cpp_tokenizer.cpp"), (2, "src/server/manager.cpp")],
    )
    ## The fuller memberdef shape the real `dossier` path reads — `bodystart`/`bodyend` and
    ## `argsstring` are load-bearing for candidate resolution, not decoration. A thinner fixture
    ## raised `no such column: m.bodystart` at the wire-level test, which is the right failure:
    ## a schema a real query cannot run against is a licence to assert over something that does
    ## not exist.
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 2, 2, 10, 20, ?, '()', '', '', 0)",
        [
            (10, "execute", f"void {QUALIFIED}"),
            (11, "run", "void run"),
        ],
    )
    conn.commit()
    conn.close()
    return db


##
# @brief A bare name held only qualified must be told its qualified form.
# @param index The seeded database.
# @return None.
# @version 1
def test_a_bare_name_held_only_qualified_is_told_the_qualified_form(index: Path) -> None:
    """THE TRACED CELL, REDUCED. `dossier('execute')` was called four times for a symbol the index
    holds as `ServerManager::execute`; 5 of that cell's 16 calls were wasted. The hint must name
    the form and must spell out the call, because "try the qualified name" without the name is
    what the old note already effectively said.

    @brief The qualified form is named.
    @return None.
    @version 1
    """
    hint = recovery_hint(index, "execute")

    assert QUALIFIED in hint, f"the hint did not name the qualified form: {hint!r}"
    assert "qualified=" in hint, f"the hint did not name the parameter to pass it in: {hint!r}"
    assert 'subject="execute"' in hint, f"the hint did not keep `subject` bare: {hint!r}"


##
# @brief The hinted form must be one the selector actually accepts.
# @param index The seeded database.
# @return None.
# @version 1
def test_the_hinted_form_is_one_the_selector_accepts(index: Path) -> None:
    """**THE SEAM THAT ALREADY FAILED ONCE.** The served parameter text used to advertise
    `signature` while the accessor took `qualified`, so obeying the documentation guaranteed a
    miss. A hint is documentation generated at runtime and can fail the same way, so this asserts
    the round trip rather than the wording: the string the hint names must select the row.

    @brief The hint round-trips through the selector.
    @return None.
    @version 1
    """
    hint = recovery_hint(index, "execute")
    named = next(part.strip("'\"") for part in hint.split() if QUALIFIED in part).strip("'\",.`")

    cands = [(10, f"void {QUALIFIED}")]
    assert qualified_name_of("execute", f"void {QUALIFIED}") == named, (
        f"the hint named {named!r}, which is not what qualified_name_of derives"
    )
    assert matching_identity("execute", cands, named), (
        f"the hint named {named!r}, which the selector does not accept — the same seam that "
        f"shipped broken in the served parameter text"
    )


##
# @brief A qualified name passed as subject must be told to split it.
# @param index The seeded database.
# @return None.
# @version 1
def test_a_qualified_subject_is_told_to_split_it(index: Path) -> None:
    """51 of 54 such subjects had a resolvable bare tail. The served text does say to keep
    `subject` bare; the model did not, and the miss reply never mentioned it.

    @brief A qualified subject gets the split advice.
    @return None.
    @version 1
    """
    hint = recovery_hint(index, QUALIFIED)

    assert 'subject="execute"' in hint, f"the hint did not name the bare tail: {hint!r}"
    assert f'qualified="{QUALIFIED}"' in hint, f"the hint did not name the selector: {hint!r}"


##
# @brief A file path passed as subject must be redirected to the files corpus.
# @param index The seeded database.
# @param subject The path as the model passed it.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "subject",
    [
        pytest.param("./src/inference/llama_cpp_tokenizer.cpp", id="dot-prefixed"),
        pytest.param("llama_cpp_tokenizer.cpp", id="basename-only"),
        pytest.param("inference/llama_cpp_tokenizer.cpp", id="partial-prefix"),
    ],
)
def test_a_file_path_subject_is_redirected(index: Path, subject: str) -> None:
    """**48 OF 48 — THE ONLY MODE THAT WAS FULLY RECOVERABLE.** Every path the model passed was a
    file this index had scanned.

    THE DESTINATION CHANGED AND THE PROPERTY DID NOT. This hint used to redirect to
    `search(corpus="files")` and to assert that `search(` appeared in it. That was the best
    available route when it was written and it was a poor one: the `files` corpus returns a path,
    a symbol count and an owning tree, and **no documentation field at all** — so a model sent
    there to find out what a file is for arrived somewhere that cannot say. C1 built the file
    subject, so the hint now names `dossier` on the path the index actually stores, which answers
    in the one call the hint is spent on.

    THE `exact` CASE IS GONE FROM THIS LIST because it no longer reaches a hint: an exact indexed
    path RESOLVES, which is what
    `test_an_exact_indexed_path_resolves_rather_than_being_hinted_at` pins. `partial-prefix`
    replaces it so the suffix leg of `_indexed_path` is still covered — the three spellings here
    are the three the model actually passed, minus the one the index now answers outright.

    @brief A path subject the index holds under a different spelling is redirected.
    @param subject The path.
    @return None.
    @version 1
    """
    hint = recovery_hint(index, subject)

    assert "src/inference/llama_cpp_tokenizer.cpp" in hint, (
        f"the hint must name the path AS THE INDEX STORES IT, so the next call can be made "
        f"verbatim: {hint!r}"
    )
    assert "dossier(" in hint, f"the hint did not name the tool that now answers: {hint!r}"
    assert "search(corpus=" not in hint, (
        f"the `files` corpus carries no documentation field; sending a reader there to learn "
        f"what a file is for is the dead end C1 replaced: {hint!r}"
    )


##
# @brief An exact indexed path is a subject now, so it must not be hinted at.
# @param index The seeded database.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_an_exact_indexed_path_resolves_rather_than_being_hinted_at(
    index: Path, tmp_path: Path
) -> None:
    """THE HINT WAS A STOPGAP AND THIS IS THE FIX IT WAS STANDING IN FOR. 48 of 237 unanswered
    subjects were file paths and every one was a file the index had scanned; a hint turned that
    into two calls, and a subject turns it into none.

    So the correct assertion on an exact path is no longer "the note names the file" — it is that
    there is no note, because there was no miss. A hint still served here would mean the subject
    did not resolve.

    @brief An indexed path answers rather than advising.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: index, lambda: tmp_path)

    reply = tools.dossier("src/inference/llama_cpp_tokenizer.cpp")

    assert reply.get("found") is not False, (
        f"an exact indexed path must resolve as a file subject, not carry a hint: {reply!r}"
    )
    assert reply["subject_kind"] == "file"
    assert recovery_hint(index, "src/inference/llama_cpp_tokenizer.cpp") == "", (
        "a path that resolves must produce no hint — a hint is for a miss, and advertising one "
        "beside a hit is how a reader learns to distrust both"
    )


##
# @brief Nothing must be suggested when the index holds no neighbour.
# @param index The seeded database.
# @param subject A subject with no neighbour.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "subject",
    [
        pytest.param("no_such_symbol_anywhere", id="absent-bare-name"),
        pytest.param("Absent::method", id="absent-qualified"),
        pytest.param("src/does/not/exist.cpp", id="absent-path"),
        pytest.param("run", id="bare-name-with-no-qualification"),
    ],
)
def test_nothing_is_suggested_when_there_is_no_neighbour(index: Path, subject: str) -> None:
    """**29 OF THE 121 BARE-NAME MISSES GENUINELY HAVE NO NEIGHBOUR.** A fabricated suggestion
    there would make every real hint suspect, because a reader cannot tell a lookup from a guess.
    `run` is the sharpest case: it IS in the index, bare and unqualified, so there is no other
    spelling to offer and the hint must stay silent rather than invent one.

    @brief Silence when nothing was found.
    @param subject The subject.
    @return None.
    @version 1
    """
    assert recovery_hint(index, subject) == "", f"a hint was invented for {subject!r}"


##
# @brief An unreadable or absent database must yield no hint rather than raise.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_an_unreadable_database_yields_no_hint(tmp_path: Path) -> None:
    """NEVER RAISES ON THE MISS PATH. This runs while building a reply that has already failed, so
    a database that cannot be opened — the very case `unbuilt_index_message` exists for — must not
    turn a clean negative into a traceback.

    @brief Failures contribute no hint.
    @return None.
    @version 1
    """
    assert recovery_hint(None, "execute") == ""
    assert recovery_hint(tmp_path / "missing.db", "execute") == ""
    junk = tmp_path / "junk.db"
    junk.write_text("this is not a database", encoding="utf-8")
    assert recovery_hint(junk, "execute") == ""
    assert recovery_hint(tmp_path / "missing.db", None) == ""


##
# @brief The path and tail helpers must classify the shapes the grid actually produced.
# @return None.
# @version 1
def test_the_shape_helpers_match_what_the_grid_produced() -> None:
    """Pinned separately because the ORDER of the checks in `_hint_from` depends on them: a
    qualified C++ name contains `::` and must not be read as a path, and a bare `main.c` must be.

    @brief Shape classification.
    @return None.
    @version 1
    """
    assert looks_like_path("src/x.cpp")
    assert looks_like_path("main.c")
    assert not looks_like_path("ServerManager::execute")
    assert not looks_like_path("execute")

    assert bare_tail("ServerManager::execute") == "execute"
    assert bare_tail("pkg.module.function") == "function"
    assert bare_tail("execute") == "execute"


##
# @brief The hint must reach the MCP tool surface on a single miss.
# @param index The seeded database.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_the_hint_reaches_the_mcp_surface_on_a_single_miss(index: Path, tmp_path: Path) -> None:
    """**A HELPER NOTHING CALLS CHANGES NOTHING.** The tests above prove `recovery_hint` works;
    this proves a model receives it. The wire is where the miss rate was measured, so the wire is
    where the fix has to be asserted.

    A FILE PATH is the subject here because, once the measurement was corrected for batch
    attribution, that is the LARGEST mode — 48 of 129 unanswered subjects, and the only one that
    was 100% recoverable: every path the model passed was a file the index had scanned.

    THE SPELLING IS NOW A BASENAME, not the exact path this test used to pass. An exact path
    resolves as a file subject since C1, so it is no longer a miss and can no longer carry a miss
    note — `test_an_exact_indexed_path_resolves_rather_than_being_hinted_at` asserts that
    directly. A basename is still a miss (the probe is an exact match on `path.name`, deliberately,
    so no identifier can collide with it) and is still a spelling the model produced, so the wire
    property this test exists for is unchanged and still has a subject to hold it.

    `found` is asserted still False in the same breath: a hint is an extra field on a negative,
    and turning near misses into hits would be far worse than the silence it replaces.

    @brief The hint is served on a miss.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: index, lambda: tmp_path)

    missed = tools.dossier("llama_cpp_tokenizer.cpp")

    assert missed["found"] is False, "a hint must not turn a miss into a hit"
    assert "src/inference/llama_cpp_tokenizer.cpp" in missed["note"], (
        f"the served miss note does not name the file the index holds, as it holds it: "
        f"{missed['note']!r}"
    )
    assert "dossier(" in missed["note"], (
        f"the note does not name the tool that answers about files: {missed['note']!r}"
    )


##
# @brief A qualified subject must be told to split it, at the wire.
# @param index The seeded database.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_qualified_subject_is_told_to_split_it_at_the_wire(index: Path, tmp_path: Path) -> None:
    """The second-largest mode: 36 unanswered subjects, 34 of which had an indexed bare tail.

    THE ADVICE BECAME THE BEHAVIOUR (C7). This asserted that the wire SERVED the split advice for
    `ServerManager::execute`. It now resolves outright, because the rewrite the hint described —
    tail as `subject`, whole as `qualified` — is deterministic, and replaying all 48 frozen
    `index_only` transcripts showed 93.6% of missed subjects were spellings clew had served
    itself. Charging a round trip to have the model type a rewrite we had already specified was
    the round trip; the hint was a stopgap for it.

    So the assertion is now that there is NO note, because there was no miss. A hint still served
    here would mean the subject did not resolve. The hint itself is NOT deleted — see the two
    tests below for the cases that survive C7 — and `recovery_hint` is still asserted directly by
    `test_a_qualified_subject_is_told_to_split_it`, which calls the library rather than the wire.

    @brief A qualified subject resolves rather than being advised about.
    @return None.
    @version 2
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: index, lambda: tmp_path)

    reply = tools.dossier(QUALIFIED)

    assert reply.get("found") is not False, (
        f"a qualified spelling naming one indexed identity must resolve: {reply!r}"
    )
    assert reply["subject_kind"] == "function"


##
# @brief A qualified spelling whose OWNER is not indexed still misses, and is still advised.
# @param index The seeded database.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_qualified_spelling_with_an_unindexed_owner_still_gets_the_hint(
    index: Path, tmp_path: Path
) -> None:
    """WHAT SURVIVES C7, AND WHY THE HINT IS NOT DELETED. `Nonexistent::execute` has an indexed
    tail and an owner this index does not hold, so the split correctly refuses it — resolving it
    would describe the real `ServerManager::execute` under a class name that does not exist.

    That refusal is exactly where the advice is still worth its bytes: the reader has a spelling
    whose tail IS indexed, and the hint names the bare form to try.

    @brief An unresolvable qualified spelling keeps its hint.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: index, lambda: tmp_path)

    missed = tools.dossier("Nonexistent::execute")

    assert missed["found"] is False, "an owner the index does not hold must stay a miss"
    assert 'subject="execute"' in missed["note"], (
        f"the note did not name the bare tail to pass: {missed['note']!r}"
    )


##
# @brief The hint must reach each entry of a batched miss.
# @param index The seeded database.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_the_hint_reaches_each_entry_of_a_batched_miss(index: Path, tmp_path: Path) -> None:
    """A BATCH NEEDS IT MORE THAN A SINGLE CALL: the model receives up to eight negatives at once
    with no indication which were near misses.

    The absent name is in the same call deliberately — it must stay silent while its neighbour
    gets a hint, which is what proves the hint is per-subject rather than stamped on the envelope.

    The reply key is `results`, not `dossiers` — an earlier version of this test guessed the
    latter and failed with a `KeyError`, which is the right failure for a test asserting over a
    shape it had not checked.

    @brief Batched misses carry per-entry hints.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: index, lambda: tmp_path)

    ## `Nonexistent::execute` rather than `ServerManager::execute` since C7: the latter now
    ## RESOLVES, so it is no longer a miss and cannot hold a miss note. This spelling has an
    ## indexed tail and an owner the index does not hold, which is the shape that still misses —
    ## see `test_a_qualified_spelling_with_an_unindexed_owner_still_gets_the_hint`.
    near = "Nonexistent::execute"
    reply = tools.dossier([near, "no_such_symbol_anywhere"])
    entries = {entry["name"]: entry for entry in reply["results"]}

    assert entries[near]["found"] is False
    assert 'subject="execute"' in entries[near]["note"], (
        f"a batched miss carried no hint: {entries[near]['note']!r}"
    )
    assert "execute" not in entries["no_such_symbol_anywhere"]["note"], (
        "a name with no neighbour was given another subject's hint"
    )


##
# @brief A name that documentation MENTIONS but nothing declares says so.
# @param tmp_path Per-test temporary directory.
# @return None.
# @version 1
def test_a_name_only_documentation_mentions_is_reported_as_such(tmp_path: Path) -> None:
    """MEASURED, replaying the 1.1.0 entropic cells against a rebuilt index.
    `dossier("entropic_free_string")` returns nothing, and that is CORRECT — that checkout
    declares no such function. The name appears four times in doc comments
    (`include/entropic/entropic.h:701`, `:812`, `src/facade/entropic.cpp:4022`, `:4099`), always
    as "frees with `entropic_free_string`", and nowhere as a definition.

    So the agent read the name out of a brief clew served it, asked for it, and was told the index
    holds nothing of that name. Both facts are true and the reply carried only the discouraging
    one. "No symbol declares this" and "this repository has never heard of it" are different
    answers: the first says the documentation is describing an API this build does not contain,
    which is itself the finding.

    `_name_exists` probes `memberdef.name` only, so documentation text was invisible to the hint
    chain. This is the `absence is not emptiness` rule applied to the hint: the index knew the
    name occurred and could not say so.

    ASSERTED ON THE ROUTE, not the wording, like every other hint here — the reply must name the
    corpus that holds the mention, or the reader is told a dead end politely.

    @brief A documented-but-undeclared name is distinguished from an unknown one.
    @return None.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'include/entropic/entropic.h')")
    conn.execute(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (1, 'function', 'entropic_ask', 1, 1, 10, 20, 'char *entropic_ask', '()', "
        "'Ask the engine.', 'The caller frees with entropic_free_string.', 0)"
    )
    conn.commit()
    conn.close()

    hint = recovery_hint(db, "entropic_free_string")

    assert hint, "a name the documentation mentions must not produce a bare negative"
    assert "entropic_free_string" in hint, hint
    assert "search(" in hint, f"the hint must name the corpus holding the mention: {hint!r}"


##
# @brief A name nothing mentions anywhere still gets no hint.
# @param index The seeded database.
# @return None.
# @version 1
def test_a_name_no_documentation_mentions_still_gets_nothing(index: Path) -> None:
    """THE NEGATIVE HALF, and the one that keeps the new branch from firing on everything. A name
    absent from the symbol table AND from every documentation field has nothing to report, and
    this module's standing rule is that a fabricated suggestion makes every real hint suspect.
    """
    assert recovery_hint(index, "totally_absent_identifier_xyz") == ""
