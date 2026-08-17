# SPDX-License-Identifier: MIT
"""gh#373 — a `#define` is reachable: its expansion, its parameters, its sites.

WHAT WENT WRONG, and why the tests are shaped the way they are. The graded
mbedtls Q2 cell asks about `MBEDTLS_PRIVATE`, which is a MACRO. Every query
surface in this package filters `kind='function'`, so:

  * `search('MBEDTLS_ALLOW_PRIVATE_ACCESS')` returned a *definitive* empty result
    while three `memberdef` rows for that exact name were in the database, and
  * `dossier('MBEDTLS_PRIVATE')` answered about a STRUCT MEMBER — doxygen records
    every field wrapped in `MBEDTLS_PRIVATE(...)` as its own `kind='function'`
    row, so ~2,000 of them shadow the one macro row.

The agent made twenty index calls, fell back to `Read` four times and to `Grep`
once, and then reported the macro layer as an index GAP. It was not: 2,063 of
mbedtls's 2,504 macro rows carry an expansion in `initializer`.

THE SHADOWING IS WHY `test_a_macro_panel_rides_a_function_dossier_of_the_same_name`
EXISTS AND IS THE LOAD-BEARING TEST. The obvious implementation — look up a macro
only when the name resolves to no function — would have stayed dark on the exact
symbol that motivated the change, while passing a test written against a name
that is only a macro. Both shapes are asserted here, deliberately, and the
collision one is the one that would have shipped broken.

@brief Tests for the macro corpus in search and the macro panel on dossier.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.query import dossier, macro_definitions, search, token_hit_counts

## The doxygen `kind` a `#define` carries. Spelled literally here rather than
## imported from `query.macros`: a test that imports the production constant cannot
## catch the constant itself being changed to something doxygen never emits.
MACRO_KIND = "macro definition"


## @brief A minimal doxygen-shaped database holding one function-like macro.
## @param tmp_path_factory pytest's session temp-directory factory.
## @return Path to the built database.
## @version 1
@pytest.fixture(scope="module")
def macro_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """PURPOSE-BUILT rather than added to `rich_db`, for one reason: the parameter
    path. `csample` contains no function-like macro, and inventing one would have
    meant editing a source tree whose file and symbol counts a dozen other tests
    assert. So the object-like half is exercised on the shared fixture (which now
    carries the real expansions out of `csample`) and the function-like half here.

    The parameter row is written the way doxygen writes one for a macro — `defname`
    set, every other column NULL — because that asymmetry is the whole content of
    `_macro_params`. A fixture that filled in `type` and `declname` too would have
    let a `type`-reading implementation pass, and on a real index that
    implementation prints a FABRICATED signature: doxygen's `param` de-duplication
    matches NULL against anything, so `MBEDTLS_PRIVATE`'s `member` row comes back
    wearing `type='unsigned char'`, `declname='mac'`, `array='[16]'` borrowed from
    an unrelated function argument.

    @brief Build a two-macro, one-function database with a real macro parameter row.
    @return Database path.
    @version 1
    """
    db = tmp_path_factory.mktemp("macro") / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT, argsstring TEXT,
            kind TEXT, static INTEGER, bodystart INTEGER, bodyend INTEGER,
            bodyfile_id INTEGER, file_id INTEGER, line INTEGER,
            initializer TEXT, briefdescription TEXT, detaileddescription TEXT
        );
        CREATE TABLE param (
            rowid INTEGER PRIMARY KEY, attributes TEXT, type TEXT, declname TEXT,
            defname TEXT, array TEXT, defval TEXT, briefdescription TEXT
        );
        CREATE TABLE memberdef_param (
            rowid INTEGER PRIMARY KEY, memberdef_id INTEGER, param_id INTEGER
        );
        INSERT INTO path VALUES (1, 'include/private_access.h', 1);
        INSERT INTO path VALUES (2, 'library/common.h', 1);
        INSERT INTO path VALUES (3, 'programs/app.c', 1);
        """
    )
    ## The collision the whole change turns on: one macro named WRAP, and a
    ## `kind='function'` row of the SAME name standing in for the struct members
    ## doxygen synthesises at every use site.
    conn.executemany(
        "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, static, "
        "bodystart, bodyend, bodyfile_id, file_id, line, initializer, "
        "briefdescription, detaileddescription) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                10,
                "WRAP",
                None,
                None,
                MACRO_KIND,
                0,
                None,
                None,
                None,
                1,
                15,
                "hidden_##member",
                "",
                "",
            ),
            (
                11,
                "WRAP",
                "int ctx::WRAP",
                "(nr)",
                "function",
                0,
                None,
                None,
                None,
                1,
                64,
                None,
                "",
                "",
            ),
            (12, "ALLOW", None, None, MACRO_KIND, 0, None, None, None, 2, 132, "", "", ""),
            (13, "ALLOW", None, None, MACRO_KIND, 0, None, None, None, 3, 8, "", "", ""),
            ## gh#403's NEGATIVE CONTROL, and it is the case that decided disclosure over
            ## re-ranking: a name that is a macro AND a real function with a BODY. The C
            ## standard library is full of the shape (`#define isalpha(c) …` beside
            ## `int isalpha(int);`), so a demotion rule keyed on "the name is #define'd"
            ## would describe a macro where a reader asked about a shipping function.
            (14, "DUAL", None, None, MACRO_KIND, 0, None, None, None, 2, 200, "", "", ""),
            (15, "DUAL", "int DUAL", "(void)", "function", 0, 210, 215, 3, 3, 210, None, "", ""),
            ## THE SHAPE A DEMOTION RULE COULD NOT TELL FROM THE ARTEFACT: a macro beside a
            ## DECLARED, never-defined function — a libc wrapper declared in a header whose
            ## implementation is not in scope. Bodiless, like the artefact, and legitimate,
            ## unlike it. `PLATFORM_CALL` carries a brief so the test can assert the
            ## declaration is still what gets DESCRIBED.
            (16, "PLATFORM_CALL", None, None, MACRO_KIND, 0, None, None, None, 2, 300, "", "", ""),
            (
                17,
                "PLATFORM_CALL",
                "int PLATFORM_CALL",
                "(int)",
                "function",
                0,
                None,
                None,
                None,
                2,
                310,
                None,
                "the platform hook",
                "",
            ),
        ],
    )
    conn.execute("INSERT INTO param (rowid, defname) VALUES (500, 'member')")
    conn.execute("INSERT INTO memberdef_param (memberdef_id, param_id) VALUES (10, 500)")
    conn.commit()
    conn.close()
    return db


