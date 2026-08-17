# SPDX-License-Identifier: MIT
"""`clew init` — register this MCP server, and check it will actually run.

The shipped adoption path is `pip install clew-trace` → `clew init` →
the agent's first MCP call drives the normal build/query flow. This command is
the middle step, and it is a DOCTOR rather than a writer: registering a server
that cannot start produces a client that shows "failed to connect" with no clue
why, so the same run also reports whether the console script resolves, whether
the MCP SDK is importable, whether `doxygen` exists, whether the repo is
indexable at all, and whether it declares its own conventions.

**Three tiers of outcome, and only two of them touch the exit code.**

* *Blocking failure* — nothing is written and the exit code is 1: the server
  command cannot be resolved (there would be nothing to put in `command`), the
  user-scope config location cannot be evidenced, the target file is malformed,
  or an existing entry differs and `--force` was not given.
* *Non-blocking failure* — the config IS written and the exit code is 1:
  `doxygen` or the MCP SDK is missing. The fix is a package install, not a config
  edit, so withholding the registration would just make the user do this twice.
* *Warning* — exit code 0: no Doxyfile and no derivable scope, or no
  `.clew.yaml`. Both are states a repo is legitimately in on day one, and both
  are fixable later without re-running `init`.

**Not exposed as an MCP tool, deliberately.** A tool is only reachable through an
already-registered server, so an `init` tool could never help the state `init`
exists to fix — it would be callable exactly when it was no longer needed. That
is the opposite of `propose_declaration`, which is tier-0 precisely because the
state IT fixes (an undeclared repo) is reachable through a server that is already
running. The residual case — "register yourself globally from inside a
repo-scoped session" — is a write into the user's home directory driven by a
model, which is the class of action that should stay a deliberate human command.

**ONE TARGET, deliberately: the MCP client config and nothing else.** This command used to
also offer a delimited guidance block for the scope's CLAUDE.md, telling an agent the index
existed and when to reach for it. That is removed. Installing a tool must not edit a file the
user curates: a CLAUDE.md is prose someone wrote by hand, how they instruct their own agent is
theirs to maintain, and the block additionally carried a performance claim that could not be
substantiated from anything shipped. A config's `mcpServers` is a machine-managed mapping and is
the only thing here with a machine's business writing it.

Whatever guidance is worth giving a model belongs in the server's own served instructions, which
are re-read on every connection and cannot go stale in someone else's file.

`--yes` went with it: it existed only to accept that write non-interactively, and a flag whose
sole target is gone is a flag that will be re-purposed into meaning something a caller did not
ask for.

@brief CLI entry point for MCP server registration + environment diagnosis.
@version 3
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .declaration import DECLARATION_NAME
from .mcp_config import (
    CLAUDE_CONFIG_DIR_ENV,
    MCP_ENTRY_NAME,
    REPO_CONFIG_NAME,
    ConfigError,
    MergePlan,
    apply_plan,
    config_path,
    global_config_available,
    global_config_evidence,
    plan_merge,
    resolve_server_command,
    server_entry,
)
from .vocabulary import (
    CHECK_FAIL,
    CHECK_OK,
    CHECK_STATUS,
    CHECK_WARN,
    INIT_ACTION_UNCHANGED,
    INIT_ACTION_UPDATE,
    INIT_SCOPE,
    INIT_SCOPE_GLOBAL,
    INIT_SCOPE_REPO,
)

## The subcommand word `clew.cli` dispatches on.
COMMAND = "init"

## Check names, spelled once so the blocking set below cannot drift from them.
CHECK_CLIENT_CONFIG = "client-config"
CHECK_SERVER_COMMAND = "server-command"
CHECK_MCP_SDK = "mcp-sdk"
CHECK_DOXYGEN = "doxygen"
CHECK_INDEXABLE = "indexable"
CHECK_DECLARATION = "declaration"

## The failures that make the WRITE itself wrong, as opposed to failures that
## make the environment incomplete. Only these stop the config being written —
## see the module docstring's three tiers.
BLOCKING_CHECKS = frozenset({CHECK_CLIENT_CONFIG, CHECK_SERVER_COMMAND})

_EPILOG = (
    f"Repo scope writes ./{REPO_CONFIG_NAME} (project-scoped, committed with the "
    "repo, and pins the server to it). Global scope writes the user-level Claude "
    "Code config and leaves the server dynamic. Re-running is safe: an identical "
    "entry is a no-op, and a DIFFERENT existing entry is refused with a diff "
    f"unless --force is given. Set {CLAUDE_CONFIG_DIR_ENV} to relocate the "
    "user-level config. The MCP client config is the ONLY file this command writes; it "
    "does not touch your CLAUDE.md."
)


## @brief One diagnostic result: what was checked, the verdict, and the evidence.
## @version 1
@dataclass(frozen=True)
class Check:
    """`status` is drawn from the `check_status` vocabulary, and `detail` always
    carries the concrete thing that was observed (a path, a version, what was
    looked for) rather than a restatement of the name — a doctor that reports
    "fail" without naming the file it wanted is not actionable.

    @brief One environment/repo diagnostic result.
    @version 1
    """

    name: str
    status: str
    detail: str


## @brief Build the `clew init` argument parser.
## @return The configured parser.
## @version 3
## @req REQ-DDB-CLI-001
## @req REQ-DDB-CLI-002
def build_parser() -> argparse.ArgumentParser:
    """Four flags, and `--force` is deliberately never implied by another. A blanket
    "assume yes" that also covered `--force` would let one flag replace a hand-tuned
    server entry, which is the outcome `--force` exists to require a separate decision
    for.

    @brief Construct the init command's CLI parser.
    @return The configured ArgumentParser.
    @version 3
    """
    parser = argparse.ArgumentParser(
        prog="clew init",
        description="Register the clew MCP server and check it can run.",
        epilog=_EPILOG,
    )
    parser.add_argument(
        "--scope",
        choices=INIT_SCOPE.values,
        default=INIT_SCOPE_REPO,
        help=(
            f"Where to register. '{INIT_SCOPE_REPO}' (default) writes "
            f"<repo>/{REPO_CONFIG_NAME}; '{INIT_SCOPE_GLOBAL}' writes the "
            "user-level Claude Code config."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo to register and diagnose (default: the current directory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Replace an existing entry for this server that differs from the one "
            "that would be written. Never implied: the config is the user's file."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact JSON that would be written, and touch nothing.",
    )
    return parser


## @brief Whether the user-scope config location can be established on this machine.
## @param scope Registration scope being used.
## @return The client-config check.
## @version 1
## @dg_internal
def _check_client_config(scope: str) -> Check:
    """Repo scope is unconditionally fine — the file lives in the repo the user
    named. Global scope must first EVIDENCE that Claude Code keeps its config
    where we think it does; with no evidence it refuses and names both paths it
    looked at, because writing a config to an invented path is worse than not
    writing one.

    @brief Verify the target config location for this scope.
    @return The client-config check.
    @version 1
    """
    if scope == INIT_SCOPE_REPO:
        return Check(CHECK_CLIENT_CONFIG, CHECK_OK, f"repo scope — <repo>/{REPO_CONFIG_NAME}")
    config, state = global_config_evidence()
    if global_config_available():
        return Check(CHECK_CLIENT_CONFIG, CHECK_OK, f"user-scope config {config}")
    return Check(
        CHECK_CLIENT_CONFIG,
        CHECK_FAIL,
        f"no user-level Claude Code config found — looked for {config} and {state}/. "
        f"Set {CLAUDE_CONFIG_DIR_ENV} if it lives elsewhere, or use --scope "
        f"{INIT_SCOPE_REPO}.",
    )


## @brief Whether the MCP server console script can be located.
## @param repo_root Repo being registered.
## @param scope Registration scope being used.
## @return The server-command check.
## @version 1
## @dg_internal
def _check_server_command(repo_root: Path, scope: str) -> Check:
    """@brief Verify the server launch command resolves on this machine.

    @return The server-command check.
    @version 1
    """
    resolution = resolve_server_command(repo_root, scope)
    if resolution.command is None:
        return Check(CHECK_SERVER_COMMAND, CHECK_FAIL, resolution.origin)
    status = CHECK_OK if resolution.portable else CHECK_WARN
    return Check(CHECK_SERVER_COMMAND, status, f"{resolution.command} — {resolution.origin}")


## @brief Whether the SDK module the server imports can actually be imported.
## @return The mcp-sdk check.
## @version 4
## @dg_internal
def _check_mcp_sdk() -> Check:
    """The SDK is a REQUIRED dependency (it was an optional extra until
    2026-07-28), so a missing one now means a broken install rather than a missing
    opt-in — and the message says so, because "run this pip command" would be
    wrong advice for a dependency that pip should already have placed.

    Still checked rather than assumed, and the probe targets the module the server
    actually imports rather than the top-level package: `import mcp` succeeds under
    every generation, so probing it would report OK for the one failure worth
    catching.

    THE PROBE PERFORMS THE SERVER'S OWN IMPORT rather than checking a name that
    stands in for it. `_sdk` is the one module that imports the SDK, so if `_sdk`
    imports, the server can start — that is ground truth, not a proxy for it, and
    it is why this is an import inside the function rather than at module scope:
    importing the SDK eagerly would crash the very command whose job is to report
    that the SDK is broken.

    The distinction is not pedantic. This check probed `find_spec` on a literal
    `mcp.server.fastmcp` and called it "the server's own import line"; that stopped
    being true when `_sdk` took over the import and the version cap moved, so the
    doctor hard-failed every environment holding the only version a fresh install
    resolves — while the suite stayed green, because the check had a test for its
    fail path and none for its OK path. Both now exist.

    @brief Verify the SDK module the server imports can actually be imported.
    @return The mcp-sdk check.
    @version 4
    """
    try:
        from .mcp_server._sdk import MCP_SERVER_MODULE
    except Exception as exc:
        return Check(
            CHECK_MCP_SDK,
            CHECK_FAIL,
            f"the server's SDK import failed ({type(exc).__name__}: {exc}), so the "
            "server cannot start. The SDK is a required dependency, so this means a "
            "broken or partial install, or an `mcp` outside the declared `>=2,<3` "
            "window. Reinstall: pip install --force-reinstall clew",
        )
    return Check(CHECK_MCP_SDK, CHECK_OK, f"{MCP_SERVER_MODULE} is importable")


## @brief Whether the external doxygen binary is available.
## @return The doxygen check.
## @version 1
## @dg_internal
def _check_doxygen() -> Check:
    """doxygen is a SUBPROCESS dependency, invisible to pip, so nothing else in
    the install path notices it is missing — the first `build_or_refresh` does.

    @brief Verify the doxygen binary is on PATH.
    @return The doxygen check.
    @version 1
    """
    found = shutil.which("doxygen")
    if found:
        return Check(CHECK_DOXYGEN, CHECK_OK, found)
    return Check(
        CHECK_DOXYGEN,
        CHECK_FAIL,
        "doxygen is not on PATH — no database can be built until it is (e.g. apt install doxygen)",
    )


## @brief Whether this repo can be indexed at all.
## @param repo_root Repo being registered.
## @return The indexable check.
## @version 4
## @dg_internal
def _check_indexable(repo_root: Path) -> Check:
    """Two routes exist and the doctor reports WHICH: the repo ships a Doxyfile,
    or it declares a doxygen-guard scope a minimal Doxyfile can be synthesized
    from. Neither is a warning rather than a failure — the registration is still
    correct, and adding either later needs no re-run of `init`.

    Imported lazily: both modules pull the pipeline's heavier dependencies, and
    `init` must stay runnable on a bare install.

    @brief Verify the repo has, or can derive, a doxygen scope.
    @return The indexable check.
    @version 4
    """
    from .doxygen import discover_doxyfile
    from .scope import derive_scope

    doxyfile = discover_doxyfile(repo_root)
    if doxyfile is not None:
        return Check(CHECK_INDEXABLE, CHECK_OK, f"Doxyfile: {doxyfile}")
    ## ANY SCOPE WITH ROOTS IS INDEXABLE, and that is the whole correction. This asked
    ## `is_derived()`, which is true ONLY for SOURCE_DECLARED — so a repo that declares nothing
    ## fell to a warn saying "index(action='refresh') will fail until this repo has one".
    ##
    ## MEASURED, on the exact configuration a new user arrives with: a git repo holding one `.c`
    ## file, no Doxyfile, no doxygen-guard config, no declaration. It BUILDS — doxygen is
    ## synthesized from the whole-repo scope and the function is indexed. The warn was wrong every
    ## time it fired, on the FIRST SCREEN `init` shows, telling a stranger the tool does not
    ## support their repository.
    ##
    ## The premise died with gh#333, which made whole-repo the DEFAULT tier rather than a last
    ## resort; `is_derived()` was not part of that change and kept meaning "declared". THE SUITE
    ## PINNED THE OLD ANSWER — `test_unindexable_repo_warns_but_still_registers` asserted the
    ## warn — so running the tests could not have found this. Running the product did.
    ##
    ## The warn is KEPT for a scope with no roots at all. `whole_repo_scope` always supplies one,
    ## so it is not currently reachable, and that is the point: a check should report what it
    ## measured rather than assert that a state is impossible.
    derived = derive_scope(repo_root)
    if derived.roots:
        route = "declared scope" if derived.is_derived() else "the whole repository"
        return Check(
            CHECK_INDEXABLE,
            CHECK_OK,
            f"no Doxyfile — one will be synthesized from {route} ({derived.reason})",
        )
    return Check(
        CHECK_INDEXABLE,
        CHECK_WARN,
        "no Doxyfile, and the derived scope named no roots to synthesize one from — "
        f"index(action='refresh') will fail until this repo has one ({derived.reason})",
    )


## @brief Whether the repo declares its own indexing conventions.
## @param repo_root Repo being registered.
## @return The declaration check.
## @version 2
## @dg_internal
def _check_declaration(repo_root: Path) -> Check:
    """Absent is the norm, not a defect — most repos run entirely on built-in
    defaults. It is still surfaced, because an empty causal layer on a repo whose
    accessors the defaults cannot see is the single most common "why is this
    database useless" report, and `clew propose` answers it from evidence.

    @brief Report whether the repo carries a `.clew.yaml`.
    @return The declaration check.
    @version 2
    """
    path = repo_root / DECLARATION_NAME
    if path.is_file():
        return Check(CHECK_DECLARATION, CHECK_OK, str(path))
    return Check(
        CHECK_DECLARATION,
        CHECK_WARN,
        f"no {DECLARATION_NAME} — built-in defaults apply. Run `clew propose` "
        "to see, from evidence, what this repo could declare.",
    )


## @brief Run every doctor check for a repo and scope.
## @param repo_root Repo being registered.
## @param scope Registration scope being used.
## @return The checks, in reporting order.
## @version 3
## @req REQ-DDB-CLI-001
## @req REQ-DDB-CLI-002
def diagnose(repo_root: Path, scope: str) -> list[Check]:
    """Ordered so the two blocking checks come first: when one of them fails,
    everything after it is context for a run that is not going to write anything.

    @brief Produce the full diagnostic report.
    @return List of checks in reporting order.
    @version 3
    """
    return [
        _check_client_config(scope),
        _check_server_command(repo_root, scope),
        _check_mcp_sdk(),
        _check_doxygen(),
        _check_indexable(repo_root),
        _check_declaration(repo_root),
    ]


## @brief Render one check as a single report line.
## @param check The check to render.
## @return The formatted line.
## @version 1
## @dg_internal
def _format_check(check: Check) -> str:
    """@brief Format a check for the report.

    @return One aligned `[status] name  detail` line.
    @version 1
    """
    return f"  [{check.status:<4}] {check.name:<15} {check.detail}"


## @brief The blocking failures among a set of checks.
## @param checks Checks to filter.
## @return Blocking failures, in order.
## @version 1
## @dg_internal
def _blocking(checks: list[Check]) -> list[Check]:
    """@brief Select the failures that must stop the write.

    @return Blocking failed checks.
    @version 1
    """
    return [c for c in checks if c.status == CHECK_FAIL and c.name in BLOCKING_CHECKS]


## @brief Print the refusal for a conflicting existing entry.
## @param plan The plan whose entry differs from what is already recorded.
## @version 1
## @dg_internal
def _print_conflict(plan: MergePlan) -> None:
    """Shows the diff and stops. Silently overwriting an entry the user tuned by
    hand — a different command, extra args, a pinned repo — is the failure mode
    this whole command is designed against, and it is invisible after the fact
    because the config still looks well-formed.

    @brief Report a conflicting entry and how to override.
    @version 1
    """
    print(f"\n  refusing to change the existing '{MCP_ENTRY_NAME}' entry in {plan.path}")
    print("  it differs from what would be written:\n")
    for line in plan.diff.splitlines():
        print(f"    {line}")
    print("\n  re-run with --force to replace it.")


## @brief Print what a dry run would change, scoped to this server's entry.
## @param plan The plan that would have been applied.
## @version 2
## @dg_internal
def _print_merge_preview(plan: MergePlan) -> None:
    """PRINTS THE ENTRY, NEVER `plan.text` — and that is a disclosure fix, not a
    formatting preference (gh#27). `plan.text` is the whole re-serialised document,
    and for `--scope global` the document is `~/.claude.json`: every project path the
    user has ever opened, plus their prompt history, ~150KB of it. `--dry-run` is
    precisely what someone runs before pasting output into a bug report and what an
    agent runs inside a transcript, so it was the one code path guaranteed to publish
    that file. It did so even when the action was `unchanged` and the run was a
    verified no-op.

    The rule is to show the REGION under review and nothing else. Everything outside
    `mcpServers.<name>` is carried through untouched by `plan_merge` — by
    construction, not by best effort — so the entry plus `plan.diff` IS the complete
    change. Nothing reviewable is lost, including on `create`, where the document
    `plan.text` would have printed holds this entry and nothing else anyway.

    `unchanged` gets one line and no body. Printing a payload under a no-op reads as a
    pending change and is simply untrue.

    @brief Show the entry a dry run would write, plus any entry-level diff.
    @version 2
    """
    head = f"\n  --dry-run ({plan.action}) — nothing written."
    if plan.action == INIT_ACTION_UNCHANGED:
        print(f"{head} {plan.path} already holds an identical '{MCP_ENTRY_NAME}' entry.")
        return
    print(f"{head} {plan.path} would {plan.action} the '{MCP_ENTRY_NAME}' entry:\n")
    for line in json.dumps(plan.entry, indent=2, sort_keys=True).splitlines():
        print(f"    {line}")
    if plan.diff:
        print("\n  replacing the entry recorded there now:\n")
        for line in plan.diff.splitlines():
            print(f"    {line}")


## @brief Emit a plan: print it under --dry-run, otherwise write it.
## @param plan The plan to emit.
## @param dry_run Whether to print instead of writing.
## @version 2
## @dg_internal
def _emit(plan: MergePlan, dry_run: bool) -> None:
    """The dry-run preview is delegated so this function stays a two-way branch, and
    so the entry-scoped rule lives in exactly one place.

    @brief Print or apply a merge plan.
    @version 2
    """
    if dry_run:
        _print_merge_preview(plan)
        return
    if plan.action == INIT_ACTION_UNCHANGED:
        print(f"\n  {plan.path}: '{MCP_ENTRY_NAME}' already registered and identical — no change.")
        return
    apply_plan(plan)
    print(f"\n  {plan.action}: wrote '{MCP_ENTRY_NAME}' to {plan.path}")


## @brief Apply a plan subject to the conflict rule, and pick the exit code.
## @param plan The computed merge plan.
## @param repo_root Repo being registered.
## @param args Parsed CLI arguments (uses --force, --yes and --dry-run).
## @param checks The diagnostic checks, which decide the exit code.
## @return Process exit code.
## @version 3
## @dg_internal
def _execute(
    plan: MergePlan, repo_root: Path, args: argparse.Namespace, checks: list[Check]
) -> int:
    """ONE WRITE, then the next-steps line. A differing existing entry is refused here rather
    than deeper in, so the refusal is reported before anything has been emitted.

    @brief Perform the write (or refuse) and return the exit code.
    @return 0 when nothing failed, else 1.
    @version 3
    """
    if plan.action == INIT_ACTION_UPDATE and not args.force:
        _print_conflict(plan)
        return 1
    _emit(plan, args.dry_run)
    _print_next_steps(plan, args.dry_run)
    return 1 if any(c.status == CHECK_FAIL for c in checks) else 0


## @brief Tell the user what happens next.
## @param plan The plan that was emitted.
## @param dry_run Whether nothing was actually written.
## @version 1
## @dg_internal
def _print_next_steps(plan: MergePlan, dry_run: bool) -> None:
    """@brief Print the follow-on step after a successful registration.

    @version 1
    """
    if dry_run:
        return
    print(
        f"  restart your MCP client so it loads {plan.path}; the agent's first "
        "call to this server will offer to build the index."
    )


## @brief Compute and perform the registration, given the diagnostics.
## @param checks The diagnostic checks already produced.
## @param repo_root Repo being registered.
## @param args Parsed CLI arguments.
## @return Process exit code.
## @version 3
## @dg_internal
def _register(checks: list[Check], repo_root: Path, args: argparse.Namespace) -> int:
    """@brief Plan and apply the config write, refusing on a blocking failure.

    @return Process exit code.
    @version 3
    """
    blocked = _blocking(checks)
    if blocked:
        print("\n  not registering — " + "; ".join(c.detail for c in blocked))
        return 1
    resolution = resolve_server_command(repo_root, args.scope)
    entry = server_entry(str(resolution.command))
    try:
        plan = plan_merge(config_path(args.scope, repo_root), entry)
    except ConfigError as exc:
        print(f"\n  not registering — {exc}")
        return 1
    return _execute(plan, repo_root, args, checks)


## @brief Run `clew init`.
## @param argv Arguments after the subcommand word (defaults to sys.argv[1:]).
## @return Process exit code: 0 when nothing failed, 1 otherwise.
## @version 1
## @req REQ-DDB-CLI-001
def init_main(argv: list[str] | None = None) -> int:
    """Diagnose first, always, and print the whole report before doing anything
    — including on the runs that end in a refusal. The report IS the product on
    those runs: a user whose `doxygen` is missing needs to see that on the same
    run that told them the entry conflicts, not one re-run later.

    @brief Diagnose the environment and register the MCP server.
    @return Process exit code.
    @version 1
    """
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    checks = diagnose(repo_root, args.scope)
    print(f"\nclew init — {repo_root} (scope: {args.scope})\n")
    print(f"  {CHECK_STATUS.means}\n")
    for check in checks:
        print(_format_check(check))
    return _register(checks, repo_root, args)
