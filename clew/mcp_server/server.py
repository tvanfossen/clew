# SPDX-License-Identifier: MIT
"""R3 MCP server over clew.db — two tiers, official Python MCP SDK.

TIER-0 (static, always available, even before any database exists):
`build_or_refresh`, `status`, `list_targets`, `cull`, `propose_declaration`. That
last one is tier-0 because the state it exists to fix — a repo that has not
declared its conventions — is exactly the state in which no tier-1 tool is
registered.
TIER-1 (dynamic, registered once this server knows of any repository at all — an
active target, or one in the registry): the R2 query tools, added with
`MCPServer.add_tool` and removed with `remove_tool`. After a successful build the
server fires `ctx.session.send_tool_list_changed()` so the client re-reads
`tools/list`.

The tier-1 gate is deliberately NOT "a target is derived". A query tool takes the
repository on the call, so it can answer about any registered index whether or not
this process derived a default — gating on the derived target would hide a working
capability from exactly the deployment this server is for: one process, launched at
no repository in particular, serving several sessions on several repositories.

## ONE PROCESS, ANY NUMBER OF REPOSITORIES

Every query tool and `build_or_refresh` take an optional `target`. Omitted, they use
the derived target and behave exactly as they would with no such argument. Supplied,
they resolve that string — a repo root path, or a slug from `list_targets` — and
answer from it WITHOUT adopting it: nothing about a routed call survives the call.
A string that matches no registered target and is not a directory is REFUSED, naming
what was searched and what is registered, because the alternative to refusing a
mistyped path is starting a multi-minute index of the wrong tree.

`status` and `propose_declaration` take no `target`, deliberately. `status` reports on
the DEFAULT — which repository this connection answers from when a call names none,
where that came from, and whether the tool list is up — and `list_targets` already
reports freshness for every registered index, so a `target` there would produce two
overlapping answers to one question with `target_source` and `tier1_registered`
meaning nothing in one of them. `propose_declaration` reads a repository's source to
draft its declaration; the repository it must read is the one the session is working
in, not one being queried about.

"Takes no `target`" is enforced by a REFUSAL, not by an absent parameter, and it has to
be: `index` is one tool with one signature serving five actions, two of which do route,
so `target` is necessarily on the wire for all five. `TARGET_ROUTING_ACTIONS` is where
the distinction lives. Between this paragraph and that constant there was once a third
document — the tool description — asserting that every action took a target; the code
followed neither, and dropped the argument in silence.

Concurrent refreshes are deduplicated per TARGET: `_build_lock` hands each repository
its own `anyio.Lock`, and the freshness re-check happens inside it, so four sessions
asking one repository to refresh produce one build and three skips. The lock is an
anyio one and not a `threading` one because it is held across `to_thread.run_sync` —
blocking the event loop there would stall the transport for every other session.

## The server does not hold a target it was TOLD to hold (gh#22)

There is no `set_target` tool and `--repo` is not a pin. The DEFAULT target — what a
call answers from when it names none — is DERIVED, in this order:

1. `--repo <path>` — an explicit override for a transport that supplies nothing
   (HTTP/SSE get no environment and may advertise no roots). It sets the target;
   it does not refuse a later retarget.
2. `$CLAUDE_PROJECT_DIR` — set in a spawned local stdio server's environment, so
   it is readable at startup and tier-1 comes up on connect.
3. the client's `roots/list` — LAZILY, on the first tool call that needs a target
   and finds none, and only when the client advertises the capability. This one
   cannot be eager: `ctx.session.list_roots()` needs a live request and there is
   no session during `main()`. Under this path the tool list grows after the first
   call, which is what `tools/list_changed` is for.

`notifications/roots/list_changed` invalidates a target that came from (3) and
only from (3) — see `state.TARGET_SOURCE_*`.

## Link (3) IS ON A DEPRECATION CLOCK AND WILL BE DELETED, NOT MIGRATED (gh#25)

Roots is deprecated as of the 2026-07-28 revision (SEP-2577) with earliest removal a
revision released on or after 2027-07-28. There is no successor request: the spec's own
migration path for Roots is "pass directories or files via tool parameters, resource URIs,
or server configuration", and `--repo` is that server configuration — so link (1) is
already the migration and link (3) is what goes away. The facts, the trigger and the
version predicate live in `state.py` next to `ROOTS_DEPRECATION_SEP`; `_roots` is the
single call site.

The per-call `target` argument IS the spec's "tool parameters" migration arm, and it is
not a return of `set_target`. `set_target` made the target a piece of SERVER state that a
caller mutated and nobody could observe; a `target` argument makes it a property of the
call, visible in the request and echoed in the reply's `target` field. Moving to the SDK's
`Resolve`/`ListRoots` resolver marker is still declined: it would buy transport-correctness
on 2026-07-28+ connections for the SAME deprecated capability with the same removal date,
at the cost of restructuring every tier-0 tool signature.

Why `set_target` went away: it made the single thing every query depends on
settable by the caller and observable by nobody. A `--repo`-pinned server could
not index a second repository at all, an unpinned one could serve a different
target after a restart than the caller believed, and no payload said which
repository had answered. The last of those is fixed on every reply — see
`tools_query.QueryTools._answered`.

## The build and the proposer run IN-PROCESS

Both call the pipeline directly and wrap it in `_common.captured_output`, which
routes every progress bar and summary line into a buffer instead of `sys.stdout`
— and `sys.stdout` on this server IS the JSON-RPC transport. No pipeline logic is
duplicated here, no argument has to survive a command line, and a failure arrives
as an exception carrying a traceback rather than as an exit code plus whatever
reached a pipe. The exception is caught at the tool boundary, so a failed build
still cannot take the server process down.

@brief MCP server construction, target resolution and routing, tier-0 tools, tier-1 (un)registration.
@version 6
"""

from __future__ import annotations

import argparse
import time
import traceback
import warnings
from pathlib import Path
from typing import Any

import anyio

from .._common import captured_output, logger
from ..scope import SCOPE_FROM_GUARD
from ._sdk import Context, MCPServer, lowlevel
from .descriptions import load_descriptions
from .freshness import code_identity, notices, stale_code_refusal
from .state import (
    PROJECT_DIR_ENV,
    ROOTS_DEPRECATED_IN,
    ROOTS_DEPRECATION_SEP,
    ROOTS_EARLIEST_REMOVAL,
    ROOTS_MIGRATION,
    TARGET_SOURCE_ROOTS,
    Answering,
    Target,
    TargetRegistry,
    cull,
    db_status,
    discover_doxyfile,
    root_uri_to_path,
    roots_request_supported,
    startup_target,
    target_for,
)
from .tools_query import TIER1_TOOLS, QueryTools

SERVER_NAME = "clew"

## The ALWAYS-AVAILABLE tools' descriptions, loaded from `descriptions/*.json` declaring
## `"tier": 0` — exactly as `tools_query` loads the tier-1 twenty. These five were inline
## string literals here until 2026-08-10, which put every wording change in a Python diff
## and let a 1.5 KB blob accumulate in the middle of registration logic. Descriptions and
## their metadata are DATA and live together, apart from source.
TIER0_TOOLS: dict[str, str] = load_descriptions(tier=0)

## The verbs `index` dispatches on, and the ONLY place they are enumerated — the refusal
## message, the dispatch and the description all read from here, so an action advertised
## but not implemented (or implemented but not advertised) fails a test rather than
## presenting a model with a tool that refuses its own documented argument.
##
## 'stats' is `graph_stats`, moved here from the query surface. It is the odd one out and
## deliberately so: the other four operate ON the index, and 'stats' reports how far the
## index can be TRUSTED — both are questions about the tool rather than about the code,
## which is exactly the line separating this tool from `dossier` and `search`.
INDEX_ACTIONS: tuple[str, ...] = ("status", "refresh", "targets", "cull", "stats")

## The notification that invalidates a roots-derived target. Registered through the
## low-level server's `add_notification_handler` rather than `Server(on_roots_list_changed=…)`
## because the constructor kwarg emits an `MCPDeprecationWarning` and the registration method
## does not. `MCPServer` registers no notification handler for it by default — verified, the
## low-level server's handler map is empty — so nothing is being overridden here.
##
## THE NOTIFICATION ITSELF IS REMOVED, NOT MERELY DEPRECATED, at 2026-07-28: the changelog
## removes `ping`, `logging/setLevel` and `notifications/roots/list_changed` (SEP-2575), and
## `mcp_types.methods.CLIENT_NOTIFICATIONS` has no row for it at that revision. An earlier
## version of this comment called the registration route "not deprecated", which was true of
## the route and quietly wrong about the notification. The handler stays because handshake-era
## clients (<= 2025-11-25) still send it and those are exactly the connections on which the
## roots fallback works at all; on a 2026-07-28 connection it can never fire, and it does not
## need to, because `_roots` refuses that revision anyway.
ROOTS_CHANGED_METHOD = "notifications/roots/list_changed"

## What a caller is told when NO source supplied a target. Names all three sources and
## the one action that always works, because the failure it replaces named a tool
## (`set_target`) that no longer exists — an error message that instructs a model to call
## a nonexistent tool is worse than no message, and a benchmark cell has already burned a
## whole run writing a page about `No such tool available`.
NO_TARGET_ERROR = (
    "No default target repository. This server derives one from --repo, then "
    f"${PROJECT_DIR_ENV}, then the client's roots/list — this connection supplied none "
    "of them. Either name a repository on the call with target=<repo root>, or relaunch "
    "the server with --repo <path to the repo root>."
)


