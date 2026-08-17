# SPDX-License-Identifier: MIT
"""The subject-agnostic dossier, the corpus-agnostic search, and the `index` lifecycle.

WHAT THESE COVER THAT NOTHING ELSE DOES. gh#372 collapsed nineteen MCP tools to four, and
every existing test in this suite was written against one of the nineteen — so the tests
that survived the collapse cover the tools that survived it, and cover nothing about the
mechanism that made the collapse possible. That mechanism is one classifier and three
dispatch tables:

  * `resolve_subject` says what KIND a name is, so `dossier` can be pointed at a variable,
    a lock, a class, a requirement, a thread or a config symbol as well as a function;
  * `_BUILDERS` maps a kind to the R2 function that already answered for it;
  * `CORPORA` maps a corpus name to the search or inventory that already answered for it;
  * `INDEX_ACTIONS` maps an action to the lifecycle method that already performed it.

A table is the failure mode a table invites: an entry declared and not implemented, or
implemented and not declared. Every parity assertion below exists for that.

@brief Tests for the four-tool surface: subject resolution, corpora, index actions.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from test_mcp_server import _FakeCtx

from clew import query as q
from clew.mcp_server.tools_query import CORPORA, QueryTools

## The fixture's file-scope mutex: a `static pthread_mutex_t` in `gen/ingot/dm.c` that is
## ALSO a row in the lock layer. Chosen deliberately as the variable-subject fixture
## because it is two subjects at once, which is the case a single-kind resolver gets
## silently wrong.
DM_MUTEX = "dm_mutex"


## @brief A tool set bound to the session index and its real working tree.
## @param rich_db The synthetic index.
## @param repo_root The C source tree it indexes.
## @return The bound tool set.
## @version 1
@pytest.fixture()
def tools(rich_db: Path, repo_root: Path) -> QueryTools:
    """@brief Bind QueryTools to the session fixture.
    @return QueryTools over rich_db.
    @version 1
    """
    return QueryTools(lambda: rich_db, lambda: repo_root)


# ─── the classifier ──────────────────────────────────────────────────────────


def test_every_declared_subject_kind_has_a_probe_and_a_builder() -> None:
    """THE TABLE PARITY, in both directions. A kind in `SUBJECT_KINDS` with no probe can
    never resolve, and a kind with no builder resolves and then raises `KeyError` inside
    the tool. Neither is visible from a payload test, because a kind nothing resolves to
    simply never appears.

    @brief `SUBJECT_KINDS`, `_PROBES` and `_BUILDERS` name the same set.
    @return None.
    @version 1
    """
    from clew.query.subject import _BUILDERS, _PROBES

    assert set(q.SUBJECT_KINDS) == set(_PROBES) == set(_BUILDERS)


def test_a_name_that_is_two_subjects_reports_both(rich_db: Path) -> None:
    """AN ARBITRARY PICK REPORTED AS THE ANSWER is this repo's own recorded failure, one
    level up: three unrelated `_classify` functions collapsed into one node and the
    dossier listed the union of their neighbours at `confidence: exact`. The classifier
    refuses to repeat it — a name that is several things says so.

    `dm_mutex` really is two subjects: a `static pthread_mutex_t` object and a row in the
    lock layer. Both are true and the resolver publishes both.

    @brief A doubly-classified name lists every kind it resolves to.
    @return None.
    @version 1
    """
    kinds = q.resolve_subject(rich_db, DM_MUTEX)
    assert set(kinds) >= {"lock", "variable"}, kinds
    ## PROBE ORDER IS THE DEFAULT, and the richness layer outranks the generic row: a
    ## question about `dm_mutex` is a question about a lock, and the lock subject is the
    ## one that carries the critical sections.
    assert kinds[0] == "lock"


def test_an_unindexed_name_resolves_to_nothing(rich_db: Path) -> None:
    """The negative half. A classifier that returned a kind for every string would make
    `dossier` answer confidently about names the index has never seen.

    @brief An unknown name classifies as no kind at all.
    @return None.
    @version 1
    """
    assert q.resolve_subject(rich_db, "no_such_symbol_anywhere_xyz") == ()


def test_a_file_row_in_compounddef_does_not_classify_as_a_class(tmp_path: Path) -> None:
    """MEASURED ON MBEDTLS: `resolve_subject("threading.c")` returned `('class',)` while
    `dossier` returned nothing at all. doxygen puts more than classes in
    `compounddef` — it registers a row per FILE with `kind='file'` — and `_is_compound` did
    not filter on `CLASS_KINDS` while `lookup_class` did. So the probe said "class" and the
    builder found none.

    A WRONG KIND IS WORSE THAN A MISS, and the disagreement is the specific harm: the caller
    is told the kind exists and handed an empty section, with nothing in the reply saying
    the two halves disagreed. Same shape as the config probe/builder split fixed one commit
    earlier, which is why this is asserted rather than left to the type filter.

    HAND-BUILT, because `rich_db`'s `compounddef` is hand-made and carries NO `kind='file'`
    rows — the fixture does not reproduce this doxygen behaviour, so a test derived from it
    would have passed vacuously while the defect shipped. That is this suite's documented
    second tier: an invariant the whole-graph fixture cannot contain gets its own database.

    @brief A `kind='file'` compound row is not a class subject.
    @return None.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.execute("INSERT INTO path(rowid, name, type) VALUES(1, 'library/threading.c', 1)")
    conn.execute(
        "CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
        "file_id INTEGER, line INTEGER, briefdescription TEXT, prot INTEGER)"
    )
    ## Doxygen's own shape: the FILE row and a real STRUCT row side by side, so the test
    ## proves the filter discriminates rather than merely refusing everything.
    conn.executemany(
        "INSERT INTO compounddef(name, kind, file_id, line, briefdescription, prot) "
        "VALUES(?, ?, 1, 10, '', 0)",
        [("threading.c", "file"), ("real_struct_t", "struct")],
    )
    conn.commit()
    conn.close()

    assert "class" not in q.resolve_subject(db, "threading.c")
    assert q.resolve_subject(db, "real_struct_t") == ("class",)
    ## THE TWO HALVES AGREE on the row that IS a class.
    assert q.dossier(db, "real_struct_t") is not None