## @brief A macro's expansion and location are reachable by name.
## @version 1
def test_a_macro_reports_its_expansion_parameters_and_site(macro_db: Path) -> None:
    """@brief The three facts a `#define` has, out of the index.
    @version 1
    """
    defs = macro_definitions(macro_db, "WRAP")
    assert len(defs) == 1
    assert defs[0].expansion == "hidden_##member"
    assert defs[0].params == "(member)"
    assert (defs[0].file, defs[0].line) == ("include/private_access.h", 15)


## @brief A parameter name comes from `defname` and drags no borrowed columns with it.
## @version 1
def test_a_macro_parameter_is_the_defname_alone(macro_db: Path) -> None:
    """The negative half. doxygen's `param` de-duplication can staple another
    symbol's `type`/`declname`/`array` onto a macro's parameter row, so a rendered
    parameter list must contain the NAME and nothing that could have been borrowed.

    @brief A macro's parameter list carries no type text.
    @version 1
    """
    params = macro_definitions(macro_db, "WRAP")[0].params
    assert params == "(member)"
    assert "int" not in params and "[" not in params


## @brief Every definition site of a conditionally redefined macro is reported.
## @version 1
def test_every_definition_site_is_reported(macro_db: Path) -> None:
    """The library-vs-application answer IS the several sites. Collapsing them would
    leave the payload technically correct and useless.

    @brief A macro defined twice reports both sites, file-ordered.
    @version 1
    """
    sites = [(d.file, d.line) for d in macro_definitions(macro_db, "ALLOW")]
    assert sites == [("library/common.h", 132), ("programs/app.c", 8)]