## Which `INDEX_ACTIONS` entries ROUTE to a repository named on the call. The rest report on
## the DERIVED target, or on the registry as a whole, and a `target` handed to one of them is
## REFUSED rather than discarded.
##
## FAIL-CLOSED BY CONSTRUCTION, and the direction is the point: this names the actions that
## DO route, so an action added to `INDEX_ACTIONS` and not listed here refuses a target
## instead of quietly dropping it. Dropping is what happened — `target` sat in scope on the
## 'status', 'targets' and 'cull' branches of `_index_action` and was never passed on, which
## made `unknown_target_error` structurally unreachable from all three. Asking 'status' about
## a second repository therefore returned the FIRST one's path, build version, coverage and
## staleness, with no error and no mention that the argument had been ignored. That is the
## defect class that voided a 36-cell benchmark grid, where every validity term checked that
## the agent called database tools and none checked WHICH database answered.
TARGET_ROUTING_ACTIONS: frozenset[str] = frozenset({"refresh", "stats"})

## Why each registry-wide action cannot honour a target, and what to do instead. "Unsupported"
## and "meaningless here" are different facts and lead a caller somewhere different: 'refresh'
## and 'stats' really do route, so 'status' has a near neighbour to be sent to, while 'cull'
## and 'targets' have no per-target operation to implement at all.
_NO_TARGET_REASON: dict[str, str] = {
    "status": (
        "reports on the DERIVED target and on where that derivation came from, which is a "
        "fact about this server rather than about a repository you can name. Two actions do "
        "route: refresh(target=...) builds a named repository and stats(target=...) grades "
        "its index. For any other repository's freshness, just ask it a question — every "
        "dossier and search reply names the target it answered from, and carries a staleness "
        "block whenever there is one."
    ),
    "targets": (
        "lists EVERY registered repository, so naming one narrows nothing: the answer "
        "already contains it. Filter the list this returns."
    ),
    "cull": (
        "sweeps the whole registry and has no per-target mode, so there is nothing here for "
        "a target to mean. Deleting one named repository's database is not an operation this "
        "tool offers."
    ),
}


## @brief Explain that a registry-wide index action will not honour a supplied target.
## @param action The action that cannot route.
## @param target The target string the caller passed.
## @return The refusal message.
## @version 1
## @req REQ-DDB-MCP-002
def registry_wide_target_error(action: str, target: str) -> str:
    """REFUSING BEATS IGNORING, and it beats it for a measurable reason: an ignored argument
    produces a confident, complete, well-formed answer about the wrong repository, which no
    caller can detect from the payload. A refusal costs one round trip and cannot be mistaken
    for a result.

    Names the action, the string, why that pairing has no meaning, and the nearest thing that
    does — the same four parts as `unknown_target_error`, because the caller's next move is
    what a refusal is for.

    @brief Compose the refusal for a target passed to a non-routing index action.
    @return The message.
    @version 1
    """
    reason = _NO_TARGET_REASON.get(
        action,
        "does not route to a repository named on the call; it reports on the derived target "
        "or on the registry as a whole",
    )
    return (
        f"index(action={action!r}) does not take a target, and {target!r} was supplied. "
        f"Refusing rather than ignoring it, because this action {reason} "
        f"Routing actions: {', '.join(sorted(TARGET_ROUTING_ACTIONS))}."
    )


## @brief Explain that a caller-supplied target string resolved to nothing.
## @param target The string the caller passed.
## @param known Targets currently in the registry.
## @return The refusal message.
## @version 2
## @req REQ-DDB-MCP-001
def unknown_target_error(target: str, known: list[Target]) -> str:
    """Names the string, says what was searched for it, and lists what IS known — because
    the caller's next move differs by which of those went wrong. A typo is fixed by
    re-reading the path; a repository that was never indexed is fixed by
    `index(action='refresh', target=...)`; a caller who does not know what exists calls
    `index(action='targets')`. A bare "unknown target" names none of the three.

    THE NAMES IN THE SERVED STRING ARE THE TOOL NAMES, not the method names. `build_or_refresh`
    and `list_targets` are still bound methods here, and internal prose may say so; a client sees
    only the four registered tools, and naming a method to it is a 404 dressed as guidance.

    Refusing rather than building is the deliberate half. A mistyped path that happens to
    be a real directory would otherwise start a doxygen run over the wrong tree and take
    minutes to say so.

    @brief Compose the unknown-target refusal.
    @return The message.
    @version 2
    """
    names = ", ".join(t.repo_path for t in known) or "(none registered)"
    return (
        f"Unknown target {target!r}: it is not a directory on this machine and matches no "
        f"registered repository path or slug. Known targets: {names}. Pass a repo root "
        f"path, or call index(action='targets') to see what is registered."
    )


## The fields a LISTING row carries, and the whole of it. Chosen to match what the `targets`
## description already promises — identity, existence, version, staleness, age — rather than to
## be a new judgement about what matters: a listing whose contents drift from its own description
## is how this reply became a wall in the first place.
##
## `staleness` IS KEPT because it is the reason a caller reads this list. `code` is NOT: it
## describes the SERVER PROCESS, is byte-identical in every row, and is already reported once by
## `status`.
_LISTING_FIELDS = (
    "repo_path",
    "db_path",
    "exists",
    "build_version",
    "expected_build_version",
    "source_changed_files",
    "stale",
    "age_days",
    "staleness",
)


## @brief Reduce a full status dict to the listing row `targets` promises.
## @param status A `db_status` mapping.
## @return The subset of keys a listing carries, in declared order.
## @version 1
## @req REQ-DDB-MCP-002
def _listing_row(status: dict[str, Any]) -> dict[str, Any]:
    """A PROJECTION, NOT A REBUILD. Selecting from `db_status` rather than computing a second,
    lighter status keeps one source for what each field means — a parallel implementation is how
    two views of one fact start disagreeing, which this project has already fixed twice.

    Absent keys are skipped rather than defaulted: an unbuilt target has no `age_days`, and
    inventing a null for it would say something the database did not.

    @brief Project a status dict onto the listing fields.
    @return The listing row.
    @version 1
    """
    return {key: status[key] for key in _LISTING_FIELDS if key in status}


INSTRUCTIONS = """Queryable knowledge graph over a C, C++, Rust or Python repository.

A `clew` is the ball of thread Ariadne gave Theseus: the thing you follow to find your way out of
the labyrinth. It is the archaic spelling and the direct ancestor of the word "clue". That is the
whole model for this server — you are somewhere inside a structure too large to hold in your head,
and this hands you the thread rather than a map of the whole maze. Pull on it: one symbol leads to
its callers, its locks, the thread it runs on, the requirement it satisfies.

WHAT THIS IS FOR. The index holds a repository's symbols, call relationships, threads, locks and
critical sections, dispatch, requirement links, file inventory and prose. It answers structural
questions about a symbol and its neighbours in one call where reading source takes several. It is
NOT a replacement for reading source: a question about how one name is spelled differently for
different consumers, or about the exact text of a comment, is one the index can point at but not
settle. Reading source after the index has named the file is the intended path, not a failure.

NO PERFORMANCE FIGURES ARE QUOTED HERE, deliberately. This text is served to a model that is
sometimes then graded on the answers it gives, so a number here describing which question types
the index wins teaches to the test and quietly turns a benchmark into a self-portrait. Measured
results live in the repository's committed acceptance artifacts, where a reader can check them
against the transcripts they came from.

ONE SERVER ANSWERS ABOUT ANY INDEXED REPOSITORY. Every tool takes an optional `target` — a repo
root path, or a slug. Pass it and that repository answers; omit it and the DEFAULT target answers.
The server keeps nothing between calls, so a `target` on one call never changes what the next one
sees.

The default target is DERIVED, not set: from --repo, else $CLAUDE_PROJECT_DIR. There is no
set_target tool. Administration is ONE tool with an `action`: `index(action='targets')` lists every
indexed repository, `index(action='refresh')` builds or updates one, `index(action='status')` gives
the full diagnosis WHEN YOU ALREADY HAVE A REASON TO WANT IT, and `index(action='stats')` grades a
named index.

DO NOT OPEN A SESSION WITH `index(action='status')`. Every query reply already carries a `target`
field naming the repository it answered from, and a `staleness` block IF AND ONLY IF that index is
stale. So a current index costs zero calls to establish, and a stale one announces itself on the
first reply you were going to make anyway. Ask your question; read `target` and `staleness` on what
comes back, and act only if one of them is wrong.

The query tools appear once this server knows of any repository at all — if the tool list looks
short, call `index(action='refresh')` and re-read it. START AT dossier for any question about one
named function: it returns that function's body, locks, threads, requirements and both neighbour
directions in ONE call, and there is no separate tool for any of those parts. Use search when you
do not have a name yet.

Check a reply's `target` before concluding a symbol does not exist.
"""


## EXEMPT FROM TOOL-SEARCH DEFERRAL (gh#7). A client may present MCP tools as DEFERRED — named
## in a reminder with no schema, callable only after a `ToolSearch` round trip. `grep` is then one
## call away and `dossier` is two, and a reporter measured what that asymmetry costs: an entire
## multi-hour session, 6 greps, 4 of them dossier-answerable, and zero spontaneous index calls.
##
## Declared in TWO independent places on purpose. This `_meta` key travels with the tool over the
## wire and works whatever the client read from the plugin manifest; `alwaysLoad` in
## `.claude-plugin/plugin.json` covers a client that decides before the server is asked. Either
## alone would be a single point of failure, and neither can be verified from inside this process.
##
## The cost is bounded and measured: four tools, 9,590 bytes of description in total. That is a
## small standing context charge against a two-call penalty on the surface this tool exists for.
ALWAYS_LOAD_META: dict[str, object] = {"anthropic/alwaysLoad": True}


