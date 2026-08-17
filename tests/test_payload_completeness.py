# SPDX-License-Identifier: MIT
"""A reply must close the loops it opens, because an open loop costs a whole turn.

MEASURED 2026-08-14 on this harness, and it is the premise for every assertion here: an
agent turn re-reads the entire accumulated context, at roughly 55-85k tokens. A payload
block costs a few hundred. So a reply may grow TENFOLD and still win if it removes ONE
call — which inverts the instinct to keep a response tidy, and makes "did the caller have
to ask again" the property worth testing.

THREE DEFECTS OF ONE FAMILY, all found by reading the Q2 and Q4 transcripts of an index-arm
run rather than by any test:

  * A CAPABILITY BEHIND AN OMITTED ARGUMENT. `search(corpus='files')` returned the directory
    rollup only when `text` was empty. Q4 called that corpus four times, always WITH text,
    never saw the inventory, and ran three `find … -type d` calls to rebuild it.
  * A MISS THAT CLAIMED EXHAUSTION. The same corpus answered "definitive empty result … Do
    not retry this query or fall back to guessing" for `doxygen`, while the declared Doxyfile
    sat in `build_meta`. The cell read that correctly as "the index cannot answer" and spent
    four shell calls. We wrote a sentence that handed the question to grep.
  * A NAMED SYMBOL WITH NOWHERE TO GO. `dossier(MBEDTLS_PRIVATE)` reported the gate
    `MBEDTLS_ALLOW_PRIVATE_ACCESS` without saying where it is defined; Q2 grepped that name
    FOUR times rather than making one more index call.

WHY THIS FILE IS SEPARATE. Each fix lives in a different module, and grouping them by module
would scatter the one property they share. The family is the point: every future payload
should be asked the same question these three failed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.mcp_server.tools_query import (
    _gate_definitions,
    QueryTools,
)
from clew.query import doc_scope


## @brief Tools bound to the rich fixture index.
## @param rich_db The fixture index.
## @return Bound tool set.
## @version 1
@pytest.fixture
def tools(rich_db: Path) -> QueryTools:
    """@brief Bind the tool set to the fixture database.
    @return QueryTools.
    @version 1
    """
    return QueryTools(lambda: rich_db, lambda: rich_db.parent)


## @brief The directory inventory rides along whether or not a glob was given.
## @param tools Bound tool set.
## @return None.
## @version 1
def test_the_files_inventory_is_not_hidden_behind_an_omitted_argument(tools: QueryTools) -> None:
    """THE LOAD-BEARING HALF IS THE GLOB CASE. The rollup always answered the no-text call; what
    it never did was accompany a glob, and a glob is what a caller with a question actually
    sends. Q4 sent four (`docs/*`, `Doxyfile`, `doxygen`, `library/*`) and saw the inventory
    zero times.

    ASSERTED ON BOTH ROUTES so the fix cannot be read as moving the capability rather than
    widening it: the no-text call must still carry it.

    Behaviour that appears only when a parameter is OMITTED cannot be described, and what cannot
    be described cannot be predicted by a caller choosing arguments from a description.

    @brief Both files routes carry the inventory.
    @version 1
    """
    for text in ("*.c", "nosuchdirectory/*"):
        reply = tools.search(text, corpus="files")
        assert "inventory" in reply, (
            f"the files corpus answered {text!r} without the directory inventory — a caller "
            f"wanting the breakdown has to ask again, and one extra call costs a full context "
            f"re-read"
        )
        assert reply["inventory"]["directories"], (
            f"the inventory accompanying {text!r} is empty; the fixture has directories, so this "
            f"is the block being attached without being populated"
        )

    ## THE NO-TEXT ROUTE IS THE ROLLUP ITSELF, and must not also carry a copy of it. The first
    ## version of this fix merged the context block into BOTH routes, so the empty-text reply
    ## emitted `directories` and the ~700-character `rollup_meaning` TWICE — measured on a real run,
    ## and the ordinary shape of a context block bolted onto a route that already had one. Tokens
    ## are a graded axis, so duplication is not cosmetic.
    rollup = tools.search("", corpus="files")
    assert rollup["directories"], "the no-text route must still BE the rollup"
    assert "inventory" not in rollup, (
        "the no-text reply already IS the inventory; a second copy duplicates every row and the "
        "whole rollup_meaning sentence"
    )
    assert "doc_scope" in rollup or not doc_scope(tools.db(None)), (
        "doc_scope is genuinely not in the rollup, so it must survive on this route"
    )


## @brief A files miss names its boundary and routes, instead of claiming the index is exhausted.
## @param tools Bound tool set.
## @return None.
## @version 1
def test_a_files_miss_routes_rather_than_claiming_exhaustion(tools: QueryTools) -> None:
    """THE DISTINCTION THIS PINS is between "this corpus does not hold that" and "the index does
    not know that". The first is true and useful; the second is false and sends the caller to the
    shell. The default `_many` wording asserted the second.

    THE NEGATIVE ASSERTION IS THE ONE THAT MATTERS. A note can name the boundary AND still carry
    the old "do not retry" sentence, and the caller would act on the stronger claim — so the test
    requires the exhaustion wording to be ABSENT, not merely the routing to be present.

    @brief An empty glob routes onward.
    @version 1
    """
    reply = tools.search("nosuchdirectory/*", corpus="files")
    note = reply.get("note", "")
    assert note, "an empty files reply must explain itself"
    assert "Do not retry this query" not in note, (
        "a miss in ONE corpus must not be phrased as the index being exhausted — that wording is "
        "what routed a measured cell to four shell calls while the answer sat in build_meta"
    )
    assert "INDEXED SOURCE FILES" in note, "the note must name what this corpus actually holds"
    assert "doc_scope" in note and "inventory" in note, (
        "route, do not disclaim: the note must name where the answer IS"
    )


## @brief Declared doc scope is returned, and its absence is reported as absence.
## @param rich_db The fixture index.
## @return None.
## @version 1
def test_doc_scope_is_empty_rather_than_invented_when_nothing_is_declared(rich_db: Path) -> None:
    """FAIL CLOSED, AND SAY WHICH. The fixture declares no Doxyfile, so {} is the correct answer
    and is a different fact from "this repository has no doc build" — the caller is told the
    index holds no statement, not that no statement exists.

    The populated direction is asserted against the real target in the acceptance run rather
    than here, because a fixture that declares a Doxyfile would be a fixture built to match the
    reader — the standing lesson that a detector agreeing with its own fixture is blind to the
    world.

    @brief An undeclared doc scope reads empty.
    @version 1
    """
    assert doc_scope(rich_db) == {}, (
        "a repository that declares nothing must return an empty mapping, not a fabricated one"
    )


## @brief A gate symbol named in a payload resolves to where it is defined.
## @param rich_db The fixture index.
## @return None.
## @version 1
def test_a_named_gate_symbol_resolves_to_its_definition_sites(rich_db: Path) -> None:
    """ONE CALL, NOT TWO. Naming a symbol the caller now needs, without saying where it lives, is
    an instruction to go looking — and the tool the caller reaches for is grep, because grep is in
    its training distribution millions of times and our tool is not.

    SELF-REFERENCE IS DROPPED, which is not a tidiness rule: a config symbol's own dossier lists
    itself among its gates, and echoing its sites back under a second key would duplicate the
    payload it is already inside while implying a second symbol exists.

    @brief Gate symbols resolve; self-reference does not.
    @version 1
    """
    payload = {"name": "SOMETHING_ELSE", "gated_by": [{"symbol": "SOUND_FINDME"}]}
    resolved = _gate_definitions(rich_db, payload)
    assert "SOUND_FINDME" in resolved, (
        "a gate symbol the index can place must come back placed — leaving it unresolved is the "
        "open loop that cost four greps in a measured cell"
    )
    assert resolved["SOUND_FINDME"][0]["file"], "a resolved site without a file is not a route"

    ## SELF-REFERENCE, and the payload is otherwise identical so nothing else can explain a change.
    itself = {"name": "SOUND_FINDME", "gated_by": [{"symbol": "SOUND_FINDME"}]}
    assert _gate_definitions(rich_db, itself) == {}, (
        "a subject listed among its own gates must not have its sites echoed back"
    )

    ## AND AN UNGATED PAYLOAD GAINS NOTHING, so the block cannot appear as noise on every reply.
    assert _gate_definitions(rich_db, {"name": "X", "gated_by": []}) == {}


## @brief The gate resolver is actually WIRED INTO the dossier payload, not merely importable.
## @param tools Bound tool set.
## @param monkeypatch Pytest patcher.
## @return None.
## @version 1
def test_gate_definitions_are_attached_to_the_payload_not_just_computable(
    tools: QueryTools, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THIS TEST EXISTS BECAUSE A MUTATION SURVIVED. Deleting the call site in `_flatten_subject`
    — the two lines that put `gate_definitions` on the payload — left the whole suite green,
    including the test directly above, because that one calls `_gate_definitions` itself. It
    proved the function works and said nothing about whether anything invokes it.

    That is the accepted-but-unread class this repo keeps rediscovering: a mechanism that is
    correct, tested, and connected to nothing. The unit test cannot see it by construction, so
    the integration assertion has to be separate.

    PATCHED RATHER THAN FIXTURED, deliberately. `rich_db` records ZERO `kconfig_gates` rows —
    its own docstring says the fixture gates nothing on configuration — so no real subject in it
    can produce a `gated_by` list, and a fixture grown to carry one would be a fixture built to
    satisfy this test. What broke was the WIRING, so the wiring is what is asserted: a sentinel
    return must reach the payload.

    @brief The dossier payload carries whatever the gate resolver returns.
    @version 1
    """
    import clew.mcp_server.tools_query as tq

    sentinel = {"SENTINEL_GATE": [{"file": "x.h", "line": 1, "expansion": ""}]}
    monkeypatch.setattr(tq, "_gate_definitions", lambda _db, _payload: sentinel)
    reply = tools.dossier("main")
    ## A MISS ENVELOPE NEVER REACHES `_flatten_subject`, so an unresolvable subject would make
    ## this test pass for the wrong reason under the very mutation it exists to catch. The first
    ## draft named a symbol the fixture does not hold and failed for exactly that reason.
    assert reply.get("found") is not False, "the fixture must resolve this subject"
    assert reply.get("gate_definitions") == sentinel, (
        "the resolver's output must reach the payload — computing it and dropping it is the "
        "failure a unit test of the resolver cannot see"
    )


