# SPDX-License-Identifier: MIT
"""R3 target registry: where each repo's clew.db lives, and how fresh it is.

The MCP server is launched AT a repo, so it needs a per-user place to keep
built databases and a memory of which repos it has seen. Nothing here
hardcodes a machine path or a repo's layout: the state root is
`$CLEW_STATE_HOME`, else `$XDG_STATE_HOME/clew`, else
`~/.local/state/clew`; a repo's Doxyfile / requirements catalog are
DISCOVERED (and always overridable by the caller).

Freshness reuses the pipeline's own signature (`build_meta.build_version` vs
`CLEW_BUILD_VERSION`) — a db built by an older pipeline is stale even when
its mtime is recent. Age (mtime) drives the cull policy.

@brief Target registry, db paths, freshness and cull policy for the MCP server.
@version 2
"""

from __future__ import annotations

import string
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from ..doxygen import discover_doxyfile
from ..query._common import meta_section
from ..signature import CLEW_BUILD_VERSION, read_build_signature
from ..tiers import OPTIONS_META_PREFIX, stated_options
from .freshness import code_identity, notices

STATE_HOME_ENV = "CLEW_STATE_HOME"

## The variable Claude Code sets in a spawned local stdio server's environment,
## naming the directory the session was launched in. It is present BEFORE the first
## request, which is the whole reason it outranks `roots/list`: a target resolved
## from it lets the tier-1 query tools be registered on connect, so the tool list
## never changes mid-session for the common case.
PROJECT_DIR_ENV = "CLAUDE_PROJECT_DIR"

## How a target was arrived at. Reported by `status`, and load-bearing for
## invalidation: a `roots/list_changed` notification may only drop a target the
## CLIENT supplied. Dropping an operator's `--repo` or a declared
## `CLAUDE_PROJECT_DIR` because the client's root list moved would silently
## discard the more authoritative answer.
TARGET_SOURCE_FLAG = "--repo"
TARGET_SOURCE_ENV = PROJECT_DIR_ENV
TARGET_SOURCE_ROOTS = "roots/list"

## THE SEP-2577 FACTS, AS CONSTANTS RATHER THAN PROSE (gh#25), because the decision they
## justify is "keep the fallback until a date" and a comment cannot be asserted by a test.
##
## Established against the spec and the installed SDK, not inferred from the decorator:
##
## - The 2026-07-28 revision DEPRECATES Roots, Sampling and Logging (SEP-2577). The
##   deprecated-features registry gives Roots the migration path "Pass directories or files
##   via tool parameters, resource URIs, or server configuration" and the earliest removal
##   "First revision released on or after 2027-07-28" (SEP-2596's twelve-month window).
## - So THERE IS NO SUCCESSOR RPC. `--repo` IS the sanctioned migration — it is the
##   "server configuration" arm — which means link 1 of this server's chain is already the
##   answer and link 3 is what gets deleted, not replaced.
## - Roots did not leave the wire at 2026-07-28; it moved INSIDE the Multi Round-Trip
##   Requests envelope (SEP-2322): `InputRequest` at that revision is
##   `CreateMessageRequest | ListRootsRequest | ElicitRequest`. But the SDK's
##   `ServerSession.list_roots()` — the route used here — sends a STANDALONE
##   server-to-client request, and the 2026-07-28 surface has none at all
##   (`mcp_types.methods.SERVER_REQUESTS` holds zero rows for that revision). Hence
##   `roots_request_supported` below: the fallback is reachable only on a
##   handshake-era connection, and that is a property to READ from the SDK, not assume.
ROOTS_DEPRECATION_SEP = "SEP-2577"
ROOTS_DEPRECATED_IN = "2026-07-28"
ROOTS_EARLIEST_REMOVAL = "the first spec revision released on or after 2027-07-28"

## What a reader of the deprecation log is told to do instead. Names the flag rather than
## the capability, because the operator's action is a launch argument.
ROOTS_MIGRATION = f"pass the repo explicitly with {TARGET_SOURCE_FLAG} <path>"


## @brief The SDK's server-to-client request surface, or None when it cannot be read.
## @return Mapping keyed by (method, protocol version), or None.
## @version 2
## @dg_internal
def server_request_surface() -> Mapping[tuple[str, str], object] | None:
    """Read the SDK's own per-revision method map instead of hardcoding revisions.

    Returns None — meaning "unknown", never "empty" — when the map cannot be imported,
    so a future SDK reshuffle degrades to attempting the call rather than to silently
    refusing to. The attempt already fails closed at the call site.

    @brief Locate the SDK's (method, version) server-request map.
    @return The map, or None when unavailable.
    @version 2
    """
    try:
        from mcp_types.methods import SERVER_REQUESTS
    except Exception:
        return None
    return SERVER_REQUESTS


## @brief Protocol revisions the installed SDK recognises, or empty when unreadable.
## @return Tuple of revision strings, possibly empty.
## @version 2
## @dg_internal
def known_protocol_versions() -> tuple[str, ...]:
    """Empty means "this code cannot tell", which `roots_request_supported` reads as
    permission to try — never as "no revisions exist".

    @brief Read the SDK's registry of known protocol revisions.
    @return The revisions, or an empty tuple.
    @version 2
    """
    try:
        from mcp_types.version import KNOWN_PROTOCOL_VERSIONS
    except Exception:
        return ()
    return tuple(KNOWN_PROTOCOL_VERSIONS)