## @brief Add the tier-1 query tools to an MCP server instance.
## @param mcp MCP server to register on.
## @param tools QueryTools bound to the active database.
## @return Names of the tools registered.
## @version 4
## @req REQ-DDB-MCP-003
def register_query_tools(mcp: MCPServer, tools: QueryTools) -> list[str]:
    """Register every tier-1 tool declared in TIER1_TOOLS by binding the
    matching `QueryTools` method. Idempotent: an already-registered name is
    replaced (the SDK's tool manager overwrites by name).

    @brief Register the dynamic tier-1 query tools.
    @return List of registered tool names.
    @version 4
    """
    for name, description in TIER1_TOOLS.items():
        mcp.add_tool(
            getattr(tools, name),
            name=name,
            description=description,
            meta=ALWAYS_LOAD_META,
        )
    return list(TIER1_TOOLS)


## @brief Remove the tier-1 query tools from an MCP server instance.
## @param mcp MCP server to unregister from.
## @return Names of the tools actually removed.
## @version 4
## @req REQ-DDB-MCP-003
def unregister_query_tools(mcp: MCPServer) -> list[str]:
    """Drop every tier-1 tool, tolerating names that are not registered (a
    target switch may happen before any registration).

    @brief Unregister the dynamic tier-1 query tools.
    @return List of removed tool names.
    @version 4
    """
    removed: list[str] = []
    for name in TIER1_TOOLS:
        try:
            mcp.remove_tool(name)
        except Exception:
            continue
        removed.append(name)
    return removed


## @brief Report an in-process pipeline failure as a tool result.
## @param exc The exception the run raised.
## @param rendered Whatever the run had written before it failed.
## @return Result dict carrying the error, its traceback and the partial output.
## @version 1
## @req REQ-DDB-MCP-002
def _failure_result(exc: BaseException, rendered: str) -> dict[str, Any]:
    """In-process the outcome IS the exception, so it is reported as one: type and
    message on `error`, the full traceback beside it. There is no exit code to
    report, and inventing a field for one would name something that no longer exists.

    `SystemExit` is handled alongside `Exception` because the pipeline's own refusals
    — an unreadable `--extra-input` root, an unresolvable Doxyfile — raise it, and
    letting one out of a worker thread would surface as a build that simply stopped.

    The partial output is kept, and it carries the pipeline's own log records up to
    the point it stopped — a build that failed in a late stage has already reported
    what it did index, and that is usually what says where it went wrong. No separate
    log line is emitted: one raised inside the capture would land in this same buffer.

    @brief Turn a raised pipeline failure into a tool result.
    @return The failure result dict.
    @version 1
    """
    return {
        "ok": False,
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(),
        "output": rendered,
    }