# ─── the variable subject: the defect that motivated the whole collapse ──────


def test_a_variable_subject_reports_every_declaration_site_and_its_source(
    tools: QueryTools,
) -> None:
    """THE HEADLINE FIX, and the reason there are four tools instead of nineteen.
    `dossier` resolved through `function_candidates`, which filters `kind='function'`, so
    every non-function subject was unreachable from the tool a model is told to call
    FIRST — and it answered `found: false`, which reads as "not indexed" rather than as
    "this tool cannot describe that".

    Measured live on the public mbedtls index, where it matters most: the whole locking
    API is `mbedtls_mutex_lock` and three siblings, all of them function POINTERS, i.e.
    variables. `dossier('mbedtls_mutex_lock')` returned `found: false` for the symbol
    every locking question in that repository runs through.

    THE DECLARATION LINE IS THE POINT, not the row. doxygen records no `initializer` for
    those pointers, so the binding lives only in the source text at `memberdef.line` —
    which `body_excerpt` could never reach, because a variable has no `bodystart`.

    @brief A variable subject carries its sites and the source line each is declared on.
    @return None.
    @version 1
    """
    reply = tools.dossier(DM_MUTEX, kind="variable")
    assert reply["subject_kind"] == "variable"
    assert reply["sites"], "a variable subject must name where it is declared"
    site = reply["sites"][0]
    assert site["file"].endswith("dm.c")
    assert site["static"] is True
    text = " ".join(site["declaration"]["lines"])
    assert "PTHREAD_MUTEX_INITIALIZER" in text, (
        "the declaration excerpt must carry the initializer, which is the only place the "
        "binding is recorded"
    )

    ## ABSENCE, NOT EMPTINESS. A variable has no body, no callers and no callees, and the
    ## payload says so by not having the fields — an empty `callers: []` here would be a
    ## measurement of something that was never measurable.
    for field in ("callers", "callees", "body", "liveness", "threads"):
        assert field not in reply, f"a variable payload must not carry {field!r}"


def test_the_declaration_excerpt_stops_at_the_statement_terminator(
    rich_db: Path, repo_root: Path
) -> None:
    """The excerpt is a bounded window cut at the first `;`, and `truncated` says when the
    bound was reached first. Pinned because it is a HEURISTIC: a `;` inside a string
    literal ends it early, and the cost of that has to stay "a short excerpt", never a
    wrong file or a wrong line.

    @brief The declaration excerpt covers one statement and reports its own bound.
    @return None.
    @version 1
    """
    import sqlite3

    conn = sqlite3.connect(str(rich_db))
    try:
        rowid = conn.execute(
            "SELECT rowid FROM memberdef WHERE name=? AND kind='variable'", (DM_MUTEX,)
        ).fetchone()[0]
        excerpt = q.declaration_excerpt(conn, rowid, repo_root)
    finally:
        conn.close()

    assert excerpt is not None
    assert excerpt.total_lines == 1, "a one-line declaration must not drag in its neighbours"
    assert excerpt.truncated is False
    assert excerpt.lines[0].rstrip().endswith(";")