## @brief Whether a standalone `roots/list` request is carriable at this protocol revision.
## @param version Negotiated protocol revision, or None when the connection does not say.
## @return True when the request may be sent (including when the answer is unknown).
## @version 2
## @dg_internal
def roots_request_supported(version: str | None) -> bool:
    """FAILS OPEN, deliberately, on every unknown: an unstated revision, a revision the
    SDK does not recognise, and an unreadable method map all return True. A
    wrongly-refused request costs a target the client could have supplied and hides the
    reason; a wrongly-attempted one costs a caught exception and one log line.

    THE "KNOWN" TERM IS LOAD-BEARING AND WAS MISSING IN THE FIRST VERSION, which asked
    only whether the map listed `(roots/list, version)` — so any revision string the SDK
    had never heard of was REFUSED. That is backwards for the case that actually matters: a
    future revision restoring the request would be silently declined by an older
    installation of this server. A control assertion caught it.

    So only a revision the SDK positively KNOWS and does not list is refused, which today
    is exactly 2026-07-28, whose surface carries no server-to-client requests at all.
    Derived from the SDK rather than compared against a literal revision, so the day a
    revision restores the standalone request this follows without an edit.

    @brief Decide whether `roots/list` can be sent on this connection.
    @return Whether to attempt the request.
    @version 2
    """
    surface = server_request_surface()
    if surface is None or version not in known_protocol_versions():
        return True
    return (TARGET_SOURCE_ROOTS, version) in surface


## Per-user state root, under XDG_STATE_HOME or ~/.local/state. Overridable by
## `CLEW_STATE_HOME` for a caller that keeps indexes elsewhere.
STATE_DIR_NAME = "clew"

REGISTRY_NAME = "targets.json"
DB_NAME = "clew.db"


## @brief Per-user state root for built databases and the registry.
## @return Path to the clew state directory (not created by this call).
## @version 2
## @req REQ-DDB-MCP-001
def state_home() -> Path:
    """Resolve the state root, env-overridable and XDG-aware — never a hardcoded machine
    path, because this path is reported in payloads and a home directory in one of those
    is a machine-layout disclosure.

    @brief Resolve the per-user clew state directory.
    @return Path to the state root.
    @version 3
    """
    override = os.environ.get(STATE_HOME_ENV)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / STATE_DIR_NAME


## @brief Resolve the target available BEFORE any request, and say where it came from.
## @param explicit Value of `--repo`, or None.
## @param env Environment to read (defaults to `os.environ`; injected for testing).
## @return (repo path or None, one of the TARGET_SOURCE_* values or None).
## @version 1
## @req REQ-DDB-MCP-001
def startup_target(
    explicit: str | None, env: Mapping[str, str] | None = None
) -> tuple[str | None, str | None]:
    """The eager half of target resolution: `--repo`, then `$CLAUDE_PROJECT_DIR`.

    Both are readable at process start, so a target found here brings the tier-1
    query tools up on connect. The third source — the client's `roots/list` — is
    NOT readable here and cannot be: the only route to it is
    `ctx.session.list_roots()`, which needs a live request, and there is no session
    during `main()`. That asymmetry is why resolution is split across two functions
    rather than expressed as one ordered list.

    THE TWO SOURCES ARE VALIDATED DIFFERENTLY, on purpose. `--repo` is taken as
    given: an operator typed it, and a wrong path should fail loudly at the first
    query rather than be silently ignored in favour of something else. An
    environment variable is not a declaration about THIS server — it describes the
    client's session and may name a directory that has been moved or deleted — so it
    must prove it is a directory before it is adopted. Adopting a phantom would
    consume the resolution chain and prevent the `roots/list` fallback from ever
    running, which is the failure this ordering exists to avoid.

    @brief Resolve a target from the flag or the environment.
    @return (repo path or None, source label or None).
    @version 1
    """
    if explicit:
        return explicit, TARGET_SOURCE_FLAG
    declared = (env if env is not None else os.environ).get(PROJECT_DIR_ENV)
    if declared and Path(declared).expanduser().is_dir():
        return declared, TARGET_SOURCE_ENV
    return None, None


## @brief Convert one MCP root URI into a local directory path.
## @param uri Root URI as advertised by the client.
## @return The directory it names, or None when it is not a local directory.
## @version 1
## @req REQ-DDB-MCP-001
def root_uri_to_path(uri: str) -> Path | None:
    """`file://` ONLY, and it must resolve to an existing directory.

    A root is a client-supplied string, and this server turns it into a repo it will
    index — so it fails closed on anything it cannot verify. A non-`file` scheme is
    not a working tree at all; a `file` URI naming a missing path or a plain file is
    not a repo root. Returning None for those lets the caller keep walking the root
    list instead of adopting the first thing it was handed.

    `url2pathname` after `unquote` rather than string surgery on the URI: a
    percent-encoded path (a space in a directory name is enough) reaches here encoded,
    and slicing `uri[7:]` would produce a path that does not exist and would therefore
    be rejected by the `is_dir` check for entirely the wrong reason.

    @brief Parse a root URI into a verified local directory.
    @return The directory, or None.
    @version 1
    """
    parsed = urlsplit(str(uri))
    if parsed.scheme != "file" or not parsed.path:
        return None
    path = Path(url2pathname(unquote(parsed.path)))
    return path if path.is_dir() else None