## @brief A name that is only a macro gets a dossier instead of nothing.
## @version 1
def test_a_macro_only_name_gets_a_dossier(macro_db: Path) -> None:
    """@brief `dossier` on a macro-only name returns the macro, not None.
    @version 1
    """
    doss = dossier(macro_db, "ALLOW")
    assert doss is not None
    assert doss.kind == MACRO_KIND
    assert [m.file for m in doss.macros] == ["library/common.h", "programs/app.c"]


## @brief The macro panel rides a dossier whose resolved subject is a function.
## @version 1
def test_a_macro_panel_rides_a_function_dossier_of_the_same_name(macro_db: Path) -> None:
    """THE ONE THAT WOULD HAVE SHIPPED BROKEN. `WRAP` resolves to a function row —
    the stand-in for the ~2,000 struct members doxygen names after the macro — so a
    macro lookup gated on "no function of this name" would return nothing here,
    which is precisely the symbol the change exists for.

    @brief A colliding function name does not hide the macro.
    @version 1
    """
    doss = dossier(macro_db, "WRAP")
    assert doss is not None
    assert doss.kind == "function", "the fixture's collision must still resolve to the function"
    assert [m.expansion for m in doss.macros] == ["hidden_##member"]


## @brief A colliding, bodiless identity DISCLOSES that it may be a macro artefact.
## @version 1
def test_a_bodiless_colliding_identity_discloses_the_macro_collision(macro_db: Path) -> None:
    """gh#403. `WRAP` resolves to the struct-member stand-in: `kind='function'`, no body
    extent, one of the rows doxygen writes for a macro appearing in a declarator. The
    graded run measured a reader acting on that headline and going to source 8-9 times per
    run, so the payload says so.

    @brief The collision note fires on a bodiless row whose name is a macro.
    @version 1
    """
    doss = dossier(macro_db, "WRAP")
    assert doss is not None
    assert doss.line_start is None, "the fixture's collision row must have no body extent"
    assert "#define" in doss.macro_collision
    assert "macros" in doss.macro_collision, "the note must name the field that answers"


## @brief A REAL function that shares a macro's name is not disclosed as an artefact.
## @version 1
def test_a_defined_function_sharing_a_macro_name_is_not_flagged(macro_db: Path) -> None:
    """THE NEGATIVE HALF, AND THE REASON THIS IS A NOTE AND NOT A DEMOTION. `DUAL` is a
    macro and also a function with a body — the C library idiom. `function_candidates`
    prefers definition rows, so the chosen row HAS an extent and the disclosure stays
    silent.

    Without this assertion the note would read as "fires whenever a name is `#define`d",
    which is a claim about ~2,000 mbedtls rows AND about every `#define`d libc wrapper,
    and a reader who saw it on both would learn to ignore it.

    @brief A defined function's dossier carries no collision note.
    @version 1
    """
    doss = dossier(macro_db, "DUAL")
    assert doss is not None
    assert doss.kind == "function"
    assert doss.line_start == 210, "the definition-preferring pick must be the body row"
    assert doss.macros, "the macro panel must still report the #define"
    assert doss.macro_collision == ""