# ─── `kind` filters, and never relabels ──────────────────────────────────────


def test_a_kind_filter_never_relabels_another_kind(tools: QueryTools) -> None:
    """AN EXPLICIT KIND IS A FILTER, NOT AN OVERRIDE. A caller that ruled a kind out must
    not be handed the thing it ruled out under the label it asked for — that is the
    silent-substitution failure a dispatching argument invites.

    @brief `kind=` narrows resolution and misses rather than substituting.
    @return None.
    @version 1
    """
    assert tools.dossier("app_run")["subject_kind"] == "function"
    assert tools.dossier("app_run", kind="variable")["found"] is False
    assert tools.dossier("app_run", kind="function")["subject_kind"] == "function"


def test_an_unknown_subject_kind_is_refused_by_name(tools: QueryTools) -> None:
    """Fail closed and list the allowed set, the same contract the declaration loader has.
    A misspelled kind that fell through to the default would answer about a function under
    a heading the caller never asked for.

    @brief An unknown `kind` raises and names the known ones.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="Unknown subject kind"):
        tools.dossier("app_run", kind="functions")


def test_every_kind_search_emits_is_followable_or_names_its_route() -> None:
    """gh#404 — THE PROMISE MADE CHECKABLE. `descriptions/search.json` tells a caller "READ `kind`
    ON EVERY ROW: it is what you pass back — dossier accepts every one of them". It was false for
    EIGHT of the eleven kinds `search` can emit, and a benchmark cell paid a full round trip
    discovering that: it read `kind: "macro definition"` off a row, passed it back exactly as
    instructed, and got `Unknown subject kind`.

    The two vocabularies grew independently — search's labels come from four unlinked places while
    this module's are `SUBJECT_KINDS` — so the fix cannot be "keep them in sync by hand". This test
    is the mechanism instead: every kind search can emit must EITHER resolve (directly or through
    an alias) OR be listed as having no subject with a route named. A new search kind added later
    fails here rather than in a transcript.

    ASSERTED AS AN EXACT PARTITION, not as "most of them work". A kind that is neither followable
    nor explained is the exact state that cost the round trip.

    @brief Every emitted kind either follows or explains itself.
    @return None.
    @version 1
    """
    from clew.query.corpus import CLASS_KINDS
    from clew.query.macros import MACRO_KIND
    from clew.query.models import SUBJECT_KINDS
    from clew.query.subject import _KIND_ALIASES, _KIND_NO_SUBJECT
    from clew.query.symbols import CONFIG_SYMBOL_KIND, SEARCHED_MEMBERDEF_KINDS

    ## Every label `search` can put on a row, gathered from the four places that produce them.
    ## `file` is a bare literal in `_file_candidates`, which is why it is spelled here.
    ## `SEARCHED_MEMBERDEF_KINDS` holds `(kind, rank)` pairs — the rank is a tie-break, not a
    ## label — so only the first element reaches the wire.
    emitted = {
        *(kind for kind, _rank in SEARCHED_MEMBERDEF_KINDS),
        *CLASS_KINDS,
        CONFIG_SYMBOL_KIND,
        MACRO_KIND,
        "file",
    }
    unexplained = {
        kind
        for kind in emitted
        if kind not in SUBJECT_KINDS and kind not in _KIND_ALIASES and kind not in _KIND_NO_SUBJECT
    }
    assert not unexplained, (
        f"search can emit {sorted(unexplained)}, which dossier neither follows nor explains — "
        f"that is the round trip gh#404 measured, waiting to happen again"
    )
    ## And an alias must land on a REAL subject kind, or it converts a clear refusal into a
    ## confusing one.
    for alias, target in _KIND_ALIASES.items():
        assert target in SUBJECT_KINDS, f"alias {alias!r} -> {target!r} is not a subject kind"


def test_a_kind_with_no_subject_refuses_by_naming_the_route(tools: QueryTools) -> None:
    """THREE KINDS CANNOT BE ALIASED and pretending otherwise would be worse than refusing: there
    is no typedef subject, no enumeration subject and no file subject to build. What made the
    original refusal expensive was not that it refused — it was that it stopped there, so the
    caller had to guess where to go next and guessed `grep`.

    So the refusal names the route. Asserted on the ROUTE, not just on the exception, because a
    bare "unknown kind" is what already existed.

    @brief An unfollowable kind refuses with the alternative named.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="corpus='prose'"):
        tools.dossier("app_run", kind="file")
    with pytest.raises(ValueError, match="no dossier subject"):
        tools.dossier("app_run", kind="typedef")