## @brief One known target repo and the db path allocated to it.
## @version 1
@dataclass(frozen=True)
class Target:
    """A repo the server can build/query: its resolved root, a stable slug
    (name + path hash, so two same-named checkouts never collide), and the
    db path allocated under the state root.

    @brief Registered target repo (root + slug + db path).
    @version 1
    """

    repo_path: str
    slug: str
    db_path: str
    ## Which sub-index of `repo_path` this is, or None for the whole repository.
    ##
    ## SEPARATE FROM `repo_path` BECAUSE THAT FIELD IS A REAL FILESYSTEM PATH. It is handed to
    ## `Path()` by `answering`, read by `db_status`, and reported in every reply; folding a
    ## sub-index name into it would produce a path that does not exist and a stamped repository
    ## the caller cannot check.
    name: str | None = None


## @brief The repository ONE query answers from, resolved before the query runs.
## @version 1
@dataclass(frozen=True)
class Answering:
    """What a routed tool call needs to know about the repository it was told to read:
    the database, the working tree its recorded paths are relative to, and the staleness
    measured for it.

    One object rather than three lookups because the three must agree. A reply that read
    one repository's database and stamped another's path would be indistinguishable from
    a correct answer, and answering from the wrong index is this project's most expensive
    recorded defect.

    @brief Resolved routing target for one query (db + repo + staleness).
    @version 1
    """

    db: Path
    repo: Path
    staleness: list[dict[str, str]]


## @brief Allocate the Target record for a repo path (pure; no I/O).
## @param repo_path Repo root to allocate for.
## @param home State root to allocate under (defaults to state_home()).
## @return Target with a stable slug and its db path.
## @version 2
## @req REQ-DDB-MCP-001
def target_for(repo_path: Path | str, home: Path | None = None, name: str | None = None) -> Target:
    """Derive `<name>-<sha1[:6]>` from the resolved repo path so distinct
    checkouts of the same project get distinct db directories.

    `name` ALLOCATES A SUB-INDEX of one repository — several indexes under one root, so a repo
    that vendors its dependencies as submodules can build them once (they are pinned, therefore
    immutable) and rebuild only first-party code on every later refresh. Measured on a target
    vendoring llama.cpp: 592 files and 13.9 s split, against 3,521 files and 69.0 s whole.

    THE UNNAMED SPELLING IS FROZEN, and that is the constraint this function is written around.
    Every index already on disk lives at a path derived from the unnamed rule, and nothing records
    where it came from — so changing it strands those indexes rather than migrating them, and the
    symptom is "no database has been built for this repo yet" against a perfectly good index. The
    name is therefore appended to a slug that is otherwise computed exactly as before, and the
    digest still covers the PATH ONLY so an unnamed slug is byte-identical to its history.

    THE NAME IS SANITISED BECAUSE IT REACHES A FILESYSTEM PATH. Sub-index names come from a
    repository's own `.clew.yaml`, which is untrusted input by this project's standing rule, and
    a name of `../../etc` would otherwise place a database outside the state root. Reduced to
    `[A-Za-z0-9._-]`, refused when nothing survives — a rejection is recoverable, a write outside
    the state directory is not.

    @brief Derive a Target (slug + db path) for a repo root, optionally a named sub-index.
    @return Target for `repo_path`, or for one of its sub-indexes.
    @version 3
    """
    repo = Path(repo_path).expanduser().resolve()
    digest = hashlib.sha1(str(repo).encode("utf-8")).hexdigest()[:6]
    slug = f"{repo.name}-{digest}"
    if name is not None:
        slug = f"{slug}.{_safe_index_name(name)}"
    root = home if home is not None else state_home()
    return Target(
        repo_path=str(repo),
        slug=slug,
        db_path=str(root / "targets" / slug / DB_NAME),
        name=name,
    )


## @brief The registry key for one target — the repo path, or the path plus a sub-index name.
## @param repo_path Resolved repository root.
## @param name Sub-index name, or None for the whole repository.
## @return The key to store and match on.
## @version 1
## @utility
## THE REGISTRY IS KEYED BY SLUG, and there is no `registry_key()` function because none is
## needed: the slug a `Target` already carries IS the key. This used to compose
## `<repo_path>#<name>` — a delimiter invented for a general-purpose string key that no caller
## ever had a reason to see, since a sub-index is addressed through its own `sub_index`
## parameter rather than by reconstructing this string. `target_for` already derives a slug
## unique per `(repo_path, name)`, so reusing it as the key adds nothing and removes a format.
##
## LEGACY ENTRIES STAY KEYED BY BARE `repo_path`, on disk, until the next `register` call
## rewrites them — `targets()` reads either shape.


## Characters a sub-index name may contribute to a directory name. An ALLOWLIST rather than a
## blocklist of separators: what makes a path escape is not only `..` and `/` but every platform's
## own oddities, and enumerating those correctly is a bigger decision tree than permitting the
## small set that is obviously inert.
_INDEX_NAME_SAFE = frozenset(string.ascii_letters + string.digits + "._-")

## Longest sub-index name kept. Bounded because the result becomes a directory component and
## filesystems cap those; truncating is safe here in a way it is not for a security decision,
## since a collision between two truncated names shows up as a shared database rather than as a
## wrong answer, and `_safe_index_name` refuses the empty result that would alias the parent.
_INDEX_NAME_MAX = 48


