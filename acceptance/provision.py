# SPDX-License-Identifier: MIT
"""Put a target on disk at its pinned commit, index it, and write the index arm's MCP config.

THE ORDER IS THE POINT, and every step refuses rather than degrades:

  1. FETCH THE PINNED COMMIT DIRECTLY, never a branch tip. Fetching a branch and checking out
     transfers a history, materialises a tip that may differ from the pin, and fails silently
     onto whatever `main` happens to be when the commit is gone. `fetch --depth 1 <sha>` fails
     loudly instead.
  2. VERIFY HEAD against the rubric. A rubric verified against one tree and run against another
     grades code the answer never saw, and every line number in it is then a claim about a
     different file.
  3. BUILD IN-PROCESS, never through a running MCP server. A server older than the working tree
     runs old pipeline logic and re-stamps the index with it — which can drop whole layers and
     then report health.
  4. ASSERT THE DECLARATION REACHED THE BUILD, by section name. A committed declaration that
     never arrives makes the measured index differ from the intended one, and every downstream
     number then describes a build nobody chose. This is the check whose absence let a whole
     phase of work go unmeasured.
  5. WRITE THE MCP CONFIG LAST, so it can only exist once the index behind it does.

WHY THE INDEX ARM CANNOT SHARE THE BASELINE ARM'S SETUP: it needs a config pointing at the built
database, and `execute.run_cell` REFUSES to run the index arm without one. An index arm that
quietly ran without its index would produce plausible answers and a publishable-looking number
with nothing downstream able to tell.

Usage:
    .venv/bin/python -m acceptance.provision --rubric <path> --root <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .grader.rubric import RubricError, Rubric, load
from .runner import check_declaration_applied, check_revision

GIT_TIMEOUT = 900
BUILD_TIMEOUT = 3600


class ProvisionError(RuntimeError):
    """@brief A target that cannot be trusted to answer questions about itself.
    @version 1
    """


## @brief Everything a run needs to point both arms at one target.
## @version 1
@dataclass(frozen=True)
class Provisioned:
    """@brief A checked-out tree, its index, and the index arm's config.
    @version 1
    """

    repo: Path
    db: Path
    mcp_config: Path
    build_version: str


## @brief Run git, raising with git's own stderr on any failure.
## @param cwd Working directory.
## @param args Git arguments.
## @return stdout.
## @version 1
def _git(cwd: Path, *args: str) -> str:
    """The message has to carry git's own stderr — telling a network refusal apart from a
    deleted commit without re-running anything depends on it.

    @brief Invoke git.
    @return stdout.
    @version 1
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError(f"git {' '.join(args)} could not run: {exc}") from exc
    if done.returncode != 0:
        raise ProvisionError(
            f"git {' '.join(args)} failed (rc={done.returncode}) in {cwd}: {done.stderr.strip()}"
        )
    return done.stdout.strip()


## @brief Fetch a target's pinned commit into a working tree.
## @param rubric The rubric naming the target and commit.
## @param repo Directory to hold the checkout.
## @return None.
## @version 1
def fetch_pinned(rubric: Rubric, repo: Path) -> None:
    """Idempotent: an existing tree already at the pin is left alone, so re-provisioning costs
    nothing and a run can resume.

    Submodules are NOT initialised. A target that declares one gets a second remote that can be
    unreachable, and the pinned commit's own tree is what the rubric was verified against.

    @brief Put the pinned commit on disk.
    @return None.
    @version 1
    """
    if (repo / ".git").exists():
        head = _git(repo, "rev-parse", "HEAD")
        if head == rubric.commit:
            return
    else:
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "--quiet", ".")
        _git(repo, "remote", "add", "origin", f"https://github.com/{rubric.target}.git")
    _git(repo, "fetch", "--quiet", "--depth", "1", "origin", rubric.commit)
    _git(repo, "checkout", "--quiet", "--force", rubric.commit)


## @brief Read a built index's build_meta rows.
## @param db Path to the database.
## @return Mapping of key to value.
## @version 1
def read_build_meta(db: Path) -> dict:
    """Returns the nested `options` shape `check_declaration_applied` expects, built from the
    flat `key`/`value` rows the pipeline stamps.

    @brief Build metadata as a mapping.
    @return build_meta.
    @version 1
    """
    if not db.is_file():
        raise ProvisionError(f"{db}: no index was written")
    conn = sqlite3.connect(str(db))
    try:
        rows = dict(conn.execute("SELECT key, value FROM build_meta").fetchall())
    except sqlite3.Error as exc:
        raise ProvisionError(f"{db}: cannot read build_meta: {exc}") from exc
    finally:
        conn.close()
    return rows