## @brief A build that turns a macro ON records that the repository ships it OFF.
## @return None.
## @version 1
def test_operator_stated_macros_are_distinguished_from_the_repos_own_defaults() -> None:
    """THE ONLY DEFECT IN THIS FAMILY THAT PRODUCED A WRONG ANSWER RATHER THAN A MISSING ONE.

    Measured on mbedtls: the acceptance build declares `MBEDTLS_THREADING_C` as PREDEFINED so
    doxygen can reach the guarded bodies. The repository ships it COMMENTED OUT. An agent asked
    whether threading is on by default, saw the name in `configured_macros`, and concluded the
    opposite of the truth — on two graded marks.

    `macros` is the UNION of what the operator stated and what the repo's own header defines, and
    the union cannot answer "does the repository ship this ON". `stated_only` is the difference,
    and membership is the whole signal: a name in it ships OFF, a name in `macros` but not in it
    was read from the header and ships ON.

    COMPARED BY BARE NAME, asserted here because both sides are rendered doxygen tokens (`"X"`,
    `"X=1"`) and a token comparison would call those two different macros — the exact drift that
    once labelled every declared macro `undeclared`.

    EMPTY WITHOUT A HEADER is the fail-closed half: with nothing harvested there is no statement
    about the repository's defaults to make, and claiming every stated macro ships OFF would be
    inventing a fact.

    @brief stated_only separates this build's variant from the repository's default.
    @version 1
    """
    from clew.preprocessor import _stated_only

    declared = ('"MBEDTLS_THREADING_C"', '"MBEDTLS_HAVE_ASM"', '"WITH_VALUE=1"')
    harvested = ('"MBEDTLS_HAVE_ASM"', '"WITH_VALUE=7"', '"MBEDTLS_CIPHER_C"')
    assert _stated_only(declared, harvested) == ("MBEDTLS_THREADING_C",), (
        "only the macro the repository's own header does NOT define ships OFF; "
        "`WITH_VALUE` differs only in its VALUE and must not count as operator-only"
    )
    assert _stated_only(declared, ()) == (), (
        "with no header read there is no claim to make about the repository's defaults — "
        "asserting every stated macro ships OFF would invent a fact"
    )