## @brief Reduce a declared sub-index name to something safe as a directory component.
## @param name The declared name.
## @return The sanitised name.
## @version 1
## @dg_internal
def _safe_index_name(name: str) -> str:
    """REFUSES RATHER THAN SUBSTITUTES when nothing survives. A name that sanitises to empty would
    make the sub-index slug identical to the PARENT's, so a vendored sub-index would silently
    overwrite the whole-repo index — a wrong answer produced by a naming accident, which is worse
    than a build that stops and says the name is unusable.

    Leading dots are stripped for the same reason `clew_hook`'s token filter rejects them: `.` and
    `..` are path components, not names, and a dotfile directory in the state root is a surprise
    nobody asked for.

    @brief Sanitise a sub-index name.
    @return A safe directory component.
    @version 1
    """
    kept = "".join(ch for ch in name if ch in _INDEX_NAME_SAFE).lstrip(".")[:_INDEX_NAME_MAX]
    if not kept:
        raise ValueError(
            f"sub-index name {name!r} contains no usable characters "
            f"(allowed: letters, digits, '.', '_', '-')"
        )
    return kept


## Where an unreadable registry's bytes are kept. ONE deterministic name, not a timestamped
## series, and deliberately never overwritten: the FIRST preserved copy is the valuable one
## because it predates any re-registration, so a second corruption must not replace it.
UNREADABLE_SUFFIX = ".unreadable"

logger = logging.getLogger(__name__)


## @brief Persistent set of known targets (a small JSON file under the state root).
## @version 2
class TargetRegistry:
    """Maps repo root → allocated db path, persisted so `list_targets` and
    `cull` survive restarts.

    LOCK-FREE, BUT NOT BECAUSE THE SERVER IS SINGLE-PROCESS — that premise was written here
    and is false in this deployment: one `clew-mcp` runs per session, and the
    benchmark harness spawns one more per cell. What makes it safe is that every write is an
    atomic RENAME over the destination, so a concurrent reader sees the whole old document or
    the whole new one. `write_text` was not that: it truncates the destination and then fills
    it, and `load` read a half-filled file as an EMPTY REGISTRY, after which the next
    `register()` persisted a registry holding only its own entry.

    That is a loss that amplifies rather than a transient read error, and it was measured:
    24 slug directories holding real databases against ONE entry in `targets.json`.

    @brief JSON-backed registry of known target repos.
    @version 2
    """

    ## @brief Construct a registry rooted at a state directory.
    ## @param home State root (defaults to state_home()).
    ## @version 1
    ## @dg_internal
    def __init__(self, home: Path | None = None) -> None:
        self.home = home if home is not None else state_home()
        self.path = self.home / REGISTRY_NAME

    ## @brief Load the raw registry mapping from disk.
    ## @return Dict of repo_path → record; empty when absent or unreadable.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def load(self) -> dict[str, dict[str, str]]:
        """Read the registry file, tolerating absence and corruption (a
        broken registry must never take the server down).

        ABSENCE AND CORRUPTION ARE DIFFERENT FACTS and are now told apart. An absent file is
        the ordinary first run and stays silent; an unreadable one is an error, is logged as
        one, and has its bytes moved aside. The bare `except … : return {}` made the two
        indistinguishable — and the empty reading is the one that gets persisted, so silence
        was how the loss stayed invisible.

        A ROOT THAT PARSES BUT IS NOT AN OBJECT is the same class of damage as one that does
        not parse, so it is raised into the same handler rather than quietly becoming `{}`.

        @brief Read the persisted registry mapping.
        @return repo_path → {slug, db_path} records.
        @version 2
        """
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise TypeError(f"registry root is a {type(data).__name__}, not an object")
        except (OSError, ValueError, TypeError) as exc:
            self._preserve_unreadable(exc)
            return {}
        return data

    ## @brief Move an unreadable registry aside and say so, loudly.
    ## @param reason The error that made it unreadable.
    ## @version 1
    ## @req REQ-DDB-MCP-001
    ## @dg_internal
    def _preserve_unreadable(self, reason: Exception) -> None:
        """Moving it aside is what stops the loss becoming permanent: `register()` calls
        `load()` and then `save()`, so an unreadable file left in place is overwritten by a
        registry containing one entry, and the only record of what was registered is gone.

        A read method with a filesystem side effect is a real cost, accepted because `load`
        is the only place that knows the file is unreadable — detecting it a second time in
        `save` would mean reading the registry on every write.

        MOVE FIRST, THEN REPORT. The first version composed the sentence "Its bytes are
        preserved at X" and only afterwards attempted the move, so a failed `os.replace`
        emitted a confident false claim followed by a correction — an operator reading the
        first line would have believed the data was safe. A mutation control found it, by
        disabling the move and leaving the message intact.

        @brief Log an unreadable registry, having first preserved its bytes.
        @version 2
        """
        kept = self.path.with_name(self.path.name + UNREADABLE_SUFFIX)
        logger.error(
            "%s is unreadable (%s: %s). Treating the registry as EMPTY for this call, so "
            "list_targets and cull will not see previously registered repositories. %s",
            self.path,
            type(reason).__name__,
            reason,
            self._move_aside(kept),
        )

    ## @brief Move the unreadable registry to `kept`, reporting what actually happened.
    ## @param kept Where the bytes should be preserved.
    ## @return A sentence describing the outcome, for the caller's log line.
    ## @version 1
    ## @dg_internal
    def _move_aside(self, kept: Path) -> str:
        """Returns prose rather than a bool so the log line cannot overstate the outcome:
        every branch here is a DIFFERENT fact for whoever reads it — already safe, newly
        safe, or about to be lost — and a boolean would collapse the third into the second.

        An existing preserved copy is never overwritten. The FIRST one predates any
        re-registration, so it is the more complete record.

        @brief Preserve the unreadable registry and describe the result.
        @return The outcome sentence.
        @version 1
        """
        if kept.exists():
            return f"An earlier copy is already preserved at {kept}; leaving this one in place."
        try:
            os.replace(self.path, kept)
        except OSError as exc:
            return (
                f"COULD NOT preserve its bytes to {kept} ({exc}); they will be lost when "
                "the registry is next written."
            )
        return f"Its bytes are preserved at {kept}."

    ## @brief Persist the registry mapping to disk.
    ## @param data Mapping to write.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def save(self, data: dict[str, dict[str, str]]) -> None:
        """Write the registry, creating the state root on demand.

        STAGE THEN RENAME, because `write_text` truncates the destination before filling it
        and a reader arriving in that window reads an empty registry rather than failing.
        `os.replace` is atomic within a filesystem, and the staging file is a sibling so it
        always is one.

        The staging name carries the PID so two processes saving at once cannot corrupt each
        other's half-written file; the rename is what serialises them, and last writer wins —
        which is the pre-existing whole-file-replacement semantics, now actually delivered.

        @brief Persist the registry mapping atomically.
        @version 2
        """
        self.home.mkdir(parents=True, exist_ok=True)
        staging = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        staging.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(staging, self.path)

    ## @brief Register (or re-register) a repo and allocate its db path.
    ## @param repo_path Repo root to register.
    ## @return The Target recorded for that repo.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def register(self, repo_path: Path | str, name: str | None = None) -> Target:
        """Allocate the Target for `repo_path`, persist it, and ensure its
        db directory exists so a build can write there.

        `name` registers a SUB-INDEX of the repository — several indexes under one root, so a
        repo vendoring pinned submodules builds them once and rebuilds only first-party code
        thereafter.

        `repo_path` IS WRITTEN INTO THE RECORD from here on, and that is what makes a composite
        key safe: `targets()` reconstructs a Target from the key when the field is absent, which
        is correct for every entry written before sub-indexes existed and wrong for a composite
        one. Storing it removes the need for the reader to parse the key at all.

        @brief Register a target repo, or one of its sub-indexes.
        @return The registered Target.
        @version 3
        """
        target = target_for(repo_path, self.home, name)
        data = self.load()
        record = {
            "slug": target.slug,
            "db_path": target.db_path,
            "repo_path": target.repo_path,
        }
        if name is not None:
            record["name"] = name
        data[target.slug] = record
        self.save(data)
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        return target

    ## @brief Every registered target.
    ## @return List of Target in registration-key order.
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def targets(self) -> list[Target]:
        """Rebuild Target records from the persisted mapping.

        @brief List all registered targets.
        @return List of Target.
        @version 2
        """
        ## `repo_path` FALLS BACK TO THE KEY, which is exactly right for every entry written
        ## before sub-indexes existed — there the key IS the repo path — and is never reached for
        ## a composite key, because `register` writes the field whenever it writes one.
        return [
            Target(
                repo_path=rec.get("repo_path") or repo,
                slug=rec.get("slug", ""),
                db_path=rec.get("db_path", ""),
                name=rec.get("name"),
            )
            for repo, rec in sorted(self.load().items())
        ]

    ## @brief Forget a target and delete its built database directory.
    ## @param repo_path Repo root to drop every sub-index of, or an exact slug.
    ## @return True when at least one entry was registered (and has now been removed).
    ## @version 2
    ## @req REQ-DDB-MCP-001
    def drop(self, repo_path: str) -> bool:
        """DROPS EVERY SUB-INDEX OF A REPOSITORY, not just the one keyed under the bare path.
        Since the registry is keyed by slug, one repository can own several entries, and a caller
        passing its root almost always means "forget this repo", not "forget whichever entry
        happens to be keyed under this exact string". The argument is still accepted as an exact
        slug too, for a caller that named one sub-index specifically.

        @brief Drop a target and its database — every sub-index if a repo root was given.
        @return Whether anything was removed.
        @version 2
        """
        data = self.load()
        matches = [
            key
            for key, rec in data.items()
            if key == repo_path or rec.get("repo_path") == repo_path
        ]
        if not matches:
            return False
        for key in matches:
            record = data.pop(key)
            db_dir = Path(record.get("db_path", "")).parent
            if db_dir.is_dir() and db_dir.is_relative_to(self.home):
                shutil.rmtree(db_dir, ignore_errors=True)
        self.save(data)
        return True