## @brief Build the index for a provisioned target.
## @param rubric The rubric, for its declaration.
## @param repo The checked-out tree.
## @param state_home CLEW_STATE_HOME for the build, shared with the server.
## @param declare_file Path to write the rubric's declaration to, or None to skip.
## @return None.
## @version 1
def build_index(rubric: Rubric, repo: Path, state_home: Path, declare_file: Path | None) -> None:
    """IN-PROCESS, never through a running server. A server process older than the working tree
    runs old pipeline logic and re-stamps the index with it, which can drop whole layers and
    then report health.

    @brief Build the target's index.
    @return None.
    @version 1
    """
    ## NO --output. The MCP server DERIVES its database location from --repo and takes no
    ## explicit path, so writing the index anywhere else guarantees the server looks somewhere
    ## the build never wrote. Instead both sides are pointed at the same state root through
    ## CLEW_STATE_HOME, and they agree by construction rather than by two paths being kept in
    ## step by hand.
    ##
    ## IT ALSO ISOLATES THE RUN. Without it a target that is a LOCAL checkout shares a state
    ## root with the operator's own indexes, so a run could silently read an index built weeks
    ## ago for ordinary work rather than the one it just built under its declaration.
    argv = [
        sys.executable,
        "-m",
        "clew",
        "--repo-root",
        str(repo),
        "--rebuild",
    ]
    if declare_file is not None:
        argv += ["--declare", str(declare_file)]
    ## THE ENV IS THE WHOLE MECHANISM, so it is built explicitly rather than inherited.
    ## Inherited, the build wrote to the OPERATOR'S OWN state root and overwrote the index they
    ## use for ordinary work on that checkout — measured, not hypothesised.
    env = dict(os.environ, CLEW_STATE_HOME=str(state_home))
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=BUILD_TIMEOUT, check=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError(f"index build could not run: {exc}") from exc
    if done.returncode != 0:
        raise ProvisionError(
            f"index build failed (rc={done.returncode}): {done.stderr.strip()[-600:]}"
        )