# ─── depth: chain_trace, folded in and bounded ───────────────────────────────


def test_depth_one_carries_no_chain_and_deeper_does(tools: QueryTools) -> None:
    """`chain_trace` was a separate tool and is now a depth. Depth 1 must stay exactly
    what it was — adjacency, no traversal, no extra bytes — or every existing call pays
    for a walk it did not ask for.

    @brief Depth 1 is adjacency; depth > 1 adds the bounded chain.
    @return None.
    @version 1
    """
    from clew import wire

    assert "chain" not in tools.dossier("app_run")
    deep = tools.dossier("app_run", depth=3)
    assert deep["chain"]["nodes"], "a depth > 1 request must actually traverse"
    ## Compared against `chain_trace` ITSELF, not merely checked for shape: the fold's
    ## whole claim is that it reuses that walk — its fan-out taper, its cycle handling and
    ## its non-fuzzy-edges-only rule — rather than being a second traversal with a second
    ## set of bounds to get wrong.
    assert deep["chain"] == wire.one(q.chain_trace(tools.db(), "app_run", max_depth=3))


def test_depth_above_the_bound_is_refused_not_clamped(tools: QueryTools) -> None:
    """REFUSED, for the reason every cap on this surface refuses: a clamped depth answers
    three hops to a request for eight and reports no difference, which is the
    silent-degradation failure the `_limited` disclosures exist to convert into a
    measurement.

    @brief A depth over `MAX_SUBJECT_DEPTH` raises and states the bound.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="depth must be between"):
        tools.dossier("app_run", depth=q.MAX_SUBJECT_DEPTH + 1)
    with pytest.raises(ValueError, match="depth must be between"):
        tools.dossier("app_run", depth=0)


def test_a_subject_with_no_traversal_seed_discloses_it(tools: QueryTools) -> None:
    """A SILENT NO-OP IS WORSE THAN A REFUSAL. Only a function is an endpoint of the call
    and shared-key edges a chain follows, so a lock or a requirement has nothing to walk
    from — and a `depth` argument that quietly did nothing would leave a caller believing
    it had seen three hops of context.

    @brief A depth request on a seedless subject returns `depth_note`.
    @return None.
    @version 1
    """
    reply = tools.dossier(DM_MUTEX, kind="lock", depth=3)
    assert reply["subject_kind"] == "lock"
    assert "chain" not in reply
    assert "only a function is an endpoint" in reply["depth_note"]


# ─── corpora ─────────────────────────────────────────────────────────────────


def test_every_declared_corpus_answers(tools: QueryTools) -> None:
    """Same table-parity argument as the subject kinds, one tool over: a corpus named in
    the dispatch that raises is a documented argument nothing can use.

    @brief Every entry in `CORPORA` returns an attributed envelope.
    @return None.
    @version 1
    """
    for corpus in CORPORA:
        reply = tools.search("dm", corpus=corpus)
        assert isinstance(reply, dict), corpus
        assert "target" in reply, f"{corpus} must name the repository it answered from"


def test_an_inventory_corpus_keeps_its_envelope_rather_than_becoming_rows(
    tools: QueryTools,
) -> None:
    """THE TWO CORPUS SHAPES ARE NOT NORMALISED, deliberately. Flattening an inventory
    into `_many` rows would drop `distinct_mutexes`, `row_meaning` and `origin` — the
    exact fields that stop a row count being reported as a mutex count, which an
    acceptance rubric grades. A tidier uniform shape would have made the graded error
    easier to commit.

    @brief The lock corpus answers with the inventory envelope, not a row list.
    @return None.
    @version 1
    """
    reply = tools.search(corpus="locks")
    for key in ("locks", "rows", "distinct_mutexes", "row_meaning", "origin", "nestings"):
        assert key in reply, f"the lock inventory lost {key!r} on the way through search"
    assert "results" not in reply, "an inventory is not a row list"


# ─── the `index` lifecycle tool ──────────────────────────────────────────────


def test_every_declared_index_action_is_dispatched() -> None:
    """`INDEX_ACTIONS` is read by the refusal message, the description and the dispatch.
    An action declared and not dispatched falls through to the last branch — `stats` —
    and would answer a `cull` request with a graph aggregate.

    @brief Each declared action reaches a distinct branch.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import INDEX_ACTIONS, TARGET_ROUTING_ACTIONS

    assert INDEX_ACTIONS == ("status", "refresh", "targets", "cull", "stats")
    ## A ROUTING action misspelled here would be refused a target it is supposed to honour —
    ## the mirror of the defect the set exists to prevent, and silent in the same way, since
    ## the guard reads the set rather than the dispatch.
    assert set(TARGET_ROUTING_ACTIONS) <= set(INDEX_ACTIONS), (
        "an action can only route if it is dispatched"
    )