## @brief Count indexed source files modified since the database was built.
## @param db Path to the built database.
## @param repo_root Working tree the indexed paths are relative to.
## @return (number of files newer than the db, the newest such path or None).
## @version 2
## @dg_internal
def _source_drift(db: Path, repo_root: Path) -> tuple[int, str | None]:
    """Stat every indexed source file against the database's own mtime.

    This is the term freshness was missing entirely. Staleness used to be just
    `stamped != CLEW_BUILD_VERSION`, so a database built before any number
    of source edits still reported `stale: false` and `build_or_refresh`
    declined to rebuild it — an agent then answered from a graph describing
    code that no longer exists, with the status tool actively asserting the
    index was current. A version check cannot see source drift; only mtimes can.

    Fails closed to "no drift" on an unreadable or table-less database: the
    version term already marks those stale, and guessing here would force
    pointless rebuilds.

    @brief Detect source files newer than the database.
    @return (changed count, newest changed repo-relative path).
    @version 2
    """
    try:
        db_mtime = db.stat().st_mtime
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        return 0, None
    try:
        indexed = [r[0] for r in conn.execute("SELECT name FROM path WHERE type=1")]
    except sqlite3.Error:
        indexed = []
    finally:
        conn.close()
    changed, newest, newest_mtime = 0, None, 0.0
    for rel in indexed:
        try:
            mtime = (repo_root / rel).stat().st_mtime
        except OSError:
            continue  # deleted/moved: the rebuild will notice, this pass will not
        if mtime > db_mtime:
            changed += 1
            if mtime > newest_mtime:
                newest, newest_mtime = rel, mtime
    return changed, newest