## @brief Lifecycle state + tier-0 tool implementations for one server.
## @version 1
class DocsDbServer:
    """Owns the target registry, the active target, and the tier-1
    registration state. Tier-0 tools are bound methods of this class, so the
    SDK server instance stays a thin transport shell.

    @brief Server lifecycle object (targets, builds, tier-1 activation).
    @version 1
    """

    ## @brief Construct the server state.
    ## @param registry Target registry (defaults to the per-user one).
    ## @version 7
    ## @dg_internal
    def __init__(self, registry: TargetRegistry | None = None) -> None:
        self.registry = registry if registry is not None else TargetRegistry()
        self.active: Target | None = None
        self.tier1_active = False
        ## HOW `self.active` was arrived at — one of `state.TARGET_SOURCE_*`, or None
        ## while there is no target. Not decoration: `invalidate_roots_target` reads it
        ## so a client's root list can only ever drop a target the client itself
        ## supplied, and `status` reports it so "which repository answered, and why
        ## that one?" is answerable without reading the launch arguments.
        self.target_source: str | None = None
        self.mcp: MCPServer | None = None
        ## One build lock PER TARGET, allocated on demand and never released back, so a
        ## repository's guard survives between the calls that contend for it. Keyed by
        ## the RESOLVED repo path rather than by whatever string a caller typed —
        ## `~/proj`, `/home/me/proj` and a slug are three spellings of one build.
        self._build_locks: dict[str, anyio.Lock] = {}
        self.tools = QueryTools(
            self.active_db, self.active_repo, self.staleness_notices, self.answering
        )

    ## @brief The build lock for one repository, allocated on first contention.
    ## @param repo_path Resolved repo path identifying the target.
    ## @return The lock guarding builds of that target.
    ## @version 1
    ## @req REQ-DDB-MCP-002
    def _build_lock(self, repo_path: str) -> anyio.Lock:
        """AN ANYIO LOCK, NOT A THREADING ONE, and the distinction is the whole point.
        The holder awaits `to_thread.run_sync` while the build runs, so the guard must
        suspend the waiting TASK and leave the event loop free — a `threading.Lock`
        acquired on the loop would block the transport for every other session, which is
        precisely the deployment per-target routing exists to serve.

        Allocating without a guard of its own is safe rather than lucky: every caller runs
        on the one event loop and there is no `await` between the lookup and the insert,
        so no other task can interleave and allocate a second lock for the same key.

        @brief Get or create the per-target build lock.
        @return The lock for that repository.
        @version 1
        """
        lock = self._build_locks.get(repo_path)
        if lock is None:
            lock = self._build_locks[repo_path] = anyio.Lock()
        return lock

    ## @brief The staleness axes in play right now, for stamping onto query replies.
    ## @return List of {axis, message}; EMPTY when the tool is current or has no target.
    ## @version 2
    ## @req REQ-DDB-MCP-004
    def staleness_notices(self) -> list[dict[str, str]]:
        """gh#2's chosen mechanism: STALENESS RIDES IN THE PAYLOAD. `status` reported it
        clearly and without being asked twice, but reading it requires already suspecting
        a problem — which is exactly what a consumer holding a fresh-looking answer does
        not have. The signal was opt-in and the failure mode silent.

        NON-RAISING BY CONTRACT, like `_target_name`. It runs on the way out of every
        reply, including replies that already succeeded, so it must never be the thing
        that turns a good answer into an error. Every failure — no target, an unreadable
        database, a vanished state root — degrades to no annotation, which is the same
        thing the tool did before this existed.

        @brief Measure the current staleness axes, never raising.
        @return List of notices, empty when current or unmeasurable.
        @version 2
        """
        found: list[dict[str, str]] = []
        if self.active is not None:
            try:
                found = notices(db_status(self.active))
            except Exception:
                logger.debug("staleness could not be measured for %s", self.active.repo_path)
        return found

    ## @brief Resolve a caller-supplied target string to a known repository.
    ## @param target Repo root path, or a slug from `list_targets`.
    ## @return The Target it names.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def resolve_target(self, target: str) -> Target:
        """THREE SPELLINGS OF ONE REPOSITORY, resolved to one record. The registry is
        consulted first by exact repo path and by slug, because both are strings this
        server itself handed the caller — `list_targets` reports the first and `status`
        the second, so a caller who echoes one back must be understood. Failing that the
        string is treated as a path and normalised the way `target_for` normalises every
        path, which makes `~/proj` and `/home/me/proj` the same target.

        A directory that is not registered still resolves, and that is deliberate: the
        slug is derived from the path, so an index built by the CLI is found by the same
        allocation rule that built it. It does not get REGISTERED here — that is a
        build-time act, and a query has no business writing to the registry.

        A registered target whose directory has since moved keeps resolving, because the
        registry match is tried first. Its index is still readable and still worth
        querying.

        @brief Resolve a target string to its Target record.
        @return The resolved Target.
        @version 1
        """
        known = self.registry.targets()
        for candidate in known:
            if target in (candidate.repo_path, candidate.slug):
                return candidate
        path = Path(target).expanduser()
        if path.is_dir():
            return target_for(path, self.registry.home)
        raise RuntimeError(unknown_target_error(target, known))

    ## @brief Resolve a routed target into the database, tree and staleness to answer with.
    ## @param target Repo root path, or a slug from `list_targets`.
    ## @return Everything one query needs about that repository.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def answering(self, target: str) -> Answering:
        """The query-side half of resolution, and the reason it is separate from
        `resolve_target`: a query needs a BUILT index and a build does not. Refusing an
        unbuilt target here — by name, with the exact call that fixes it — is what stops
        it surfacing as a bare sqlite "unable to open database file" three frames deeper.

        Staleness is measured for the ROUTED repository, never the derived one, and
        non-raising for the same reason `staleness_notices` is: it decorates a reply that
        has otherwise succeeded, so a state directory that vanished mid-session must cost
        an annotation rather than the answer.

        @brief Resolve a routed target for querying.
        @return The database, working tree and staleness for it.
        @version 2
        """
        resolved = self.resolve_target(target)
        db = Path(resolved.db_path)
        if not db.is_file():
            raise RuntimeError(
                f"No database has been built for {resolved.repo_path} yet — call "
                f"index(action='refresh', target={resolved.repo_path!r}) first."
            )
        found: list[dict[str, str]] = []
        try:
            found = notices(db_status(resolved))
        except Exception:
            logger.debug("staleness could not be measured for %s", resolved.repo_path)
        return Answering(db=db, repo=Path(resolved.repo_path), staleness=found)

    ## @brief Bring tier-1 into line with whether this server knows of any repository.
    ## @version 2
    ## @req REQ-DDB-MCP-003
    def _sync_tier1(self) -> None:
        """THE GATE IS "IS THERE ANYTHING TO ANSWER ABOUT", not "is a target derived".

        A query tool takes the repository on the call, so the derived target stopped being
        a precondition for one working. Gating on it would leave a server launched at no
        repository offering zero query tools while holding a registry full of indexes it
        can read — and that server is the whole point of routing. Gating on the registry
        instead keeps the honest half of the old behaviour: a first-ever run, with nothing
        indexed anywhere, still offers only the lifecycle tools, because there genuinely is
        nothing for a query tool to read.

        Idempotent in both directions, so every caller can just say "sync" rather than
        reasoning about what the last transition left behind.

        @brief Register or unregister tier-1 to match what is answerable.
        @version 2
        """
        if self.mcp is None:
            return
        ## ALWAYS REGISTERED (gh#7). The gate used to be "is there anything to answer about",
        ## which meant a first-ever session offered no `dossier` and no `search` at all — and a
        ## tool that does not exist teaches a model that the CAPABILITY does not exist. Worse,
        ## it made the surface appear MID-SESSION, so the two tools most worth reaching for were
        ## the two least likely to be in a client's eagerly-loaded set.
        ##
        ## The gate was only ever defensible because the tools died with
        ## `sqlite3.OperationalError: unable to open database file` on an unbuilt index. They now
        ## refuse with `unbuilt_index_message`, which NAMES the call that fixes it — so an
        ## always-present tool is strictly better than a conditionally-absent one.
        ##
        ## `unregister_query_tools` is kept: the CLI and the tests still exercise it, and a
        ## capability removed while its callers remain is a property that reads as enforced and
        ## is not.
        if not self.tier1_active:
            register_query_tools(self.mcp, self.tools)
            self.tier1_active = True

    ## @brief Make a repo the active target and expose its query tools.
    ## @param repo_path Repo root to serve.
    ## @param source Which resolution source supplied it (a TARGET_SOURCE_* value).
    ## @return The newly-active Target.
    ## @version 3
    ## @req REQ-DDB-MCP-001
    def adopt(self, repo_path: str, source: str) -> Target:
        """Make the repo active. Does NOT register it, and does NOT build.

        RESOLUTION IS NOT REGISTRATION (gh#1). This called `registry.register`, which persists
        the entry AND mkdirs its state directory — so merely LAUNCHING the server in a directory
        registered it forever, before any database existed. A reporter found three targets listed
        with `exists: false`, one of them their entire home directory, and `cull` could not clear
        any of them: it removes aged-out or version-stale DATABASES, and these had none. The
        registry could accumulate rows nothing could reach. Same root cause as the orphaned state
        directories that had to be deleted by hand.

        Registration now happens where it is earned: `_build_target`, because a build has to have
        somewhere to write. So `$HOME` can only be registered by someone explicitly building it.

        WHAT MADE THE EAGER REGISTRATION LOOK NECESSARY IS GONE. `_sync_tier1` used to gate on
        `registry.targets()`, so a resolved target had to be in the registry for the query tools
        to appear at all; tier-1 is unconditional now (gh#7). And an unbuilt target refuses with
        `unbuilt_index_message` rather than a driver error, so nothing needs the directory to
        pre-exist.

        Deliberately does NOT build. A doxygen run takes tens of seconds, so
        building here would hang the whole session on connect, on every editor
        restart. Staleness is reported instead (see #43's source-drift term),
        leaving the decision to refresh with the caller.

        Tier-1 is registered even when no database exists yet, and that is a
        deliberate trade rather than an oversight. The tools are bound to
        `active_db`/`active_repo`, which resolve at CALL time, so they follow a
        retarget without re-binding — meaning a retarget needs no tool-list change
        and the caller never watches the surface shrink and regrow. The cost is that
        a query against an unbuilt target has to fail legibly instead of not being
        offered, which `active_db` now does by name.

        @brief Adopt a target repo and register the query tools.
        @return The active Target.
        @version 3
        """
        self.active = target_for(repo_path, self.registry.home)
        self.target_source = source
        self._sync_tier1()
        status = db_status(self.active)
        logger.info(
            "target %s (from %s): db %s, stale=%s, %s source file(s) changed since build",
            self.active.repo_path,
            source,
            "present" if status["exists"] else "NOT BUILT",
            status["stale"],
            status["source_changed_files"],
        )
        return self.active

    ## @brief Resolve the target readable before any request arrives.
    ## @param explicit Value of `--repo`, or None.
    ## @return The adopted Target, or None when neither eager source supplied one.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    def resolve_startup_target(self, explicit: str | None = None) -> Target | None:
        """`--repo`, else `$CLAUDE_PROJECT_DIR`. Returning None is NORMAL, not a
        failure: it means the client will be asked for its roots on the first call
        that needs a target, so the message says so rather than reading as an error.

        @brief Resolve and adopt a startup target, if one is available.
        @return The adopted Target, or None.
        @version 1
        """
        repo, source = startup_target(explicit)
        if repo is None or source is None:
            logger.info(
                "no target at startup (no --repo, no usable $%s) — will ask the client for "
                "its roots on the first call that needs one",
                PROJECT_DIR_ENV,
            )
            return None
        return self.adopt(repo, source)

    ## @brief The active target, resolving one from the client's roots if needed.
    ## @param ctx MCP request context (the only route to `roots/list`).
    ## @return The active Target, or None when no source supplied one.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    async def ensure_target(self, ctx: Context) -> Target | None:
        """THE LAZY HALF of resolution, and every tier-0 tool that needs a target
        goes through it.

        Called on each such tool rather than once, because the roots route is only
        reachable from a live request: there is no session during `main()`, so a
        server whose ONLY available source is the client's root list starts with no
        target at all and acquires one here. Cheap on the common path — an already
        resolved target short-circuits before any request is sent.

        @brief Return the active target, lazily resolving from roots.
        @return The active Target, or None.
        @version 1
        """
        if self.active is not None:
            return self.active
        repo = await self._target_from_roots(ctx)
        return None if repo is None else self.adopt(repo, TARGET_SOURCE_ROOTS)

    ## @brief Drop a target that came from the client's root list.
    ## @return True when a roots-derived target was dropped.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def invalidate_roots_target(self) -> bool:
        """Handles `notifications/roots/list_changed` by forgetting the DEFAULT target,
        so the next call that needs one re-resolves against the new root list.

        SCOPED TO ROOTS-DERIVED TARGETS ONLY. `--repo` is an operator's explicit
        instruction and `$CLAUDE_PROJECT_DIR` is the session the server was launched
        for; letting a client's root list override either would discard the more
        authoritative answer in favour of the least, and would do it silently.

        Re-resolving lazily rather than fetching the new roots here keeps this off
        the request path entirely: a notification handler that issued a
        server-to-client request would be doing I/O in a fire-and-forget callback for
        a target nothing has asked for yet.

        THE QUERY TOOLS DO NOT GO WITH IT. They take the repository on the call, so a
        dropped default costs a caller the ability to OMIT the argument and nothing else;
        the indexes the registry knows about are all still readable. Withdrawing the tools
        here would be a mid-session capability change for a target nothing has asked for
        yet.

        @brief Invalidate a roots-derived target.
        @return Whether a target was dropped.
        @version 2
        """
        if self.target_source != TARGET_SOURCE_ROOTS:
            return False
        logger.info(
            "%s — dropping the roots-derived target %s; the next call will re-resolve",
            ROOTS_CHANGED_METHOD,
            self.active.repo_path if self.active else "?",
        )
        self.active = None
        self.target_source = None
        self._sync_tier1()
        return True

    ## @brief Handle the client's roots/list_changed notification.
    ## @param _ctx Server request context (unused — invalidation needs no I/O).
    ## @param _params Notification params (this notification carries none).
    ## @version 1
    ## @req REQ-DDB-MCP-001
    async def on_roots_list_changed(self, _ctx: Any, _params: Any) -> None:
        """A method rather than a closure in `build_server` so it carries its own
        documentation and can be asserted directly by a test without constructing a
        transport.

        @brief Invalidate a roots-derived target on notification.
        @version 1
        """
        self.invalidate_roots_target()

    ## @brief Roots advertised by the client, or an empty list.
    ## @param ctx MCP request context.
    ## @return The client's roots (empty when unavailable for any reason).
    ## @version 3
    ## @dg_internal
    async def _roots(self, ctx: Context) -> list[Any]:
        """FAILS CLOSED, FOUR WAYS, because this runs inside an ordinary tool call
        and a target-resolution problem must degrade to "no target" rather than to a
        traceback the caller cannot act on: a client that advertises no roots
        capability is never asked, a protocol revision that cannot carry the request is
        never asked, a transport with no back-channel raises `NoBackChannelError`, and a
        client may simply refuse.

        THE REVISION CHECK IS NOT BELT-AND-BRACES. `ServerSession.list_roots()` sends a
        STANDALONE server-to-client request, and 2026-07-28 has no such surface at all —
        roots moved inside the MRTR envelope (SEP-2322), which this server does not
        implement. Without the check the call still fails, but as an opaque `KeyError`
        from the SDK's result validation, logged as "unavailable" with no hint that the
        cause is the negotiated revision rather than the client's answer.

        THE ROOTS CAPABILITY IS DEPRECATED as of 2026-07-28 (SEP-2577) with no successor
        request — see `state.ROOTS_DEPRECATION_SEP` for what was established and the
        module docstring for what was decided. `ServerSession.list_roots` is decorated
        accordingly in mcp 2.0.0, and the warning is silenced HERE, at the one call site,
        rather than globally: a blanket filter would also hide the day a DIFFERENT
        deprecated call is introduced.

        @brief Fetch the client's roots, tolerating every unavailability.
        @return List of roots, possibly empty.
        @version 3
        """
        from mcp.shared.exceptions import MCPDeprecationWarning

        if not self._roots_askable(ctx):
            return []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", MCPDeprecationWarning)
                result = await ctx.session.list_roots()
        except Exception as exc:
            logger.info("roots/list unavailable (%s) — no target from the client", exc)
            return []
        return list(getattr(result, "roots", None) or ())

    ## @brief Whether this connection can be asked for its roots at all.
    ## @param ctx MCP request context.
    ## @return True when the request is worth sending.
    ## @version 1
    ## @dg_internal
    def _roots_askable(self, ctx: Context) -> bool:
        """The two refusals that are decidable WITHOUT sending anything: a client that
        advertises no roots capability, and a protocol revision that cannot carry the
        standalone request.

        Split out of `_roots` rather than inlined so each refusal is reachable from a test
        without a session, and so `_roots` keeps one exit per outcome.

        The revision refusal logs and the capability refusal does not, on purpose. A client
        that advertises nothing is the ordinary case for link (1) and (2) and would print on
        every call; a revision that structurally cannot answer is a state an operator can
        only fix by passing `--repo`, so it says so.

        @brief Decide whether to send `roots/list`.
        @return Whether the request may be attempted.
        @version 1
        """
        capabilities = getattr(ctx, "client_capabilities", None)
        if capabilities is None or getattr(capabilities, "roots", None) is None:
            return False
        version = getattr(ctx, "protocol_version", None)
        if roots_request_supported(version):
            return True
        logger.info(
            "protocol %s carries no standalone %s request (%s deprecated roots in %s; it is "
            "reachable there only via MRTR, which this server does not implement) — no target "
            "from the client, %s",
            version,
            TARGET_SOURCE_ROOTS,
            ROOTS_DEPRECATION_SEP,
            ROOTS_DEPRECATED_IN,
            ROOTS_MIGRATION,
        )
        return False

    ## @brief First usable repo root among the client's advertised roots.
    ## @param ctx MCP request context.
    ## @return Path string of the first local directory, or None.
    ## @version 2
    ## @dg_internal
    async def _target_from_roots(self, ctx: Context) -> str | None:
        """Takes the FIRST root that verifies as a local directory. A client may
        advertise several (Claude Code adds one per `--add-dir`), and there is no
        evidence available here for ranking them — so it takes the launch directory,
        which is the one the client lists first, and leaves `--repo` as the way to
        say otherwise.

        WARNS when this link actually supplies the target, which it did not before
        (gh#25). Silence was the problem: an operator whose server has been running on the
        deprecated link for months had no way to learn it, and the day the SDK drops
        `list_roots` their target becomes `NO_TARGET_ERROR` with no prior notice. WARNING
        rather than INFO because it names an action with a deadline, and it fires only on
        the resolution — not per query — because `ensure_target` short-circuits once the
        target is adopted.

        @brief Pick a target repo from the client's roots, warning that the link is deprecated.
        @return Repo path, or None.
        @version 2
        """
        for root in await self._roots(ctx):
            path = root_uri_to_path(getattr(root, "uri", ""))
            if path is not None:
                logger.warning(
                    "target %s came from the client's %s, which is DEPRECATED (%s, in %s) and "
                    "removable in %s — %s",
                    path,
                    TARGET_SOURCE_ROOTS,
                    ROOTS_DEPRECATION_SEP,
                    ROOTS_DEPRECATED_IN,
                    ROOTS_EARLIEST_REMOVAL,
                    ROOTS_MIGRATION,
                )
                return str(path)
        return None

    ## @brief Path of the active target's database.
    ## @return Path to the active clew.db.
    ## @version 4
    ## @req REQ-DDB-MCP-001
    def active_db(self) -> Path:
        """Resolve the active db path, raising a NAMED error for each of the two
        ways it can be unavailable.

        Both messages matter more than they used to. Since the target is derived
        rather than set, tier-1 is registered as soon as a target is known — so
        "target known, database not built yet" is now the common first state of a
        fresh install, and it used to surface as a bare sqlite "unable to open
        database file" from three frames deeper. The second message names
        `build_or_refresh`, which is the one action that fixes it.

        @brief Resolve the active database path.
        @return Active clew.db path.
        @version 4
        """
        if self.active is None:
            raise RuntimeError(NO_TARGET_ERROR)
        db = Path(self.active.db_path)
        if not db.is_file():
            raise RuntimeError(
                f"No database has been built for {self.active.repo_path} yet — call "
                "index(action='refresh') first."
            )
        return db

    ## @brief Working-tree root of the active target.
    ## @return Path to the repo the active database was built from.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def active_repo(self) -> Path:
        """Resolve the active repo root. The server DERIVED it, so `source` never
        has to ask the model for a path — and no path is ever hardcoded.

        @brief Resolve the active repo root.
        @return Active repo root path.
        @version 2
        """
        if self.active is None:
            raise RuntimeError(NO_TARGET_ERROR)
        return Path(self.active.repo_path)

    # ── tier-0 tools ────────────────────────────────────────────────────────

    ## @brief Build or refresh the active target's clew.db, then expose tier-1.
    ## @param ctx MCP request context (used to notify the tool-list change).
    ## @param force Rebuild even when the existing database is current.
    ## @param doxyfile Explicit Doxyfile path; discovered from the repo when omitted.
    ## @param scope Scope source: `from-guard` (the repo's declared doxygen mandate) or `doxyfile`.
    ## @param exclude Repo-relative paths to leave out of the index; None inherits the recorded ones, [] withdraws them.
    ## @param target Repo root or slug to build; omit for the server's derived target.
    ## @param options Tier-1 build options keyed by declaration-file section name; omit to state nothing.
    ## @return Result dict with build outcome, MEASURED duration, status, registered tool names and the answering target; or a refusal when this process predates its source.
    ## @version 10
    ## @req REQ-DDB-MCP-002
    ## @req REQ-DDB-MCP-004
    ## @req REQ-DDB-CONFIG-001
    ## @req REQ-DDB-CONFIG-008
    async def build_or_refresh(
        self,
        ctx: Context,
        force: bool = False,
        doxyfile: str | None = None,
        scope: str = SCOPE_FROM_GUARD,
        exclude: list[str] | None = None,
        target: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the pipeline for the named target — or the derived one when the call names
        none — unless its database is already current (`force` overrides). On success,
        register the tier-1 query tools and notify the client that the tool list changed.

        A NAMED TARGET IS REGISTERED, NOT ADOPTED. Registration allocates its database
        directory and records it so `list_targets` and `cull` can see it; adoption would
        change which repository every OTHER session's un-targeted call answers from, which
        is precisely the coupling the argument exists to remove.

        CONCURRENT REFRESHES OF ONE TARGET PRODUCE ONE BUILD. The freshness check runs
        INSIDE the per-target lock, so the second caller through re-reads a database the
        first one just made current and skips. Both halves are load-bearing: the lock alone
        would serialise four builds instead of preventing three, and the check alone would
        let four start together. `force` deliberately still forces — four forced refreshes
        are four builds, run one at a time.

        The default scope is DERIVED from the target repo's own doxygen-guard
        declaration, so an agent-triggered build indexes the repo's enforced
        first-party surface rather than whatever subset its Doxyfile happens to
        list — with no operator step. Repos without that declaration fall back
        to the Doxyfile automatically.

        IT REPORTS WHAT IT COST (gh#9). `duration_ms` is the wall time of THIS call,
        measured — not estimated from a constant — so an agent can state the cost of
        correcting a stale view instead of guessing at it. The per-stage breakdown the
        pipeline itself measured (files reprocessed, cache hits) rides in
        `status["refresh"]`, persisted into the index so the NEXT session's estimate is
        grounded in this target's own history rather than in a number baked in here. A
        114-file target and a 420-file one differ by 5.7x; no single constant is right
        for both.

        `duration_ms` is present on the SKIP path too, where it measures what checking
        cost. That is the honest reading of "how long did that take", and a skip that
        reported no duration would look like a missing measurement rather than a cheap one.

        THE INDEX DEFAULTS TO COMPLETE, and `exclude` is the only way to narrow it: an
        explicit, recorded act rather than a rule nobody wrote down. It is stated once
        and REPLAYED — the pipeline reads it back off the previous build, because scope
        is otherwise re-derived from the repo and the tree every time — so a later
        refresh that passes nothing still honours it. `[]` withdraws it. The record is
        `status.scope.operator_excludes`, deliberately apart from `scope.excludes`,
        which is what the tree walker pruned rather than what anyone decided. A `cull`
        deletes the database and the record with it.

        IT REFUSES WHEN THIS PROCESS PREDATES ITS OWN SOURCE (gh#348), and the refusal sits
        ahead of the build decision rather than inside it, so `force` cannot argue past it.
        A stale process reads live data and WRITES DEAD LOGIC: measured, a build-30 process
        rebuilt a build-32 index AT 30, dropping the `external` stage and then reporting the
        result healthy. The guard is placed after target resolution so "you have no target"
        still gets its own answer, and immediately before the lock so nothing can be written
        past it. `stale_code_refusal` owns the wording; this is one `if`.

        `options` IS TIER 1, AND BEFORE gh#332 IT DID NOT EXIST HERE. This tool exposed
        `force`/`doxyfile`/`scope`/`exclude`/`target` and none of the ten layered settings, so
        the built-in defaults were the whole policy through MCP — gh#319 built a five-tier
        precedence rule whose top tier no consumer could reach. Its keys are the declaration
        file's own section names, and they are the same words the `diagnostics` section uses to
        name what this build could not see: the tool says what it missed in the vocabulary you
        answer in. WITHOUT that reply this argument would be a knob with no reason to turn it,
        which is why the two landed together.

        Values are inline for the list and small-mapping options and a PATH for the six
        manifest-shaped documents; a relative path resolves against the repo root. A malformed
        mapping is REFUSED and applies nothing — no partial policy, and a correctly-spelled but
        derived key is refused with the reason rather than as unknown.

        @brief Build/refresh the target database and activate query tools.
        @return Build result dict, carrying a measured duration.
        @version 10
        """
        started = time.perf_counter()
        try:
            resolved = await self._build_subject(ctx, target)
        except RuntimeError as exc:
            return {"ok": False, "error": str(exc)}
        if resolved is None:
            return {"ok": False, "error": NO_TARGET_ERROR}
        identity = code_identity()
        refusal = stale_code_refusal(identity)
        if refusal is not None:
            return {"ok": False, "error": refusal, "code": identity}
        async with self._build_lock(resolved.repo_path):
            result = await self._build_once(resolved, force, doxyfile, scope, exclude, options)
        if result.get("ok"):
            result["tools"] = await self._activate_tier1(ctx)
        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        result["status"] = db_status(resolved)
        result["target"] = resolved.repo_path
        return result

    ## @brief The repository a build call is about.
    ## @param ctx MCP request context (the only route to the client's roots).
    ## @param target Repo root or slug the call named, or None for the derived target.
    ## @return The Target to build, or None when no source supplied one.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    async def _build_subject(self, ctx: Context, target: str | None) -> Target | None:
        """A named target is REGISTERED, which allocates its database directory — the
        build has to have somewhere to write. It is not adopted, and the client's roots
        are never consulted for it: the caller already said which repository it means.

        @brief Resolve and register the repository a build is for.
        @return The Target, or None when nothing supplied one.
        @version 1
        """
        if target is None:
            return await self.ensure_target(ctx)
        return self.registry.register(self.resolve_target(target).repo_path)

    ## @brief Build one target, skipping when its index is already current.
    ## @param target The repository to build.
    ## @param force Rebuild even when the existing database is current.
    ## @param doxyfile Explicit Doxyfile path, or None to discover one.
    ## @param scope Scope source handed to the pipeline.
    ## @param exclude Operator-stated exclusions; None inherits the recorded ones, [] withdraws them.
    ## @param options Tier-1 build options; a stated one makes this a build, like an exclusion does.
    ## @return Build result dict (built true) or the skip result (built false).
    ## @version 2
    ## @req REQ-DDB-MCP-002
    ## @req REQ-DDB-CONFIG-008
    async def _build_once(
        self,
        target: Target,
        force: bool,
        doxyfile: str | None,
        scope: str,
        exclude: list[str] | None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """CALLED WITH THE TARGET'S BUILD LOCK HELD, which is what makes the freshness
        check a deduplication rather than a race: a second caller reaches this only after
        the first has finished, so it reads a database that is already current and skips.
        Split out of `build_or_refresh` so the critical section is exactly the check plus
        the build, with no reply assembly inside it.

        A STATED EXCLUSION IS A BUILD, even when the index is otherwise current: the skip
        asks "does this describe the code as it is now", which an unindexed narrowing does
        not change. Without it, the first `exclude=[...]` on a fresh index returns
        `built: false` and silently does nothing.

        A STATED OPTION IS A BUILD FOR THE SAME REASON (gh#332), and this is the whole of
        why it is threaded down here rather than only into `_run_build`. An operator who
        declares their accessor patterns against a current index wants that dataflow layer
        built; without this term the call would return `built: false` and change nothing,
        which is the exact defect the exclusion clause above already records.

        @brief Run or skip the build for one target.
        @return Build or skip result dict.
        @version 2
        """
        status = db_status(target)
        if not status["stale"] and not force and exclude is None and not options:
            return {"ok": True, "built": False, "status": status}
        return await anyio.to_thread.run_sync(
            self._run_build, target, doxyfile, scope, exclude, options
        )

    ## @brief Current target, how it was resolved, database freshness and tier-1 state.
    ## @param ctx MCP request context (the only route to the client's roots).
    ## @return Status dict for the active target (or a no-target marker).
    ## @version 3
    ## @req REQ-DDB-MCP-002
    async def status(self, ctx: Context) -> dict[str, Any]:
        """Report what the server is pointed at, WHERE THAT CAME FROM, and whether
        its query tools are live.

        Async and ctx-taking because it participates in lazy resolution: on a client
        that supplies only `roots/list`, `status` is very likely the first call, and a
        `status` that reported "no target" while a target was one request away would
        be reporting on the server's laziness rather than on the session.

        `target_source` is reported because "which repository is this?" and "why that
        one?" are the same question in practice. A stale pin that nobody could see
        invalidated a 36-cell benchmark run; the source is what makes the equivalent
        mistake visible in one call.

        @brief Report server/target status.
        @return Status dict.
        @version 3
        """
        target = await self.ensure_target(ctx)
        if target is None:
            return {
                "active": False,
                "tier1_registered": self.tier1_active,
                "error": NO_TARGET_ERROR,
            }
        status = db_status(target)
        status["active"] = True
        status["slug"] = target.slug
        status["target_source"] = self.target_source
        status["tier1_registered"] = self.tier1_active
        return status

    ## @brief Every known target with its database age and staleness.
    ## @return List of listing rows, one per registered target.
    ## @version 3
    ## @req REQ-DDB-MCP-002
    def list_targets(self) -> list[dict[str, Any]]:
        """A LISTING, WHICH IS WHAT THE TOOL DESCRIPTION ALREADY PROMISED — "every indexed
        repository with its database age and staleness". It returned `db_status` per target
        instead: scope, coverage, per-stage refresh timings, options, diagnostics, data_model,
        code identity and the staleness block, once for every repository.

        MEASURED ON THE LIVE SERVER at nine targets: tens of kilobytes, with the same ~700
        character code-staleness message repeated nine times and one target's `excludes` string
        running to thousands of characters on its own. This is the ORIENTATION call for someone
        with several repositories, and it answered with a wall.

        AND IT WAS THE ONE REPLY WITH NO BOUND. Every query tool trims to
        `RESPONSE_BUDGET_BYTES`; this multiplied an unbounded per-target payload by an unbounded
        target count. Verbose is a preference; unbounded is a defect.

        WHAT IS NOT LOST, because a listing that drops the fact a caller needed is the opposite
        mistake: every field the description names is kept, and the detail moves to the tools
        that exist for it — `index(action='status')` for the derived target, `stats(target=...)`
        for any named one. `code` identity is dropped from the ROW because it is a fact about
        this SERVER PROCESS, identical in every row, and already reported by `status`.

        @brief List registered targets, compactly.
        @return List of listing rows.
        @version 3
        """
        return [_listing_row(db_status(t)) for t in self.registry.targets()]

    ## @brief Remove aged-out or version-stale databases.
    ## @param max_age_days Age threshold in days (null disables the age rule).
    ## @param include_stale Also cull databases built by an older pipeline version.
    ## @return Dict with the culled targets and how many remain.
    ## @version 4
    ## @req REQ-DDB-MCP-003
    def cull(self, max_age_days: float | None = 30.0, include_stale: bool = True) -> dict[str, Any]:
        """Sweep the registry and delete the databases that are no longer
        worth keeping, dropping the active target too if it was culled.

        Tier-1 is re-synced afterwards rather than dropped: a cull that leaves other
        registered targets standing has taken away one repository, not the ability to
        answer about any. Only a cull that empties the registry withdraws the tools.

        @brief Cull stale/aged target databases.
        @return Cull summary dict.
        @version 4
        """
        culled = cull(self.registry, max_age_days=max_age_days, include_stale=include_stale)
        culled_paths = {c["repo_path"] for c in culled}
        if self.active is not None and self.active.repo_path in culled_paths:
            self.active = None
            self.target_source = None
        self._sync_tier1()
        return {"culled": culled, "remaining": len(self.registry.targets())}

    ## @brief Administer the index: status, refresh, targets, cull, stats — one tool, one action.
    ## @param ctx MCP request context (the only route to the client's roots).
    ## @param action Which lifecycle operation to perform (see INDEX_ACTIONS).
    ## @param target Repo root or slug to act on; omit for the server's derived target.
    ## @param force Rebuild even when the database is current (action='refresh').
    ## @param doxyfile Explicit Doxyfile path (action='refresh').
    ## @param scope Index scope to derive (action='refresh').
    ## @param exclude Repo-relative paths to leave out (action='refresh').
    ## @param options Declaration sections to state for this build (action='refresh').
    ## @param max_age_days Age threshold in days, null to disable the age rule (action='cull').
    ## @param include_stale Also cull version-stale databases (action='cull').
    ## @return The chosen action's result, stamped with the `action` that produced it.
    ## @version 1
    ## @req REQ-DDB-MCP-002
    ## @req REQ-DDB-MCP-003
    async def index(
        self,
        ctx: Context,
        action: str = "status",
        target: str | None = None,
        force: bool = False,
        doxyfile: str | None = None,
        scope: str = SCOPE_FROM_GUARD,
        exclude: list[str] | None = None,
        options: dict[str, Any] | None = None,
        max_age_days: float | None = 30.0,
        include_stale: bool = True,
    ) -> dict[str, Any]:
        """FIVE ADMINISTRATIVE TOOLS WERE FIVE ENTRIES IN EVERY SESSION'S TOOL LIST, and
        four of them are never called in a session that only asks questions. Tool cost is
        linear in tool COUNT, and these were the cheapest four to remove because they are
        one subject — the index — with five verbs.

        THE METHODS BELOW SURVIVE; ONLY THE TOOL ENTRIES COLLAPSE. `status`,
        `build_or_refresh`, `list_targets` and `cull` are still bound methods with their
        own signatures, called by `_sync_tier1`, by the CLI and by the tests. This is the
        same rule the query library follows one layer down: collapse the SURFACE, keep the
        functions. A collapse that deleted the implementations would have made every
        internal caller route through an action string.

        `action='stats'` IS THE ONE ADDITION, and it is here rather than in the query
        surface because of what it asks. `graph_stats` answers "how much of this index can
        be trusted" — edge counts by layer and confidence, coverage, the doxygen-vs-parser
        split. That is a question about the TOOL, not about the repository, which is
        exactly what distinguishes this tool from `dossier` and `search`. Filing it beside
        them would have put an index-quality metric next to two code-answering tools and
        invited it to be quoted as a finding about the code.

        EVERY REPLY NAMES ITS ACTION. A dispatching tool whose result did not say which
        branch produced it is a payload a caller has to identify by shape — and two of
        these five return a bare mapping.

        @brief Administer the index through one action-dispatched tool.
        @return The action's result, carrying `action`.
        @version 1
        """
        if action not in INDEX_ACTIONS:
            raise ValueError(
                f"Unknown index action {action!r}. Known actions: "
                f"{', '.join(INDEX_ACTIONS)}. This tool administers the INDEX; for a "
                "question about the code call dossier or search."
            )
        result = await self._index_action(
            ctx,
            action,
            target,
            force,
            doxyfile,
            scope,
            exclude,
            options,
            max_age_days,
            include_stale,
        )
        return (
            {**result, "action": action}
            if isinstance(result, dict)
            else {
                "action": action,
                "results": result,
            }
        )

    ## @brief Run one index action and return its raw result.
    ## @param ctx MCP request context.
    ## @param action The validated action name.
    ## @param target Repo root or slug, or None for the derived target.
    ## @param force Rebuild even when current.
    ## @param doxyfile Explicit Doxyfile path.
    ## @param scope Index scope to derive.
    ## @param exclude Repo-relative paths to leave out.
    ## @param options Declaration sections to state.
    ## @param max_age_days Cull age threshold.
    ## @param include_stale Cull version-stale databases too.
    ## @return Whatever the underlying method returns.
    ## @version 2
    ## @dg_internal
    async def _index_action(
        self,
        ctx: Context,
        action: str,
        target: str | None,
        force: bool,
        doxyfile: str | None,
        scope: str,
        exclude: list[str] | None,
        options: dict[str, Any] | None,
        max_age_days: float | None,
        include_stale: bool,
    ) -> Any:
        """SPLIT OUT SO THE STAMP CANNOT BE FORGOTTEN. `index` adds `action` to every
        reply, and a dispatch written inline would have five `return` statements each of
        which had to remember to do it — which is how one branch ends up unstamped.

        `list_targets` returns a LIST, not a mapping, so the caller wraps it rather than
        spreading it; that asymmetry is the reason the wrapping happens in one place.

        THE TARGET GUARD IS HERE, ABOVE THE DISPATCH, for the same reason the stamp is:
        per-branch is where one branch forgets. Three of these five once accepted `target`
        into scope and never read it, so a caller could ask about one repository and be
        answered about another with no error anywhere in the payload.

        @brief Dispatch one validated index action.
        @return The underlying method's result.
        @version 2
        """
        if target is not None and action not in TARGET_ROUTING_ACTIONS:
            raise ValueError(registry_wide_target_error(action, target))
        if action == "status":
            return await self.status(ctx)
        if action == "refresh":
            return await self.build_or_refresh(
                ctx,
                force=force,
                doxyfile=doxyfile,
                scope=scope,
                exclude=exclude,
                target=target,
                options=options,
            )
        if action == "targets":
            return self.list_targets()
        if action == "cull":
            return self.cull(max_age_days=max_age_days, include_stale=include_stale)
        return self.tools.graph_stats(target)

    ## @brief Propose a starter `.clew.yaml` for the active target.
    ## @param ctx MCP request context (the only route to the client's roots).
    ## @param ignore_declaration Detect as if the repo declared nothing (audit mode).
    ## @return Dict with the rendered all-comments draft, the same proposal as a statable mapping, or an error.
    ## @version 4
    ## @req REQ-DDB-MCP-001
    ## @req REQ-DDB-CONFIG-008
    async def propose_declaration(
        self, ctx: Context, ignore_declaration: bool = False
    ) -> dict[str, Any]:
        """TIER-0 on purpose. The proposer's whole reason to exist is a repo that
        has not declared its conventions yet, which is precisely the state in which
        no tier-1 tool is registered — putting it in tier-1 would make it reachable
        only after the problem it solves had already been worked around by hand. It
        also queries no clew.db table; it reads the repo.

        The draft is entirely comments, so a caller may write it into the repo
        verbatim without changing any behaviour. Every proposed entry carries the
        evidence it came from and the measured delta it produced against the
        target's index; every refused candidate carries its reason.

        `statement` IS THE SAME PROPOSAL, MACHINE-READABLE (gh#360) — the draft's
        activatable lines parsed into the `{section: document}` mapping
        `build_or_refresh(options=…)` takes. Without it there was no path from a draft to a
        build at all: the draft is prose by design and `options` takes a structure, so an
        agent could only reach one by writing a YAML file into a tree it may not own. It
        does NOT make the draft authoritative — a caller still has to state it explicitly,
        and it is validated then.

        @brief Propose a starter declaration for the active repo.
        @return Draft dict, with the proposal also as a statable mapping.
        @version 4
        """
        target = await self.ensure_target(ctx)
        if target is None:
            return {"ok": False, "error": NO_TARGET_ERROR}
        return await anyio.to_thread.run_sync(self._run_propose, target, ignore_declaration)

    # ── internals ───────────────────────────────────────────────────────────

    ## @brief Register tier-1 tools and notify the client of the change.
    ## @param ctx MCP request context carrying the session.
    ## @return Names of the tier-1 tools now registered.
    ## @version 2
    ## @req REQ-DDB-MCP-003
    async def _activate_tier1(self, ctx: Context) -> list[str]:
        """Add the query tools (once a database exists) and fire
        `tools/list_changed` so the client re-reads the tool list.

        @brief Activate the tier-1 query tools and notify.
        @return Registered tool names.
        @version 2
        """
        if self.mcp is None:
            return []
        names = register_query_tools(self.mcp, self.tools)
        self.tier1_active = True
        await ctx.session.send_tool_list_changed()
        return names

    ## @brief Run the build pipeline in this process for one target.
    ## @param target Target to build.
    ## @param doxyfile Explicit Doxyfile path, or None to discover one.
    ## @param scope Scope source handed to the pipeline.
    ## @param exclude Operator-stated exclusions; None inherits the recorded ones, [] withdraws them.
    ## @param options Tier-1 build options keyed by declaration-file section name; None states nothing.
    ## @return Result dict (ok / built / doxyfile / output, plus error and traceback on a failure).
    ## @version 10
    ## @req REQ-DDB-CONFIG-008
    ## @dg_internal
    def _run_build(
        self,
        target: Target,
        doxyfile: str | None,
        scope: str = SCOPE_FROM_GUARD,
        exclude: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call `cli.build_index` directly, with the pipeline's whole rendered output
        captured so none of it reaches the stdio transport. Blocking — callers
        dispatch it to a worker thread, and the capture is context-local so it cannot
        touch what any other thread is writing.

        The pipeline is imported HERE rather than at module scope: it pulls tree-sitter
        and every extraction stage in, and a server session that only answers queries
        should never pay for that.

        `exclude` is FORWARDED UNCHANGED, `None` included, because `None` is what makes
        a plain refresh honour an exclusion stated in some earlier session. Defaulting
        it to `[]` here would turn every refresh into a withdrawal of the operator's
        own decision — the failure this whole path exists to prevent, reintroduced one
        layer above the code that prevents it.

        `exclude` is an index-SHAPE argument: scope is what the operator wants indexed,
        which nothing in the repository can state on their behalf.

        THIS PARAGRAPH USED TO ARGUE THAT CONVENTIONS NEED NO ROUTE THROUGH HERE — that a
        declared lock or thread or dispatch manifest is a fact about the CODE, read from the
        target's own `.clew.yaml`, so the CLI and this server could not honour
        different ones. That was half right and it is retired (gh#332, owner decision). The
        half that holds: a convention IS a fact about the code, and `.clew.yaml`
        remains the durable place to put it. The half that failed: it left TIER 1
        unreachable, so a five-tier precedence rule had a ceiling where it should have had a
        floor — and `event_tags` had no route at all, meaning the only way to state a bus
        vocabulary was to edit a tree the operator may not own.

        The build is not a one-shot: an operator refines an index with the values their
        repository actually needs, through these calls. `options` carries that, and a stated
        value wins over the declaration it is not obliged to write.

        @brief Execute the build pipeline in-process.
        @return Build result dict.
        @version 9
        """
        from ..cli import build_index

        repo = Path(target.repo_path)
        doxy = Path(doxyfile).expanduser().resolve() if doxyfile else discover_doxyfile(repo)
        # A missing Doxyfile is never fatal here: under `from-guard` the pipeline
        # synthesizes one from a declared `index_scope:`, and a repo that declares
        # nothing gets the whole-repo tier. Under `doxyfile` scope there is no
        # third tier to fall to, so that combination still fails loud rather than
        # starting a build that would index nothing.
        doxy_missing = doxy is None or not doxy.is_file()
        if doxy_missing and scope != SCOPE_FROM_GUARD:
            return {
                "ok": False,
                "built": False,
                "error": f"No Doxyfile found under {repo}, and scope={scope!r} names no "
                f"other source for the indexed tree — pass doxyfile=<path>, or "
                f"scope={SCOPE_FROM_GUARD!r} to index the repo's declared scope.",
            }
        doxy_arg = None if doxy_missing else doxy
        described = str(doxy) if doxy_arg is not None else "(synthesized from guard scope)"
        # NO LONGER COMPOSED HERE (gh#368 follow-up). This used to be
        # `repo / "requirements.yaml"`, passed below as `requirements=`, which is the
        # EXPLICIT-FLAG slot — so the conventional filename outranked a repo's DECLARED
        # `impact.requirements.file`, and only through this door. `cli` resolved
        # `flag or declaration` and never looked for the convention at all, so the same
        # repo could get two different catalogs depending on which entry point built it.
        # `requirements.resolve_catalog_path` now owns the whole order for both:
        # flag > declaration > convention > nothing. Passing None here means "no flag",
        # which is the truth: a build through MCP states no catalog path.
        with captured_output() as rendered:
            try:
                build_index(
                    output=Path(target.db_path),
                    repo_root=repo,
                    doxyfile=doxy_arg,
                    scope=scope,
                    requirements=None,
                    exclude=exclude,
                    options=options,
                )
            except (Exception, SystemExit) as exc:
                return {
                    **_failure_result(exc, rendered.getvalue()),
                    "built": False,
                    "doxyfile": described,
                }
            return {
                "ok": True,
                "built": True,
                "doxyfile": described,
                "output": rendered.getvalue(),
            }

    ## @brief Run the declaration proposer in this process for one target.
    ## @param target Target whose repo is analysed.
    ## @param ignore_declaration Detect as if the repo declared nothing.
    ## @return Result dict (ok / draft / statement / measured_against, plus error and traceback on a failure).
    ## @version 4
    ## @dg_internal
    def _run_propose(self, target: Target, ignore_declaration: bool) -> dict[str, Any]:
        """Every dry run re-runs a pipeline importer, and those render a rich progress
        bar — which on this server would land in the JSON-RPC stream. `captured_output`
        binds those bars to a buffer for the duration of this call only, so the
        transport is untouched and the draft comes back as a value.

        The index is passed only when it EXISTS, and `measured_against` reports exactly
        what was passed, so the two cannot disagree about what the numbers describe.

        THE STATEMENT IS DERIVED INSIDE THE SAME `try`, so a draft whose own activatable
        lines do not parse is a FAILURE rather than a reply carrying a draft nobody can
        act on. That can only be a defect in this renderer, and one that reached a caller
        as a silently-absent field would present as "the proposer found nothing".

        @brief Execute the proposer in-process.
        @return Proposal result dict.
        @version 4
        """
        from ..propose.registry import propose
        from ..propose.render import statement_from_draft

        db = Path(target.db_path)
        measured = db if db.is_file() else None
        with captured_output() as rendered:
            try:
                proposal = propose(
                    Path(target.repo_path),
                    measured,
                    use_declaration=not ignore_declaration,
                )
                statement = statement_from_draft(proposal.yaml_text)
            except (Exception, SystemExit) as exc:
                return _failure_result(exc, rendered.getvalue())
            return {
                "ok": True,
                "repo_path": target.repo_path,
                "measured_against": str(measured) if measured is not None else None,
                "draft": proposal.yaml_text,
                ## THE SAME PROPOSAL, MACHINE-READABLE (gh#360). `draft` is prose a human
                ## audits; this is the `{section: document}` mapping
                ## `build_or_refresh(options=…)` accepts, so an agent that finds at its
                ## first question what bringup missed can state it and refresh in-session
                ## instead of needing a file it may have nowhere to write. Deriving it
                ## costs nothing and changes nothing: the draft stays all-comments and a
                ## statement still has to be made explicitly.
                "statement": statement,
            }


## @brief Construct the MCP server with tier-0 tools registered.
## @param registry Target registry to use (defaults to the per-user one).
## @return Tuple of the MCP server instance and its DocsDbServer state object.
## @version 15
## @req REQ-DDB-MCP-001
def build_server(registry: TargetRegistry | None = None) -> tuple[MCPServer, DocsDbServer]:
    """Create the MCP server instance, register the tier-0 lifecycle tools, and bring
    tier-1 up if the registry already knows of a repository to answer about.

    That last step is what lets a process launched at NO repository serve query tools
    for the indexes it already holds. Without it the tool list would depend on how this
    process was started rather than on what a call asks for, which is the coupling the
    per-call `target` argument exists to remove.

    Also registers the `roots/list_changed` notification handler, HERE rather than in
    `run_stdio`, so the invalidation path is reachable from a test that never starts a
    transport. See `ROOTS_CHANGED_METHOD` on why the registration goes through
    `add_notification_handler` instead of the deprecated constructor keyword.

    THE TOOL TEXT IS NOT HERE. Each tier-0 description comes from `TIER0_TOOLS`, loaded
    from `descriptions/<tool>.json`, so this function registers tools and holds no prose —
    the same separation `tools_query` has always had for the tier-1 twenty. It used to
    carry all five inline, which put every wording change in a Python diff and had grown a
    1.5 KB paragraph inside a registration call before anyone looked.

    @brief Build the MCP server and its state object.
    @return (MCPServer, DocsDbServer).
    @version 15
    """
    from mcp.types import NotificationParams

    state = DocsDbServer(registry)
    mcp = MCPServer(name=SERVER_NAME, instructions=INSTRUCTIONS)
    state.mcp = mcp
    lowlevel(mcp).add_notification_handler(
        ROOTS_CHANGED_METHOD, NotificationParams, state.on_roots_list_changed
    )
    ## Registration order is FIXED HERE, because each call names its own bound method —
    ## the declared `priority` orders the tier-1 list, which is loaded rather than written
    ## out. The text itself lives in `descriptions/<tool>.json`: a description is the only
    ## thing a model reads before choosing a tool, so it is CONTENT, and a missing key
    ## raises here at startup rather than shipping a tool nothing can choose correctly.
    for tool, method in (
        ("index", state.index),
        ("propose_declaration", state.propose_declaration),
    ):
        ## SAME EXEMPTION FOR TIER 0 (gh#7). `index` is what a first-time user must call before
        ## anything else works, so leaving it deferred puts the two-call penalty on the very first
        ## interaction — the one where a reader is deciding whether the tool is worth the trouble.
        mcp.add_tool(method, name=tool, description=TIER0_TOOLS[tool], meta=ALWAYS_LOAD_META)
    state._sync_tier1()
    return mcp, state


## @brief Serve one MCP server instance over stdio, advertising tools/list_changed.
## @param mcp MCP server instance to serve.
## @version 3
## @req REQ-DDB-MCP-001
async def run_stdio(mcp: MCPServer) -> None:
    """Run the stdio transport with `tools_changed=True` in the initialization
    options. `MCPServer.run("stdio")` would advertise `tools.listChanged=False`,
    and a client that believes that has no reason to re-read `tools/list` when
    tier-1 appears — which is the whole design.

    The low-level server is the only route to `NotificationOptions`, and it is a PRIVATE
    attribute that was RENAMED between SDK generations (`_mcp_server` → `_lowlevel_server`)
    — the exposure a private hook implies, arriving on schedule. `_sdk.lowlevel` resolves
    it in one place and fails by name if a future generation drops it.

    @brief Run the server over stdio with the tool-list-changed capability.
    @version 4
    """
    from mcp.server.lowlevel.server import NotificationOptions
    from mcp.server.stdio import stdio_server

    low = lowlevel(mcp)
    async with stdio_server() as (read_stream, write_stream):
        await low.run(
            read_stream,
            write_stream,
            low.create_initialization_options(NotificationOptions(tools_changed=True)),
        )


## @brief Entry point — run the server over stdio.
## @version 5
## @req REQ-DDB-MCP-001
def main() -> None:
    """Run the clew MCP server on the stdio transport.

    `--repo <path>` is an OVERRIDE, not a pin. It exists for a transport that
    supplies nothing else: HTTP/SSE get no environment and may advertise no roots,
    and a caller that writes a config it will not run from (the benchmark harness's
    cells run in a scratch working directory) has no other way to name a target. It
    outranks the environment and the client's roots, and it does NOT refuse a later
    retarget — that refusal is what made a server unable to index a second
    repository (gh#19).

    Omitting it is the normal case for a Claude Code stdio server: the target comes
    from `$CLAUDE_PROJECT_DIR` at startup, or from the client's `roots/list` on the
    first call that needs one.

    @brief Run the MCP server (stdio) with a derived target.
    @version 4
    """
    parser = argparse.ArgumentParser(prog="clew-mcp", description="clew MCP server (stdio).")
    parser.add_argument(
        "--repo",
        help=(
            "Explicit target repo root, overriding $CLAUDE_PROJECT_DIR and the "
            "client's roots/list. Not a pin — the target can still change. Omit it "
            "under a client that supplies either of those."
        ),
    )
    args = parser.parse_args()
    mcp, state = build_server()
    state.resolve_startup_target(args.repo)
    anyio.run(run_stdio, mcp)