@pytest.mark.anyio
async def test_index_stamps_the_action_that_produced_the_reply(tmp_path: Path) -> None:
    """A DISPATCHING TOOL WHOSE RESULT DOES NOT SAY WHICH BRANCH RAN is a payload a caller
    has to identify by shape, and two of these five return a bare mapping. The stamp is
    added in ONE place for exactly that reason — five returns each remembering to do it is
    how one branch ships unstamped.

    `list_targets` returns a LIST, so the wrapping is asymmetric; both shapes are asserted
    because the asymmetry is where a stamp goes missing.

    @brief Every `index` reply carries the `action` that produced it.
    @return None.
    @version 1
    """
    from clew.mcp_server import state as st
    from clew.mcp_server.server import build_server

    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    listed = await state.index(None, action="targets")
    assert listed["action"] == "targets"
    assert listed["results"] == [], "an empty registry lists nothing, in the wrapped shape"

    culled = await state.index(None, action="cull")
    assert culled["action"] == "cull"
    assert "culled" in culled, "the mapping-shaped result must survive the stamp"


@pytest.mark.anyio
async def test_an_unknown_index_action_is_refused_by_name(tmp_path: Path) -> None:
    """Fail closed, list the allowed set, and say where a CODE question goes instead —
    `index` is the tool a model reaches for when it has confused administering the index
    with querying it.

    @brief An unknown `action` raises and names the known ones.
    @return None.
    @version 1
    """
    from clew.mcp_server import state as st
    from clew.mcp_server.server import build_server

    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    with pytest.raises(ValueError, match="Unknown index action"):
        await state.index(None, action="statuses")


@pytest.mark.anyio
async def test_no_index_action_answers_about_a_repository_it_was_not_asked_about(
    tmp_path: Path,
) -> None:
    """THE GUARD THAT WOULD HAVE CAUGHT THE SILENT DROP, and it is structural on purpose.
    `target` was in scope on the `status`, `targets` and `cull` branches of `_index_action`
    and simply never passed on, so `unknown_target_error` was UNREACHABLE from all three —
    there was no error path because nothing on those branches ever resolved the string.

    Measured before the fix: asking `status` about a second repository returned the FIRST
    one's `repo_path`, build version, coverage and staleness, with no error and no mention
    that the target had been dropped. That is the class of defect that voided a 36-cell
    acceptance grid, where every validity term checked that the agent called database tools
    and none checked that the database held the right repository.

    THE ASSERTION IS A DISJUNCTION BECAUSE TWO ANSWERS ARE CORRECT and one is not: an action
    may honour the target, or refuse it by name. What it may not do is answer about something
    else. Written this way the test survives a later decision to thread `target` into
    `status` properly, and it covers any action added to `INDEX_ACTIONS` afterwards without
    being edited — which is what the suite's existing completeness sweep cannot do, because
    `test_mcp_routing` asserts over `TIER1_TOOLS` and `index` is tier 0.

    Its negative half is built in rather than written separately: `refresh` already REPORTS a
    refusal naming the target and `stats` already RAISES one, so two of the five branches must
    pass unchanged. A version of this test that everything failed would not distinguish "the
    three droppers are broken" from "my probe is wrong".

    @brief No index action may silently answer about a target other than the one asked for.
    @return None.
    @version 1
    """
    from clew.mcp_server import state as st
    from clew.mcp_server.server import INDEX_ACTIONS, build_server
    from clew.mcp_server.state import TARGET_SOURCE_FLAG

    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    ## An ADOPTED target is what makes this reproduce the measured defect rather than a
    ## no-target marker: the wrong answer is another repository's status, not an absence.
    adopted = tmp_path / "repo_a"
    adopted.mkdir()
    state.adopt(str(adopted), TARGET_SOURCE_FLAG)

    ## Deliberately never created, so no branch can start a doxygen run over it.
    asked_about = str(tmp_path / "repo_b_never_existed")

    for action in INDEX_ACTIONS:
        try:
            reply = await state.index(_FakeCtx(), action=action, target=asked_about)
        except (ValueError, RuntimeError) as exc:
            assert asked_about in str(exc), (
                f"{action!r} refused, but did not name the target it could not honour"
            )
            continue
        assert asked_about in str(reply), (
            f"index(action={action!r}, target=...) answered without naming the target it "
            f"was asked about — so it silently answered about {adopted} instead"
        )