## @brief One namespaced `build_meta` section, read without its key prefix.
## @param db Path to a built clew.db.
## @param prefix Section name (`scope`, `coverage`, `refresh`), without the dot.
## @return Mapping of unprefixed key to value; {} when absent or unreadable.
## @version 2
## @req REQ-DDB-MCP-001
def _meta_section(db: Path, prefix: str) -> dict[str, str]:
    """ONE reader for every section, because there were two byte-identical copies of it
    and a third was about to be pasted in for `refresh.*`. `build_meta` is deliberately a
    namespaced key/value table so that a further section is a one-line change; three
    copies of the same six-line SQLite dance is the opposite of that design.

    THE IMPLEMENTATION MOVED to `query._common.meta_section` when gh#7 needed the same
    section from the query layer — a fourth copy would have been the exact drift this
    function was written to stop. The delegation is kept as a named function rather than
    an import alias because the single-path audit's exemption for this module is written
    against these three readers by name, and because the `Path`-typed signature is what
    every caller here passes.

    @brief Read one namespaced build_meta section.
    @return Mapping without the key prefix, or {}.
    @version 2
    """
    return meta_section(db, prefix)


## @brief The scope decision recorded at build time, if any.
## @param db Path to a built clew.db.
## @return {source, reason, roots, excludes} without the `scope.` prefix; {} when absent.
## @version 2
## @req REQ-DDB-MCP-001
def _scope_meta(db: Path) -> dict[str, str]:
    """WHY a file set is what it is, which nothing in the database answered before build 16.

    Measured on the entropic acceptance grid: the raw arm scored 3/3 on "checks the Doxyfile
    and reports its INPUT does not list examples/" against the index arm's 1/3 — the only
    clearly actionable gap in 56 marks. The raw arm simply reads the Doxyfile; the index arm
    had no route to it, because the pipeline logged its scope decision and never stored it.

    @brief Read the stored scope provenance.
    @return Mapping without the key prefix, or {}.
    @version 2
    """
    return _meta_section(db, "scope")


## @brief The index-coverage measurement recorded at build time, if any.
## @param db Path to a built clew.db.
## @return Coverage keys without the `coverage.` prefix; {} when absent.
## @version 2
## @req REQ-DDB-INDEX-003
def _coverage_meta(db: Path) -> dict[str, str]:
    """HOW MUCH of what was indexed actually yielded anything — which nothing in the
    database answered before build 18, and which `status` could not report even though
    the pipeline had measured it.

    gh#6: a build announced 2,555 functions and 28,151 call edges for a target whose
    index held almost none of the library, and `status` reported that index as present,
    current and healthy. Size was queryable and coverage was not, so a consumer had no
    way to ask the one question that would have voided a 198-cell acceptance run before
    it was paid for.

    @brief Read the stored coverage measurement.
    @return Mapping without the key prefix, or {}.
    @version 2
    """
    return _meta_section(db, "coverage")


## @brief What the last refresh of this index actually cost, if it was measured.
## @param db Path to a built clew.db.
## @return {duration_ms, payloads_recomputed, cache_hits, at} as strings; {} when absent.
## @version 1
## @req REQ-DDB-MCP-004
def _refresh_meta(db: Path) -> dict[str, str]:
    """THE COST OF CORRECTING STALENESS, AS A MEASUREMENT (gh#9). The pipeline knew its
    wall duration, how many files it reprocessed and how many it took from cache, and
    returned none of it — so an agent asked what a refresh costs had to estimate, and
    the two benchmark marks that demand a measured number missed 9 of 9 cells across
    every model tier.

    Persisted rather than estimated from a constant so the number is grounded in THIS
    target's own history: 1.6 s for a 114-file target and 9.1 s for 420 files are the
    same tool, and a single built-in constant would be wrong for both.

    Values are STRINGS because `build_meta` is a TEXT table — and, load-bearingly,
    because `write_build_signature` DROPS FALSY VALUES, so a measured zero survives as
    `"0"` and would vanish as `0`. gh#6, gh#17 and gh#18 each worked around that; this
    is the fourth section to do so on purpose.

    @brief Read the measured cost of the last refresh.
    @return Mapping without the key prefix, or {}.
    @version 1
    """
    return _meta_section(db, "refresh")


## @brief Which precedence tier chose each layered setting this index was built with.
## @param db Path to a built clew.db.
## @return `<option>.tier` (and `<option>.explicit` when an operator stated one); {} when absent.
## @version 1
## @req REQ-DDB-CONFIG-006
def _options_meta(db: Path) -> dict[str, str]:
    """WHOSE POLICY the index was built under (gh#319), which is the half of the
    scope story the other sections do not tell. `scope.*` says which files were
    indexed and `coverage.*` how much of them yielded anything — neither says
    whether the liveness split came from the repo's own declared dispatch
    vocabulary, from a flag an operator passed once, or from our provisional
    name-shape guesses. A consumer reading a surprising orphan count has opposite
    responses available for those three, and nothing to choose between them with.

    Reporting it is not decoration: a tiered resolution whose winner is not visible
    is the same opacity as an untiered one, with more moving parts. Absent on an
    index built before build 30, which is the honest signal.

    @brief Read the stored layered-option provenance.
    @return Mapping without the key prefix, or {}.
    @version 1
    """
    return _meta_section(db, OPTIONS_META_PREFIX)


