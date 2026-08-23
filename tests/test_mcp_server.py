# SPDX-License-Identifier: MIT
"""R3 tests — the two-tier MCP server over clew.db.

Unit-level only: no live transport, no spawned process. The tests exercise
the pieces the server owns and nothing the SDK owns —
  * tier-0 tools registered at construction, tier-1 ABSENT until activated;
  * the register/unregister helpers add and drop exactly the tier-1 set;
  * every tier-1 wrapper returns JSON-serializable output against the shared
    `rich_db` (session-scoped) and agrees field-for-field with the R2 library;
  * `_activate_tier1` fires `send_tool_list_changed` (asserted through a fake
    ctx/session, never a real one);
  * the target registry's paths, freshness and cull policy, including the
    env-var state-root override (no machine path is ever hardcoded).

The database's PROVENANCE is irrelevant to every assertion here: the wrapper tests
compare a serialization against the R2 call that produced it, and the registry
tests only need a byte-copyable file carrying a current build signature. What the
fixture has to supply is data in the right SHAPES — a function with callers, one
with none, a shared-key neighbour so both `edge_class` values appear, a readable
body, prose to search, and a lock with an acquisition.

@brief Tests for clew.mcp_server (R3).
@version 2
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import logging
import os
import re
import sqlite3
import threading
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="MCP server is an optional extra (pip install -e '.[mcp]')")

from clew.mcp_server import freshness as fr
from clew.mcp_server import state as st
from clew.mcp_server.server import (
    NO_TARGET_ERROR,
    ROOTS_CHANGED_METHOD,
    DocsDbServer,
    build_server,
    register_query_tools,
    unregister_query_tools,
)
from clew.mcp_server.tools_query import TIER1_TOOLS, QueryTools
from clew.scope import SCOPE_FROM_GUARD
from clew.signature import (
    CLEW_BUILD_VERSION,
    write_build_signature,
)

TIER0 = {
    # `build_or_refresh`, `status`, `list_targets` and `cull` WERE FOUR NAMES HERE and are
    # now four `action=` values on one tool (gh#372). A MAJOR-bump act, taken on purpose:
    # they are one subject with five verbs, and four of the five are never called in a
    # session that only asks questions, while every one of them was served on every turn.
    # The METHODS survive on DocsDbServer — only the tool entries collapsed — so
    # `state.status(ctx)` still works and the tests below still call it.
    "index",
    # Tier-0 because the state it fixes — a repo that has declared nothing — is
    # exactly the state in which no tier-1 tool is registered (#54).
    "propose_declaration",
}

## THE FROZEN PUBLIC TOOL NAMES — the semver surface, written out by hand.
##
## README declares MCP tool names as COVERED by semantic versioning, and until this
## existed that promise was unenforceable: every assertion below compared
## `TIER1_TOOLS` against ITSELF, so renaming a tool passed the entire suite. A
## covered surface with only self-referential tests is not covered.
##
## Duplicating the list is the point, not an oversight. A rename now fails HERE,
## which forces the rename to be a deliberate act with a major-version consequence
## rather than an editing accident. The same reasoning as the golden schema snapshot,
## applied to the surface that is actually promised.
##
## THE GUARD WORKED, AND THIS IS WHAT IT LOOKS LIKE WHEN IT FIRES. Five names left in one
## deliberate MAJOR break — `source`, `list_files`, `sections_in`, `locks_held_when`,
## `thread_of` — because `dossier` now returns each of their payloads for a named symbol
## in the call an agent was already making, and a tool whose entire answer is inside
## another tool's answer is fixed prompt every cell pays for and tool calls every cell
## spends. The measured driver: on the mbedtls Q1 cell the index arm made 15.5 tool calls
## per question against the source arm's 8, and 14,935 tokens of tool description were
## billed before a single query ran.
##
## What each deletion rests on, so a reader can re-check rather than trust:
##   `source`          — dossier.body is the same excerpt from the same repo_root; the one
##                       thing it could do that the panel could not is a cap above 120
##                       lines, so `dossier(max_body_lines=)` was added in the same change.
##   `sections_in` /   — dossier.sections / .locks_held run the SAME query (locks.py's
##   `locks_held_when`   `sections_for_rowids` / `locks_held_for_rowids`) against the
##                       RESOLVED IDENTITY's rowids instead of every rowid sharing the
##                       name. Measured on entropic: they disagree on 19 of 97 non-vacuous
##                       comparisons and the by-name tool is HIGHER every time — that is
##                       gh#26 conflation, i.e. the deleted tools were the wrong answer.
##   `thread_of`       — dossier.threads, same relation, same identity scoping.
##   `list_files`      — the owner's call: `ls | grep` beats it for finding files. What
##                       genuinely goes with it is the per-file documented-symbol count;
##                       the scope lives in `status`, the root list in `graph_stats`.
## THE FOUR-TOOL SURFACE (gh#372). A MAJOR-bump act: twelve tier-1 names were REMOVED and
## `dossier` gained a renamed first parameter. Every one of their answers still exists —
## the collapse was of the SURFACE, not of the capability — and the map is:
##
##   callers, callees      -> `dossier`'s own `callers`/`callees` fields, byte-identical.
##                            Measured live: callers("threading_mutex_lock_pthread")
##                            returned 38 rows already present in the dossier reply that
##                            preceded it. An entire tool for a field.
##   resolve_symbol        -> `dossier`'s identity block and its `candidates` list.
##   chain_trace           -> `dossier(depth=2..6)`, which runs chain_trace's own walk.
##   lookup_class          -> `dossier` on the class name (`subject_kind: 'class'`).
##   req_trace             -> `dossier` on the requirement id.
##   runs_under_lock       -> `dossier` on the lock name.
##   kconfig(symbol=…)     -> `dossier` on the config symbol.
##   search_prose          -> `search(corpus='prose')`. A corpus is an argument, not a tool.
##   lock_roster           -> `search(corpus='locks')`, envelope intact.
##   thread_roster         -> `search(corpus='threads')`, envelope intact.
##   kconfig()             -> `search(corpus='config')`, envelope intact.
##   graph_stats           -> `index(action='stats')`, because "how good is this index" is
##                            a question about the TOOL, not about the repository.
##
## THE ROOT CAUSE the removals rest on, confirmed live against the public mbedtls index:
## `dossier` accepted only a FUNCTION, so `dossier('mbedtls_mutex_lock')` returned
## `found: false` for the symbol that repository's entire locking API runs through — it is
## a function POINTER, i.e. a variable. Every other subject type needed its own tool
## BECAUSE the composite would not take it. Nineteen tools were one capability that could
## not be pointed at eight kinds of subject.
##
## NOTE THE MISSING APOSTROPHE two paragraphs up, which is load-bearing: an ODD number of
## apostrophes in a comment INSIDE a multi-line literal makes doxygen read the rest of the
## file as a string. This block once said "that inventory's own acquisitions" and cost this
## file 103 of its 106 memberdef rows — the build still exited 0.
FROZEN_TIER1_NAMES = frozenset({"dossier", "search"})


## @brief A server whose registry lives entirely under a tmp state root.
## @version 1
@pytest.fixture()
def server(tmp_path: Path) -> tuple[object, DocsDbServer]:
    """Construct a FastMCP + DocsDbServer pair isolated from the user's real
    state directory.

    @brief Isolated server fixture.
    @version 1
    """
    return build_server(st.TargetRegistry(tmp_path / "state"))


## @brief One advertised root, shaped like `mcp.types.Root`.
## @version 1
class _FakeRoot:
    """Only `.uri` is read, and `state.root_uri_to_path` is what reads it.

    @brief Fake MCP root.
    @version 1
    """

    ## @brief Construct around a root URI.
    ## @version 1
    def __init__(self, uri: str) -> None:
        self.uri = uri


## @brief Stand-in `ListRootsResult`.
## @version 1
class _FakeRootsResult:
    """@brief Fake roots/list result.
    @version 1
    """

    ## @brief Construct around a root list.
    ## @version 1
    def __init__(self, roots: list[_FakeRoot]) -> None:
        self.roots = roots


## @brief Stand-in `ClientCapabilities` advertising the roots capability.
## @version 1
class _FakeCapabilities:
    """`_roots` gates on `capabilities.roots is not None`, so the truthiness of the
    object is irrelevant and only its presence matters.

    @brief Fake client capabilities.
    @version 1
    """

    ## @brief Construct advertising roots.
    ## @version 1
    def __init__(self, roots: list[str]) -> None:
        self.roots = {"listChanged": True} if roots is not None else None


## @brief Minimal stand-in session recording tool-list-changed notifications.
## @version 1
class _FakeSession:
    """Records each `send_tool_list_changed` call so the notification path can
    be asserted without a live transport.

    @brief Fake MCP session capturing notifications.
    @version 1
    """

    ## @brief Construct with an empty notification log.
    ## @param roots Root URIs this session will serve, or None to refuse.
    ## @version 2
    def __init__(self, roots: list[str] | None = None) -> None:
        self.notifications = 0
        self._roots = roots
        self.roots_calls = 0

    ## @brief Record a tools/list_changed notification.
    ## @version 1
    async def send_tool_list_changed(self) -> None:
        """@brief Count a tool-list-changed notification.
        @version 1
        """
        self.notifications += 1

    ## @brief Serve the fake roots/list response.
    ## @return A ListRootsResult-shaped object.
    ## @version 1
    async def list_roots(self):
        """Counts its calls, because "was the client asked at all?" is a distinct
        assertion from "what did it answer" — a target resolved eagerly must never
        reach here, and only a call count can show that.

        @brief Serve a fake roots/list result.
        @return Object with a `roots` list.
        @version 1
        """
        self.roots_calls += 1
        if self._roots is None:
            raise RuntimeError("this client refuses roots/list")
        return _FakeRootsResult([_FakeRoot(uri) for uri in self._roots])


## @brief Minimal stand-in Context exposing `.session`, `.client_capabilities`, `.protocol_version`.
## @version 2
class _FakeCtx:
    """Exposes `.session`, `.client_capabilities` and `.protocol_version`, which is
    everything the tier-0 code touches.

    `client_capabilities` defaults to None — a client that advertises NOTHING — so
    every pre-existing test keeps describing a session with no roots route, and the
    lazy-resolution tests have to opt in explicitly by passing `roots=`. The default
    matters: if it silently advertised roots, a test asserting "no target" would be
    asserting that a roots fetch failed rather than that none was attempted.

    `protocol_version` defaults to None — "this connection does not say" — because that is
    what `_roots` must treat as permission to try: `roots_request_supported` fails OPEN on
    an unknown revision, so the default keeps every pre-existing test describing a
    connection whose revision is not the thing under assertion.

    @brief Fake MCP request context.
    @version 3
    """

    ## @brief Construct around a fake session, optionally advertising roots.
    ## @param roots Root URI strings to serve from `list_roots`, or None to advertise none.
    ## @param protocol_version Negotiated revision to report, or None for "unstated".
    ## @version 3
    def __init__(self, roots: list[str] | None = None, protocol_version: str | None = None) -> None:
        self.session = _FakeSession(roots)
        self.client_capabilities = _FakeCapabilities(roots) if roots is not None else None
        self.protocol_version = protocol_version


## @brief Collect the currently registered tool names from a FastMCP server.
## @return Set of tool names.
## @version 1
async def _names(mcp) -> set[str]:
    """@brief Registered tool names.
    @return Set of tool names.
    @version 1
    """
    return {t.name for t in await mcp.list_tools()}


# ─── same-name ambiguity: disclosed at the MCP boundary, never in R2 ─────────


## Number of distinct callers wired into the ambiguity fixture below. Bigger than the old
## sample cap it replaces, so a payload that quietly reintroduced one would be visible.
_AMBIGUOUS_CALLERS = 13


## @brief Copy an index and add one name carried by three unrelated functions.
## @param rich_db The built fixture index to copy.
## @param tmp_path Directory to write the copy into.
## @return Path to the copy.
## @version 1
def _with_an_ambiguous_name(rich_db: Path, tmp_path: Path) -> Path:
    """BUILT ON THE REAL FIXTURE, not on a four-table stub, and that is the change gh#372
    forced. The old stub carried `memberdef`, `path` and `call_edges` and nothing else,
    which was enough for the deleted `callers` tool — it read exactly those three. The
    composite dossier reads twenty tables, so a stub would now fail on a missing column
    and the failure would say nothing about ambiguity.

    Three same-named `poll` functions with DISTINCT signatures, so they read as a genuine
    overload rather than as decl/def duality, each reached by every caller through a fuzzy
    `ast_member` edge — which is the shape that makes the rows genuinely shared.

    @brief An index copy containing a deliberately ambiguous name.
    @return Path to the modified copy.
    @version 1
    """
    db = tmp_path / "ambiguous.db"
    db.write_bytes(rich_db.read_bytes())
    conn = sqlite3.connect(str(db))
    base = conn.execute("SELECT MAX(rowid) FROM memberdef").fetchone()[0] + 1
    callers = [
        (base + i, f"caller_{i:02d}", f"void caller_{i:02d}()") for i in range(_AMBIGUOUS_CALLERS)
    ]
    targets = [(base + 100 + i, "poll", f"int Cls{i}::poll()") for i in range(3)]
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, file_id, line, column, "
        "dg_source) VALUES (?, 'function', ?, ?, 1, 1, 1, 'doxygen')",
        callers + targets,
    )
    conn.executemany(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, 'ast_member', 'fuzzy')",
        [(c[0], t[0]) for c in callers for t in targets],
    )
    conn.commit()
    conn.close()
    return db


def test_ambiguity_is_not_disclosed_for_an_unambiguous_name(tools: QueryTools) -> None:
    """The block must be ABSENT on the common path, so a consumer can treat its presence
    as a warning rather than comparing a number against 1 on every call.

    ON `dossier` NOW, NOT ON `callers` (gh#372). The two neighbour tools are gone and
    their rows are this payload's `callers`/`callees` fields, so the disclosure moved with
    them — leaving it behind would have deleted the warning from the whole surface.
    """
    payload = tools.dossier("handle_cloud_command")
    assert "ambiguous" not in payload
    assert payload["subject_kind"] == "function"


def test_the_measurement_is_r2_and_the_dossier_withholds_nothing(
    rich_db: Path, tmp_path: Path
) -> None:
    """THE LOSSY/LOSSLESS SPLIT, and gh#372 moved the line — so this asserts where it is
    now rather than where it was.

    The MEASUREMENT was always lossless and always R2's (`query.name_ambiguity`), and that
    is unchanged. What changed is the TRIMMING: the deleted `callers`/`callees` tools
    capped an ambiguous list at a sample of 8 and disclosed the withholding. The composite
    dossier never capped, and adding a cap in order to warn about it would change what a
    call RETURNS in order to deliver a warning about it. So the dossier discloses and
    withholds nothing; the byte budget stays the only thing that removes rows, and it
    discloses separately in `_limited`.

    Asserted against a name that IS ambiguous, because on an unambiguous one the two
    behaviours are indistinguishable — which is how a cap would slip back in unnoticed.
    """
    from clew import query as q

    db = _with_an_ambiguous_name(rich_db, tmp_path)
    assert q.name_ambiguity(db, "poll") is not None, "premise: the fixture name is ambiguous"

    reply = QueryTools(lambda: db, lambda: tmp_path).dossier("poll")
    assert "ambiguous" in reply, "premise: an ambiguous name must reach the disclosure path"
    assert len(reply["callers"]) == len(q.callers(db, "poll")), (
        "the dossier must return every row R2 returns — the ambiguity block DISCLOSES, "
        "it does not withhold"
    )


def test_ambiguity_disclosure_states_the_spread_it_cannot_resolve(
    rich_db: Path, tmp_path: Path
) -> None:
    """A number, not an adjective. Every one of these rows already says
    `confidence: 'fuzzy'`, and that was measured to be insufficient: fuzzy is a
    three-value enum over a quantity that is a COUNT. The block names how many signatures
    share the name and how many rows arrived through the shared spelling.

    AND THE ADVICE MUST NAME A MOVE THAT EXISTS. It used to say "call resolve_symbol",
    which gh#372 deleted — a disclosure that sends a reader to a tool that is gone is
    worse than silence. The move is now `qualified`, and `candidates` in this same payload
    is where the value comes from.
    """
    db = _with_an_ambiguous_name(rich_db, tmp_path)
    reply = QueryTools(lambda: db, lambda: tmp_path).dossier("poll")

    block = reply["ambiguous"]["callers"]
    assert block["candidates"] == 3
    ## The count is of ROWS IN THE NEIGHBOUR LIST that arrived through the shared name,
    ## not of edges: `_call_edges` collapses one row per neighbour reporting the strongest
    ## evidence, so thirteen callers reaching three namesakes is thirteen shared rows and
    ## not thirty-nine. Pinned at the collapsed number deliberately — the inflated one is
    ## what a reader would over-report.
    assert block["shared_rows"] == _AMBIGUOUS_CALLERS
    assert "qualified" in block["how_to_narrow"]
    assert "resolve_symbol" not in block["how_to_narrow"], (
        "the remedy must not name a tool this surface no longer has"
    )
    assert reply["candidates"], "the identities the block tells the reader to pick between"


# ─── the SDK compatibility shim ──────────────────────────────────────────────


def test_sdk_exposes_everything_the_server_calls() -> None:
    """`_sdk` is the ONE module that imports the SDK, so it is the single point of failure
    for the whole server on an SDK upgrade.

    Asserts what the module PROMISES rather than which version happens to be installed:
    the server class carries the four methods this package calls, and the injected Context
    is a class. A test pinned to a version number would fail on an upgrade that WORKED,
    which is the opposite of useful.

    `SDK_GENERATION` is gone with generation-1 support — a constant that can hold only one
    value states nothing, the same reasoning that removed `req_edges.confidence`."""
    from clew.mcp_server import _sdk

    for method in ("add_tool", "remove_tool", "list_tools", "run_stdio_async"):
        assert hasattr(_sdk.MCPServer, method), f"SDK server class lacks {method}"
    assert isinstance(_sdk.Context, type), "Context must be a class — it is used as an annotation"


def test_probed_module_name_is_derived_from_the_real_import() -> None:
    """The doctor's probe target must come FROM the import, not from a literal beside it.

    A literal is what rotted last time: `_check_mcp_sdk` named `mcp.server.fastmcp` and
    described it as the server's own import line long after `_sdk` took that over, so the
    doctor failed every environment holding the only SDK version a fresh install resolves.
    `MCP_SERVER_MODULE` is now computed from `Context.__module__`, so it cannot name a
    module the package does not actually import."""
    from clew.mcp_server import _sdk

    assert _sdk.Context.__module__.startswith(_sdk.MCP_SERVER_MODULE + "."), (
        "the probed module must be a package prefix of the module Context really came from"
    )
    assert importlib.util.find_spec(_sdk.MCP_SERVER_MODULE) is not None, (
        "the derived name must be importable — the doctor reports on this exact string"
    )


def test_sdk_shim_reaches_the_lowlevel_server_by_the_right_name() -> None:
    """The private attribute holding the low-level server was RENAMED between generations
    (`_mcp_server` → `_lowlevel_server`), and it is the only route to
    `NotificationOptions(tools_changed=True)` — without which a client is told
    `tools.listChanged=False` and never re-reads the tool list when tier-1 appears. That
    is the entire two-tier design, resting on one private attribute.

    Also asserts the failure is LOUD and NAMED: a future generation that drops the hook
    must stop the server, not silently ship without the capability."""
    from clew.mcp_server import _sdk

    mcp = _sdk.MCPServer(name="probe")
    low = _sdk.lowlevel(mcp)
    assert hasattr(low, "create_initialization_options")

    with pytest.raises(AttributeError, match="_sdk needs updating"):
        _sdk.lowlevel(object())


# ─── tier separation ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_every_tool_is_present_at_construction(server) -> None:
    """RETIRED AND INVERTED (gh#7). This asserted that query tools "must not exist before a
    database does", which was the design until it was measured: a tool that does not exist teaches
    a model that the CAPABILITY does not exist, and because tier-1 appeared MID-SESSION the two
    tools most worth reaching for were the two least likely to be in a client's eagerly-loaded
    set. A reporter ran an entire multi-hour session and called neither once.

    The old gate was only defensible while the tools died on an unbuilt index with
    `sqlite3.OperationalError: unable to open database file`. They now refuse with
    `unbuilt_index_message`, which names the call that fixes it — so present-and-refusing beats
    absent, and this asserts the whole surface is there from construction.

    @brief Both tiers are registered at construction, before any index exists.
    @return None.
    @version 1
    """
    mcp, _state = server
    names = await _names(mcp)
    assert TIER0 <= names, "the lifecycle tools must be present"
    assert set(TIER1_TOOLS) <= names, (
        "the query tools must be present too — a conditionally-absent tool is one a model never "
        "learns it has"
    )


@pytest.mark.anyio
## @req REQ-DDB-MCP-003
async def test_register_and_unregister_query_tools(server) -> None:
    """The register helper adds exactly the tier-1 set; the unregister helper
    removes exactly it, leaving tier-0 intact."""
    mcp, state = server
    registered = register_query_tools(mcp, state.tools)
    assert set(registered) == set(TIER1_TOOLS)
    names = await _names(mcp)
    assert set(TIER1_TOOLS) <= names
    assert TIER0 <= names

    removed = unregister_query_tools(mcp)
    assert set(removed) == set(TIER1_TOOLS)
    names = await _names(mcp)
    assert names & set(TIER1_TOOLS) == set()
    assert TIER0 <= names


@pytest.mark.anyio
async def test_unregister_is_tolerant_when_never_registered(server) -> None:
    """Dropping tier-1 when it is not there is a no-op, not an error.

    THE SETUP CHANGED, NOT THE CLAIM (gh#7). Construction now registers tier-1, so "never
    registered" is no longer the construction state — the first unregister removes it and the
    SECOND is the case this test is about. The tolerance property is unchanged.
    """
    mcp, _state = server
    assert set(unregister_query_tools(mcp)) == set(TIER1_TOOLS), (
        "precondition: construction registers tier-1, so the first call removes it"
    )
    assert unregister_query_tools(mcp) == [], "a second removal is a no-op"


@pytest.mark.anyio
## @req REQ-DDB-MCP-003
async def test_activate_tier1_notifies_tool_list_changed(server) -> None:
    """Activation registers the tools AND fires tools/list_changed exactly
    once (asserted through the fake session, never a live transport)."""
    mcp, state = server
    ctx = _FakeCtx()
    names = await state._activate_tier1(ctx)
    assert set(names) == set(TIER1_TOOLS)
    assert state.tier1_active is True
    assert ctx.session.notifications == 1
    assert set(TIER1_TOOLS) <= await _names(mcp)


@pytest.mark.anyio
async def test_retargeting_follows_the_new_repo_without_a_tool_list_change(
    server, tmp_path: Path
) -> None:
    """gh#19, inverted: a server that refused to retarget could not index a second
    repository, so retargeting must WORK — and must not disturb the tool list.

    The tools are bound to `active_db`/`active_repo`, which resolve at call time, so
    they follow the new target with no re-registration. Asserting the tool set is
    UNCHANGED across a retarget is the point: the old `set_target` dropped tier-1 and
    made the caller re-discover it, which is a mid-session capability change for no
    gain."""
    mcp, state = server
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()

    state.adopt(str(repo_a), "--repo")
    assert state.tier1_active is True
    before = await _names(mcp)
    assert set(TIER1_TOOLS) <= before

    state.adopt(str(repo_b), "--repo")
    assert Path(state.active.repo_path) == repo_b, "a retarget must actually retarget"
    assert state.tier1_active is True
    assert await _names(mcp) == before, "a retarget must not change the tool list"
    assert state.tools.repo() == repo_b, "the tools must follow the new target"


@pytest.mark.anyio
async def test_build_or_refresh_without_target_is_an_error(server) -> None:
    """build_or_refresh reports (never raises) when no source supplied a target, and
    does not register tier-1.

    The message must NOT name `set_target`: that tool is gone, and an error telling a
    model to call a nonexistent tool is worse than no error. A benchmark cell has
    already burned a full run writing a page about `No such tool available`."""
    mcp, state = server
    result = await state.build_or_refresh(_FakeCtx())
    assert result["ok"] is False
    assert result["error"] == NO_TARGET_ERROR
    assert "set_target" not in result["error"]
    for source in ("--repo", "CLAUDE_PROJECT_DIR", "roots/list"):
        assert source in result["error"], f"the error must name the {source} source"
    ## The tier-1 absence assertion that stood here was incidental to this test's subject (the
    ## error's wording) and pinned the retired conditional-registration contract (gh#7). Tier-1
    ## presence at construction is asserted by `test_every_tool_is_present_at_construction`.


@pytest.mark.anyio
async def test_build_or_refresh_skips_current_db_and_activates(
    server, rich_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the target's db is already current, no build runs — but tier-1 is
    still activated and the client is notified."""
    mcp, state = server
    repo = tmp_path / "repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    state.active = target
    Path(target.db_path).write_bytes(rich_db.read_bytes())

    def _fail_build(*_args, **_kwargs):
        raise AssertionError("a current db must not be rebuilt without force=True")

    monkeypatch.setattr(state, "_run_build", _fail_build)
    ctx = _FakeCtx()
    result = await state.build_or_refresh(ctx)
    assert result["ok"] is True
    assert result["built"] is False
    assert set(result["tools"]) == set(TIER1_TOOLS)
    assert ctx.session.notifications == 1
    assert set(TIER1_TOOLS) <= await _names(mcp)


@pytest.mark.anyio
async def test_a_stated_option_forces_a_build_on_a_current_index(
    server, rich_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """gh#332, and a mutation control found it untested: deleting `and not options` from the
    skip condition left the whole suite green, so a stated policy would have been silently
    inert on any current index.

    SAME REASONING AS A STATED EXCLUSION, which the skip condition already handles. The
    freshness check asks "does this index describe the code as it is now" — declaring an
    accessor family does not change the answer to that, and yet it must rebuild, because the
    dataflow layer the operator just asked for does not exist yet. Without this an operator
    states their conventions, gets `built: false`, and sees no new edges.
    """
    _, state = server
    repo = tmp_path / "repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    state.active = target
    Path(target.db_path).write_bytes(rich_db.read_bytes())

    seen: list[object] = []

    def _record_build(_target, _doxyfile, _scope=None, _exclude=None, options=None):
        seen.append(options)
        return {"ok": True, "built": True, "output": "stubbed build"}

    monkeypatch.setattr(state, "_run_build", _record_build)

    skipped = await state.build_or_refresh(_FakeCtx())
    assert skipped["built"] is False, "premise: the fixture index is current and skips"
    assert seen == [], "premise: nothing stated, nothing built"

    result = await state.build_or_refresh(_FakeCtx(), options={"entry_patterns": ["app_main"]})

    assert result["built"] is True, "a stated option must force a build"
    assert seen == [{"entry_patterns": ["app_main"]}]


@pytest.mark.anyio
async def test_build_or_refresh_refuses_when_the_process_predates_its_source(
    server, rich_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MEASURED, gh#348: a server process holding build-30 code rebuilt a build-32 index
    AT 30. The `external` stage vanished from the stage list, `external_files` and
    `unresolved_files` left `coverage`, and `status` afterwards reported
    `stale: false, build_version: 30` — perfectly healthy, having just destroyed a layer.

    `force=True` is the case under test on purpose. It is the argument that exists to
    override the freshness skip, and the incident used it; a refusal it could bypass would
    not have prevented anything. So the guard sits ahead of the build decision entirely,
    and this asserts `_run_build` is never reached — not merely that the reply says no.
    """
    _, state = server
    repo = tmp_path / "repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    state.active = target
    Path(target.db_path).write_bytes(rich_db.read_bytes())
    before = Path(target.db_path).read_bytes()

    def _fail_build(*_args, **_kwargs):
        raise AssertionError("a process that predates its source must not write an index")

    monkeypatch.setattr(state, "_run_build", _fail_build)
    monkeypatch.setattr(fr, "PROCESS_SOURCE_FINGERPRINT", "000000000000")

    result = await state.build_or_refresh(_FakeCtx(), force=True)

    assert result["ok"] is False
    assert "restart" in result["error"].lower()
    assert result["code"]["matches_source"] is False
    assert Path(target.db_path).read_bytes() == before, "the refusal must write nothing"


@pytest.mark.anyio
async def test_build_or_refresh_proceeds_when_the_process_matches_its_source(
    server, rich_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE CONTROL, and the half that decides whether the guard above is shippable. A
    refusal that cannot be silent would block every build on every target — strictly worse
    than the downgrade it prevents, and the exact failure mode of every warning this repo
    has had to switch off.

    Same call, same `force=True`, only the fingerprint agreeing: the build must be reached.
    """
    _, state = server
    repo = tmp_path / "repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    state.active = target
    Path(target.db_path).write_bytes(rich_db.read_bytes())

    reached: list[bool] = []

    def _record_build(*_args, **_kwargs):
        reached.append(True)
        return {"ok": True, "built": True, "output": "stubbed build"}

    monkeypatch.setattr(state, "_run_build", _record_build)
    monkeypatch.setattr(fr, "PROCESS_SOURCE_FINGERPRINT", fr.source_fingerprint())

    result = await state.build_or_refresh(_FakeCtx(), force=True)

    assert reached == [True], "a matching process must reach the build"
    assert result["ok"] is True


@pytest.mark.anyio
async def test_build_or_refresh_reports_a_measured_duration(
    server, rich_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """gh#9. An agent asked what refreshing cost had no way to find out — `build_or_refresh`
    returned no timing at all — so it had to estimate, and Q7 mark 7 and Q8 mark 5 missed 9
    of 9 cells across every model tier. Q8 is the worst result in the whole matrix, and the
    losses were LARGEST for the strongest models: a capable model reasons confidently from
    whatever it is given.

    Asserted on the SKIP path deliberately. It is the cheapest possible refresh, so it is
    where a duration would most plausibly have been left out as uninteresting — and a skip
    that reported nothing would read as a missing measurement rather than a cheap one. An
    int, not a string: this is the number a model quotes, and `>= 0` admits the sub-millisecond
    case rather than demanding a fabricated floor."""
    _mcp, state = server
    repo = tmp_path / "repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    state.active = target
    Path(target.db_path).write_bytes(rich_db.read_bytes())
    monkeypatch.setattr(
        state, "_run_build", lambda *_a, **_k: pytest.fail("a current db must not rebuild")
    )

    result = await state.build_or_refresh(_FakeCtx())

    assert result["built"] is False
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0


@pytest.mark.anyio
async def test_status_interprets_an_unresolvable_version_skew(server, tmp_path: Path) -> None:
    """gh#29's cheapest half, end to end through the real `status` tool. An index stamped
    NEWER than the server expects makes `stale: true` unclearable by any action the
    consumer can take — a rebuild re-stamps the same newer version — and it shipped for
    months as two mismatched integers with nothing interpreting them. Observed live at 23
    against a server expecting 17.

    Drives `status` rather than `notices` so the assertion covers the wiring, which is the
    part that was missing rather than the arithmetic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _mcp, state = server
    target = state.registry.register(str(repo))
    state.active = target
    state.target_source = st.TARGET_SOURCE_FLAG
    db = Path(target.db_path)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE memberdef (id INTEGER)")
    conn.commit()
    conn.close()
    write_build_signature(db, version=CLEW_BUILD_VERSION + 6)

    payload = await state.status(_FakeCtx())

    assert payload["stale"] is True
    schema = [n for n in payload["staleness"] if n["axis"] == "schema"]
    assert len(schema) == 1, "an unresolvable skew must be explained, not merely flagged"
    assert "restart" in schema[0]["message"].lower()
    assert "CANNOT CLEAR" in schema[0]["message"]


@pytest.mark.anyio
async def test_status_on_a_current_index_carries_no_staleness_block(
    server, rich_db: Path, tmp_path: Path
) -> None:
    """The control on the wiring, matching the control on the messages. `status` reports
    `stale` unconditionally because that is its job; the INTERPRETATION must be absent when
    there is nothing to interpret, or it becomes a permanent banner and stops being read."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _mcp, state = server
    target = state.registry.register(str(repo))
    state.active = target
    Path(target.db_path).write_bytes(rich_db.read_bytes())

    payload = await state.status(_FakeCtx())

    assert payload["stale"] is False, "premise: the fixture index must be current"
    assert "staleness" not in payload


def test_staleness_notices_without_a_target_is_empty_not_an_error() -> None:
    """The provider runs on the way OUT of every query reply, so it must never be the thing
    that turns a good answer into an error. No target is the state a fresh server is in."""
    assert DocsDbServer().staleness_notices() == []


@pytest.mark.anyio
async def test_stdio_run_advertises_tool_list_changed(
    server, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stdio transport must advertise tools.listChanged=True — a client
    told otherwise has no reason to re-read tools/list when tier-1 appears."""
    import contextlib

    import mcp.server.stdio as stdio_mod

    from clew.mcp_server.server import run_stdio

    mcp_server, _state = server
    captured: dict[str, object] = {}

    @contextlib.asynccontextmanager
    async def _fake_stdio():
        yield (None, None)

    async def _fake_run(_read, _write, options, *args, **kwargs):
        captured["options"] = options

    ## Through `_sdk.lowlevel`, not `mcp_server._mcp_server` directly: that private
    ## attribute is named `_lowlevel_server` on mcp 2.x, so hardcoding the 1.x spelling
    ## made this the ONE test that failed on 2.0 after everything else passed. A test that
    ## reaches past the shim tests a different program than the one that ships.
    from clew.mcp_server._sdk import lowlevel

    monkeypatch.setattr(stdio_mod, "stdio_server", _fake_stdio)
    monkeypatch.setattr(lowlevel(mcp_server), "run", _fake_run)
    await run_stdio(mcp_server)
    caps = captured["options"].capabilities
    assert caps.tools is not None
    ## The SDK renamed this field between generations — `listChanged` on 1.x,
    ## `list_changed` on 2.x — so the test reads whichever exists. Only the assertion
    ## needs this: the SERVER sets `NotificationOptions(tools_changed=True)`, which is
    ## spelled the same on both, so nothing shipped has to care.
    ##
    ## `getattr` with a default would hide a THIRD rename as a pass, so both names are
    ## looked up explicitly and their absence is a failure.
    spellings = [s for s in ("listChanged", "list_changed") if hasattr(caps.tools, s)]
    assert spellings, (
        f"ToolsCapability has neither listChanged nor list_changed: {dir(caps.tools)} — "
        "the SDK renamed the tool-list-changed capability again"
    )
    assert getattr(caps.tools, spellings[0]) is True


def test_build_without_doxyfile_reports_error(server, tmp_path: Path) -> None:
    """A repo with no Doxyfile yields a legible error instead of a traceback,
    and never starts the pipeline."""
    _mcp, state = server
    repo = tmp_path / "bare_repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    result = state._run_build(target, None, False)
    assert result["ok"] is False
    assert "No Doxyfile" in result["error"]


## @brief Trap writes to the real stdout so a leak is observable.
## @return Context manager yielding the capture buffer.
## @version 1
@contextlib.contextmanager
def _captured_stdout():
    """`rich.Console` resolves `sys.stdout` at WRITE time, so redirecting it here is
    enough to catch a progress bar that renders through the process console —
    which is exactly the leak the sink exists to prevent.

    @brief Capture anything written to sys.stdout.
    @version 1
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer


def test_the_build_runs_in_process_and_keeps_stdout_clean(tmp_path: Path) -> None:
    """On this server `sys.stdout` IS the JSON-RPC transport, and the pipeline renders
    progress bars, doxygen warnings and a table summary while it builds. In-process
    those would be spliced into the protocol stream, so every writer goes through
    `_common.active_console` and the build wraps itself in `_common.captured_output`.

    Asserted on the OUTCOME — nothing reached stdout — rather than on the mechanism,
    and against a REAL build: the bars only render when there are files to walk, so a
    mocked pipeline would make this pass without exercising anything.

    The captured output is asserted too, in both halves. Capturing must not mean
    discarding: the summary is what a caller reads back from the tool, and the log is
    where the pipeline explains which scope tier it fell back to and why.

    @brief A real in-process build leaks nothing onto stdout.
    @version 1
    """
    repo = tmp_path / "tiny"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.c").write_text(
        "/** @brief Add two numbers. */\nint add(int a, int b) { return a + b; }\n",
        encoding="utf-8",
    )
    (repo / "Doxyfile").write_text(
        f"INPUT = {repo / 'src'}\nGENERATE_SQLITE3 = YES\nRECURSIVE = YES\n",
        encoding="utf-8",
    )
    target = st.Target(
        repo_path=str(repo), slug="tiny-test", db_path=str(tmp_path / "state" / "clew.db")
    )

    with _captured_stdout() as leaked:
        result = DocsDbServer.__new__(DocsDbServer)._run_build(target, None)

    assert result["ok"] is True, result
    assert leaked.getvalue() == "", "the build must never write to this process's stdout"
    assert result["built"] is True
    assert Path(target.db_path).is_file()
    assert "memberdef" in result["output"], "the build summary must be captured, not discarded"
    assert "scope:" in result["output"], "the pipeline's own explanation must reach the caller"


def test_a_capture_on_one_thread_leaves_another_threads_output_alone() -> None:
    """The build runs on a worker thread while the transport thread writes JSON-RPC
    frames, so the capture has to be scoped to the thread that opened it. A capture
    implemented as a module-level rebind would silence the other thread; a log handler
    added to the shared `clew` logger would swallow the other thread's records
    into this build's result.

    Both halves are asserted from the OTHER thread's side, which is the side that gets
    silently damaged: its console output must still reach stdout, and neither its
    console output nor its log records may appear in the holder's buffer.

    @brief Capturing output is scoped to one thread.
    @version 1
    """
    from clew import _common

    holding = threading.Event()
    release = threading.Event()
    held: dict[str, str] = {}

    def _hold() -> None:
        with _common.captured_output() as buffer:
            holding.set()
            release.wait(5)
            held["text"] = buffer.getvalue()

    thread = threading.Thread(target=_hold)
    thread.start()
    try:
        assert holding.wait(5), "the holding thread never entered the capture"
        with _captured_stdout() as elsewhere:
            _common.active_console().print("frame from another thread")
            _common.logger.warning("log from another thread")
    finally:
        release.set()
        thread.join(5)

    assert "frame from another thread" in elsewhere.getvalue()
    assert held["text"] == "", f"the other thread's output was swallowed: {held['text']!r}"


def test_a_failing_build_reports_the_exception_not_an_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In-process the outcome IS an exception, so the result says so: the type and
    message on `error`, the traceback beside it, and NO `returncode` — a field that
    would name something the call no longer has.

    @brief A build failure surfaces as a reported exception.
    @version 1
    """
    import clew.cli as cli_mod

    repo = tmp_path / "boom"
    repo.mkdir()
    (repo / "Doxyfile").write_text("GENERATE_SQLITE3 = YES\n", encoding="utf-8")
    target = st.Target(
        repo_path=str(repo), slug="boom-test", db_path=str(tmp_path / "state" / "clew.db")
    )

    def _explode(**_kwargs):
        raise RuntimeError("doxygen went missing mid-build")

    monkeypatch.setattr(cli_mod, "build_index", _explode)
    with _captured_stdout() as leaked:
        result = DocsDbServer.__new__(DocsDbServer)._run_build(target, None)

    assert result["ok"] is False
    assert result["built"] is False
    assert "returncode" not in result
    assert result["error"] == "RuntimeError: doxygen went missing mid-build"
    assert "RuntimeError" in result["traceback"]
    assert leaked.getvalue() == ""


def test_the_pipeline_exiting_is_reported_rather_than_escaping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline refuses some inputs with `sys.exit`, which is a BaseException.
    Out of process that was an exit code; in-process, uncaught, it would escape the
    worker thread and read as a build that simply stopped.

    @brief A pipeline `sys.exit` becomes a reported failure.
    @version 1
    """
    import clew.cli as cli_mod

    repo = tmp_path / "refused"
    repo.mkdir()
    (repo / "Doxyfile").write_text("GENERATE_SQLITE3 = YES\n", encoding="utf-8")
    target = st.Target(
        repo_path=str(repo), slug="refused-test", db_path=str(tmp_path / "state" / "clew.db")
    )

    def _refuse(**_kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(cli_mod, "build_index", _refuse)
    result = DocsDbServer.__new__(DocsDbServer)._run_build(target, None)

    assert result["ok"] is False
    assert result["error"].startswith("SystemExit:")


# ─── tier-1 wrappers over the shared synthetic db ─────────────────────────────


## @brief QueryTools bound to the session fixture database + its source tree.
## @version 1
@pytest.fixture()
def tools(rich_db: Path, repo_root: Path) -> QueryTools:
    """@brief Tier-1 tools reading the shared fixture db.
    @version 1
    """
    return QueryTools(lambda: rich_db, lambda: repo_root)


def test_a_response_over_budget_is_trimmed_AND_says_so(tools: QueryTools) -> None:
    """A hub symbol must not blow a model's context, and must not lie about it.

    MEASURED before this cap existed: `dossier` on a symbol with 331 callers
    returned **125,559 bytes** on a real C++ index, and 138 functions on that target
    have more than 50 callers. Nothing bounded the flat one-hop lists — only
    `chain_trace` had a fan-out limit — so the tool a model is told to CALL FIRST was
    the unbounded one.

    Both halves are asserted, and the second matters more. A silent truncation would
    leave a model believing 82 rows were all 331, reasoning confidently from a
    quarter of the evidence — the same failure class as an empty layer read as "no
    dataflow". So `_limited` must name the field, its before/after count, and the
    true total.

    Synthesises the fan-out rather than depending on a fixture symbol having 300
    callers, so the test states its own premise.

    @brief An over-budget response is trimmed and discloses the reduction.
    @version 1
    """
    from clew.mcp_server import tools_query as tq

    payload = {
        "kind": "callers",
        "count": 400,
        "results": [
            {"name": f"caller_{i}", "source": "ast_member", "confidence": "resolved",
             "edge_class": "call", "implementors": [], "padding": "x" * 120}
            for i in range(400)
        ],
    }  # fmt: skip
    assert len(json.dumps(payload)) > tq.RESPONSE_BUDGET_BYTES, "premise: must start over budget"

    cut = tq._shrink_to_budget(payload, ("results",))
    assert len(json.dumps(payload)) <= tq.RESPONSE_BUDGET_BYTES, (
        "the trimmed payload must fit the cap — a cap that can be exceeded is not a cap"
    )
    assert cut == {"results": 400}, f"the ORIGINAL length must be reported, got {cut}"

    block = tq._limited_block("callers", cut["results"], len(payload["results"]), "narrow it")
    assert block["total_available"] == 400, "a model must be told the true total"
    assert block["adjusted"]["callers"].startswith("400 -> "), (
        f"before/after must be explicit, got {block['adjusted']}"
    )
    assert len(payload["results"]) < 400, "something must actually have been dropped"


def test_lock_roster_trims_its_nesting_passenger_rather_than_the_locks_asked_for(
    tools: QueryTools, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`lock_roster` WAS UNBUDGETED UNTIL THE ROUND-3 FOLD, and every `wire.one` envelope
    still is: `_shrink_to_budget` only ever ran inside `_many`. That was survivable while
    the reply was a lock list; folding the nestings in made it live, so the guard went in
    with the fold.

    THE PRIORITY IS THE POINT, not the trimming. The roster is the answer the caller asked
    for; the nestings ride along because they are cheap, and a passenger must never evict
    the payload. A guard that trimmed whichever list was biggest would drop locks from an
    inventory whose entire purpose is to be complete — measured on the public entropic
    index the locks are 103 rows and 23 KB, so "biggest" is always them.

    Synthesises the fan-out rather than relying on a fixture, so the test states its own
    premise: a fixture with two locks can never exercise a 32 KB cap.

    @brief An over-budget roster loses nestings, never locks, and says so.
    @version 1
    """
    from clew.mcp_server import tools_query as tq
    from clew.query.models import LockEntry, LockInventory, LockNestingPair, OriginSplit

    locks = tuple(
        LockEntry(
            name=f"mutex_{i}",
            scope=f"class:Owner{i}",
            kind="std::mutex",
            identity_confidence="high",
            source="declaration",
            file=f"src/subsystem/component_{i}/owner.cpp",
            line=i,
            acquisitions=i,
        )
        for i in range(60)
    )
    nestings = tuple(
        LockNestingPair(
            outer=f"mutex_{i}",
            outer_scope=f"class:Owner{i}",
            inner=f"mutex_{i + 1}",
            inner_scope=f"class:Owner{i + 1}",
            sites=2,
            resolved_sites=1,
            via=f"handoff_{i}",
            holder=f"Owner{i}::publish",
            file=f"src/subsystem/component_{i}/owner.cpp",
            line=i * 7,
        )
        for i in range(300)
    )
    inventory = LockInventory(
        locks=locks,
        rows=len(locks),
        distinct_mutexes=len(locks),
        row_meaning="synthetic",
        origin=OriginSplit.of([""] * len(locks)),
        nestings=nestings,
        nesting_meaning="synthetic",
    )
    monkeypatch.setattr(tq.q, "lock_roster", lambda _db: inventory)

    ## Through `search(corpus='locks')` since gh#372 — the roster is a corpus, not a tool.
    ## The envelope and its budgeting are unchanged, which is the whole claim of that
    ## collapse and is what this test now also pins.
    reply = tools.search(corpus="locks")

    assert len(json.dumps(reply)) <= tq.RESPONSE_BUDGET_BYTES, (
        "a cap that can be exceeded is not a cap"
    )
    assert len(reply["locks"]) == 60, (
        "every lock must survive — the roster is the answer, the nestings are the passenger"
    )
    assert 0 < len(reply["nestings"]) < 300, "the passenger must be the thing that yielded"
    assert reply["_limited"]["total_available"] == 300, "a model must be told the true total"
    assert reply["_limited"]["adjusted"]["nestings"].startswith("300 -> ")


def test_a_response_under_budget_is_left_alone(tools: QueryTools) -> None:
    """The counter-case, and the reason the trim is measured rather than estimated.

    An earlier version spent the budget list-by-list in declaration order, which
    charged small lists for what large ones had consumed: a TWO-element list was cut
    to one while reporting "full response would be about 540 bytes" against a 32 KB
    cap. Nothing under budget may be touched, and no `_limited` block may appear on a
    response that was never limited.

    @brief A small response is returned whole, with no disclosure block.
    @version 1
    """
    from clew.mcp_server import tools_query as tq

    payload = {"kind": "callees", "count": 2, "results": [{"name": "a"}, {"name": "b"}]}
    assert tq._shrink_to_budget(payload, ("results",)) == {}, "nothing should be reported as cut"
    assert len(payload["results"]) == 2, "an under-budget list must be untouched"

    doss = tools.dossier("sensor_poll")
    if doss is not None:
        assert "_limited" not in doss, (
            "a fixture-sized dossier fits the cap; a _limited block here would mean "
            "the trim fires on responses that never needed it"
        )


def test_every_tier1_wrapper_is_json_serializable(tools: QueryTools) -> None:
    """Each wrapper returns plain JSON types (asdict output) — the MCP wire
    format cannot carry dataclasses."""
    results = {
        "dossier": tools.dossier("sensor_poll"),
        "search": tools.search("telemetry"),
    }
    assert set(results) == set(TIER1_TOOLS)
    ## THE SURFACE IS TWO TOOLS AND THE COVERAGE IS NOT (gh#372). Driving only
    ## `TIER1_TOOLS` would now exercise two payload shapes where it used to exercise
    ## fifteen, because the shapes moved INSIDE the two tools as subject kinds and
    ## corpora. Each one is still a distinct serialization that must round-trip, so they
    ## are named here — a collapse that quietly shrank this test's reach would be the
    ## coverage hole that looks exactly like a passing test.
    variants = {
        "dossier:depth": tools.dossier("sensor_poll", depth=3),
        "dossier:batch": tools.dossier(["sensor_poll", "no_such_function_xyz"]),
        "dossier:miss": tools.dossier("no_such_function_xyz"),
        "dossier:class": tools.dossier("nothing_here"),
        "dossier:requirement": tools.dossier("REQ-0621"),
        "dossier:lock": tools.dossier("dm_mutex"),
        "search:prose": tools.search("chime", corpus="prose"),
        "search:threads": tools.search(corpus="threads"),
        ## The fixture repo has no Kconfig, so this exercises the `found: false` reply —
        ## which still has to be a JSON-serialisable envelope rather than a bare None.
        "search:config": tools.search(corpus="config"),
        "search:locks": tools.search(corpus="locks"),
    }
    for name, value in {**results, **variants}.items():
        assert json.loads(json.dumps(value)) == value, f"{name} is not JSON round-trippable"


def test_every_tier1_reply_names_the_target_it_answered_from(
    tools: QueryTools, repo_root: Path
) -> None:
    """gh#22's ADDITION, checked STRUCTURALLY over the whole frozen tool surface rather
    than on a sample.

    A sampled check is what the retracted benchmark grid had: every validity term
    verified that database tools were CALLED and none verified WHICH repository
    answered, so 36 cells recorded `valid=True` against the wrong index. A per-tool
    literal here means adding a tool without its attribution fails, and the reason to
    drive every tool through `TIER1_TOOLS` is that the set is the semver-frozen surface
    — so this cannot silently cover 16 of 17.

    The `is a MISS` cases are included deliberately: the miss reply is where the target
    matters most, because an index of the wrong repository is the commonest reason a
    symbol is not found."""
    calls = {
        "dossier": lambda: tools.dossier("no_such_function_xyz"),
        "search": lambda: tools.search("telemetry"),
    }
    assert set(calls) == set(TIER1_TOOLS), (
        "a tier-1 tool exists with no attribution case here — add it deliberately, "
        "because an unattributed reply is the defect gh#22 closed"
    )
    ## EVERY SUBJECT KIND AND EVERY CORPUS, not just every tool (gh#372). The stamp is
    ## applied by `_answered`, which each branch has to reach — a corpus that returned its
    ## envelope without going through it would be unattributed, and there is now more than
    ## one route through each of the two tools. `SUBJECT_KINDS` and `CORPORA` are driven
    ## rather than listed so a kind or corpus added without attribution fails here.
    from clew.mcp_server.tools_query import CORPORA
    from clew.query import SUBJECT_KINDS

    per_kind = {
        f"dossier:{kind}": (lambda k=kind: tools.dossier("does_not_matter", kind=k))
        for kind in SUBJECT_KINDS
    }
    per_corpus = {
        f"search:{name}": (lambda c=name: tools.search("chime", corpus=c)) for name in CORPORA
    }
    for name, call in {**calls, **per_kind, **per_corpus}.items():
        reply = call()
        assert isinstance(reply, dict), f"{name} must answer with an envelope, never a bare None"
        assert reply.get("target") == str(repo_root), f"{name} does not name its target"


## @brief Strip the gh#22 target stamp, asserting it was there.
## @param reply A tier-1 tool reply.
## @return The reply without `target`, for comparison against an R2 result.
## @version 1
def _payload(reply: dict) -> dict:
    """The R2 parity tests compare a wrapper's output against the library call that
    produced it, and the wrapper now adds one field the library cannot know: which
    repository answered. Popping it here rather than ignoring it means the attribution
    is ASSERTED by every parity test instead of excused by them.

    @brief Remove and assert the target stamp.
    @return The payload without `target`.
    @version 1
    """
    assert "target" in reply, "every query reply must name the target it answered from"
    stripped = dict(reply)
    stripped.pop("target")
    return stripped


def test_wrappers_match_the_r2_library_exactly(
    tools: QueryTools, rich_db: Path, repo_root: Path
) -> None:
    """MVVM: a wrapper is a serialization of the R2 result, never its own
    query — so the payloads must agree field for field.

    The reference side is computed by `tests/wire_expect.py`, a SECOND
    implementation of the two transformations the boundary is allowed: tuple→JSON
    array (gh#8's `implementors`, since JSON has no tuple) and row-level elision
    of fields carrying no value (a call row's `strength`/`key_name`/… are null by
    KIND, and 54% of a measured real row was null). It deliberately does not import
    the wrapper's own pruner — a reference computed by the code under test moves
    with it and asserts nothing.

    What THIS test pins is that beyond those two, no field is added, dropped,
    renamed, or re-valued, and that the ENVELOPE keeps every key regardless.

    ONE-SHOT DOSSIER, THREE THINGS PINNED. `dossier` gained a THIRD sanctioned
    boundary transform — a NAMED set of one-shot panels is elided from the envelope
    when it says nothing — and the temptation here was to loosen the equality to
    accommodate it. That is refused: the elision is asserted as an exact set, so a
    panel dropped for any OTHER reason (a bug, a widened elision list) still fails,
    and every remaining field must still agree exactly.

    It also pins the WORKING TREE. The wrapper resolves the repo from the same target
    as the db, so the reference call must be given the same `repo_root` — comparing
    against a `repo_root`-less library call would compare a payload WITH a body
    against one without and could only be made to pass by weakening it."""
    from dataclasses import asdict

    from wire_expect import expected_wire

    from clew import query as q

    def wire(obj: object) -> dict:
        """@brief Plain asdict, then the independently-computed wire transform."""
        return expected_wire(asdict(obj))  # type: ignore[arg-type]

    reference = wire(q.function_dossier(rich_db, "sensor_poll", repo_root=repo_root))
    reply = _payload(tools.dossier("sensor_poll"))
    ## Spelled out rather than imported from `_DOSSIER_OPTIONAL`, deliberately: the
    ## docstring above says a WIDENED elision list must still fail here, and importing
    ## the production constant is exactly what would stop it failing. gh#373 widens it
    ## on purpose — `macros` is a fifth one-shot panel, empty on every ordinary
    ## function — so the literal moves with it, by hand, which is the point.
    ##
    ## `gated_by` is the SIXTH, and it failed this assertion when it was added, which is the
    ## mechanism working rather than a cost: the elision widened and a human had to come here
    ## and say so. `gates_unplaceable` is deliberately NOT in this tuple — it is an int whose
    ## zero is a measurement ("every gate in this file had an extent, so an empty `gated_by`
    ## means ungated"), and eliding it would leave that indistinguishable from "cannot tell".
    ##
    ## `macro_collision` is the SEVENTH (gh#403) and it failed here too, on the same mechanism.
    ## It is a STRING, so unlike `gates_unplaceable` an empty one carries no measurement: it
    ## says the two conditions for the disclosure did not both hold, which is silence rather
    ## than a finding about this symbol.
    ONE_SHOT = (
        "body",
        "sections",
        "locks_held",
        "external_callees",
        "macros",
        "gated_by",
        "macro_collision",
    )
    ## gh#372's FOURTH sanctioned transform, and the only one: the flat payload adds
    ## `subject` and `subject_kind` in front of the section's own fields. Named as an
    ## exact set for the same reason the elision is — a field added for any other reason
    ## still fails, and the equality below is otherwise untouched. The FLATNESS is what
    ## this pins: a nested `{"function": {...}}` shape would have taken every list in the
    ## payload out of `_DOSSIER_LISTS`'s reach and silently unbudgeted the largest reply
    ## on the surface.
    ADDED = {"subject", "subject_kind"}
    assert set(reply) - set(reference) == ADDED
    assert reply["subject_kind"] == "function"
    assert set(reference) - set(reply) == {k for k in ONE_SHOT if not reference[k]}
    assert {k: v for k, v in reply.items() if k not in ADDED} == {
        k: v for k, v in reference.items() if k in reply
    }
    ## The body is the panel this could get silently wrong: the wrapper resolves the
    ## working tree itself, so a WRONG tree would still produce a dict here and only a
    ## real line of the fixture's source proves it read the right file.
    assert reply["body"]["lines"], "the one-shot body must carry the fixture's source"

    ## THE NEIGHBOUR ROWS, still field for field (gh#372). `callers`/`callees` were their
    ## own tools and are now these two fields, so the parity assertion moved rather than
    ## being dropped — the claim of that collapse is that the rows are the SAME rows, and
    ## this is what makes the claim checkable.
    ## The whole LIST is transformed, not each element separately: a row is a row
    ## because it sits inside a list, and `wire()` on a lone dataclass would treat it
    ## as an envelope and prune nothing.
    neighbours = _payload(tools.dossier("handle_cloud_command"))
    assert neighbours["callers"] == expected_wire(
        [asdict(c) for c in q.callers(rich_db, "handle_cloud_command")]
    )
    assert neighbours["callees"] == expected_wire(
        [asdict(c) for c in q.callees(rich_db, "handle_cloud_command")]
    )

    ## The non-function subject kinds, each against the R2 function that builds it, so
    ## the dispatch cannot quietly substitute one section for another.
    req = _payload(tools.dossier("REQ-0621"))
    assert req["subject_kind"] == "requirement"
    assert {k: v for k, v in req.items() if k not in ADDED} == wire(
        q.req_trace(rich_db, "REQ-0621")
    )


def test_graph_stats_ships_its_zeroes_and_never_a_bare_edge_count(tools: QueryTools) -> None:
    """gh#7 on the WIRE, where the two ways to lose an aggregate both live.

    ONE: elision. `graph_stats` is returned through `wire.one`, so it is an ENVELOPE
    and every key survives even at zero. A measured `pairs_without_nonfuzzy: 0` is the
    strongest statement the tool can make; dropped, it becomes indistinguishable from
    an index that was never measured. Same for a layer row whose `rows` is 0 — the
    `state` beside it is the whole point, and eliding the count would leave a state
    with nothing to state it about.

    TWO: an unqualified count. The payload must never offer a single number a consumer
    could read as "the edges". Both counts ship under names that differ, and the
    sentence that distinguishes them ships with them.

    Serialization is compared against the R2 dataclass so a renamed or retyped field
    fails here, not silently at a consumer.
    """
    from dataclasses import asdict

    from wire_expect import expected_wire

    from clew import query as q

    reply = _payload(tools.graph_stats())
    ## Through the INDEPENDENT wire reference, not `wire.one`: `layers` is a tuple on
    ## the dataclass and a JSON array on the wire, which is the same lossless transform
    ## `implementors` needs, and a reference computed by the code under test would
    ## move with it and assert nothing.
    assert reply == expected_wire(asdict(q.graph_stats(tools.db())))

    calls = reply["calls"]
    for key in ("rows", "logical_pairs", "row_inflation", "row_meaning"):
        assert key in calls, f"{key} must reach the wire; the envelope elides nothing"
    assert "pairs_without_nonfuzzy" in calls, "a measured zero must survive elision"
    assert str(calls["rows"]) in calls["row_meaning"]
    assert str(calls["logical_pairs"]) in calls["row_meaning"]

    # A layer at zero rows still ships both its count and the state that interprets it.
    zero_rows = [layer for layer in reply["layers"] if layer["rows"] == 0]
    assert zero_rows, "the fixture has at least one unpopulated layer"
    for layer in zero_rows:
        assert layer["state"] in {"empty", "absent"}
        assert "rows" in layer, "a zero count is a measurement and must not be elided"


def test_empty_results_are_explicit_not_bare(tools: QueryTools) -> None:
    """A bare empty list is indistinguishable from a broken tool. An earlier
    benchmark of a different query layer was invalidated exactly this way:
    agents read empty responses as failures, abandoned the index, and guessed
    names instead. So an empty result must SAY it is empty and say it is not an
    error."""
    ## Through `search` since gh#372: `callers` was the list-returning tool this pinned,
    ## and the two remaining list-returning routes are `search`'s text corpora. The
    ## invariant is the envelope's, not any one tool's — `_many` is what produces it.
    empty = tools.search("no_such_token_anywhere_xyz", corpus="prose")
    assert empty["count"] == 0
    assert empty["results"] == []
    assert "note" in empty, "an empty result must explain itself"
    note = empty["note"].lower()
    assert "not an error" in note
    assert "no_such_token_anywhere_xyz" in empty["note"], "the note must name what was searched for"

    populated = tools.search("telemetry")
    assert populated["count"] > 0
    assert "note" not in populated, "a populated result needs no disclaimer"

    ## AND AN EMPTY NEIGHBOUR LIST INSIDE A DOSSIER IS STILL PRESENT AND EMPTY. Nothing
    ## calls `main`, and `callers` is a pre-existing envelope key that `_DOSSIER_OPTIONAL`
    ## deliberately does not elide — a consumer reading `doss["callers"] == []` as "no
    ## callers" must keep working, and an absent key would read as "not measured".
    doss = tools.dossier("main")
    assert doss["callers"] == [], "an always-present envelope key must survive at empty"


def test_wrapper_content_reaches_the_r1_richness(tools: QueryTools) -> None:
    """Spot-check that the serialized shapes carry the semantic layer, not a
    thinned-out projection."""
    d = tools.dossier("sensor_poll")
    assert d is not None
    assert d["liveness"] == "live"
    write = next(w for w in d["writes"] if w["key_name"] == "DEMOBOT_POWER_BATTERY_MV")
    assert write["other"] == "telemetry_report"
    ## The R1 semantic fields are asserted against R2 rather than by mere key presence,
    ## because the wire elides a row field that carries no value — `assert
    ## "dispatch_mode" in write` would fail on a correct absence while passing on a
    ## wrongly-absent one. What matters is that an INFORMATIVE field reaches the wire
    ## unchanged, which is what a thinned projection breaks.
    ##
    ## "Carries no value" covers two spellings, and conflating them was a real bug:
    ## a nullable field is None, but `dispatch_mode`/`edge_kind` are
    ## `TEXT NOT NULL DEFAULT 'unknown'` and record undetermined as a LITERAL. The wire
    ## used to keep those two and drop `crosses_thread = NULL`, so the fields that said
    ## nothing shipped as measurements while the informative one read as inapplicable.
    from wire_expect import absent

    from clew import query as q

    source_row = next(
        w
        for w in q.function_dossier(tools.db(), "sensor_poll").writes
        if w.key_name == "DEMOBOT_POWER_BATTERY_MV"
    )
    for field in ("edge_kind", "dispatch_mode", "edge_triggered", "crosses_thread"):
        expected = getattr(source_row, field)
        if absent(field, expected):
            assert field not in write, (
                f"{field} carries no value in R2 ({expected!r}) but ships on the wire"
            )
        else:
            assert write[field] == expected, f"{field} did not survive serialization"

    ## THE CHAIN IS A DEPTH, NOT A TOOL (gh#372). `chain_trace` was folded into `dossier`
    ## as `depth > 1`, and the fold has to carry the same traversal — the R1 semantics on
    ## a hop are the reason the walk exists, so a depth that produced a call-only chain
    ## would be a capability loss dressed as a collapse.
    chain = tools.dossier("sensor_poll", depth=3)["chain"]
    assert any(h["edge_class"] == "key" for h in chain["hops"])
    assert "telemetry_report" in {n["name"] for n in chain["nodes"]}
    assert "depth_note" not in tools.dossier("sensor_poll", depth=3), (
        "a function HAS a traversal seed; the no-seed note must not fire on one"
    )


## Every field a neighbour row can carry, spelled out. See the test below for
## why this is a LITERAL rather than derived from the dataclass.
_NEIGHBOUR_KEYS = frozenset(
    {
        "name",
        "rowid",
        "source",
        "confidence",
        "edge_class",
        "strength",
        "key_name",
        "edge_kind",
        "dispatch_mode",
        "edge_triggered",
        "crosses_thread",
        "to_thread",
        # gh#8: the concrete overrides a virtual endpoint can dispatch to. Added
        # deliberately, same gate. An ANNOTATION on the edge — it does not change
        # `confidence`, which still grades the call itself.
        "implementors",
        # gh#350: the macro that makes a composed hop exist, and its expansion. Added
        # deliberately, same gate. Also an annotation, and also not a confidence input —
        # a macro hop is `resolved` because both halves are doxygen's own observations
        # and the join is ours, which naming the macro does not change.
        "via_macro",
        "via_macro_expansion",
    }
)


def test_neighbour_wire_keys_are_pinned_literally(tools: QueryTools) -> None:
    """The MCP wire contract, asserted against a LITERAL key set written here.

    Every other wire test in this file is asdict-compared-to-asdict, so a field
    rename, removal or retype in `CallEdge` is invisible to the entire suite —
    both sides of the comparison move together. Meanwhile the callers/callees
    tool descriptions instruct a model to read `source`, `confidence`,
    `edge_class` and `strength` by name, so a silent rename breaks the contract
    the description promises while every test stays green.

    Deriving this set from the dataclass would reproduce exactly that hole.
    Changing it must be a deliberate edit here — which is also the gate #38's
    per-neighbour collapse had to pass through.

    #38 landed with `source` still SINGULAR and still ONE vocabulary-registered
    value, NOT as the `source` → `sources` rename anticipated here. A joined or
    pluralised `source` would put an unregistered value into a field
    `vocabulary.py` checks.

    The literal is pinned in TWO steps, because the wire now elides a row field
    that carries no value. Step 1 asserts the full set against the UNPRUNED
    serialization of the R2 dataclass, so a rename or removal still fails here —
    that is the gate, and elision must not be allowed to hide it. Step 2 asserts
    the shipped rows are a SUBSET, so the wire can never carry a key the literal
    does not list."""
    from dataclasses import asdict, fields

    from clew import query as q

    unpruned = {f.name for f in fields(q.callers(tools.db(), "handle_cloud_command")[0])}
    assert unpruned == _NEIGHBOUR_KEYS, (
        "a neighbour field was renamed, added or removed — update the literal above deliberately"
    )
    assert set(asdict(q.callers(tools.db(), "handle_cloud_command")[0])) == _NEIGHBOUR_KEYS

    ## Read off `dossier` since gh#372 — the neighbour tools are gone and these are their
    ## rows, in the fields they became. Step 2 is what it always was: the shipped rows may
    ## never carry a key the literal does not list.
    inbound = tools.dossier("handle_cloud_command")
    outbound = tools.dossier("sensor_poll")
    for rows in (inbound["callers"], outbound["callees"]):
        assert rows, "the fixture rows must be non-empty to pin anything"
        for row in rows:
            assert set(row) <= _NEIGHBOUR_KEYS, f"unlisted wire key: {set(row) - _NEIGHBOUR_KEYS}"

    ## THE SPLIT, AND THAT IT LOSES NOTHING. The deleted `callees` tool MERGED both edge
    ## classes into one `CallEdge` list; the dossier keeps calls in `callees` and dataflow
    ## in `writes`/`reads` as `KeyEdge` rows, which have no `edge_class` because their
    ## class is the field they are in. So the merged list's key set is pinned above, and
    ## what has to hold after the fold is that the UNION of the two halves is the same set
    ## of neighbours — a claim about capability, not about shape, and the one a collapse
    ## can silently break.
    assert {r["edge_class"] for r in outbound["callees"]} == {"call"}
    merged = {c.name for c in q.callees(tools.db(), "sensor_poll")}
    split = {r["name"] for r in outbound["callees"]} | {w["other"] for w in outbound["writes"]}
    assert merged == split, (
        "folding callers/callees into dossier must lose no neighbour: the merged tool's "
        f"rows and the split fields disagree on {merged ^ split}"
    )


def test_the_descriptions_name_every_subject_kind_the_tools_accept(tools: QueryTools) -> None:
    """A tool description is the only thing a model reads before choosing a tool, so a
    stale one is a live defect. WHAT THIS REPLACES: the `callers`/`callees` descriptions
    used to be checked field by field against the neighbour key set. Both tools are gone
    and their rows are `dossier` fields, so the equivalent live risk moved with them —
    and it got bigger, because a caller can no longer discover a capability by seeing a
    tool named after it.

    A SUBJECT KIND THE DESCRIPTION DOES NOT NAME IS UNREACHABLE IN PRACTICE. `dossier`
    accepts eight and a model will pass it a function; nothing else on the surface hints
    that a lock name or a requirement id is a legal argument. Same for a corpus: `search`
    reads five and defaults to one. So the description must name every one of both, and
    this is what stops a kind or corpus being added to the dispatch and nowhere else.
    """
    import typing

    from clew.mcp_server.tools_query import CORPORA, QueryTools
    from clew.query import SUBJECT_KINDS

    ## THE SCHEMA, NOT THE PROSE. The enumerations moved into the parameter descriptions when the
    ## prose was cut to fit the client's 2,048-char cap — which is the better home for them
    ## anyway, because the schema is re-sent whole on every request while a third of the prose was
    ## being discarded. The requirement is unchanged: a kind the surface does not name is
    ## unreachable in practice. Only where it must be named moved.
    def described(fn: object, param: str) -> str:
        hint = typing.get_type_hints(fn, include_extras=True)[param]
        return next(m.description for m in hint.__metadata__ if getattr(m, "description", None))

    subject = described(QueryTools.dossier, "subject")
    for kind in SUBJECT_KINDS:
        assert kind in subject or kind in TIER1_TOOLS["dossier"], (
            f"dossier accepts subject kind {kind!r} and neither its schema nor its description "
            f"says so, which makes that kind unreachable in practice"
        )
    corpus = described(QueryTools.search, "corpus")
    for name in CORPORA:
        assert name in corpus or name in TIER1_TOOLS["search"], (
            f"search reads corpus {name!r} and neither its schema nor its description says so"
        )

    ## The claim #46 falsified stays falsified, and the split it replaced with stays named.
    ## THE WHOLE DELIVERED SURFACE for dossier is its description plus its parameter schema, and
    ## both arrive untruncated now, so a capability counts as disclosed if it appears in either.
    surface = TIER1_TOOLS["dossier"] + " " + described(QueryTools.dossier, "depth")
    assert "returns strictly less" not in surface
    assert "direct CALL edges only" not in surface

    ## The depth fold must be discoverable, or `chain_trace`'s capability is present and
    ## unreachable — a worse outcome than having deleted it.
    assert "depth" in surface.lower()
    assert str(q_max_depth()) in surface, "the depth BOUND must be disclosed, not implied"


## @brief The traversal depth bound, read from the library rather than restated.
## @return The maximum depth a subject dossier will traverse.
## @version 1
def q_max_depth() -> int:
    """Read from R2 so the description test cannot pass against a number the code no
    longer honours — the failure mode a hand-copied bound has.

    @brief The MAX_SUBJECT_DEPTH constant.
    @return The bound.
    @version 1
    """
    from clew.query import MAX_SUBJECT_DEPTH

    return MAX_SUBJECT_DEPTH


def test_unknown_symbols_return_a_self_describing_miss_naming_the_target(
    tools: QueryTools, repo_root: Path
) -> None:
    """A miss is now an ENVELOPE, not a bare None, for the same reason `_many` wraps an
    empty list: `None` is indistinguishable from a malformed call, and this is the reply
    where the target matters MOST — the commonest cause of a missing symbol is an index
    of the wrong repository.

    Returning None here would have omitted the gh#22 attribution from precisely the case
    that motivated it."""
    ## Every route to a miss, not one: gh#372 gave `dossier` several ways to fail to
    ## resolve — an unknown name, a name that resolves to a kind the caller ruled out —
    ## and each is a separate branch that has to reach the same envelope.
    for miss in (
        tools.dossier("no_such_function_xyz"),
        tools.dossier("NoSuchClass", kind="class"),
        tools.dossier("sensor_poll", kind="lock"),
    ):
        assert miss["found"] is False
        assert miss["target"] == str(repo_root), "a miss must still name what answered"
        note = miss["note"].lower()
        assert "not an error" in note, "a miss must say it is not a failure"
        assert "target" in note, "and must point the reader at the attribution"

    ## A HIT must not carry the miss discriminator, or `found` says nothing.
    assert "found" not in tools.dossier("sensor_poll")


def test_active_db_without_target_raises(server) -> None:
    """Tier-1 tools bound to a server with no DEFAULT target fail loudly rather than
    reading a bogus path — and name both remedies.

    Naming `target=` matters as much as naming `--repo`: a server with no derived target
    can still answer about any registered repository, so an error that offered only the
    relaunch would send a caller to restart a process that did not need restarting."""
    _mcp, state = server
    for accessor in (state.active_db, state.active_repo):
        with pytest.raises(RuntimeError, match="No default target repository") as exc:
            accessor()
        assert "target=" in str(exc.value), "the per-call remedy must be offered"
        assert "--repo" in str(exc.value), "and so must the launch-time one"
        ## The message must not name the retired tool. An error instructing a model to
        ## call `set_target` would send it after a tool that does not exist.
        assert "set_target" not in str(exc.value)


# ─── tier-1: the benchmark-parity capabilities (body / prose / class) ────────


def test_the_parity_capabilities_survive_the_tool_cull(server, tools: QueryTools) -> None:
    """The comparison query layer this is benchmarked against offered a source body, a
    file listing, prose search and a class lookup. Without equivalents, rubric marks
    would be unreachable for reasons unrelated to the database.

    TWO OF THE FOUR ARE NO LONGER TOOLS, and the distinction this test now draws is
    between a CAPABILITY and a TOOL — because "we deleted a tool" and "we can no longer
    answer that" must not be allowed to look the same from in here:

      * the source body MOVED into `dossier.body`, so the capability is asserted through
        the tool that carries it rather than declared absent;
      * the file listing was DELETED outright on the owner's call that `ls | grep` beats
        it, so there is nothing to assert and this test says so in one place instead of
        leaving a silently shortened set.

    @brief The parity capabilities are still reachable after the cull.
    @version 2
    """
    mcp, state = server
    ## gh#372 TOOK TWO MORE OF THE FOUR, and the distinction holds: prose search became
    ## `search(corpus='prose')` and the class lookup became `dossier` on a class name.
    ## Both are asserted through the tool that carries them — a capability reachable by a
    ## different argument is not a capability lost, and this is what stops the two from
    ## looking the same.
    registered = set(register_query_tools(mcp, state.tools))
    assert {"dossier", "search"} <= set(TIER1_TOOLS) <= registered
    for name in TIER1_TOOLS:
        assert TIER1_TOOLS[name].strip(), f"{name} must describe itself to a model"

    ## Every parity capability, EXERCISED rather than named, and against the built fixture
    ## rather than `state.tools` — the `server` fixture has no target, so a call through it
    ## would raise for a reason unrelated to the capability. A test that only checked the
    ## tool list would pass while `corpus='prose'` raised, because a corpus is invisible to
    ## a name check: that is the whole hazard a collapse from nineteen names to two creates.
    assert tools.search("chime", corpus="prose")["kind"] == "prose matches"
    assert tools.dossier("sensor_poll")["body"]["lines"], "the source body panel"

    ## The deleted names must be GONE, not merely unregistered somewhere else — a tool
    ## that survives in one registration path is the drift this whole file guards.
    assert {
        "source",
        "list_files",
        "sections_in",
        "locks_held_when",
        "thread_of",
        ## gh#372's twelve. Listed so a partial revert — one wrapper quietly re-registered
        ## while the frozen set stayed at two — fails here rather than shipping a
        ## thirteen-tool surface that both name checks call correct.
        "callers",
        "callees",
        "chain_trace",
        "resolve_symbol",
        "search_prose",
        "lookup_class",
        "req_trace",
        "runs_under_lock",
        "kconfig",
        "lock_roster",
        "thread_roster",
        "graph_stats",
    } & set(TIER1_TOOLS) == set()

    ## And the description must still TELL a model the panels are there. Deleting the
    ## focused tools while leaving `dossier` silent about what absorbed them removes the
    ## capability in every way that matters, since a model only ever sees the description.
    ##
    ## WORD-BOUNDARY, NOT `in`. A concurrent change to these files found that
    ## `assert field in desc` is satisfiable by a LONGER field name containing the shorter
    ## one — `via_macro` was "present" only because `via_macro_expansion` was — so the
    ## guard passed vacuously. `body` is the same hazard here: it is an ordinary English
    ## word this description uses in prose, so a substring test would survive the field
    ## itself being renamed away. Every panel is checked, not just the one that motivated
    ## the change, because the next deletion will be one of the other three.
    desc = TIER1_TOOLS["dossier"]
    for panel in ("body", "sections", "locks_held", "external_callees"):
        assert re.search(rf"`{re.escape(panel)}`", desc), (
            f"dossier's description must name the `{panel}` panel as a field, since the "
            f"tool that used to answer it is gone"
        )


def test_the_dossier_body_caps_and_reports_truncation(tools: QueryTools) -> None:
    """`max_body_lines` is what `source` could do that the panel could not, so it is the
    one part of that tool that had to survive its deletion. No single call can return an
    unbounded body (the failure that distorted the comparison layer's own benchmark), and
    a caller who needs past the cap raises it on the same call rather than making a
    second one.

    Measured need: mbedtls's `mbedtls_x509_crt_parse_path` is 139 lines, so the 120-line
    default truncates it and the tail was reachable only through `source`.

    @brief The dossier body honours a caller's cap and discloses the cut.
    @version 1
    """
    full = tools.dossier("sensor_poll")
    assert full["body"]["truncated"] is False
    assert full["file"].endswith("sensor_driver.c")
    assert "sensor_poll" in "\n".join(full["body"]["lines"])

    capped = tools.dossier("sensor_poll", max_body_lines=2)
    body = capped["body"]
    assert len(body["lines"]) == 2
    assert body["truncated"] is True
    assert body["total_lines"] == full["body"]["total_lines"], (
        "a cut body must still report the body's TRUE length, or the disclosure is unusable"
    )


def test_the_dossier_body_takes_the_repo_root_from_the_server_not_the_model(
    server, tmp_path: Path, rich_db: Path, repo_root: Path
) -> None:
    """The repo root is NEVER a tool parameter: the server already knows which
    working tree the active database was built from."""
    _mcp, state = server
    repo = tmp_path / "repo"
    repo.mkdir()
    target = state.registry.register(str(repo))
    state.active = target
    assert state.active_repo() == Path(target.repo_path)
    assert "repo_root" not in TIER1_TOOLS["dossier"]

    state.active = st.target_for(repo_root, tmp_path / "state")
    Path(state.active.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state.active.db_path).write_bytes(rich_db.read_bytes())
    assert state.tools.dossier("sensor_poll")["body"]["lines"]


def test_the_prose_corpus_returns_snippets(tools: QueryTools) -> None:
    """`search_prose` was a TOOL and is now an ARGUMENT (gh#372) — the two searches
    differed in which table they read and in nothing a caller cares about, so shipping
    them separately made a model choose a corpus before it could find out which one held
    its answer. What it returns is unchanged, which is what this pins.

    @brief The prose corpus is reachable through `search` and returns what it always did.
    @version 1
    """
    hits = tools.search("chime", corpus="prose")
    assert hits["count"] > 0
    assert hits["kind"] == "prose matches"
    assert all(h["snippet"] for h in hits["results"])
    assert tools.search("chime", corpus="prose", limit=1)["count"] == 1

    ## AND THE DEFAULT CORPUS IS STILL SYMBOLS. A corpus argument that changed the default
    ## would silently repoint every existing call at the markdown.
    assert tools.search("telemetry")["kind"] == "matching symbols"
    assert tools.search("telemetry", corpus="symbols") == tools.search("telemetry")


def test_a_widened_prose_search_says_so_in_the_envelope(tools: QueryTools) -> None:
    """THE DISCLOSURE IS THE HALF THAT KEEPS THE FIX HONEST. Relaxing FTS5's implicit AND
    to an OR removes a false negative — measured on mbedtls, five natural phrasings of a
    question the corpus could answer all returned nothing, and the agent grepped instead.
    Returning those rows WITHOUT saying the query was relaxed just swaps that for a false
    positive: "matched some of your terms" is a weaker claim than "matched all of them",
    and a reader who cannot tell them apart is no better off.

    This is also a GRADED SURFACE, so the note is deliberately explicit about what the
    rows are worth rather than quietly making the arm look better.

    @brief A relaxed prose query is announced, and an exact one is not.
    @version 1
    """
    widened = tools.search("chime zzqqxwv", corpus="prose")
    assert widened["count"] > 0, "the OR must recover the 'chime' hits"
    assert widened["matched"] == "some terms"
    assert "RELAXED" in widened["note"]
    ## NAMES THE TOKENS, so a reader can see WHICH word cost them the exact match.
    assert "zzqqxwv" in widened["note"]

    ## An exact hit must carry NO such note — otherwise every reply hedges and the signal
    ## stops meaning anything.
    exact = tools.search("chime", corpus="prose")
    assert exact["count"] > 0
    assert "matched" not in exact


def test_an_unknown_corpus_is_refused_by_name(tools: QueryTools) -> None:
    """FAIL CLOSED, and name the allowed set. A misspelled corpus that fell through to
    the default would answer a markdown question out of the symbol table and look like a
    definitive empty result — the exact silent-degradation shape this repo keeps
    recording. Same reasoning as the declaration loader's entry-level rejection.

    @brief An unknown `corpus` raises and lists the known ones.
    @version 1
    """
    with pytest.raises(ValueError, match="Unknown corpus"):
        tools.search("chime", corpus="proze")


def test_the_class_subject_matches_the_r2_library(rich_db: Path, repo_root: Path) -> None:
    """MVVM again: the wrapper is a serialization of the R2 result. The fixture is
    C and has no compounds, so the populated case is unit-tested in
    tests/test_query.py; here the agreement is what matters.

    Through `dossier` since gh#372 — `lookup_class` was a tool BECAUSE the composite
    refused a non-function subject, so folding it in is the fix rather than a
    consolidation. `q.lookup_class` is untouched and still builds the section.
    """
    from dataclasses import asdict

    from clew import query as q

    tools = QueryTools(lambda: rich_db, lambda: repo_root)
    ## R2 returns None for an absent class; the wrapper turns that into a miss envelope,
    ## so the agreement to assert is that BOTH report nothing found.
    assert q.lookup_class(rich_db, "NoSuchClass") is None
    assert tools.dossier("NoSuchClass")["found"] is False

    ## `wire.rows`, NOT a bare `asdict`, and the difference is the point of the wire
    ## layer rather than a looser assertion. gh#335 gave `FileEntry` an
    ## `external_root` that is `''` for a first-party file, and `''` is ABSENT on the
    ## wire — so a raw `asdict` comparison started failing the moment a field had an
    ## empty default, having only ever passed because every field was always present.
    ## Comparing against the serializer keeps this a parity test between the wrapper
    ## and the library instead of a second, drifting copy of the elision rule.
    ##
    ## The `list_files` and `source` legs went with those tools. `list_files` was the leg
    ## that MOTIVATED the `wire.rows` comparison, so the reasoning above is kept: it is
    ## the reason this is not an `asdict` comparison, and the next row-bearing tool added
    ## here must not relearn it.
    assert tools.search("chime", corpus="prose")["results"] == [
        asdict(h) for h in q.search_prose(rich_db, "chime")
    ]


## `_optional_asdict` lived here and is deleted: its only caller was the `source` parity
## leg, and a helper kept alive with no caller is the dead code the next reader has to
## prove is dead. `_payload` above is NOT in that position — four parity legs still use it.


def test_a_dossier_without_a_bound_repo_root_still_answers_minus_the_body(
    rich_db: Path,
) -> None:
    """A `QueryTools` built without a repo provider must not traceback on an implicit
    None path — and must not REFUSE either, which is where this differs from the
    `source` test it replaces.

    `source` raised, correctly: with no working tree there was no answer at all. A
    dossier is index-first and the body is one panel of many, so it resolves the tree
    non-raising (`_repo_or_none`) and drops only what it cannot read. Refusing the whole
    call because one panel is unavailable would make an unbound tool set — the test-only
    shape, and any server whose target has no checkout — answer nothing.

    @brief An unbound working tree costs the body panel and nothing else.
    @version 1
    """
    doss = QueryTools(lambda: rich_db).dossier("sensor_poll")
    assert doss.get("found") is not False, "the index-only panels must still answer"
    assert doss["signature"], "and carry the identity"
    assert "body" not in doss, "the one panel that needs a working tree is absent"


# ─── state: paths, freshness, cull ───────────────────────────────────────────


def test_state_home_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The state root is env-overridable and XDG-aware — never a hardcoded
    machine path."""
    monkeypatch.setenv(st.STATE_HOME_ENV, str(tmp_path / "explicit"))
    assert st.state_home() == tmp_path / "explicit"

    monkeypatch.delenv(st.STATE_HOME_ENV)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert st.state_home() == tmp_path / "xdg" / "clew"


def test_target_slug_disambiguates_same_named_checkouts(tmp_path: Path) -> None:
    """Two checkouts with the same directory name get distinct db paths."""
    a = tmp_path / "one" / "firmware"
    b = tmp_path / "two" / "firmware"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    ta = st.target_for(a, tmp_path / "state")
    tb = st.target_for(b, tmp_path / "state")
    assert ta.slug.startswith("firmware-")
    assert ta.slug != tb.slug
    assert ta.db_path != tb.db_path


def test_registry_roundtrip_and_drop(tmp_path: Path) -> None:
    """Registration persists, and drop removes both the entry and the db dir."""
    home = tmp_path / "state"
    reg = st.TargetRegistry(home)
    repo = tmp_path / "repo"
    repo.mkdir()
    target = reg.register(repo)
    assert [t.repo_path for t in st.TargetRegistry(home).targets()] == [target.repo_path]

    Path(target.db_path).write_text("db")
    assert reg.drop(target.repo_path) is True
    assert reg.targets() == []
    assert not Path(target.db_path).parent.exists()
    assert reg.drop(target.repo_path) is False


def test_corrupt_registry_is_tolerated(tmp_path: Path) -> None:
    """A damaged registry file must not take the server down."""
    home = tmp_path / "state"
    home.mkdir()
    (home / st.REGISTRY_NAME).write_text("{not json")
    assert st.TargetRegistry(home).targets() == []


def test_the_registry_is_replaced_atomically_never_truncated_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_text` TRUNCATES THE DESTINATION AND THEN FILLS IT, so a reader arriving in
    between sees a partial document — and `load` treats a partial document as an EMPTY
    registry, after which the next `register()` persists a registry containing only its own
    entry. That is a write-amplifying loss, not a transient read error.

    The class docstring called this safe on the premise that "the server is single-process".
    The premise is false in this deployment: one `clew-mcp` runs per session, and
    `run_matrix` spawns one more per benchmark cell. Measured symptom on this machine — 24
    slug directories under `targets/`, holding real databases, against ONE entry in
    `targets.json`, with a `clew.db` written four minutes before the registry's own mtime by
    a build that must have called `register()`.

    Asserted from both sides, because either half alone is satisfiable the wrong way: a
    rename with an in-place write before it is still torn, and no in-place write with no
    rename means nothing was saved at all.

    @brief The registry file appears by atomic rename and is never written in place.
    @return None.
    @version 1
    """
    written: list[str] = []
    replaced: list[str] = []
    real_write = Path.write_text
    real_replace = os.replace

    def spy_write(self: Path, *args: object, **kwargs: object) -> int:
        written.append(str(self))
        return real_write(self, *args, **kwargs)  # type: ignore[arg-type]

    def spy_replace(src: object, dst: object, **kwargs: object) -> None:
        replaced.append(str(dst))
        real_replace(src, dst, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", spy_write)
    monkeypatch.setattr(os, "replace", spy_replace)

    reg = st.TargetRegistry(tmp_path / "state")
    reg.save({"/some/repo": {"slug": "repo-abc123", "db_path": "/some/db"}})

    assert str(reg.path) not in written, (
        "the registry was written in place, so a concurrent reader can see a partial "
        "document and read it as an empty registry"
    )
    assert str(reg.path) in replaced, "the registry must be put in place by an atomic rename"
    ## And it really landed — an atomicity test that stopped at the mechanism would pass on
    ## a save that renamed an empty temp file over the destination.
    assert reg.load() == {"/some/repo": {"slug": "repo-abc123", "db_path": "/some/db"}}


def test_an_unreadable_registry_is_reported_and_its_content_survives(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TOLERATING CORRUPTION SILENTLY IS WHAT MADE THE LOSS INVISIBLE. `load` caught
    `OSError`/`ValueError` and returned `{}` with no log line, so an unreadable registry and
    a genuinely empty one were the same observable event — and the empty reading is the one
    that gets persisted.

    Absence stays silent, because absence is the ordinary first run. Only an unreadable
    FILE is an error, which is the distinction the bare `except` could not make.

    THE SURVIVOR CHECK EXCLUDES `targets.json` ITSELF, and an earlier version of this test
    did not — which made it VACUOUS. With nothing preserved, the damaged bytes are still
    sitting at `targets.json`, so reading every file in the directory found them and the
    assertion passed against a disabled preserve. A mutation control caught that; the test
    was green for the wrong reason and would have been deleted later as redundant.

    @brief An unreadable registry logs an error and its bytes are moved somewhere recoverable.
    @return None.
    @version 2
    """
    home = tmp_path / "state"
    home.mkdir()
    damaged = '{"/previously/registered": {"slug": "prev-000000", "db_path": "/prev/db"}'
    (home / st.REGISTRY_NAME).write_text(damaged)

    reg = st.TargetRegistry(home)
    with caplog.at_level(logging.ERROR):
        assert reg.targets() == [], (
            "still tolerated — a broken registry must not take the server down"
        )
    assert any(st.REGISTRY_NAME in record.getMessage() for record in caplog.records), (
        "an unreadable registry must name itself in a log record, not vanish into a bare except"
    )

    elsewhere = [
        p.read_text(encoding="utf-8")
        for p in home.iterdir()
        if p.is_file() and p.name != st.REGISTRY_NAME
    ]
    assert any(damaged in text for text in elsewhere), (
        "the unreadable bytes must be moved OUT of the path the next save overwrites — they "
        "are the only record of what was registered"
    )


def test_a_failed_preserve_is_reported_as_a_failure_not_as_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The log line must not claim a preservation that did not happen. The first version of
    `_preserve_unreadable` composed "Its bytes are preserved at X" and only THEN attempted
    the move, so a failing `os.replace` produced a confident false claim followed by a
    correction — and an operator who read the first line would have believed the data was
    safe.

    Found by disabling the move and leaving the message intact, which is the mutation this
    test now makes permanent.

    @brief A preserve that fails says so, and does not report success.
    @return None.
    @version 1
    """
    home = tmp_path / "state"
    home.mkdir()
    (home / st.REGISTRY_NAME).write_text("{not json")

    def refuse(_src: object, _dst: object, **_kwargs: object) -> None:
        raise OSError("read-only file system")

    reg = st.TargetRegistry(home)
    with caplog.at_level(logging.ERROR):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(st.os, "replace", refuse)
            assert reg.targets() == []

    said = " ".join(record.getMessage() for record in caplog.records)
    assert "COULD NOT preserve" in said, "a failed preserve must be reported as a failure"
    assert "bytes are preserved at" not in said, (
        "the message claimed the bytes were preserved when the move had failed"
    )


def test_registering_after_an_unreadable_registry_does_not_destroy_it(tmp_path: Path) -> None:
    """THE LOSS SCENARIO END TO END, which neither of the two tests above covers on its own:
    read fails, `register` proceeds, and the single surviving entry becomes the whole
    registry. This asserts the new entry lands AND the previous content is still on disk to
    recover from.

    @brief A register() after an unreadable read keeps the old content recoverable.
    @return None.
    @version 1
    """
    home = tmp_path / "state"
    home.mkdir()
    damaged = '{"/previously/registered": {"slug": "prev-000000", "db_path": "/prev/db"}'
    (home / st.REGISTRY_NAME).write_text(damaged)

    reg = st.TargetRegistry(home)
    repo = tmp_path / "newly_registered"
    repo.mkdir()
    target = reg.register(repo)

    assert [t.repo_path for t in reg.targets()] == [target.repo_path], (
        "the new registration must still succeed"
    )
    survivors = [
        p.read_text(encoding="utf-8")
        for p in home.iterdir()
        if p.is_file() and p.name != st.REGISTRY_NAME
    ]
    assert any("/previously/registered" in text for text in survivors), (
        "registering over an unreadable registry destroyed the only record of what it held"
    )


def test_db_status_freshness_uses_build_signature(tmp_path: Path, rich_db: Path) -> None:
    """A missing db is stale; a db stamped with the current pipeline version is
    not; an older stamp is stale again even with a fresh mtime."""
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "repo"
    repo.mkdir()
    target = reg.register(repo)
    assert st.db_status(target)["stale"] is True

    Path(target.db_path).write_bytes(rich_db.read_bytes())
    status = st.db_status(target)
    assert status["exists"] is True
    assert status["build_version"] == CLEW_BUILD_VERSION
    assert status["stale"] is False

    write_build_signature(target.db_path, CLEW_BUILD_VERSION - 1)
    assert st.db_status(target)["stale"] is True


def test_db_status_detects_source_drift(tmp_path: Path, rich_db: Path) -> None:
    """#43: staleness used to be `stamped != CLEW_BUILD_VERSION` and nothing
    else, so a database built before any number of source edits still reported
    `stale: false` — and because build_or_refresh short-circuits on that flag,
    it REFUSED to rebuild. An agent then answered from a graph describing code
    that no longer existed, with `status` asserting the index was current. A
    version check cannot see source drift; only mtimes can."""
    import os
    import sqlite3
    import time

    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "repo"
    repo.mkdir()
    target = reg.register(repo)
    Path(target.db_path).write_bytes(rich_db.read_bytes())

    # Nothing materialised in the working tree: no file is newer than the db,
    # so the drift term must stay silent rather than force pointless rebuilds.
    assert st.db_status(target)["stale"] is False
    assert st.db_status(target)["source_changed_files"] == 0

    conn = sqlite3.connect(target.db_path)
    rel = conn.execute("SELECT name FROM path WHERE type=1 LIMIT 1").fetchone()[0]
    conn.close()

    src = repo / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("// edited after the build\n", encoding="utf-8")
    future = time.time() + 10
    os.utime(src, (future, future))

    status = st.db_status(target)
    assert status["source_changed_files"] == 1
    assert status["newest_changed_source"] == rel
    assert status["stale"] is True, "an edited source file must make the index stale"


def test_db_status_source_drift_survives_a_corrupt_db(tmp_path: Path) -> None:
    """The drift scan must fail closed on an unreadable/table-less database —
    the version term already marks those stale, and raising here would break
    `status`, the one tool a caller uses to find out something is wrong."""
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "repo"
    repo.mkdir()
    target = reg.register(repo)
    Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target.db_path).write_bytes(b"not a database")

    status = st.db_status(target)
    assert status["source_changed_files"] == 0
    assert status["stale"] is True


def test_cull_drops_stale_and_keeps_current(tmp_path: Path, rich_db: Path) -> None:
    """The sweep removes version-stale and never-built targets while leaving a
    current database registered."""
    reg = st.TargetRegistry(tmp_path / "state")
    good, stale, missing = (tmp_path / n for n in ("good", "stale", "missing"))
    for d in (good, stale, missing):
        d.mkdir()
    t_good = reg.register(good)
    t_stale = reg.register(stale)
    reg.register(missing)
    Path(t_good.db_path).write_bytes(rich_db.read_bytes())
    Path(t_stale.db_path).write_bytes(rich_db.read_bytes())
    write_build_signature(t_stale.db_path, CLEW_BUILD_VERSION - 1)

    culled = st.cull(reg, max_age_days=None)
    assert {c["repo_path"] for c in culled} == {t_stale.repo_path, str(missing)}
    assert [t.repo_path for t in reg.targets()] == [t_good.repo_path]


def test_cull_age_rule(tmp_path: Path, rich_db: Path) -> None:
    """A current-but-aged database is culled by the age rule."""
    import os
    import time

    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "old"
    repo.mkdir()
    target = reg.register(repo)
    Path(target.db_path).write_bytes(rich_db.read_bytes())
    old = time.time() - 40 * 86400
    os.utime(target.db_path, (old, old))

    assert st.cull(reg, max_age_days=90.0) == []
    assert st.cull(reg, max_age_days=30.0)
    assert reg.targets() == []


def test_the_build_passes_only_what_the_repo_actually_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Optional inputs are passed ONLY when the repo has them — no assumption about a
    target repo's layout. A requirements catalog that does not exist must arrive as
    None rather than as a path the pipeline then fails to read, and a repo shipping no
    Doxyfile must arrive as `doxyfile=None` so the pipeline synthesizes one over the
    derived scope instead of being handed a phantom.

    Every DECLARED convention (shared_key_patterns, threads, locks, dispatch,
    preprocessor, index_scope) is deliberately absent from this call: the pipeline
    reads them from the repo's own `.clew.yaml` under `repo_root`. A new
    convention that is reachable only from an argument here would be invisible on the
    MCP surface, honoured by the CLI and silently dropped here.

    `exclude` IS IN THE PERMITTED SET, AND IT IS NOT A CRACK IN THAT RULE. The rule
    separates facts about the CODE — which the repository can state for itself, and
    must, or the two entry points diverge — from what the OPERATOR wants indexed,
    which no file in the repository can state on their behalf. A lock idiom is the
    first; an index boundary is the second. The keyword set below is the enforcement
    point, so anything added to it needs that argument made afresh.

    Its DEFAULT is asserted separately: `None`, meaning inherit what the index already
    records. A default of `[]` would read as harmless and would make every plain
    refresh withdraw the operator's own exclusion.

    @brief The in-process build is handed only inputs the repo really carries.
    @version 2
    """
    import clew.cli as cli_mod

    calls: list[dict] = []
    monkeypatch.setattr(cli_mod, "build_index", lambda **kwargs: calls.append(kwargs))
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "repo"
    repo.mkdir()
    target = reg.register(repo)
    doxyfile = repo / "Doxyfile"
    doxyfile.write_text("")
    state = DocsDbServer.__new__(DocsDbServer)

    state._run_build(target, None, SCOPE_FROM_GUARD)
    assert calls[-1]["requirements"] is None
    assert calls[-1]["doxyfile"] == doxyfile
    assert calls[-1]["repo_root"] == repo
    assert calls[-1]["output"] == Path(target.db_path)
    assert calls[-1]["scope"] == SCOPE_FROM_GUARD
    assert calls[-1]["exclude"] is None, "a refresh that states nothing must INHERIT"
    assert calls[-1]["options"] is None, "a refresh that states nothing must state NOTHING"
    assert not set(calls[-1]) - {
        "output",
        "repo_root",
        "doxyfile",
        "scope",
        "requirements",
        "exclude",
        "options",
    }

    state._run_build(target, None, SCOPE_FROM_GUARD, ["evidence"])
    assert calls[-1]["exclude"] == ["evidence"], "a stated exclusion must reach the pipeline"

    state._run_build(target, None, SCOPE_FROM_GUARD, None, {"entry_patterns": ["app_main"]})
    assert calls[-1]["options"] == {"entry_patterns": ["app_main"]}, (
        "a stated tier-1 option must reach the pipeline"
    )

    ## THE CONTRACT CHANGED HERE, deliberately (gh#368 follow-up), and this assertion is
    ## INVERTED from what it used to be rather than relaxed. It read
    ## `== repo / "requirements.yaml"`, pinning the server's own composition of that path —
    ## which passed it in `build_index`'s EXPLICIT-FLAG slot and so ranked the conventional
    ## filename ABOVE a repo's declared `impact.requirements.file`, through this door only.
    ##
    ## A build through MCP states no catalog path, so the honest argument is None, and
    ## `requirements.resolve_catalog_path` owns the order for both entry points:
    ## flag > declaration > convention. The conventional file is still ingested — that is
    ## asserted at the resolver in `test_the_catalog_precedence_is_declaration_then_convention`,
    ## which is where it belongs now that there is one resolver instead of two.
    (repo / "requirements.yaml").write_text("requirements: []")
    state._run_build(target, None, SCOPE_FROM_GUARD)
    assert calls[-1]["requirements"] is None, "MCP states no flag; the resolver decides"

    doxyfile.unlink()
    state._run_build(target, None, SCOPE_FROM_GUARD)
    assert calls[-1]["doxyfile"] is None
    assert calls[-1]["scope"] == SCOPE_FROM_GUARD


def test_discover_doxyfile(tmp_path: Path) -> None:
    """Root Doxyfile wins; a one-level-down Doxyfile is the fallback; neither
    present yields None."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    assert st.discover_doxyfile(repo) is None
    (repo / "docs" / "Doxyfile").write_text("")
    assert st.discover_doxyfile(repo) == repo / "docs" / "Doxyfile"
    (repo / "Doxyfile").write_text("")
    assert st.discover_doxyfile(repo) == repo / "Doxyfile"


# ─── gh#22: the target is DERIVED, never held on instruction ──────────────────


def test_the_server_holds_no_set_target_tool(server) -> None:
    """The tool is GONE, asserted by name rather than inferred from TIER0.

    It is the surface a caller reaches for out of habit, and its absence is the whole
    point of gh#22 — a tool that made the single thing every query depends on settable
    by the caller and observable by nobody."""
    _mcp, state = server
    assert "set_target" not in TIER0
    assert not hasattr(state, "set_target"), "the method must go with the tool"
    assert not hasattr(state, "pinned"), "and so must the pin flag it branched on"


def test_repo_flag_sets_the_target_and_does_NOT_pin_it(tmp_path: Path) -> None:
    """`--repo` keeps working as an override and STOPS being a pin.

    Both halves matter. The override is still needed — a transport with no
    environment and no roots has nothing else — but the refusal it used to carry meant
    a session could not index a second repository at all (gh#19). So: tools up at
    startup, AND a later retarget succeeds."""
    reg = st.TargetRegistry(tmp_path / "state")
    repo, other = tmp_path / "mine", tmp_path / "theirs"
    repo.mkdir()
    other.mkdir()

    _mcp, state = build_server(reg)
    ## tier-1 is registered at construction now (gh#7); this test is about which SOURCE supplies
    ## the startup target, which the assertions below cover.

    state.resolve_startup_target(str(repo))
    assert Path(state.active.repo_path) == repo
    assert state.target_source == st.TARGET_SOURCE_FLAG
    assert state.tier1_active is True, "an explicit target exposes its tools immediately"

    state.adopt(str(other), st.TARGET_SOURCE_FLAG)
    assert Path(state.active.repo_path) == other, "--repo must not refuse a retarget"


def test_project_dir_env_resolves_a_target_at_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`$CLAUDE_PROJECT_DIR` is readable BEFORE any request, which is the only reason
    it outranks `roots/list`: tier-1 can come up on connect, so the common case never
    watches the tool list change mid-session."""
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "from_env"
    repo.mkdir()
    monkeypatch.setenv(st.PROJECT_DIR_ENV, str(repo))

    _mcp, state = build_server(reg)
    state.resolve_startup_target(None)
    assert Path(state.active.repo_path) == repo
    assert state.target_source == st.TARGET_SOURCE_ENV
    assert state.tier1_active is True


def test_the_flag_outranks_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An operator who typed `--repo` outranks the client's session directory. Without
    this the override would be unusable in exactly the case it exists for: a Claude
    Code session that also exports `CLAUDE_PROJECT_DIR`."""
    flagged, envd = tmp_path / "flagged", tmp_path / "envd"
    flagged.mkdir()
    envd.mkdir()
    monkeypatch.setenv(st.PROJECT_DIR_ENV, str(envd))
    assert st.startup_target(str(flagged)) == (str(flagged), st.TARGET_SOURCE_FLAG)


def test_a_stale_project_dir_falls_through_rather_than_being_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An environment variable is not a declaration about THIS server — it describes
    the client's session and may name a directory that has been moved or deleted.

    Adopting a phantom would consume the resolution chain and prevent the roots
    fallback from EVER running, which is the failure the ordering exists to avoid. So
    the env source must verify before it claims. `--repo` deliberately does not: an
    operator typed it, and a wrong path must fail loudly rather than be silently
    ignored in favour of something else."""
    monkeypatch.setenv(st.PROJECT_DIR_ENV, str(tmp_path / "deleted_yesterday"))
    assert st.startup_target(None) == (None, None), "a missing directory must not be adopted"

    monkeypatch.setenv(st.PROJECT_DIR_ENV, "")
    assert st.startup_target(None) == (None, None), "nor must an empty value"


@pytest.mark.anyio
async def test_roots_resolve_lazily_on_the_first_call_that_needs_a_target(
    tmp_path: Path,
) -> None:
    """THE ROUTE THAT CANNOT BE EAGER, and why the tool list is allowed to grow.

    `ctx.session.list_roots()` needs a live request; there is no session during
    `main()`. So a client that supplies only roots starts the server with NO target,
    and the first tool call that needs one acquires it — which registers tier-1 and
    fires `tools/list_changed`.

    Asserts the ORDER as well as the outcome: nothing is asked of the client until a
    call needs a target (`roots_calls == 0` at startup), and the second call does not
    ask again."""
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "from_roots"
    repo.mkdir()

    mcp, state = build_server(reg)
    assert state.resolve_startup_target(None) is None, "no eager source supplies one"
    ## Two tier-1-absence assertions removed here (gh#7): this test's subject is that startup
    ## resolves no target and does not call the client, both asserted below.

    ctx = _FakeCtx(roots=[repo.as_uri()])
    assert ctx.session.roots_calls == 0, "startup must not touch the client"

    status = await state.status(ctx)
    assert status["active"] is True
    assert Path(status["repo_path"]) == repo
    assert status["target_source"] == st.TARGET_SOURCE_ROOTS
    assert ctx.session.roots_calls == 1
    assert set(TIER1_TOOLS) <= await _names(mcp), "tier-1 arrives after the first call"

    await state.status(ctx)
    assert ctx.session.roots_calls == 1, "a resolved target must not re-ask the client"


@pytest.mark.anyio
async def test_a_client_advertising_no_roots_is_never_asked(tmp_path: Path) -> None:
    """Gated on `client_capabilities.roots`, so a client that does not offer the
    capability is not sent a request it would reject. The reply must still be the
    legible no-target error rather than a traceback."""
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    ctx = _FakeCtx()  # advertises nothing

    status = await state.status(ctx)
    assert status["active"] is False
    assert status["error"] == NO_TARGET_ERROR
    assert ctx.session.roots_calls == 0, "an unadvertised capability must not be probed"


@pytest.mark.anyio
async def test_a_refused_or_unusable_roots_list_degrades_to_no_target(tmp_path: Path) -> None:
    """Fails closed on both shapes of unusable answer: a client that raises, and a
    client that answers with roots that are not local directories.

    A target-resolution problem inside an ordinary tool call must degrade to "no
    target" — a message the caller can act on — never to an exception surfacing as a
    tool error the model will read as its own mistake."""
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)

    ## Advertises the capability, then raises when asked (see _FakeSession).
    refusing = _FakeCtx()
    refusing.client_capabilities = _FakeCapabilities([])
    refusing.session._roots = None
    assert await state._target_from_roots(refusing) is None

    ## Answers, but with nothing that verifies as a local directory.
    junk = _FakeCtx(roots=["https://example.invalid/repo", (tmp_path / "nope").as_uri()])
    assert await state._target_from_roots(junk) is None
    assert (await state.status(junk))["active"] is False


@pytest.mark.anyio
async def test_roots_list_changed_invalidates_only_a_roots_derived_target(
    tmp_path: Path,
) -> None:
    """`notifications/roots/list_changed` drops a roots-derived DEFAULT target and
    NOTHING ELSE — not an explicitly-set target, and not the query tools.

    The scoping is the assertion worth having. `--repo` is an operator's explicit
    instruction and `$CLAUDE_PROJECT_DIR` is the session the server was launched for;
    letting a client's root list override either would discard the more authoritative
    answer in favour of the least, silently. The handler is also reachable through the
    SDK's own registration map, so this cannot pass while the wiring is absent.

    THE TOOLS STAY, which is the half that changed with per-call routing. A query tool
    takes the repository on the call, so a dropped default costs a caller the ability to
    OMIT the argument and nothing else — every index the registry knows about is still
    readable. Withdrawing the tools here would be a mid-session capability change for a
    target nothing has asked for yet."""
    from mcp.types import NotificationParams

    reg = st.TargetRegistry(tmp_path / "state")
    from_roots, from_flag = tmp_path / "roots_repo", tmp_path / "flag_repo"
    from_roots.mkdir()
    from_flag.mkdir()

    mcp, state = build_server(reg)

    ## The notification is actually registered on the low-level server, by the
    ## non-deprecated route — not merely implemented as a method nothing calls.
    from clew.mcp_server._sdk import lowlevel

    entry = lowlevel(mcp).get_notification_handler(ROOTS_CHANGED_METHOD)
    assert entry is not None, f"{ROOTS_CHANGED_METHOD} has no registered handler"
    assert entry.params_type is NotificationParams

    ## A roots-derived target IS dropped — and the tools it never owned are not.
    state.adopt(str(from_roots), st.TARGET_SOURCE_ROOTS)
    assert state.tier1_active is True
    await entry.handler(None, NotificationParams())
    assert state.active is None
    assert state.target_source is None
    assert state.tier1_active is True, "the registry still holds an index worth querying"
    assert set(TIER1_TOOLS) <= await _names(mcp)
    ## But an un-targeted call has nothing to answer from, and says so.
    with pytest.raises(RuntimeError, match="No default target repository"):
        state.active_db()

    ## An explicitly-set target is NOT.
    state.adopt(str(from_flag), st.TARGET_SOURCE_FLAG)
    assert state.invalidate_roots_target() is False
    assert Path(state.active.repo_path) == from_flag
    assert state.tier1_active is True


# ─── gh#25: the roots link is on a deprecation clock, so pin the clock ────────


def test_the_sdk_still_offers_the_deprecated_roots_route() -> None:
    """TRIPWIRE. Fails the day mcp removes `ServerSession.list_roots`, which is the day
    resolution link (3) stops existing.

    Deliberately NOT a warning filter and NOT an `xfail`. A filter would hide exactly the
    signal this exists to deliver, and the failure mode being guarded against is silent:
    `_roots` catches every exception, so an SDK that dropped the method would degrade to
    "no target from the client" and read as a client that declined. The three assertions
    separate the ways it can change — the method going away, the deprecation being
    escalated or retracted, and the wire surface losing the request everywhere — because
    each implies a different next action.

    What to do when this fails: nothing is broken in this repo. Delete link (3) (`_roots`,
    `_target_from_roots`, `_roots_askable`, the `roots/list_changed` handler and
    `TARGET_SOURCE_ROOTS`), keep `--repo` and `$CLAUDE_PROJECT_DIR`, and update
    `NO_TARGET_ERROR` so it no longer names a source that cannot supply anything."""
    from mcp.server.session import ServerSession
    from mcp.shared.exceptions import MCPDeprecationWarning

    assert callable(getattr(ServerSession, "list_roots", None)), (
        "mcp removed ServerSession.list_roots — resolution link (3) is gone; "
        "delete the roots path rather than migrating it (there is no successor request)"
    )
    assert st.ROOTS_DEPRECATION_SEP in getattr(ServerSession.list_roots, "__deprecated__", ""), (
        "the deprecation notice on list_roots changed shape; re-read it before trusting "
        f"{st.ROOTS_DEPRECATION_SEP} facts recorded in state.py"
    )
    assert issubclass(MCPDeprecationWarning, Warning), "the silenced category must stay a Warning"

    surface = st.server_request_surface()
    assert surface is not None, (
        "the SDK's server-request map moved; roots_request_supported now fails open"
    )
    assert any(method == st.TARGET_SOURCE_ROOTS for method, _version in surface), (
        f"no protocol revision carries a standalone {st.TARGET_SOURCE_ROOTS} request any more"
    )


def test_no_successor_has_appeared_for_roots_on_the_modern_revisions() -> None:
    """TRIPWIRE ON THE FINDING, not on the code: SEP-2577 named no successor request, and
    the modern (per-request-envelope) revisions carry no standalone server-to-client
    request at all — roots moved inside the MRTR envelope, which this server does not
    implement.

    Pinned because that is the whole justification for containing rather than migrating. If
    a modern revision ever carries the request again, or the SDK grows a non-deprecated route
    to a client's working directory, this fails and gh#25's decision needs re-deciding — and
    the alternative to a test is a paragraph of prose nobody re-checks."""
    from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS

    for version in MODERN_PROTOCOL_VERSIONS:
        assert st.roots_request_supported(version) is False, (
            f"protocol {version} now carries a standalone {st.TARGET_SOURCE_ROOTS} request — "
            "re-read gh#25's decision, the roots path may be reachable there after all"
        )
    assert all(st.roots_request_supported(v) for v in HANDSHAKE_PROTOCOL_VERSIONS), (
        "every handshake-era revision must still carry the request; those are the only "
        "connections on which resolution link (3) works"
    )
    assert st.roots_request_supported(None) is True, "an unstated revision must fail OPEN"
    assert st.roots_request_supported("not-a-revision") is True, (
        "an unknown revision must fail OPEN"
    )


@pytest.mark.anyio
async def test_roots_is_not_asked_on_a_revision_that_cannot_carry_the_request(
    tmp_path: Path,
) -> None:
    """A 2026-07-28 connection is never sent `roots/list`, and a handshake-era one still is.

    The control arm is the point. Without it this passes on a `_roots` that never asks
    anybody anything — which is exactly the bug an over-eager version check would
    introduce, and it would look identical from the outside: no target, one log line."""
    repo = tmp_path / "advertised_repo"
    repo.mkdir()
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)

    modern = _FakeCtx(roots=[repo.as_uri()], protocol_version="2026-07-28")
    assert await state._target_from_roots(modern) is None
    assert modern.session.roots_calls == 0, (
        "the request must not be sent where it cannot be carried"
    )

    handshake = _FakeCtx(roots=[repo.as_uri()], protocol_version="2025-11-25")
    assert Path(await state._target_from_roots(handshake)) == repo
    assert handshake.session.roots_calls == 1, (
        "control: the same client IS asked on a handshake revision"
    )


@pytest.mark.anyio
async def test_a_roots_derived_target_announces_that_the_link_is_deprecated(
    tmp_path: Path, caplog
) -> None:
    """The operator must be able to LEARN that their target came from the deprecated link,
    before the day it stops working.

    It was silent before gh#25: `adopt` logged the source label at INFO alongside every
    other source, so "roots/list" appeared as one ordinary word in one ordinary line. A
    WARNING naming the SEP and the action is the difference between a year of notice and
    none.

    The negative arm matters as much: an explicit `--repo` must NOT be warned about, or the
    warning becomes noise that the one operator who needs it learns to ignore."""
    repo = tmp_path / "roots_repo"
    repo.mkdir()
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)

    with caplog.at_level(logging.WARNING, logger="clew"):
        await state.ensure_target(_FakeCtx(roots=[repo.as_uri()]))
    warned = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warned, "a roots-derived target must warn that the link is deprecated"
    assert any(st.ROOTS_DEPRECATION_SEP in m for m in warned), f"the SEP must be named: {warned}"
    assert any(st.TARGET_SOURCE_FLAG in m for m in warned), f"the migration must be named: {warned}"

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="clew"):
        state.adopt(str(repo), st.TARGET_SOURCE_FLAG)
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == [], (
        "an explicit --repo is not deprecated and must not warn"
    )


def test_root_uri_parsing_verifies_before_it_trusts(tmp_path: Path) -> None:
    """A root is a client-supplied string that this server turns into a repo it will
    INDEX, so it fails closed on anything it cannot verify.

    The percent-encoding case is the one that would have been missed by string surgery
    on the URI: a space in a directory name arrives encoded, and `uri[7:]` yields a
    path that does not exist — rejected by the directory check for entirely the wrong
    reason, and indistinguishable from a genuinely absent root."""
    spaced = tmp_path / "my repo"
    spaced.mkdir()
    assert st.root_uri_to_path(spaced.as_uri()) == spaced, "percent-encoding must round-trip"
    assert "%20" in spaced.as_uri(), "premise: the URI really is encoded"

    plain_file = tmp_path / "file.txt"
    plain_file.write_text("x")
    assert st.root_uri_to_path(plain_file.as_uri()) is None, "a file is not a repo root"
    assert st.root_uri_to_path((tmp_path / "absent").as_uri()) is None
    assert st.root_uri_to_path("https://example.invalid/repo") is None, "only file:// is local"
    assert st.root_uri_to_path("") is None


@pytest.mark.anyio
async def test_a_server_with_no_target_does_not_answer_from_a_previous_one(
    tmp_path: Path, rich_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE PIN HAZARD, asserted directly — this is the test whose absence let the
    hazard stand.

    The recorded failure: a 36-cell benchmark grid published "the index is 8 points
    WORSE" from an arm whose server was pinned to a sanitized target by an OLDER grid,
    while every question asked about a different repository. 15 of 18 cells said so in
    prose and all 36 were recorded valid, because every validity term checked that
    database tools were CALLED and none checked which repository answered.

    So two properties, and the second is the one that was missing:
      * a server that resolves no target must REFUSE, not serve a stale one;
      * and when it does serve, the reply must NAME the repository, so a caller can
        see the mismatch instead of inferring it from prose."""
    reg = st.TargetRegistry(tmp_path / "state")
    previous = tmp_path / "previous_target"
    previous.mkdir()

    _mcp, state = build_server(reg)
    ## A target is REGISTERED and BUILT — exactly the residue a restart leaves behind. Registered
    ## explicitly because `adopt` no longer registers (gh#1): resolution is not registration, so
    ## simulating a built target now means saying so rather than relying on adoption's side effect.
    target = reg.register(str(previous))
    Path(target.db_path).write_bytes(rich_db.read_bytes())
    state.adopt(str(previous), st.TARGET_SOURCE_FLAG)
    assert state.tools.dossier("sensor_poll")["target"] == str(previous)

    ## Now a FRESH server, same registry, no --repo, no env, a client with no roots.
    monkeypatch.delenv(st.PROJECT_DIR_ENV, raising=False)
    _mcp2, fresh = build_server(reg)
    assert fresh.resolve_startup_target(None) is None
    assert fresh.active is None, "a registered target is not an ACTIVE one"

    status = await fresh.status(_FakeCtx())
    assert status["active"] is False, "it must not adopt the previously-registered target"
    assert str(previous) not in repr(status), "and must not even name it"

    ## And the tier-1 accessors refuse rather than reaching for the registry. A call that
    ## NAMES the previous target may still have it — the registry is public and `cull`
    ## exists — but a call that names nothing must never be answered from it.
    with pytest.raises(RuntimeError, match="No default target repository"):
        fresh.active_db()
    assert [t.repo_path for t in reg.targets()] == [str(previous)], "the registry is untouched"


def test_an_unbuilt_target_fails_by_name_not_by_sqlite(tmp_path: Path) -> None:
    """Now that tier-1 comes up as soon as a TARGET is known, "target known, database
    not built" is the first state of every fresh install — and it used to surface as a
    bare sqlite "unable to open database file" three frames deeper.

    The message must name `build_or_refresh`, which is the one action that fixes it."""
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "unbuilt"
    repo.mkdir()
    _mcp, state = build_server(reg)
    state.adopt(str(repo), st.TARGET_SOURCE_FLAG)

    with pytest.raises(RuntimeError, match=r"index\(action='refresh'"):
        state.active_db()
    with pytest.raises(RuntimeError, match=str(repo)):
        state.active_db()


# ─── the promised surface ────────────────────────────────────────────────────


def test_the_public_tool_names_are_frozen() -> None:
    """README declares MCP tool names COVERED by semantic versioning. Until this
    test existed that promise could not be kept: every other assertion in this file
    compares `TIER1_TOOLS` against ITSELF, so renaming a tool — a breaking change for
    every agent configuration in existence — passed the whole suite silently.

    The duplication is deliberate. A rename now fails here, which turns it into a
    deliberate act with a major-version consequence instead of an editing accident.
    Same reasoning as the committed schema snapshot, applied to the surface that is
    actually promised rather than the one explicitly excluded."""
    assert set(TIER1_TOOLS) == set(FROZEN_TIER1_NAMES), (
        "the MCP tool-name surface changed. README declares these names covered by "
        "semver, so adding one is a MINOR bump and renaming or removing one is a "
        "MAJOR bump — update this frozen set in the same commit, on purpose."
    )


def test_tier0_and_tier1_names_do_not_collide() -> None:
    """Two tools with one name means whichever registers last wins, and the loser
    becomes silently unreachable. Cheap to assert, and it holds the boundary that
    every register/unregister test below depends on."""
    assert TIER0.isdisjoint(FROZEN_TIER1_NAMES)


def test_status_reports_WHY_the_file_set_is_what_it_is(tmp_path: Path) -> None:
    """The only clearly actionable gap the corrected entropic grid found in 56 marks.

    Q4 mark 3 asks whether an answer "checks the Doxyfile too and reports that its `INPUT`
    does NOT list `examples/`". The raw arm scored 3/3, the index arm 1/3 — the raw arm just
    reads the Doxyfile, and the index arm had no route to it. `build_meta` held exactly one
    key, `build_version`, so a consumer could see WHAT was indexed and never WHY.

    The pipeline had the answer all along: `scope.DerivedScope` carries the source, a reason,
    and the roots and excludes, and its own docstring says it exists "so the BUILD LOG can
    always say which scope was used and why". The log is gone by the time anyone queries.

    Two properties, and the second was a defect I introduced and caught here:
      - the provenance round-trips through `build_meta` into `db_status`
      - paths are REPO-RELATIVE. The first cut stamped `DerivedScope`'s absolute paths
        verbatim, reintroducing the machine-layout disclosure that forced the build-version-9
        bump (`path.name` held the builder's home directory in 112 of 112 rows). `status` is
        published over MCP; the build machine's directory layout is not a consumer's business.
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    write_build_signature(
        db,
        scope={
            "source": "doxygen-guard",
            "reason": "doxygen-guard hook scope declared in .pre-commit-config.yaml",
            "roots": "clew/cli.py",
            "excludes": "tests/",
        },
    )

    status = db_status(Target(repo_path=str(tmp_path), slug="t", db_path=str(db)))
    scope = status["scope"]
    assert scope["source"] == "doxygen-guard"
    assert scope["roots"] == "clew/cli.py"
    for key, value in scope.items():
        assert not value.startswith("/home/"), f"scope.{key} leaks an absolute machine path"


def test_status_on_a_PRE_SCOPE_index_says_nothing_rather_than_guessing(tmp_path: Path) -> None:
    """An index built before build 16 has no scope keys. `db_status` must omit the field
    rather than invent a default — "not recorded" and "recorded as empty" are different
    claims, and a consumer weighing why a file is missing must be able to tell them apart."""
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db = tmp_path / "old.db"
    sqlite3.connect(str(db)).close()
    write_build_signature(db)  # no scope, as an older pipeline wrote it

    status = db_status(Target(repo_path=str(tmp_path), slug="t", db_path=str(db)))
    assert status["scope"] == {}, "an unrecorded scope must be empty, never fabricated"


def test_status_reports_WHAT_THE_BUILD_DID_NOT_FIND(tmp_path: Path) -> None:
    """gh#320, and the reader half of it. `collect` and `write_build_signature` are covered
    in tests/test_diagnostics.py; nothing there notices if `db_status` stops reporting the
    section, which would leave the rows on disk and invisible to every consumer — the same
    shape as the scope provenance that was computed, logged and discarded.

    Both counts are asserted as the STRING `"0"` on purpose. `write_build_signature` drops
    falsy values, so an int would vanish here and "searched and found nothing" would be
    indistinguishable from "never looked" — which is the entire point of the section.
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    write_build_signature(
        db,
        diagnostics={
            "accessor_families": "Store_Set_* (5 keys)",
            "accessor_families_count": "1",
            "accessor_names_examined": "2196",
            "unclaimed_event_aliases_count": "0",
            "event_vocabulary_source": "built-in",
        },
    )

    status = db_status(Target(repo_path=str(tmp_path), slug="t", db_path=str(db)))
    diagnostics = status["diagnostics"]

    assert diagnostics["accessor_families"] == "Store_Set_* (5 keys)"
    assert diagnostics["accessor_names_examined"] == "2196", "a zero needs its denominator"
    assert diagnostics["unclaimed_event_aliases_count"] == "0", "the zero must survive"


def test_status_on_a_PRE_DIAGNOSTICS_index_says_nothing_rather_than_guessing(
    tmp_path: Path,
) -> None:
    """The control, and it is the same one the scope section gets. An index built before
    gh#320 has no `diagnostics.*` rows, and the SECTION being empty is the honest report for
    it — "this pipeline never looked" is a different claim from "it looked and found none",
    and only a fabricated zero here would confuse them.
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db = tmp_path / "old.db"
    sqlite3.connect(str(db)).close()
    write_build_signature(db)

    status = db_status(Target(repo_path=str(tmp_path), slug="t", db_path=str(db)))
    assert status["diagnostics"] == {}, "an unrecorded diagnostic must not read as a zero"


## @brief thread_roster answers with an inventory envelope, not a bare `_many` list.
## @param tools The tier-1 tool surface over the fixture index.
## @version 1
def test_thread_roster_answers_with_an_envelope_carrying_its_split(tools: QueryTools) -> None:
    """THE GAP THAT LET THE SHAPE CHANGE PASS UNNOTICED. gh#346 moved this tool from `_many` to
    `wire.one`, and the whole suite stayed green: the two tests that drive every tier-1 tool check
    JSON round-tripping and target attribution, and both hold under either shape. Nothing pinned
    the payload, so nothing would have caught the reverse either — a later edit routing it back
    through `_many` would silently drop `origin` and `row_meaning`.

    THE FIXTURE SPAWNS NO THREADS, which is the case that discriminates. Through `_many` an empty
    result gets the definitive-sounding "the database records none" note — correct for a list of
    matches, wrong here, because it converts "this build recorded no spawn sites" into a claim
    about the code. The envelope's own `row_meaning` is what says which of those two it is.

    @brief The reply is an inventory envelope with origin and row_meaning.
    @version 1
    """
    ## Through `search(corpus='threads')` since gh#372. The roster is a corpus — "what
    ## does this repo have" is the same question `search` answers with the filter empty —
    ## and the ENVELOPE is what survives the fold. An inventory flattened into `_many`
    ## rows would lose exactly the fields below, which is why the corpora are deliberately
    ## not normalised to one shape.
    reply = tools.search(corpus="threads")

    assert "threads" in reply and "origin" in reply and "row_meaning" in reply, (
        "routed through `_many` this would be a bare list under `results` with no split"
    )
    assert reply["origin"]["total"] == 0
    ## `False`/`0` are not absent, so the zero buckets must survive wire pruning — a
    ## `first_party` that vanished would read as "not measured".
    assert reply["origin"]["first_party"] == 0
    assert "records none" not in json.dumps(reply), (
        "an empty roster must not claim the DATABASE records none — the fixture's build is what "
        "found no spawns, and the two are different facts"
    )


## @brief The inventory reports the mutex count apart from the row count.
## @param tmp_path pytest temp dir.
## @version 1
def test_lock_roster_separates_the_mutex_count_from_the_row_count(tmp_path: Path) -> None:
    """THE TRAP THE OBVIOUS SHAPE WOULD HAVE SET. `locks` is keyed
    UNIQUE(name, scope, kind), so one `std::shared_mutex` taken with both a
    `lock_guard` and a `shared_lock` occupies TWO rows. A roster returning only rows
    invites "the codebase has len(rows) mutexes", and an acceptance rubric grades
    refusing exactly that conflation — so a convenience tool that returned rows alone
    would have made its own graded error easier to commit rather than harder.

    The fixture is that case and nothing else: two rows, one physical mutex, plus an
    unrelated mutex in another scope so the collapse cannot be a no-op that happens to
    look right. `distinct_mutexes` must be 2, not 3.

    Collapsing on (name, scope) rather than on `name` alone is also asserted, by giving
    both classes a member called `mutex_` — the real C++ member name that recurs across
    unrelated classes. A bare-name collapse would merge them and UNDER-count, which is
    the opposite error and the harder one to notice.
    """
    from clew import query as q

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
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
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'src/engine.cpp')")
    conn.execute("INSERT INTO memberdef (rowid, name) VALUES (1, 'poll')")
    ## ONE physical shared_mutex, split across two guard kinds by the UNIQUE key.
    conn.executemany(
        "INSERT INTO locks (id, name, scope, kind, decl_path_rowid, decl_line, "
        "identity_confidence, source) VALUES (?, ?, ?, ?, 1, ?, 'high', 'ast')",
        [
            (1, "mutex_", "class:Registry", "shared_mutex", 10),
            (2, "mutex_", "class:Registry", "mutex", 10),
            ## A DIFFERENT mutex that shares the bare member name, so a collapse on
            ## `name` alone would wrongly merge it into the pair above.
            (3, "mutex_", "class:Cache", "mutex", 44),
        ],
    )
    conn.executemany(
        "INSERT INTO lock_acquisitions (lock_id, holder_rowid, path_rowid, form, role, "
        "mode, start_line, pattern_name, declared, confidence) "
        "VALUES (?, 1, 1, 'raii', 'scoped', 'exclusive', ?, 'lock_guard', 0, 'high')",
        [(1, 11), (1, 12), (3, 45)],
    )
    conn.commit()
    conn.close()

    inv = q.lock_roster(db)

    assert inv.rows == 3, "three identities"
    assert inv.distinct_mutexes == 2, "but two physical mutexes — the collapse must fire"
    ## "identity(ies)", not "mutex(es)". The collapse this test guards is still asserted above
    ## on `distinct_mutexes`; what changed is that the PAYLOAD no longer calls the collapsed
    ## number a mutex count, because it is not one — `name` is the operand SPELLING at an
    ## acquisition site, so two spellings of one object count twice and one spelling reached
    ## from unrelated types counts once. The field keeps its name for compatibility and the
    ## sentence now says so.
    assert "3 row(s) over 2 distinct lock identity(ies)" in inv.row_meaning
    assert "distinct_mutexes" in inv.row_meaning, "the field must still be explained by name"
    ## Ordered by acquisition count descending, so the heavily-used lock is first —
    ## "then report what runs inside a heavily-used one" is the actual follow-up.
    assert inv.locks[0].acquisitions == 2
    ## A lock declared and never acquired still appears, with zero. An inner join would
    ## have dropped it, answering "that lock does not exist" for a real declaration.
    assert sorted(e.acquisitions for e in inv.locks) == [0, 1, 2]


## @brief An index predating the lock layer yields an empty inventory, not an error.
## @param tmp_path pytest temp dir.
## @version 1
def test_lock_roster_on_an_index_without_the_layer_says_so(tmp_path: Path) -> None:
    """`row_meaning` must distinguish "no locks in this repo" from "no lock TABLE in
    this index". An absent table is a fact about the BUILD and never evidence about the
    code, and a caller that cannot tell them apart reports a threadless codebase and a
    pre-layer index identically."""
    from clew import query as q

    db = tmp_path / "bare.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("CREATE TABLE path (name TEXT);")
    conn.commit()
    conn.close()

    inv = q.lock_roster(db)

    assert inv.locks == ()
    assert inv.rows == 0
    assert "predates the lock layer" in inv.row_meaning
    assert "NOT evidence" in inv.row_meaning, "absence of a table is not absence of mutexes"


## @brief An unregistered target is REFUSED, never answered from the derived default.
## @return None.
## @version 1
def test_an_unknown_target_is_refused_by_name(tmp_path: Path) -> None:
    """THE MOST EXPENSIVE RECORDED DEFECT IN THIS PROJECT, and until now it had no test.
    A 36-cell grid published "the index is 8 points WORSE" from an arm pointed at the wrong
    repository: 15 of 18 cells said so in their own prose and all 36 were recorded valid,
    because every validity term checked that database tools were CALLED and none checked
    which repository answered.

    `resolve_target` refuses correctly today — registry match, else derive if the string is
    a real directory, else raise — and `answering` refuses an unbuilt index by name. Both
    were verified live. Neither was pinned, so a single edit could restore the silent
    fallback and every downstream number would look exactly as healthy as before.

    THE REFUSAL MUST NAME THE KNOWN TARGETS. "Unknown target" alone tells a model nothing
    it can act on; the list is what turns a dead call into a corrected one.

    @brief An unregistered target raises and lists what IS registered.
    @return None.
    @version 1
    """
    registry = st.TargetRegistry(tmp_path / "state")
    real = tmp_path / "registered"
    real.mkdir()
    registry.register(str(real))
    _mcp, srv = build_server(registry)

    with pytest.raises(RuntimeError) as caught:
        srv.resolve_target("mbedtls")
    message = str(caught.value)
    assert "mbedtls" in message, "the refusal must name what was asked for"
    assert str(real) in message, "and must list what IS registered, or it is unactionable"


## @brief A real directory with no built index refuses with the build call, not a wrong answer.
## @return None.
## @version 1
def test_an_unbuilt_directory_target_refuses_instead_of_answering(tmp_path: Path) -> None:
    """THE SECOND HALF, and the one a naive fix breaks. An unregistered string that IS a
    directory must NOT raise `unknown target` — deriving a target for it is how a
    third-party repo gets indexed in the first place — but it must not silently answer from
    the DERIVED DEFAULT either. It has to refuse with the exact call that fixes it.

    Do not "fix" this by auto-building an unknown target: a typo would then silently index
    something, which trades a loud wrong answer for a quiet expensive one.

    @brief An unbuilt but real directory refuses, naming build_or_refresh.
    @return None.
    @version 1
    """
    registry = st.TargetRegistry(tmp_path / "state")
    _mcp, srv = build_server(registry)
    unbuilt = tmp_path / "never_indexed"
    unbuilt.mkdir()

    ## Resolution SUCCEEDS — the directory exists, so a target can be derived for it.
    assert srv.resolve_target(str(unbuilt)).repo_path == str(unbuilt)

    ## Querying it must not. This is the boundary the grid failure crossed.
    with pytest.raises(RuntimeError) as caught:
        srv.answering(str(unbuilt))
    message = str(caught.value)
    assert "index(action='refresh'" in message, "the refusal must carry the call that fixes it"
    assert str(unbuilt) in message


## @brief The refusal reaches MORE THAN ONE tool, because it lives where target is resolved.
## @return None.
## @version 1
def test_the_target_refusal_is_shared_by_every_routed_tool(rich_db: Path, tmp_path: Path) -> None:
    """THE PLAN'S EXPLICIT REQUIREMENT, and the reason it is explicit: a guard added at one
    tool's entry point protects that tool and quietly leaves the other twenty-one answering
    from the wrong index. Driving two DIFFERENT tools through the same bad target is what
    proves the check sits where the target is RESOLVED rather than where one caller happens
    to ask.

    @brief Two different tools both refuse the same unroutable target.
    @return None.
    @version 1
    """
    ## Bound to ONE database with no answerer, which is the shape that must refuse to route.
    tools = QueryTools(lambda: rich_db, lambda: tmp_path)
    for call in (
        lambda: tools.search("anything", target="some-other-repo"),
        lambda: tools.dossier("anything", target="some-other-repo"),
    ):
        with pytest.raises(RuntimeError) as caught:
            call()
        assert "some-other-repo" in str(caught.value)


## @brief `targets` is a LISTING and must not return full status per repository.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_targets_is_a_listing_not_a_wall_of_full_status(tmp_path: Path) -> None:
    """THE TOOL DESCRIPTION PROMISES "every indexed repository with its database age and
    staleness" AND THE CODE RETURNED EVERYTHING — `db_status` per target, which carries scope
    (including a full `excludes` string that ran to thousands of characters on one real target),
    coverage, the per-stage refresh timings, options, diagnostics, data_model, code identity and
    the staleness block.

    MEASURED ON THE LIVE SERVER with nine registered targets: tens of kilobytes for a call whose
    job is orientation, with the SAME ~700-character code-staleness message repeated once per
    target. It is the first call a consumer with several repositories makes, and it answers with
    a wall.

    AND IT IS UNBOUNDED. Every query tool trims to `RESPONSE_BUDGET_BYTES`; this one applied no
    budget at all, so the reply grows without limit in the number of registered repositories.
    That is the difference between "verbose" and "breaks at scale".

    THE FIX IS TO MATCH THE PROMISE, not to invent a new one: identity, existence, version,
    staleness and age — the fields the description already names — and route to
    `index(action='status')` or `index(action='stats')` for the rest.

    @brief Targets rows are compact, bounded, and carry what the description promises.
    @return None.
    @version 1
    """
    import json as _json

    from clew.mcp_server.server import DocsDbServer
    from clew.mcp_server.tools_query import RESPONSE_BUDGET_BYTES

    from clew.mcp_server import state as st

    state = DocsDbServer(st.TargetRegistry(tmp_path / "state"))
    for name in ("alpha", "beta", "gamma"):
        repo = tmp_path / name
        repo.mkdir()
        target = state.registry.register(repo)
        ## THE HEAVY BLOCKS ONLY APPEAR FOR AN EXISTING DATABASE, so a registered-but-unbuilt
        ## target does not reproduce this at all — the first version of this test passed against
        ## the defect for exactly that reason.
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target.db_path).write_text("db")

    rows = state.list_targets()
    assert len(rows) == 3, "every registered repository must still be listed"

    ## The fields the description promises, all present.
    for row in rows:
        for key in ("repo_path", "exists", "build_version", "stale"):
            assert key in row, f"a listing row must carry {key!r}"

    ## The heavy per-target blocks belong to status/stats, not to a listing.
    heavy = {"scope", "coverage", "refresh", "options", "diagnostics", "data_model"}
    for row in rows:
        carried = heavy & set(row)
        assert not carried, (
            f"a listing row carries {sorted(carried)}; that is `status`/`stats` detail and it "
            f"multiplies by the number of registered repositories"
        )

    assert len(_json.dumps(rows)) <= RESPONSE_BUDGET_BYTES, (
        "the listing must respect the same response budget every query tool does — it was the "
        "one reply with no bound at all"
    )


@pytest.mark.anyio
## @req REQ-DDB-MCP-003
async def test_every_served_tool_is_exempt_from_tool_search_deferral(server) -> None:
    """gh#7, AND THE EVIDENCE IS A MEASURED SESSION RATHER THAN A THEORY. A client may present
    MCP tools as DEFERRED — named in a reminder with no schema, callable only after a `ToolSearch`
    round trip. `grep` is then one call away and `dossier` is two. A reporter documented clew in
    their repo's CLAUDE.md, indexed it, ran a multi-hour session, made 6 greps of which 4 were
    dossier-answerable, and called the index ZERO times spontaneously. One of those greps produced
    a wrong conclusion a `dossier` reply later corrected.

    ASSERTED ON EVERY TOOL, not just the query pair. `index` is what a first-time user must call
    before anything works, so a deferred `index` puts the penalty on the first interaction — the
    one where someone decides whether the tool is worth the trouble.

    READ OFF `list_tools`, which is the wire, not off the constant. A test asserting
    `ALWAYS_LOAD_META == {...}` would pass while `add_tool` dropped the argument on the floor.

    The manifest half of this (`alwaysLoad` in `.claude-plugin/plugin.json`) cannot be verified
    from inside this process and is pinned by tests/test_plugin_manifest.py instead.

    @brief Every served tool carries the always-load exemption on the wire.
    @return None.
    @version 1
    """
    mcp, _state = server
    served = await mcp.list_tools()
    assert served, "precondition: the server must serve tools for this to mean anything"

    missing = sorted(
        tool.name for tool in served if not (tool.meta or {}).get("anthropic/alwaysLoad")
    )
    assert not missing, (
        f"these tools would be deferred behind a ToolSearch round trip: {missing}. `grep` is one "
        f"call away; a deferred tool is two, and that asymmetry decides which gets reached for."
    )


@pytest.mark.anyio
## @req REQ-DDB-MCP-001
async def test_resolving_a_target_registers_nothing(tmp_path: Path) -> None:
    """gh#1. `adopt` called `registry.register`, which persists the entry AND mkdirs its state
    directory — so merely LAUNCHING the server in a directory registered it forever, before any
    database existed. A reporter found three targets listed with `exists: false`, one of them their
    entire home directory. `cull` could clear none of them: it removes aged-out or version-stale
    DATABASES and these had none, so the registry could accumulate rows nothing could reach. Same
    root cause as the orphaned state directories that had to be deleted by hand.

    ASSERTS THE DIRECTORY TOO, not only the registry row. The mkdir is the half that consumed disk,
    and a fix that stopped persisting while still creating directories would pass a registry-only
    check.

    @brief Adopting a repo makes it active without registering or creating anything.
    @return None.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "somewhere"
    repo.mkdir()

    _mcp, state = build_server(reg)
    active = state.adopt(str(repo), st.TARGET_SOURCE_FLAG)

    assert active is not None and active.repo_path == str(repo), "it must still become active"
    assert reg.targets() == [], (
        f"resolving a target registered it: {[t.repo_path for t in reg.targets()]}. Launching the "
        f"server somewhere is not a statement that the directory should be indexed."
    )
    assert not Path(active.db_path).parent.exists(), (
        "no state directory may be created for a target nothing has built"
    )


@pytest.mark.anyio
## @req REQ-DDB-MCP-001
async def test_building_a_target_does_register_it(tmp_path: Path) -> None:
    """THE POSITIVE HALF, and without it the fix above is satisfied by never registering at all —
    which would break `targets` and `cull` completely. Registration is EARNED by a build, because
    a build has to have somewhere to write.

    @brief An explicitly registered target is listed and has its directory.
    @return None.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "real"
    repo.mkdir()

    target = reg.register(str(repo))

    assert [t.repo_path for t in reg.targets()] == [str(repo)], (
        "a registered target must be listed — this is what `targets` and `cull` operate on"
    )
    assert Path(target.db_path).parent.is_dir(), "a build needs its directory to exist"


## @brief NOTHING the server serves exceeds the client's cap, so nothing is ever truncated.
## @return None.
## @version 2
def test_no_served_text_is_ever_truncated() -> None:
    """OWNER RULING: no truncation should occur, ever — fit everything inside the budget and prove
    it. This is that proof, and it replaces a weaker test that only asserted the IMPORTANT phrases
    landed inside the cap. That version tolerated discarded bytes as long as the routing survived,
    which is a different and much softer promise.

    THE CAP IS MEASURED, NOT ASSUMED. A client truncates each served string at 2,048 characters
    and reports nothing: verified against one session's own delivered context, where dossier's
    3,079-char description arrived cut at exactly 2,048 and search's 3,064 at the identical offset.
    PER TOOL, not a shared budget, so the fix is what occupies each 2 KiB rather than how many
    tools there are.

    WHY THIS SHIPPED WITHOUT ANYONE NOTICING: the server sends the bytes, gets no error, and
    `server.py`'s own comment budgets the cost in bytes SENT. Nothing measured bytes RECEIVED. So
    INSTRUCTIONS carried every routing rule past the cut while the one line that did arrive said
    the index is not a substitute for reading source — and a session spent twenty turns on grep
    asserting exactly that.

    A LENGTH ASSERTION CANNOT BE GAMED, which is why it is the whole test now. Reordering satisfies
    "the important part survives"; only fitting satisfies "nothing is lost".

    @brief Every served string fits the cap.
    @return None.
    @version 2
    """
    from clew.mcp_server.descriptions import load_descriptions
    from clew.mcp_server.server import INSTRUCTIONS, TIER0_TOOLS

    cap = 2048
    surfaces = {"INSTRUCTIONS": INSTRUCTIONS, **load_descriptions(), **TIER0_TOOLS}
    over = {k: len(v) - cap for k, v in surfaces.items() if len(v) > cap}
    assert not over, (
        f"these served strings exceed the {cap}-char cap and will be silently truncated: {over}. "
        f"Cut them; the parameter schema is the place for per-argument detail, since it is never "
        f"truncated."
    )

    ## AND THE ROUTING MUST STILL BE THERE. Fitting by deleting the reason to use the tool would
    ## pass the length check and defeat the point, so the load-bearing sentences are named.
    for phrase, why in (
        ("START AT `dossier`", "the routing rule"),
        ("VERBATIM SOURCE", "the fact whose absence sent a session to grep for 20 turns"),
        ("max_body_lines", "how to read past a truncated body"),
        ("USE `search`", "what to do without a name"),
    ):
        assert phrase in INSTRUCTIONS, f"INSTRUCTIONS lost {phrase!r} — {why}"

    ## dossier must say what it returns in its OPENING sentence. It previously said so at char 640,
    ## inside the cap, and a session still got it wrong; position is doing work presence did not.
    head = load_descriptions()["dossier"][:200]
    assert "VERBATIM SOURCE BODY" in head, (
        f"dossier must state it returns source in its first 200 chars; got: {head!r}"
    )


## @brief Every tool parameter carries a description, in the one channel a client cannot cut.
## @return None.
## @version 1
def test_every_tool_parameter_is_described() -> None:
    """THE ONLY UNTRUNCATABLE SURFACE, AND IT USED TO CARRY NOTHING. Parameter descriptions land in
    the JSON Schema, which a client re-sends whole on every request — while a measured 33% of every
    prose description is discarded at a 2,048-character cap. Before this, every parameter arrived
    as an auto-generated title and nothing else: `{"default": 120, "title": "Max Body Lines"}`.

    That absence has a measured cost. A session read `Max Body Lines` with no explanation, never
    learned that `body` is verbatim source with inline comments, and told its operator the index
    could not return source at all — then spent twenty turns on grep on the strength of it. One
    schema field would have prevented it, and the schema field is the one thing that always
    arrives.

    @brief Parameters are described where truncation cannot reach.
    @return None.
    @version 1
    """
    import typing

    from clew.mcp_server.server import DocsDbServer
    from clew.mcp_server.tools_query import QueryTools

    for owner, name in (
        (QueryTools, "dossier"),
        (QueryTools, "search"),
        (DocsDbServer, "index"),
        (DocsDbServer, "propose_declaration"),
    ):
        fn = getattr(owner, name)
        hints = typing.get_type_hints(fn, include_extras=True)
        undescribed = []
        for pname, hint in hints.items():
            if pname in ("return", "self", "ctx"):
                continue
            meta = getattr(hint, "__metadata__", ())
            if not any(getattr(m, "description", None) for m in meta):
                undescribed.append(pname)
        assert not undescribed, (
            f"{name}: {undescribed} carry no schema description, so they reach a model as bare "
            f"auto-titles in the one channel that is never truncated"
        )

    ## AND THE ONE THAT MATTERS MOST BY NAME. This is the field whose silence produced a wrong
    ## claim to an operator, so it is asserted on its content and not merely its presence.
    body = typing.get_type_hints(QueryTools.dossier, include_extras=True)["max_body_lines"]
    text = next(m.description for m in body.__metadata__ if getattr(m, "description", None))
    assert "VERBATIM SOURCE" in text and "truncated" in text, (
        f"max_body_lines must state that it returns verbatim source and how to read past a "
        f"truncated body; got: {text!r}"
    )