## @brief A legitimate bodiless DECLARATION is disclosed, not replaced.
## @version 1
def test_a_declared_undefined_function_is_disclosed_and_still_described(macro_db: Path) -> None:
    """THE ASSERTION THAT MAKES THE DESIGN DECISION AUDITABLE, and it pins a deliberate
    FALSE POSITIVE rather than the absence of one.

    `PLATFORM_CALL` is a macro AND a declared, never-defined function — indistinguishable
    by any structural rule from the doxygen artefact, because `function_candidates` prefers
    definition rows and so the chosen row is bodiless in both cases. A demotion would
    therefore replace this documented declaration with a macro payload, which is why the
    fix is a note.

    So the note DOES fire here, and the payload still describes the DECLARATION — same
    signature, same brief, nothing substituted. That is what makes firing on the legitimate
    case harmless: the reader is told both things are true and chooses.

    @brief A legitimate bodiless declaration keeps its own payload beside the note.
    @version 1
    """
    doss = dossier(macro_db, "PLATFORM_CALL")
    assert doss is not None
    assert doss.macro_collision, "the shape is ambiguous and the payload must say so"
    assert doss.kind == "function", "the note must not change which subject is described"
    assert doss.signature == "int PLATFORM_CALL(int)"
    assert doss.brief == "the platform hook", "the declaration's documentation must survive"


## @brief An unmatched `qualified` selector still returns nothing, not a macro.
## @version 1
def test_an_unmatched_selector_is_not_answered_with_a_macro(macro_db: Path) -> None:
    """A `qualified` argument names ONE function identity. Substituting a macro for
    an identity that does not exist would answer a different question than the one
    asked, and look authoritative doing it.

    @brief A failed disambiguation returns None even when a macro shares the name.
    @version 1
    """
    assert dossier(macro_db, "WRAP", qualified="nothing::like::this") is None


## @brief `search` finds a macro by name.
## @version 1
def test_search_finds_a_macro_by_name(macro_db: Path) -> None:
    """The measured defect verbatim: this query returned a confident zero.

    @brief The gating macro is findable.
    @version 1
    """
    hits = search(macro_db, "ALLOW")
    assert [h.kind for h in hits] == [MACRO_KIND]
    assert hits[0].name == "ALLOW"


## @brief `search` finds a macro by its EXPANSION.
## @version 1
def test_search_finds_a_macro_by_its_expansion(macro_db: Path) -> None:
    """The reverse lookup: a reader who meets a generated identifier finds the macro
    that generates it. This is the half a name-only corpus would have missed.

    @brief A macro is findable by the text it expands to.
    @version 1
    """
    hits = search(macro_db, "hidden_##member")
    assert [h.name for h in hits] == ["WRAP"]
    assert hits[0].kind == MACRO_KIND
    assert hits[0].brief == "hidden_##member", "the expansion stands in for an absent brief"


## @brief The zero-result token diagnosis counts the macro corpus too.
## @version 1
def test_the_token_diagnosis_counts_macros(macro_db: Path) -> None:
    """gh#31's defect reintroduced through a new corpus: a token that matches ONLY a
    macro must not be named as the token that emptied the query. Asserted on the
    expansion, not just the name, because that is what `search` matches.

    @brief A macro-only token is counted, by name and by expansion.
    @version 1
    """
    counts = token_hit_counts(macro_db, ["allow", "hidden_##member", "nosuchtoken"])
    assert counts["allow"] >= 1
    assert counts["hidden_##member"] >= 1
    assert counts["nosuchtoken"] == 0


## @brief The shared fixture's object-like macros carry the expansions csample writes.
## @version 1
def test_the_shared_fixture_reaches_an_object_like_macro(rich_db: Path) -> None:
    """Runs against the SHARED index rather than the purpose-built one, so the macro
    path is exercised on a database assembled by the real pipeline stages. `8` is the
    literal in `tests/data/csample/src/event_bus/event_bus.c`.

    @brief An object-like macro's expansion survives a full fixture build.
    @version 1
    """
    defs = macro_definitions(rich_db, "EVENT_QUEUE_DEPTH")
    assert [d.expansion for d in defs] == ["8"]
    assert [d.params for d in defs] == [""], "an object-like macro has no parameter list"