## @brief What the build searched for and did NOT find, counts included when they are zero.
## @param db Path to a built clew.db.
## @return Named accessor families and unclaimed event aliases with their counts; {} when absent.
## @version 1
## @req REQ-DDB-CONFIG-007
def _diagnostics_meta(db: Path) -> dict[str, str]:
    """THE ONLY SECTION ABOUT ABSENT ROWS (gh#320). Every other section describes what
    the index HAS; this one names what the build looked for, did not claim, and therefore
    wrote nothing for — so a sparse causal layer can be told apart from a repository that
    genuinely has no dataflow.

    The counts arrive as `"0"` rather than as missing keys, which is the whole point:
    "searched 3,784 names and matched no undeclared family" is a measurement an agent can
    report, while an absent key is indistinguishable from a diagnostic that never ran.
    The SECTION being absent still means "not recorded" — true only for an index built
    before this existed, and honest for one.

    A LITERAL prefix, like `scope`/`coverage`/`refresh` above and unlike `options`.
    Importing `diagnostics.META_PREFIX` would pull the shared-key and event importers into
    the server's startup path to read one string. The spelling is pinned by a round-trip
    test instead, which catches a divergence at either end rather than only at this one.

    @brief Read the stored build diagnostics.
    @return Mapping without the key prefix, or {}.
    @version 1
    """
    return _meta_section(db, "diagnostics")


## @brief The generated data model the repository declares, and what was declined.
## @param db Path to a built clew.db.
## @return Dialect(s), key/class/manifest counts, every refusal count and the unresolved-fields
##         note; {} when absent.
## @version 2
## @req REQ-DDB-CONFIG-007
def _data_model_meta(db: Path) -> dict[str, str]:
    """gh#351, and it is a DIAGNOSTIC as much as an inventory. `data_model.keys` beside
    `data_model.keys_listed` and the `data_model_keys.observed` column is the declared-vs-
    observed measurement the layer exists for: a repository declaring 135 keys and touching 5
    of them is a fact about that repository nothing else in the index reports.

    The REFUSALS are the half a consumer acts on. `manifests_unlisted` says shape-matching
    manifests were found and declined because no key list vouched for them, which is the
    difference between "this repository has no data model" and "it has one and nothing selects
    it"; `documents_oversized` means a document was refused unread for its size, and
    `toml_unavailable` that the INGOT half specifically could not be looked at — both mean
    "could not look" rather than "looked and found none". A count of zero is the measurement.

    `unresolved_note` is the one PROSE field in this section and it earns that. gh#351 reads
    two dialects, and one of them declares a key's default as a base value plus per-variant
    siblings that only a build's variant selection resolves — so those rows carry a NULL
    `default_value` BY DIALECT rather than by absence. A consumer cannot tell those apart from
    a count, and the per-row `data_model_keys.unresolved_fields` it points at is what makes
    the distinction queryable. The field is absent when nothing was unresolved, so it never
    asserts a policy that did not apply to this repository.

    A LITERAL prefix, for the reason `_diagnostics_meta` gives one screenful up: importing the
    writer's constant would pull the discovery module into the server's startup path to read
    one string, and a round-trip test pins the spelling at both ends instead.

    @brief Read the stored data-model inventory and its refusals.
    @return Mapping without the key prefix, or {}.
    @version 2
    """
    return _meta_section(db, "data_model")


