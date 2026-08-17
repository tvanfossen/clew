# SPDX-License-Identifier: MIT
"""Locate, merge and write the MCP client configs `clew init` registers in.

Everything here is about ONE property: **an MCP config belongs to the user, not
to us.** A `.mcp.json` almost always already names other servers, and
`~/.claude.json` holds the whole user-level Claude Code state — hundreds of keys
that have nothing to do with this tool. So this module never writes a document it
did not first read: it parses, replaces exactly one entry under `mcpServers`, and
re-serialises the rest verbatim (dict order is insertion order in both
`json.loads` and `json.dumps`, so unrelated keys keep their place). A file that
does not parse is REFUSED, never rewritten — a doctor that repairs a config by
truncating it is worse than no doctor.

**Where the two scopes live, and how that was established.** Both were probed on
a real Claude Code install (2.1.220) rather than recalled:

* repo scope → `<repo>/.mcp.json`, top-level `mcpServers`. `claude mcp add -s
  project` writes exactly this. (This sentence used to add "and it is the shape
  this repo's own committed `.mcp.json` already uses" — there is no such file
  here, and `resolve_server_command` carried the same invented claim to argue
  that re-running `init` in this checkout is a no-op. It is not; it creates a
  file. A justification asserting a fact about the repo is worth checking against
  the repo.)
* global scope → `$CLAUDE_CONFIG_DIR/.claude.json` (default `~/.claude.json`),
  ALSO top-level `mcpServers`. `claude mcp add -s user` with `CLAUDE_CONFIG_DIR`
  pointed at a scratch directory created `<that dir>/.claude.json` and reported
  the path it modified.

Note what global scope is NOT: `~/.claude/settings.json` (that is settings, not
servers) and not `.projects[<cwd>].mcpServers` inside the same file — that key
holds `claude mcp add -s local`, the per-directory private scope, which is a
third thing this command deliberately does not offer.

The entry KEY is `clew` and is deliberately not
`mcp_server.server.SERVER_NAME` (which is `clew`, the name the server
advertises inside the protocol handshake). They are different namespaces: the
config key is how a human refers to the server in their own file, and importing
the constant would also drag the optional MCP SDK into a command whose whole job
is to run BEFORE that SDK is necessarily installed.

**This module also owns the atomic writer both `init` targets use.** `WritePlan` +
`apply_plan` know nothing about JSON, and `guidance.py` — which writes a delimited
block into the user's CLAUDE.md — plans against the same base and applies with the
same function. That is deliberate rather than incidental: the backup-before-swap
ordering here is the one piece of this command whose failure is unrecoverable, so it
exists once.

@brief MCP client config discovery, merge planning and the shared atomic write.
@version 2
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import logger
from .vocabulary import (
    INIT_ACTION_ADD,
    INIT_ACTION_CREATE,
    INIT_ACTION_UNCHANGED,
    INIT_ACTION_UPDATE,
    INIT_SCOPE_REPO,
)

## The key under which this server is recorded. See the module docstring on why
## it is not `mcp_server.server.SERVER_NAME`.
MCP_ENTRY_NAME = "clew"
## The object both config shapes carry their servers in.
SERVERS_KEY = "mcpServers"
## Project-scoped config, committed in the repo it belongs to.
REPO_CONFIG_NAME = ".mcp.json"
## User-scoped config file and the env var that relocates the directory holding
## it (both verified live — see the module docstring).
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
CLAUDE_USER_CONFIG_NAME = ".claude.json"
CLAUDE_STATE_DIR_NAME = ".claude"
## The console script `pip install clew` puts on PATH.
CONSOLE_SCRIPT = "clew-mcp"
## Fallback indentation for a file we are creating. Matches what Claude Code
## itself writes, so an `init`-created file and a `claude mcp add`-created one
## are not gratuitously different.
DEFAULT_INDENT = 2


## @brief A target file that cannot be safely rewritten.
## @version 2
class ConfigError(RuntimeError):
    """Raised when the file at the target path exists but cannot be edited
    surgically — for a config, because it is not a JSON object or its `mcpServers`
    is not an object.

    Deliberately fatal rather than recoverable: the only way to "handle" an
    unparseable target here is to overwrite it, and that destroys content the user
    wrote by hand. The message names the path and what was wrong with it so the fix
    is a one-line edit.

    `guidance.GuidanceError` subclasses this, so a caller that already refuses on a
    malformed config refuses on a malformed CLAUDE.md too rather than needing to
    remember a second exception type.

    @brief A target `init` writes into is malformed — refuse to touch it.
    @version 2
    """


## @brief Where the console script was found and whether the answer travels.
## @version 1
@dataclass(frozen=True)
class CommandResolution:
    """The `command` string to write, plus how it was arrived at.

    `portable` is False for an absolute path: it works on this machine and
    nowhere else, which matters because a repo-scoped `.mcp.json` is normally
    committed. The caller surfaces it rather than silently choosing for the user.

    @brief Resolved MCP server command plus its provenance.
    @version 1
    """

    command: str | None
    origin: str
    portable: bool


## @brief A computed-but-unperformed write to one file `init` owns a slice of.
## @version 1
@dataclass(frozen=True)
class WritePlan:
    """The whole contract `apply_plan` needs, and nothing about JSON.

    Holding the exact `text` rather than re-serialising at write time is what
    makes `--dry-run` honest: the string printed is byte-for-byte the string that
    would land on disk, not a re-render that could differ.

    Extracted as a base when `init` acquired a SECOND target — a delimited block in
    the user's CLAUDE.md (`guidance.py`). That write has the same three properties
    the JSON one does (the file belongs to the user, an identical write must be a
    no-op, an overwrite must leave a backup) and none of its shape, so the atomic
    swap is shared and the document model is not. A second `apply_plan` would have
    been a second place for the backup ordering to be got wrong.

    @brief Planned write of one file, in the form the atomic writer needs.
    @version 1
    """

    path: Path
    action: str
    text: str
    diff: str


## @brief What registering the server would do to one config file.
## @version 2
@dataclass(frozen=True)
class MergePlan(WritePlan):
    """A `WritePlan` plus the JSON-document detail the config surface reports on.

    `entry`/`existing` drive the conflict diff and `document` is the merged object
    a caller can assert against without re-parsing `text`.

    @brief Planned merge of this server's entry into a config file.
    @version 2
    """

    entry: dict[str, Any]
    existing: dict[str, Any] | None
    document: dict[str, Any]


## @brief Directory Claude Code keeps its per-user state in.
## @return Path to `$CLAUDE_CONFIG_DIR`, else `~/.claude`.
## @version 1
## @req REQ-DDB-MCP-001
def claude_state_dir() -> Path:
    """`CLAUDE_CONFIG_DIR` relocates the WHOLE config directory, and when it is
    set the state directory is that directory itself — not a `.claude` child of
    it. Verified by probing a real install: with the variable pointed at a scratch
    path, Claude Code created `<scratch>/.claude.json` and `<scratch>/backups/`
    directly.

    @brief Resolve Claude Code's per-user state directory.
    @return Path to the state directory (not created by this call).
    @version 1
    """
    override = os.environ.get(CLAUDE_CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / CLAUDE_STATE_DIR_NAME


## @brief The user-scoped Claude Code config file.
## @return Path to `.claude.json` under the resolved config directory.
## @version 1
## @req REQ-DDB-MCP-001
def global_config_path() -> Path:
    """`$CLAUDE_CONFIG_DIR/.claude.json`, else `~/.claude.json`. NOT under
    `~/.claude/` — the state directory and the config file are siblings in the
    default layout, which is the detail an assumption would get wrong.

    @brief Resolve the user-scope MCP config path.
    @return Path to the user-scope config file.
    @version 1
    """
    override = os.environ.get(CLAUDE_CONFIG_DIR_ENV)
    base = Path(override).expanduser() if override else Path.home()
    return base / CLAUDE_USER_CONFIG_NAME


## @brief The two paths that evidence a Claude Code install for this user.
## @return (user config file, state directory) — either existing is sufficient.
## @version 1
## @req REQ-DDB-MCP-001
def global_config_evidence() -> tuple[Path, Path]:
    """Global scope writes into the user's home directory, so it demands evidence
    that the client actually lives there before creating a file. Either artefact
    is enough: the config exists (Claude Code has run) or the state directory
    exists (it is installed and has at least started).

    Returned as a pair rather than a bool so a refusal can NAME what was looked
    for — writing a config to an invented path is the failure this guards.

    @brief Report the paths that would evidence a user-level Claude Code config.
    @return (config file path, state directory path).
    @version 1
    """
    return global_config_path(), claude_state_dir()


## @brief Whether a user-level Claude Code config can be written with confidence.
## @return True when the location is declared or evidenced on disk.
## @version 2
## @req REQ-DDB-MCP-001
def global_config_available() -> bool:
    """An explicitly set `CLAUDE_CONFIG_DIR` IS the evidence and short-circuits
    the disk check: the user has DECLARED where their config lives, and refusing
    to honour a declaration in favour of a built-in guess is exactly the
    hardcoded-only assumption this project forbids.

    Otherwise the default location has to prove itself, because global scope
    writes into a home directory: either the config file is already there, or
    Claude Code's state directory is.

    @brief Whether the user-scope config location is declared or evidenced.
    @return True when the location is declared or evidenced.
    @version 2
    """
    if os.environ.get(CLAUDE_CONFIG_DIR_ENV):
        return True
    config, state = global_config_evidence()
    return config.is_file() or state.is_dir()


## @brief The config file a given scope writes to.
## @param scope Registration scope (`repo` or `global`).
## @param repo_root Repo being registered, used by repo scope only.
## @return Path to the config file for that scope.
## @version 1
## @req REQ-DDB-MCP-001
def config_path(scope: str, repo_root: Path) -> Path:
    """@brief Resolve the config file for a registration scope.

    @return Path to `<repo>/.mcp.json` or the user-scope `.claude.json`.
    @version 1
    """
    if scope == INIT_SCOPE_REPO:
        return repo_root / REPO_CONFIG_NAME
    return global_config_path()


## @brief Locate the MCP server console script.
## @param which PATH lookup (injected for testing; defaults to shutil.which).
## @param bindir Directory to check beside the interpreter (defaults to sys.executable's).
## @return (path to the script or None, whether it came from PATH).
## @version 1
## @dg_internal
def _locate_script(which: Any, bindir: Path) -> tuple[Path | None, bool]:
    """PATH first, because that is what a `pip install clew` user has.
    The interpreter's own `bin/` second, which is the developer-checkout case:
    running `.venv/bin/clew init` without activating the venv means the
    script is real and usable but invisible to `which`.

    @brief Find the server console script.
    @return (script path or None, found-on-PATH flag).
    @version 1
    """
    found = which(CONSOLE_SCRIPT)
    if found:
        return Path(found), True
    candidate = bindir / CONSOLE_SCRIPT
    return (candidate, False) if candidate.is_file() else (None, False)


## @brief Express a path relative to a repo root, when it is inside it.
## @param path Absolute path to express.
## @param repo_root Repo root to express it against.
## @return POSIX relative path, or None when `path` is outside the repo.
## @version 1
## @dg_internal
def _repo_relative(path: Path, repo_root: Path) -> str | None:
    """@brief Make a path repo-relative, or report that it is not inside.

    @return Relative POSIX path or None.
    @version 1
    """
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


## @brief Choose between the bare console-script name and an absolute path.
## @param path The located script.
## @param on_path Whether it was found via PATH.
## @return The resolution to write.
## @version 1
## @dg_internal
def _path_or_name(path: Path, on_path: bool) -> CommandResolution:
    """@brief Prefer the PATH-resolvable name; fall back to an absolute path.

    @return CommandResolution for a script outside the target repo.
    @version 1
    """
    if on_path:
        return CommandResolution(CONSOLE_SCRIPT, f"console script on PATH ({path})", True)
    return CommandResolution(
        str(path),
        f"absolute path to {path} — not on PATH, so the bare name would not launch",
        False,
    )


## @brief Decide the `command` string to record for this machine.
## @param repo_root Repo being registered.
## @param scope Registration scope (`repo` or `global`).
## @param which PATH lookup (injected for testing).
## @param bindir Interpreter bin directory (injected for testing).
## @return The resolution, whose `command` is None when nothing was found.
## @version 3
## @req REQ-DDB-MCP-001
def resolve_server_command(
    repo_root: Path,
    scope: str,
    *,
    which: Any = None,
    bindir: Path | None = None,
) -> CommandResolution:
    """THE DELIBERATE DECISION this module exists to make.

    For a `pip install clew` user the right answer is the bare console
    script `clew-mcp`: that is the interface the package publishes, it
    survives the checkout moving, and it is what any other installed MCP server
    looks like in a config. An absolute interpreter path plus `-m` is not an
    interface — the same reasoning that put `[project.scripts]` in pyproject.

    But a bare name that the launching shell cannot resolve produces a server
    that silently never starts, which is strictly worse than a machine-specific
    path. So the order is: PATH name → repo-relative path (when the script lives
    inside the repo being registered, the developer-checkout case) → absolute path, flagged
    non-portable → nothing found, and the caller refuses to write a config naming
    a command that does not exist.

    Repo-relative is offered for repo scope ONLY. A user-scoped config loads from
    every directory the user works in, so a relative command there would resolve
    against whatever happened to be the cwd.

    @brief Resolve the MCP server command to record.
    @return CommandResolution (`command` None when the script is absent).
    @version 2
    """
    lookup = which if which is not None else shutil.which
    bins = bindir if bindir is not None else Path(sys.executable).parent
    path, on_path = _locate_script(lookup, bins)
    if path is None:
        return CommandResolution(
            None,
            f"{CONSOLE_SCRIPT} not found on PATH or in {bins} — the package is "
            "installed but its console script is missing, which usually means a "
            "broken install: pip install --force-reinstall clew",
            False,
        )
    relative = _repo_relative(path, repo_root) if scope == INIT_SCOPE_REPO else None
    if relative is not None:
        return CommandResolution(relative, f"repo-relative script ({path})", True)
    return _path_or_name(path, on_path)


## @brief The server entry this tool writes.
## @param command Command string to launch the server with.
## @param repo Explicit target repo, for a caller whose cwd is not the repo.
## @return The `mcpServers` entry value.
## @version 3
## @req REQ-DDB-MCP-001
def server_entry(command: str, repo: str | None = None) -> dict[str, Any]:
    """NEITHER SCOPE PASSES `--repo` ANY MORE, so there is no longer a `scope`
    parameter to branch on (gh#22).

    Repo scope used to write `--repo .`, which PINNED the server: it registered its
    tools at startup and refused to retarget. Both halves of that turned out to be
    wrong. The refusal meant a session could not index a second repository at all
    (gh#19), and the pin was not even reliable at the job it was for — a stale one
    invalidated a 36-cell benchmark run, where 15 of 18 cells said in prose that they
    were looking at the wrong repository and all 36 were recorded valid. A pin makes a
    server MORE confidently wrong, not less.

    The server now derives its target — `$CLAUDE_PROJECT_DIR` at startup, else the
    client's `roots/list` on the first call — so a project-scoped config that names no
    repo resolves to the project it is committed in, which is what `--repo .` was
    trying to express and could not, because `.` resolves against the LAUNCHING
    process's cwd rather than the config's directory.

    `repo` remains, for a caller that writes a config it will not run from. The
    benchmark harness is the case: its cells run in a scratch working directory, so
    nothing in the environment names the target. It had been hand-rolling this entry as
    a literal dict, and that copy is what went stale — one definition, so the two
    cannot drift again.

    No `env` key is emitted. The entry is compared for equality against whatever
    is already in the file, so every field written is a field a re-run must
    reproduce exactly; an empty `env: {}` would be one more thing to disagree
    about for no behavioural gain.

    @brief Build this server's MCP config entry.
    @return The entry mapping.
    @version 3
    """
    return {
        "type": "stdio",
        "command": command,
        "args": [] if repo is None else ["--repo", repo],
    }


## @brief Read a config file into a document plus its original text.
## @param path Config file to read.
## @return (parsed document, raw text; both empty when the file is absent).
## @version 1
## @req REQ-DDB-MCP-001
def load_document(path: Path) -> tuple[dict[str, Any], str]:
    """Absent is not an error — it is the `create` case. Present-but-unparseable
    IS an error, and it is raised before anything is written so the user's file
    survives intact.

    @brief Load a config document, refusing a malformed one.
    @return (document, raw text).
    @version 1
    """
    if not path.exists():
        return {}, ""
    raw = path.read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(f"{path} is not valid JSON ({exc}) — refusing to touch it") from exc
    if not isinstance(document, dict):
        raise ConfigError(f"{path} does not hold a JSON object — refusing to touch it")
    return document, raw


## @brief Indentation to re-serialise with, taken from the file itself.
## @param raw Original file text ("" for a new file).
## @return An indent string, or the default width for a new/unindented file.
## @version 1
## @dg_internal
def _indent_of(raw: str) -> int | str:
    """Reuses whatever the file already used, so registering a server does not
    reformat a config the user maintains by hand (and does not produce a diff
    that is 90% whitespace).

    @brief Detect a config file's existing indentation.
    @return The detected indent string, or DEFAULT_INDENT.
    @version 1
    """
    match = re.search(r'^([ \t]+)"', raw, re.MULTILINE)
    return match.group(1) if match else DEFAULT_INDENT


## @brief Unified diff between the existing entry and the proposed one.
## @param existing The entry already in the file, or None.
## @param entry The entry this tool would write.
## @return A unified diff, or "" when there is nothing to show.
## @version 1
## @dg_internal
def _entry_diff(existing: dict[str, Any] | None, entry: dict[str, Any]) -> str:
    """Rendered over pretty-printed JSON rather than the raw file text: the point
    is to show the user WHAT would change about this one server, not where the
    bytes moved.

    @brief Diff an existing server entry against the proposed one.
    @return Unified diff text ("" when the entry is new or identical).
    @version 1
    """
    if existing is None or existing == entry:
        return ""
    before = json.dumps(existing, indent=2, sort_keys=True).splitlines()
    after = json.dumps(entry, indent=2, sort_keys=True).splitlines()
    return "\n".join(
        difflib.unified_diff(before, after, fromfile="current", tofile="proposed", lineterm="")
    )


## @brief Classify what writing this entry would do.
## @param file_existed Whether the config file was already present.
## @param existing The entry already recorded for this server, or None.
## @param entry The entry this tool would write.
## @return One of the `init_action` vocabulary's values.
## @version 1
## @dg_internal
def _classify(file_existed: bool, existing: dict[str, Any] | None, entry: dict[str, Any]) -> str:
    """@brief Decide the merge action for a target file.

    @return `create`, `add`, `unchanged` or `update`.
    @version 1
    """
    if existing is None:
        return INIT_ACTION_CREATE if not file_existed else INIT_ACTION_ADD
    return INIT_ACTION_UNCHANGED if existing == entry else INIT_ACTION_UPDATE


## @brief Plan the merge of this server's entry into a config file.
## @param path Config file to merge into.
## @param entry The entry to record.
## @param name Key to record it under (defaults to this server's name).
## @return The computed plan; nothing is written.
## @version 1
## @req REQ-DDB-MCP-001
def plan_merge(path: Path, entry: dict[str, Any], name: str = MCP_ENTRY_NAME) -> MergePlan:
    """Read → replace exactly one key → re-serialise. Every other key in the
    document, at every level, is carried through untouched and in its original
    order, because `json.loads`/`json.dumps` both preserve insertion order. That
    matters most for the user-scope file, which holds the entire Claude Code
    user state and would be catastrophic to rewrite from a template.

    @brief Compute the merge without performing it.
    @return The MergePlan.
    @version 1
    """
    document, raw = load_document(path)
    servers = document.get(SERVERS_KEY, {})
    if not isinstance(servers, dict):
        raise ConfigError(f"{path}: '{SERVERS_KEY}' is not an object — refusing to touch it")
    existing = servers.get(name)
    if existing is not None and not isinstance(existing, dict):
        raise ConfigError(f"{path}: '{SERVERS_KEY}.{name}' is not an object — refusing to touch it")
    action = _classify(path.exists(), existing, entry)
    merged = {**document, SERVERS_KEY: {**servers, name: entry}}
    # Keep the file's own trailing-newline convention; only an existing file that
    # lacked one stays without.
    newline = "" if raw and not raw.endswith("\n") else "\n"
    text = json.dumps(merged, indent=_indent_of(raw)) + newline
    return MergePlan(
        path=path,
        action=action,
        entry=entry,
        existing=existing,
        document=merged,
        text=text,
        diff=_entry_diff(existing, entry),
    )


## @brief Write a planned edit to disk atomically, keeping a backup.
## @param plan The plan to apply (any `WritePlan`, not only a `MergePlan`).
## @return The path written.
## @version 3
## @req REQ-DDB-MCP-001
## @req REQ-DDB-CLI-002
def apply_plan(plan: WritePlan) -> Path:
    """Written to a sibling temp file and `os.replace`d onto the target, the same
    swap the build pipeline uses. A config file is read by a long-running client;
    a partial write would leave it holding a truncated document, and on the
    user-scope file that is the user's whole Claude Code state.

    ATOMICITY IS NOT ENOUGH, WHICH IS WHY THERE IS A BACKUP. `os.replace` only
    guarantees the target is never half-written; it guarantees nothing about the
    CONTENT being right. The user-scope target is `~/.claude.json` — on this
    machine ~144KB of hand-accumulated Claude Code state that no tool can
    regenerate — and it reaches here having survived a full
    `json.loads` -> mutate -> `json.dumps` round-trip. A defect anywhere in that
    round-trip destroys the file perfectly atomically. This is the single most
    consequential write in the whole tool, so it keeps a copy.

    ORDERING IS DELIBERATE: the backup is written FIRST and a failure to write it
    aborts before the target is touched at all. Backing up after the swap, or
    treating a failed backup as a warning, would leave exactly the case the backup
    exists for uncovered.

    Nothing to back up on a fresh file — no target, no loss — and in that case a
    stray `.bak` would be misleading rather than helpful.

    TAKES A `WritePlan`, not a `MergePlan`. The second `init` target is a delimited
    block in the user's CLAUDE.md, which is a hand-curated prose file rather than a
    JSON document — every sentence above applies to it verbatim, so it gets this
    writer rather than a parallel one that could drift on the backup ordering.

    @brief Apply a write plan atomically, preserving a backup of any existing file.
    @return The path that was written.
    @version 3
    """
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    if plan.path.is_file():
        backup = plan.path.with_name(plan.path.name + ".clew.bak")
        backup.write_bytes(plan.path.read_bytes())
        logger.info("init: previous %s saved as %s", plan.path.name, backup.name)
    tmp = plan.path.with_name(plan.path.name + ".clew.tmp")
    tmp.write_text(plan.text, encoding="utf-8")
    os.replace(tmp, plan.path)
    return plan.path