## @brief Write the MCP config the index arm needs.
## @param db The built index.
## @param repo The target tree.
## @param path Where to write the config.
## @param state_home CLEW_STATE_HOME shared with the build.
## @return None.
## @version 1
def write_mcp_config(db: Path, repo: Path, path: Path, state_home: Path) -> None:
    """WRITTEN LAST, so it cannot exist before the index it points at. A config naming a database
    that was never built sends the index arm to an empty index, which answers — badly — rather
    than refusing.

    @brief Write the index arm's MCP config.
    @return None.
    @version 1
    """
    if not db.is_file():
        raise ProvisionError(
            f"{db}: refusing to write an MCP config for an index that does not exist"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "clew": {
                        ## THE CONSOLE SCRIPT, NOT `python -m`. Measured: with
                        ## `-m clew.mcp_server.server` the server appeared to start, emitted no
                        ## error, and registered NO TOOLS AT ALL — not even the tier-0 ones that
                        ## need no database. An agent given that config answered from source and
                        ## the run reported 4/4 ok. `clew-mcp` is the entry point the package
                        ## declares and the only one observed to work.
                        "command": str(Path(sys.executable).parent / "clew-mcp"),
                        ## ABSOLUTE, AND THIS IS THE SECOND TIME A RELATIVE PATH BROKE THE
                        ## INDEX ARM. The server subprocess inherits the ANSWERING agent's cwd —
                        ## the target checkout — so a relative --repo resolves inside the target,
                        ## finds no database, and registers no query tools.
                        ##
                        ## MEASURED: the server started cleanly, emitted no error, the agent
                        ## raised no denial, and the run reported 4/4 ok. The index arm answered
                        ## WITHOUT ITS INDEX and produced prose indistinguishable from a real
                        ## cell. The only signal was that it made ZERO index calls.
                        "args": ["--repo", str(repo.resolve())],
                        ## THE SAME STATE ROOT THE BUILD USED. The server derives its database
                        ## from --repo under this root, so config and build cannot disagree.
                        "env": {"CLEW_STATE_HOME": str(state_home)},
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


## @brief Refuse unless the written config actually surfaces the index tools.
## @param config Path to the MCP config.
## @param repo The target tree, used as the probe's working directory.
## @return None.
## @version 1
def check_index_tools_reachable(config: Path, repo: Path) -> None:
    """THE ONLY CHECK THAT DISTINGUISHES A WORKING INDEX ARM FROM A SILENT ONE.

    Every earlier signal was absent by construction: the server starts, exits 0, writes nothing
    to stderr, the agent raises no denial, and the run reports every cell ok. Twice a config that
    surfaced NO TOOLS produced four plausible answers, and the only evidence was a tool count
    nobody had a reason to read until the numbers looked odd.

    So this SPENDS ONE CHEAP CALL before any cell is generated. A probe that costs a fraction of
    a cell and refuses is strictly better than a run that costs all of them and cannot be
    interpreted.

    @brief The index arm can actually reach the index.
    @return None.
    @version 1
    """
    argv = [
        "claude",
        "-p",
        "Call the clew search tool with text 'int' and corpus 'symbols'. "
        "Reply with the single word FOUND, or NOTOOL if no such tool exists.",
        "--model",
        "sonnet",
        "--output-format",
        "json",
        "--allowedTools",
        "mcp__clew__dossier,mcp__clew__search,mcp__clew__index",
        "--strict-mcp-config",
        "--mcp-config",
        str(config.resolve()),
    ]
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=300, check=False, cwd=str(repo)
        )
        reply = str(json.loads(done.stdout).get("result") or "")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ProvisionError(f"index-tool probe could not run: {exc}") from exc
    if "NOTOOL" in reply.upper() or "FOUND" not in reply.upper():
        raise ProvisionError(
            f"the index arm cannot reach the index through {config}. The probe replied:\n"
            f"{reply[:400]}\n"
            f"Generating cells now would produce an index arm answering from source with no "
            f"error anywhere — which has happened twice and is invisible in the artifacts."
        )


## @brief Provision one target end to end.
## @param rubric The validated rubric.
## @param root Directory to hold the checkout, index and config.
## @return Provisioned.
## @version 1
def provision(rubric: Rubric, root: Path) -> Provisioned:
    """Every step refuses rather than degrades, and the order is what makes the refusals mean
    something — see the module docstring.

    @brief Provision a target.
    @return Provisioned.
    @version 1
    """
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    repo = root / "repo"
    state_home = root / "state"

    fetch_pinned(rubric, repo)
    try:
        check_revision(rubric, repo)
    except ValueError as exc:
        raise ProvisionError(str(exc)) from exc

    declare_file: Path | None = None
    if rubric.declare:
        import yaml

        declare_file = root / "declaration.yaml"
        declare_file.write_text(yaml.safe_dump(rubric.declare, sort_keys=False), encoding="utf-8")

    build_index(rubric, repo, state_home, declare_file)
    ## FOUND, NOT COMPUTED. The slug is the server's business; globbing the state root it was
    ## just given avoids reimplementing that derivation and drifting from it.
    built = sorted((state_home / "targets").glob("*/clew.db"))
    if len(built) != 1:
        raise ProvisionError(
            f"expected exactly one index under {state_home}/targets, found {len(built)}: "
            f"{[str(b) for b in built]}"
        )
    db = built[0]
    meta = read_build_meta(db)
    try:
        check_declaration_applied(rubric, meta)
    except ValueError as exc:
        raise ProvisionError(str(exc)) from exc

    config = root / "mcp.json"
    write_mcp_config(db, repo, config, state_home)
    check_index_tools_reachable(config, repo)
    return Provisioned(
        repo=repo,
        db=db,
        mcp_config=config,
        build_version=str(meta.get("build_version", "")),
    )


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """@brief Provision a target from its rubric.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(prog="acceptance.provision", description=__doc__)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        rubric = load(args.rubric)
    except RubricError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1
    try:
        out = provision(rubric, args.root)
    except ProvisionError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1
    print(f"{rubric.target} @ {rubric.commit[:10]}")
    print(f"  repo   {out.repo}")
    print(f"  index  {out.db}  (build {out.build_version})")
    print(f"  mcp    {out.mcp_config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