## @brief Freshness/identity report for one target's database.
## @param target Target to inspect.
## @return Dict with existence, stamped/expected build version, source drift, staleness, age, scope, coverage, refresh cost, layered-option tiers, the options an operator stated, build diagnostics, the declared data model, code identity and interpreted notices.
## @version 11
## @req REQ-DDB-MCP-001
## @req REQ-DDB-MCP-004
## @req REQ-DDB-CONFIG-006
## @req REQ-DDB-CONFIG-007
def db_status(target: Target) -> dict[str, object]:
    """Describe the db behind a target: does it exist, which pipeline version
    stamped it, HAVE ITS SOURCES CHANGED SINCE, and how old is it.

    Staleness is now two-termed, matching what the word means to a caller: an
    older pipeline stamp OR drifted sources. Previously only the stamp counted,
    which made `status` affirmatively wrong for the commonest case in live
    development — edit a file, and the index still claimed to be current.

    COVERAGE is reported beside size for gh#6: an index can be present, current and
    entirely trustworthy-looking while holding almost none of the repository. Staleness
    answers "does this describe the code as it is now"; coverage answers "does it
    describe the code at all". A consumer that checks only the first can still be
    reasoning about a library whose implementation never parsed.

    AND `stale` IS NOW INTERPRETED, not merely raised. Three different things make it
    true and they are cleared by three different actions — a rebuild, a client restart,
    or nothing the consumer can do — so the flag alone under-determines the remedy. The
    worst case shipped for months: `expected_build_version` below `build_version` makes
    `stale: true` UNRESOLVABLE, because a rebuild re-stamps the same newer version. Both
    integers were already right here in the payload and nothing read them out loud.
    `staleness` is ABSENT when the tool is current, so it stays a signal.

    AND WHOSE POLICY THIS INDEX CARRIES IS NAMED, not merely derivable (gh#364). A tier-1
    statement now SURVIVES a rebuild, which means the index can carry a policy the
    repository does not declare — so two operators of one commit can hold different
    indexes. That is allowed only because it is deliberate AND visible: `stated_options`
    names the options an operator stated, so the difference is findable without reading
    every `options.*` row and knowing which tier word matters. Absent when nothing was
    stated, so it stays a signal rather than a field to skim past.

    @brief Report a target database's freshness, coverage, refresh cost, option tiers, stated options, build diagnostics, declared data model and code identity.
    @return Status dict (exists / build_version / drift / stale / age_days / coverage / refresh / options / stated_options / diagnostics / data_model / code / staleness).
    @version 10
    """
    db = Path(target.db_path)
    exists = db.is_file()
    ## Read ONCE and used twice — the stored rows and the derived summary of them. Two
    ## reads could not disagree today, but the summary must be a projection of exactly
    ## the rows reported beside it rather than of a second look at the database.
    options = _options_meta(db) if exists else {}
    stated = stated_options(options)
    stamped = read_build_signature(db) if exists else None
    age_days = round((time.time() - db.stat().st_mtime) / 86400.0, 3) if exists else None
    changed, newest = _source_drift(db, Path(target.repo_path)) if exists else (0, None)
    status: dict[str, object] = {
        "repo_path": target.repo_path,
        "db_path": target.db_path,
        ## ABSENT FOR A WHOLE-REPO TARGET, present and named for a sub-index — so a caller can
        ## tell the two apart without parsing anything, and `list_targets` can offer every
        ## sub_index name a repository has without a second call.
        **({"sub_index": target.name} if target.name is not None else {}),
        "exists": exists,
        "build_version": stamped,
        "expected_build_version": CLEW_BUILD_VERSION,
        "source_changed_files": changed,
        "newest_changed_source": newest,
        "stale": (not exists) or stamped != CLEW_BUILD_VERSION or changed > 0,
        "age_days": age_days,
        ## WHY this file set, not just what. Absent on an index built before build 16, which
        ## is the honest signal — "not recorded" rather than a fabricated default.
        **({"scope": _scope_meta(db)} if exists else {}),
        ## HOW MUCH of that file set yielded anything. Absent before build 18, same signal.
        **({"coverage": _coverage_meta(db)} if exists else {}),
        ## WHAT CORRECTING IT COSTS, measured on this target rather than estimated. Read
        ## BEFORE the notices below, which quote it, so the advice to refresh carries a
        ## number instead of inviting a guess.
        **({"refresh": _refresh_meta(db)} if exists else {}),
        ## WHOSE POLICY chose the layered settings — an operator's flag, the target's
        ## own declaration, or our provisional guesses. Absent before build 30.
        **({"options": options} if exists else {}),
        ## WHICH OF THEM AN OPERATOR STATED, and therefore which are being REPLAYED onto
        ## every later rebuild of this index. DERIVED from the rows above, never stored: a
        ## stored summary is a second source of truth that can disagree with what it
        ## summarises, which is where a silent wrong answer hides. Absent when nothing was
        ## stated — the common case, and the one that needs no attention.
        **({"stated_options": list(stated)} if stated else {}),
        ## WHAT THE BUILD LOOKED FOR AND DID NOT FIND, counts included when zero. The
        ## only section about absent rows, and the one that makes an empty causal layer
        ## distinguishable from a repo that has no dataflow (gh#320).
        **({"diagnostics": _diagnostics_meta(db)} if exists else {}),
        ## WHICH GENERATED DATA MODEL the repository declares, how much of it the code was
        ## observed to touch, and every manifest the discovery declined and why (gh#351).
        ## Absent before build 37. Empty-but-present for the many repositories that have no
        ## generated data model, which is a correct negative rather than a gap.
        **({"data_model": _data_model_meta(db)} if exists else {}),
        ## WHICH CODE IS ANSWERING. Not about the database at all — about this process —
        ## and the one axis that had no signal whatsoever before gh#29.
        "code": code_identity(),
    }
    found = notices(status)
    if found:
        status["staleness"] = found
    return status


## @brief Remove databases that are aged out or built by an older pipeline.
## @param registry Registry to sweep.
## @param max_age_days Age threshold in days; None culls only version-stale dbs.
## @param include_stale Also cull dbs whose stamped build version is not current.
## @return List of status dicts for the targets that were culled.
## @version 2
## @req REQ-DDB-MCP-001
def cull(
    registry: TargetRegistry,
    max_age_days: float | None = 30.0,
    include_stale: bool = True,
) -> list[dict[str, object]]:
    """Sweep the registry, dropping each target whose db is older than
    `max_age_days` or (when `include_stale`) carries a non-current build
    signature. Targets with no db on disk are dropped too — the registry
    entry is dead weight.

    @brief Cull aged/stale target databases.
    @return Status dicts of the culled targets.
    @version 2
    """
    culled: list[dict[str, object]] = []
    for target in registry.targets():
        status = db_status(target)
        age = status["age_days"]
        aged_out = max_age_days is not None and isinstance(age, float) and age > max_age_days
        version_stale = include_stale and status["build_version"] != CLEW_BUILD_VERSION
        if not status["exists"] or aged_out or version_stale:
            registry.drop(target.repo_path)
            culled.append(status)
    return culled


# Re-exported from the pipeline so the MCP server and the CLI share ONE
# discovery implementation. They previously diverged — only the MCP path looked
# for the repo's Doxyfile — which silently produced different databases for the
# same repo depending on the entry point used.
__all__ = ["discover_doxyfile"]