@pytest.mark.anyio
async def test_the_registry_wide_actions_refuse_a_target_and_still_answer_without_one(
    tmp_path: Path,
) -> None:
    """The chosen resolution, pinned: `status`, `targets` and `cull` REFUSE a supplied target
    rather than honouring it. That is not a stopgap — two of the three have no per-target
    meaning to honour. `cull` is a registry-wide sweep, and `targets` IS the registry
    listing; a target argument on either is a category error, not an unimplemented feature.

    `status` could be threaded properly and deliberately is not yet: doing so needs a
    `target_source` value meaning "named on this call", a decision about what `active` and
    `tier1_registered` report for a routed reply, and a slug→path inverse that does not exist
    (`target_for` is path→slug only). Refusing closes the silent wrong answer without any of
    that.

    THE SECOND HALF IS THE LOAD-BEARING ONE. A refusal that also broke the ordinary
    no-target call would trade a wrong answer for no answer, and a test asserting only the
    raise would call that a fix.

    @brief The registry-wide actions refuse a target by name, and still work without one.
    @return None.
    @version 1
    """
    from clew.mcp_server import state as st
    from clew.mcp_server.server import build_server

    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    ## A REAL directory, so the refusal cannot be the unknown-target path in disguise.
    real = tmp_path / "an_actual_directory"
    real.mkdir()

    for action in ("status", "targets", "cull"):
        with pytest.raises(ValueError) as exc:
            await state.index(_FakeCtx(), action=action, target=str(real))
        message = str(exc.value)
        assert str(real) in message, "the refusal must name the target it will not honour"
        assert action in message, "and which action refused it"

    ## The other half: omitted, every one of them still answers.
    listed = await state.index(_FakeCtx(), action="targets")
    assert listed["results"] == [], "an empty registry still lists, in the wrapped shape"
    culled = await state.index(_FakeCtx(), action="cull")
    assert "culled" in culled, "cull still sweeps the registry"
    reported = await state.index(_FakeCtx(), action="status")
    assert "error" in reported or reported.get("active") is True, (
        "status still reports on the derived target, or says plainly there is none"
    )


## @brief The exported `dossier` must be the any-kind form, and `function_dossier` the narrow one.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_the_exported_dossier_answers_about_a_non_function_subject(rich_db: Path) -> None:
    """`clew.query.dossier` was the FUNCTION-ONLY form while the MCP tool of the same name
    described any indexed kind, so the documented `from clew.query import dossier` returned
    `None` for a requirement, lock, thread, class or variable — and `None` is also what "not
    indexed" looks like, so the weaker function was indistinguishable from an empty index.

    Both directions are asserted. Checking only that `dossier` handles a requirement would
    still pass if `function_dossier` were quietly widened to the same thing, leaving two names
    for one behaviour and nothing recording which the tool layer is a view over.

    @brief `dossier` takes any subject kind; `function_dossier` takes functions.
    @return None.
    @version 1
    """
    req = next(iter(q.all_req_edges(rich_db)), None)
    assert req is not None, "precondition: the fixture must hold at least one requirement edge"

    wide = q.dossier(rich_db, req.req_id)
    assert wide is not None and wide.kind == "requirement", (
        f"the exported `dossier` returned {wide!r} for requirement {req.req_id!r}; it must be "
        f"the any-kind form, matching the MCP tool that shares its name"
    )
    assert q.function_dossier(rich_db, req.req_id) is None, (
        "`function_dossier` must stay the narrow form — if it answers about a requirement too, "
        "the two exported names describe one behaviour and the distinction is undocumented"
    )