## @brief An explicit `kind="macro"` selects the MACRO, not the colliding function row.
## @return None.
## @version 1
def test_an_explicit_macro_kind_selects_the_macro_not_the_field_row(macro_db: Path) -> None:
    """gh#404 — THE DEFECT A BENCHMARK CELL PAID FOR TWICE. `_chosen_kind` filtered correctly
    (it returned `"macro"`), and then `_BUILDERS["macro"]` threw the answer away by being
    byte-identical to the function builder. Its comment justified that on the premise that
    `_dossier_conn` "already resolves a macro-only name to `_macro_dossier`" — true, and it names
    its own exception: MACRO-ONLY. `dossier.py`'s guard is `if not cands`, so a name that is ALSO a
    function never reached the macro path however explicitly the caller asked.

    Measured on mbedtls: `MBEDTLS_PRIVATE` has 473 `kind='function'` rows and NONE with a body
    extent, so the pick degenerated to lowest rowid — `include/mbedtls/aes.h`, `line_start: null` —
    and the agent read the file instead. `WRAP` is that shape in fixture form.

    THE ENVELOPE AND THE PAYLOAD USED TO DISAGREE: `subject_kind: "macro"` over a payload saying
    `kind: "function"`. Both halves are asserted here, because a label that contradicts its own
    contents is worse than either being wrong alone.

    @brief kind="macro" builds the macro dossier.
    @version 1
    """
    from clew.query import subject_dossier

    ## BOTH SPELLINGS, and the aliased one is what the benchmark cell actually sent: it read
    ## `kind: "macro definition"` off a search row and passed it straight back. Testing only the
    ## canonical `"macro"` would leave the alias mapped but unwired — the exact state
    ## `_BUILDERS["macro"]` was in.
    for spelling in ("macro", MACRO_KIND):
        built = subject_dossier(macro_db, "WRAP", kind=spelling)
        assert built is not None, f"kind={spelling!r} must resolve — the name defines a macro"
        assert built.kind == "macro", (
            f"kind={spelling!r} must land on the canonical subject kind: {built.kind!r}"
        )
        payload = built.function
        assert payload is not None
        assert payload.kind == MACRO_KIND, (
            f"the payload must BE the macro, not a function row relabelled: {payload.kind!r}"
        )
        assert [m.expansion for m in payload.macros] == ["hidden_##member"]


## @brief An explicit `kind="function"` on the same name still returns the function.
## @return None.
## @version 1
def test_an_explicit_function_kind_still_returns_the_function(macro_db: Path) -> None:
    """THE NEGATIVE HALF, and without it the fix above is indistinguishable from routing every
    colliding name to the macro. `WRAP` is both; asking for the function must still get the
    function, or the kind filter has simply been inverted rather than honoured.

    @brief The other kind is unaffected.
    @version 1
    """
    from clew.query import subject_dossier

    built = subject_dossier(macro_db, "WRAP", kind="function")
    assert built is not None and built.kind == "function"
    payload = built.function
    assert payload is not None
    assert payload.kind == "function", f"asking for the function must yield one: {payload.kind!r}"


## @brief A BARE lookup is unchanged — still the function, still the disclosure.
## @return None.
## @version 1
def test_a_bare_lookup_is_unchanged_by_the_macro_kind_fix(macro_db: Path) -> None:
    """THE REGRESSION GUARD FOR THE DECISION NOT TAKEN. The tempting fix was to change
    `dossier.py`'s `if not cands` guard so a colliding name preferred the macro. That is the
    re-ranking this repo already tried and WITHDREW — the standing disposition for a bare name is a
    NOTE, not a demotion, because the same rule would fire on `#define isalpha(c)` sitting beside a
    legitimate `int isalpha(int);`.

    So the fix was confined to the builder, and this asserts the bare path still behaves exactly as
    the withdrawn-re-ranking tests above require: the function wins and the collision is disclosed.

    @brief The bare-name path did not move.
    @version 1
    """
    doss = dossier(macro_db, "WRAP")
    assert doss is not None
    assert doss.kind == "function", "a BARE lookup must still resolve to the function"
    assert "#define" in doss.macro_collision, "and must still disclose the collision"
